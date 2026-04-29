"""
QUAL-1 backfill — extract entities for every newspaper_clippings row whose
`entities_extracted` is empty/null. Runs inside rig-backend.

Idempotent: skips rows that already have entities. Safe to re-run.

Usage (from host):
    docker exec rig-backend python -m scripts.backfill_clipping_entities

The script reuses the same `extract_entities()` function the regular NLP
batch task uses for articles/social_posts/youtube_clips, so the JSONB
shape is identical: list of {"name", "type", "label", "confidence",
"prominence"} objects.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import spacy
from sqlalchemy import text

from backend.database import get_db
from backend.nlp.nlp_entities import extract_entities, load_entity_dictionary

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


async def backfill() -> None:
    logger.info("Loading spaCy en_core_web_sm…")
    nlp_model = spacy.load("en_core_web_sm")
    logger.info("spaCy ready.")

    async with get_db() as db:
        # CRITICAL — _ENTITY_DICT is module-level and populated lazily by
        # the worker bootstrap. A standalone backfill script must seed it
        # explicitly or extract_entities() returns [] for every row.
        n_keys = await load_entity_dictionary(db)
        logger.info("Entity dictionary loaded: %d lookup keys", n_keys)

        rows_result = await db.execute(
            text(
                """
                SELECT id, headline, headline_translated,
                       article_text, article_text_translated,
                       newspaper_language
                FROM newspaper_clippings
                WHERE entities_extracted IS NULL
                   OR entities_extracted = '[]'::jsonb
                ORDER BY collected_at DESC
                """
            )
        )
        rows = rows_result.fetchall()
        total = len(rows)
        logger.info("Backfilling entities for %d clippings…", total)

        updated = 0
        skipped = 0
        for idx, row in enumerate(rows, start=1):
            # Prefer translated fields when available so spaCy en_core_web_sm
            # actually catches entities in non-English clippings.
            title = row.headline_translated or row.headline or ""
            body = row.article_text_translated or row.article_text or ""
            if not title and not body:
                skipped += 1
                continue

            try:
                entities: list[dict[str, Any]] = extract_entities(
                    title=title,
                    text=body,
                    nlp_model=nlp_model,
                )
            except Exception as exc:  # noqa: BLE001 - tolerate per-row failures
                logger.warning("entity extraction failed for clipping %s: %s", row.id, exc)
                skipped += 1
                continue

            await db.execute(
                text(
                    """
                    UPDATE newspaper_clippings
                    SET entities_extracted = CAST(:entities AS jsonb)
                    WHERE id = :id
                    """
                ),
                {"entities": json.dumps(entities), "id": row.id},
            )
            updated += 1
            if idx % 50 == 0 or idx == total:
                await db.commit()
                logger.info("  progress %d/%d (updated=%d skipped=%d)", idx, total, updated, skipped)

        await db.commit()
        logger.info("Backfill complete: updated=%d skipped=%d total=%d", updated, skipped, total)


if __name__ == "__main__":
    asyncio.run(backfill())
