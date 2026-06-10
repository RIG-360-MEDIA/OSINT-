"""
Celery task: daily newspaper clipping collection (P16 Cutting Room).

Per-paper fan-out on the 'documents' queue. Two beat entries (design §3):
  collect-newspapers-primary   02:00 UTC (07:30 IST)  — fires every active paper
  collect-newspapers-fallback  03:00 UTC (08:30 IST)  — only papers with NO
                                                          clipping row for today
Both dispatch collect_one_newspaper.delay(paper_id) per source, so one dead
Drive link can't sink the batch and each paper gets independent retry/timeout.

Per paper:
  1. Resolve today's PDF URL from CareersWave.
  2. Download (retain at /data/newspapers/<paper>/<date>.pdf, 14-day purge).
  3. extract_articles_hybrid  — Vision segment + OCR-grounded body + snapshot.
  4. Postprocess filter: drop is_notice + is_duplicate.
  5. Relevance gate against watched entities + geo (grounded body).
  6. INSERT clippings (extraction + provenance fields), substrate_status=pending.
  7. enqueue enrich_clipping.delay(id) per new row  → substrate enrichment.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date

from backend.celery_app import app

logger = logging.getLogger(__name__)

# Host volume for short-retention PDF storage (design §4.1). 14-day purge runs
# via the daily cron; the per-article snapshots already live in the DB.
_PDF_STORE_ROOT = os.environ.get("NEWSPAPER_PDF_STORE", "/data/newspapers")


# ── Celery entry points ───────────────────────────────────────────────────────

@app.task(name="tasks.collect_newspapers", queue="documents")
def collect_newspapers(paper_ids: list[str] | None = None) -> dict:
    """PRIMARY pass: fan out collect_one_newspaper per active source."""
    return asyncio.run(_dispatch(paper_ids=paper_ids, only_missing=False))


@app.task(name="tasks.collect_newspapers_fallback", queue="documents")
def collect_newspapers_fallback() -> dict:
    """FALLBACK pass: fan out only for papers with NO clipping row today."""
    return asyncio.run(_dispatch(paper_ids=None, only_missing=True))


@app.task(name="tasks.collect_one_newspaper", queue="documents")
def collect_one_newspaper(paper_id: str) -> dict:
    """Collect + extract a single newspaper edition (one fan-out unit)."""
    return asyncio.run(_process_one_paper(paper_id))


# ── Dispatch (fan-out) ────────────────────────────────────────────────────────

async def _dispatch(paper_ids: list[str] | None, only_missing: bool) -> dict:
    from sqlalchemy import text
    from backend.database import get_db

    async with get_db() as db:
        if paper_ids:
            rows = (
                await db.execute(
                    text(
                        "SELECT id FROM newspaper_sources "
                        "WHERE is_active=TRUE AND careerswave_url IS NOT NULL "
                        "AND id = ANY(:ids)"
                    ),
                    {"ids": paper_ids},
                )
            ).fetchall()
        elif only_missing:
            rows = (
                await db.execute(
                    text(
                        "SELECT id FROM newspaper_sources s "
                        "WHERE s.is_active=TRUE AND s.careerswave_url IS NOT NULL "
                        "AND s.id NOT IN ("
                        "  SELECT DISTINCT newspaper_source_id FROM clippings "
                        "  WHERE edition_date = CURRENT_DATE"
                        ")"
                    )
                )
            ).fetchall()
        else:
            rows = (
                await db.execute(
                    text(
                        "SELECT id FROM newspaper_sources "
                        "WHERE is_active=TRUE AND careerswave_url IS NOT NULL "
                        "ORDER BY language, name"
                    )
                )
            ).fetchall()

    dispatched = 0
    for row in rows:
        collect_one_newspaper.delay(str(row.id))
        dispatched += 1

    logger.info(
        "collect_newspapers dispatch: %d papers (only_missing=%s)",
        dispatched, only_missing,
    )
    return {"dispatched": dispatched, "only_missing": only_missing}


# ── Single-paper processing ───────────────────────────────────────────────────

async def _process_one_paper(paper_id: str) -> dict:
    from sqlalchemy import text
    from backend.database import get_db

    async with get_db() as db:
        row = (
            await db.execute(
                text(
                    "SELECT id, name, language, careerswave_url "
                    "FROM newspaper_sources WHERE id = :id"
                ),
                {"id": paper_id},
            )
        ).fetchone()

    if not row:
        logger.warning("collect_one_newspaper: unknown paper %s", paper_id)
        return {"paper_id": paper_id, "error": "unknown_paper"}

    try:
        ins, skip = await _collect_and_extract(
            paper_id=str(row.id),
            paper_name=row.name,
            language=row.language or "en",
            careerswave_url=row.careerswave_url,
        )
    except Exception:
        logger.exception("collect_one_newspaper failed for %s", row.name)
        return {"paper_id": paper_id, "error": "exception"}

    return {"paper_id": paper_id, "paper": row.name, "inserted": ins, "skipped": skip}


async def _collect_and_extract(
    paper_id: str,
    paper_name: str,
    language: str,
    careerswave_url: str,
) -> tuple[int, int]:
    from backend.collectors.newspaper_collector import (
        get_pdf_url_from_careerswave,
        download_pdf_from_url,
        is_relevant_to_user,
    )
    from backend.collectors.newspaper_layout.hybrid_pipeline import extract_articles_hybrid
    from backend.database import get_db
    from backend.tasks.clipping_enrich import enrich_clipping
    from sqlalchemy import text

    pdf_url = await get_pdf_url_from_careerswave(careerswave_url)
    if not pdf_url:
        logger.warning("No PDF URL for %s (%s)", paper_name, careerswave_url)
        return 0, 0

    pdf_path = _pdf_store_path(paper_name)
    ok = await download_pdf_from_url(pdf_url, pdf_path)
    if not ok:
        logger.warning("PDF download failed: %s", paper_name)
        return 0, 0

    # Grounded hybrid extraction with per-article snapshots.
    articles = await extract_articles_hybrid(
        pdf_path, language=language, with_clip_images=True,
    )
    if not articles:
        return 0, 0

    async with get_db() as db:
        user_entities, user_geos = await _load_relevance_scope(db)

        inserted = skipped = 0
        new_ids: list[str] = []
        for art in articles:
            # Filter statutory notices and front-page teasers (design §4 step 5).
            if art.get("is_notice") or art.get("is_duplicate"):
                skipped += 1
                continue

            headline = (art.get("headline") or "").strip()
            body = (art.get("text") or "").strip()  # grounded OCR body
            if not headline or len(body) < 60:
                skipped += 1
                continue

            relevant, score, _ = await is_relevant_to_user(
                headline, body, user_entities, user_geos
            )
            if not relevant:
                skipped += 1
                continue

            new_id = await _insert_clipping(
                db, paper_id, language, pdf_path, art, headline, body, score
            )
            if new_id:
                inserted += 1
                new_ids.append(new_id)
            else:
                skipped += 1

        await db.commit()

    # Enqueue substrate enrichment per new row (decoupled from ingest).
    for cid in new_ids:
        enrich_clipping.delay(cid)

    logger.info(
        "%s: %d inserted, %d skipped, %d enrich enqueued",
        paper_name, inserted, skipped, len(new_ids),
    )
    return inserted, skipped


async def _load_relevance_scope(db) -> tuple[list[str], list[str]]:
    """Watched entity names + geo states (union across users) for scoring."""
    from sqlalchemy import text

    entity_rows = (
        await db.execute(
            text(
                "SELECT DISTINCT e.canonical_name FROM user_watched_entities uwe "
                "JOIN entity_dictionary e ON e.id = uwe.entity_id LIMIT 300"
            )
        )
    ).fetchall()
    user_entities = [r.canonical_name for r in entity_rows]

    geo_rows = (
        await db.execute(
            text(
                "SELECT DISTINCT lower(e.state) AS state "
                "FROM user_watched_entities uwe "
                "JOIN entity_dictionary e ON e.id = uwe.entity_id "
                "WHERE e.state IS NOT NULL AND e.state <> ''"
            )
        )
    ).fetchall()
    user_geos = [r.state for r in geo_rows if r.state]
    for baseline in ("andhra pradesh", "telangana"):
        if baseline not in user_geos:
            user_geos.append(baseline)
    return user_entities, user_geos


async def _insert_clipping(
    db, paper_id: str, language: str, pdf_path: str,
    art: dict, headline: str, body: str, score: float,
) -> str | None:
    """INSERT one clipping with extraction + provenance fields. Returns id or None."""
    from sqlalchemy import text

    row = await db.execute(
        text(
            """
            INSERT INTO clippings (
                newspaper_source_id, headline, subheadline, byline,
                body_text, vision_text, text_source, section,
                language, detected_language, relevance_score,
                page_number, bbox, clip_source, clipping_image_b64,
                extraction_confidence, needs_review,
                is_notice, is_duplicate, duplicate_of,
                source_pdf_path, substrate_status,
                edition_date, collected_at
            ) VALUES (
                :src_id, :headline, :subheadline, :byline,
                :body, :vision_text, :text_source, :section,
                :lang, :detected_lang, :score,
                :page_num, :bbox, :clip_source, :clip_img,
                :conf, :needs_review,
                :is_notice, :is_duplicate, :duplicate_of,
                :pdf_path, 'pending',
                :edition_date, NOW()
            )
            ON CONFLICT DO NOTHING
            RETURNING id
            """
        ),
        {
            "src_id": paper_id,
            "headline": headline[:500],
            "subheadline": (art.get("subheadline") or "")[:500] or None,
            "byline": (art.get("byline") or "")[:300] or None,
            "body": body[:8000],
            "vision_text": (art.get("vision_text") or "")[:8000] or None,
            "text_source": (art.get("text_source") or "none")[:8],
            "section": (art.get("section") or "")[:100],
            "lang": language[:10],
            "detected_lang": (art.get("detected_language") or language)[:8],
            "score": score,
            "page_num": art.get("page_number", 1),
            "bbox": str(art.get("bounding_box", [])),
            "clip_source": (art.get("clip_source") or "none")[:8],
            "clip_img": art.get("clipping_image_b64"),
            "conf": art.get("extraction_confidence"),
            "needs_review": bool(art.get("needs_review", False)),
            "is_notice": bool(art.get("is_notice", False)),
            "is_duplicate": bool(art.get("is_duplicate", False)),
            "duplicate_of": art.get("duplicate_of"),
            "pdf_path": pdf_path,
            "edition_date": date.today().isoformat(),
        },
    )
    fetched = row.fetchone()
    return str(fetched.id) if fetched else None


def _pdf_store_path(paper_name: str) -> str:
    """Retained PDF path: /data/newspapers/<paper>/<edition_date>.pdf.

    Falls back to a tempfile if the store root is not writable (dev / CI).
    """
    safe = paper_name.replace(os.sep, "_").replace(" ", "_")
    edition = date.today().isoformat()
    paper_dir = os.path.join(_PDF_STORE_ROOT, safe)
    try:
        os.makedirs(paper_dir, exist_ok=True)
        return os.path.join(paper_dir, f"{edition}.pdf")
    except OSError:
        import tempfile
        fd, tmp = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        return tmp
