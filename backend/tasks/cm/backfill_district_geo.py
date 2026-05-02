"""
One-shot historical backfill of ``article_districts``.

Iterates articles in batches of ``BATCH_SIZE``, ordered by
``collected_at DESC`` (newest first — same convention as
``nlp_processor`` for demo quality). For each article, runs
``backend.nlp.cm.geo_district.tag_districts`` against its title +
lead text + ``entities_extracted`` and INSERTs one row per matched
district into ``article_districts`` with ``ON CONFLICT DO UPDATE``.

The task is **resumable**: a cursor row in
``district_geo_backfill_cursor`` records the last article_id processed
so a restart picks up where the last batch left off. Set
``surface = 'articles'`` for this task (other surfaces will get their
own variants later).

Routing: ``nlp`` queue (concurrency 4 per ``start.sh``). Same queue as
the existing CM tasks. Idempotent — safe to re-run.

Triggered via:
    celery -A backend.celery_app call tasks.cm.backfill_district_geo
or in code via Beat (not added by default — this is one-shot).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db
from backend.nlp.cm.geo_district import (
    DistrictMatch,
    load_gazetteer,
    tag_districts,
)

logger = logging.getLogger(__name__)


BATCH_SIZE = 500
MAX_BATCHES_PER_RUN = 200          # safety cap — 100k rows per call max
SURFACE = "articles"


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------


async def _read_cursor(db) -> str | None:
    row = (
        await db.execute(
            text(
                "SELECT last_processed FROM district_geo_backfill_cursor "
                "WHERE surface = :s"
            ),
            {"s": SURFACE},
        )
    ).first()
    return str(row.last_processed) if row and row.last_processed else None


async def _write_cursor(db, last_id: str, rows_added: int) -> None:
    await db.execute(
        text(
            """
            INSERT INTO district_geo_backfill_cursor (surface, last_processed, rows_done, updated_at)
            VALUES (:s, CAST(:lid AS uuid), :n, now())
            ON CONFLICT (surface) DO UPDATE SET
              last_processed = EXCLUDED.last_processed,
              rows_done      = district_geo_backfill_cursor.rows_done + EXCLUDED.rows_done,
              updated_at     = now()
            """
        ),
        {"s": SURFACE, "lid": last_id, "n": rows_added},
    )


# ---------------------------------------------------------------------------
# Article batch fetch
# ---------------------------------------------------------------------------


async def _fetch_batch(db, after_id: str | None) -> list[dict[str, Any]]:
    """Return up to BATCH_SIZE articles strictly older than ``after_id``.

    Articles with no NER output are skipped — ``entities_extracted`` is
    a hard requirement for the matcher to work without re-running NER.
    """
    if after_id:
        sql = """
            SELECT a.id, a.title, a.lead_text_translated, a.lead_text_original,
                   a.entities_extracted, a.collected_at
            FROM articles a
            JOIN articles a2 ON a2.id = CAST(:after AS uuid)
            WHERE a.nlp_processed = TRUE
              AND a.collected_at < a2.collected_at
              AND a.entities_extracted IS NOT NULL
            ORDER BY a.collected_at DESC
            LIMIT :n
        """
        params = {"after": after_id, "n": BATCH_SIZE}
    else:
        sql = """
            SELECT a.id, a.title, a.lead_text_translated, a.lead_text_original,
                   a.entities_extracted, a.collected_at
            FROM articles a
            WHERE a.nlp_processed = TRUE
              AND a.entities_extracted IS NOT NULL
            ORDER BY a.collected_at DESC
            LIMIT :n
        """
        params = {"n": BATCH_SIZE}
    rows = (await db.execute(text(sql), params)).all()
    return [
        {
            "id": str(r.id),
            "title": r.title or "",
            "body": r.lead_text_translated or r.lead_text_original or "",
            "entities": _parse_entities(r.entities_extracted),
            "collected_at": r.collected_at,
        }
        for r in rows
    ]


def _parse_entities(raw: Any) -> list[dict]:
    """``entities_extracted`` is JSONB. asyncpg returns it pre-parsed as a
    list/dict; legacy rows may have a string. Be permissive."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [e for e in raw if isinstance(e, dict)]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


# ---------------------------------------------------------------------------
# District writes
# ---------------------------------------------------------------------------


async def _persist_matches(
    db,
    article_id: str,
    matches: list[DistrictMatch],
) -> int:
    """Idempotent INSERT for one article's tag list. Returns rows written."""
    if not matches:
        return 0
    sql = """
        INSERT INTO article_districts
            (article_id, district_id, mention_count, confidence, is_primary)
        VALUES
            (CAST(:aid AS uuid), :did, :n, :c, :p)
        ON CONFLICT (article_id, district_id) DO UPDATE SET
            mention_count = EXCLUDED.mention_count,
            confidence    = EXCLUDED.confidence,
            is_primary    = EXCLUDED.is_primary
    """
    written = 0
    for m in matches:
        await db.execute(
            text(sql),
            {
                "aid": article_id,
                "did": m.district_id,
                "n": m.mention_count,
                "c": m.confidence,
                "p": m.is_primary,
            },
        )
        written += 1
    return written


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


async def _run() -> dict[str, int]:
    total_articles = 0
    total_tag_rows = 0
    total_skipped = 0

    async with get_db() as db:
        gazetteer = await load_gazetteer(db)

    if not gazetteer:
        logger.warning("backfill_district_geo: empty gazetteer — seed districts first")
        return {"articles": 0, "tags": 0, "skipped": 0, "batches": 0}

    batches_done = 0
    while batches_done < MAX_BATCHES_PER_RUN:
        async with get_db() as db:
            cursor = await _read_cursor(db)
            batch = await _fetch_batch(db, cursor)

        if not batch:
            logger.info(
                "backfill_district_geo: no more articles after cursor=%s — done",
                cursor,
            )
            break

        async with get_db() as db:
            batch_tag_rows = 0
            last_id_in_batch = batch[-1]["id"]
            for row in batch:
                matches = tag_districts(
                    title=row["title"],
                    body=row["body"],
                    entities=row["entities"],
                    gazetteer=gazetteer,
                )
                if not matches:
                    total_skipped += 1
                    continue
                batch_tag_rows += await _persist_matches(db, row["id"], matches)
                total_articles += 1
            await _write_cursor(db, last_id_in_batch, batch_tag_rows)
            await db.commit()

        total_tag_rows += batch_tag_rows
        batches_done += 1
        logger.info(
            "backfill_district_geo: batch %d — %d articles tagged, %d new tag rows, last_id=%s",
            batches_done,
            len(batch),
            batch_tag_rows,
            last_id_in_batch,
        )

    return {
        "articles": total_articles,
        "tags": total_tag_rows,
        "skipped": total_skipped,
        "batches": batches_done,
    }


@app.task(name="tasks.cm.backfill_district_geo", bind=True, max_retries=1)
def backfill_district_geo(self) -> dict[str, int]:  # type: ignore[no-untyped-def]
    """One-shot backfill. Idempotent. Run via ``celery call``."""
    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("backfill_district_geo failed")
        raise self.retry(exc=exc, countdown=300)
