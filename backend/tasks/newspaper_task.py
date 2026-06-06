"""
Celery task: daily newspaper clipping collection (P16 Cutting Room).

Scheduled at 07:30 daily on the 'documents' queue.
For each active newspaper source with a careerswave_url:
  1. Scrape CareersWave for today's PDF URL.
  2. Download the PDF.
  3. Extract articles via the newspaper_layout pipeline.
  4. Score relevance against all watched entities + AP/Telangana geo.
  5. Insert relevant articles as clippings rows.

Add to celery_app.py beat_schedule:
    'collect-newspapers-daily': {
        'task': 'tasks.collect_newspapers',
        'schedule': crontab(hour=7, minute=30),
        'options': {'queue': 'documents'},
    },
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from datetime import date

from backend.celery_app import app

logger = logging.getLogger(__name__)


@app.task(name="tasks.collect_newspapers", queue="documents")
def collect_newspapers(paper_ids: list[str] | None = None) -> dict:
    """
    Collect newspaper clippings for all active sources (or a subset).

    paper_ids  Optional list of newspaper_sources.id values to restrict run.
    """
    return asyncio.run(_run(paper_ids=paper_ids))


# ── Async orchestration ───────────────────────────────────────────────────────

async def _run(paper_ids: list[str] | None) -> dict:
    from sqlalchemy import text
    from backend.database import get_db

    async with get_db() as db:
        if paper_ids:
            rows = (
                await db.execute(
                    text(
                        "SELECT id, name, language, careerswave_url "
                        "FROM newspaper_sources "
                        "WHERE is_active=TRUE AND careerswave_url IS NOT NULL "
                        "AND id = ANY(:ids)"
                    ),
                    {"ids": paper_ids},
                )
            ).fetchall()
        else:
            rows = (
                await db.execute(
                    text(
                        "SELECT id, name, language, careerswave_url "
                        "FROM newspaper_sources "
                        "WHERE is_active=TRUE AND careerswave_url IS NOT NULL "
                        "ORDER BY language, name"
                    )
                )
            ).fetchall()

    inserted_total = skipped_total = 0
    for row in rows:
        try:
            ins, skip = await _process_paper(
                paper_id=str(row.id),
                paper_name=row.name,
                language=row.language or "en",
                careerswave_url=row.careerswave_url,
            )
            inserted_total += ins
            skipped_total += skip
        except Exception:
            logger.exception("collect_newspapers: unhandled error for %s", row.name)

    logger.info(
        "collect_newspapers: %d papers, %d inserted, %d skipped",
        len(rows), inserted_total, skipped_total,
    )
    return {"papers": len(rows), "inserted": inserted_total, "skipped": skipped_total}


async def _process_paper(
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
    from backend.collectors.newspaper_layout.pipeline import extract_articles_from_pdf
    from backend.database import get_db
    from sqlalchemy import text

    pdf_url = await get_pdf_url_from_careerswave(careerswave_url)
    if not pdf_url:
        logger.warning("No PDF URL for %s (%s)", paper_name, careerswave_url)
        return 0, 0

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp_path = tmp.name
    tmp.close()
    try:
        ok = await download_pdf_from_url(pdf_url, tmp_path)
        if not ok:
            logger.warning("PDF download failed: %s", paper_name)
            return 0, 0

        articles = await extract_articles_from_pdf(
            tmp_path,
            paper_id=paper_id,
            language=language,
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if not articles:
        return 0, 0

    async with get_db() as db:
        # Load all watched entity names for relevance scoring
        entity_rows = (
            await db.execute(
                text(
                    "SELECT DISTINCT e.name FROM user_watched_entities uwe "
                    "JOIN entity_dictionary e ON e.id = uwe.entity_id LIMIT 300"
                )
            )
        ).fetchall()
        user_entities = [r.name for r in entity_rows]
        user_geos = ["andhra pradesh", "telangana"]

        inserted = skipped = 0
        for art in articles:
            headline = (art.get("headline") or "").strip()
            body = (art.get("text") or "").strip()
            if not headline or len(body) < 60:
                skipped += 1
                continue

            relevant, score, _ = await is_relevant_to_user(
                headline, body, user_entities, user_geos
            )
            if not relevant:
                skipped += 1
                continue

            row = await db.execute(
                text(
                    """
                    INSERT INTO clippings (
                        newspaper_source_id, headline, body_text,
                        section, language, relevance_score,
                        page_number, bbox, edition_date, collected_at
                    ) VALUES (
                        :src_id, :headline, :body,
                        :section, :lang, :score,
                        :page_num, :bbox, :edition_date, NOW()
                    )
                    ON CONFLICT DO NOTHING
                    RETURNING id
                    """
                ),
                {
                    "src_id": paper_id,
                    "headline": headline[:500],
                    "body": body[:8000],
                    "section": art.get("section", ""),
                    "lang": art.get("detected_language") or language,
                    "score": score,
                    "page_num": art.get("page_number", 1),
                    "bbox": str(art.get("bounding_box", [])),
                    "edition_date": date.today().isoformat(),
                },
            )
            if row.fetchone():
                inserted += 1
            else:
                skipped += 1

        await db.commit()

    logger.info("%s: %d inserted, %d skipped", paper_name, inserted, skipped)
    return inserted, skipped
