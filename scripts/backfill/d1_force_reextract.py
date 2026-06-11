"""d1_force_reextract.py — re-run substrate v3 on articles whose claims lack SPO.

After the D1 prompt patch deploys, existing substrate-ok articles still
have claims with NULL predicate / object_text from the pre-patch prompt.
This script:

  1. Finds articles where substrate_status='ok' AND extraction_version=3 AND
     EVERY claim has NULL predicate (meaning: extracted before D1).
  2. Resets their extraction_version to 0 so the existing semantic_repass /
     run_corpus_pass picks them back up.
  3. Run the repass task batch by batch — concurrency=4, batch=200.

Runs only when LLM_QUOTAS_RESET (00:05 UTC) — gated by env LLM_OK=1.
Idempotent — articles whose claims already have SPO are skipped.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

sys.path.insert(0, "/app")
from sqlalchemy import text
from backend.database import get_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("d1_reextract")

BATCH = 200
TARGET_TOTAL = int(os.environ.get("D1_TARGET_TOTAL", "80000"))


async def find_articles_missing_spo(limit: int) -> list[str]:
    """Articles whose ALL claims have NULL predicate (= pre-D1 extraction)."""
    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT a.id::text AS aid
              FROM articles a
             WHERE a.substrate_status = 'ok'
               AND a.extraction_version = 3
               AND EXISTS (SELECT 1 FROM article_claims c WHERE c.article_id = a.id)
               AND NOT EXISTS (
                   SELECT 1 FROM article_claims c
                    WHERE c.article_id = a.id
                      AND c.predicate IS NOT NULL
                      AND c.object_text IS NOT NULL
               )
             ORDER BY a.collected_at DESC
             LIMIT :lim
        """), {"lim": limit})).mappings().all()
    return [r["aid"] for r in rows]


async def reset_for_repass(article_ids: list[str]) -> int:
    if not article_ids:
        return 0
    async with get_db() as db:
        result = await db.execute(text("""
            UPDATE articles
               SET extraction_version = 0,
                   substrate_status = 'pending',
                   substrate_processed_at = NULL
             WHERE id::text = ANY(:ids)
        """), {"ids": article_ids})
        await db.commit()
        return result.rowcount or 0


async def main() -> int:
    if os.environ.get("LLM_OK") != "1":
        log.error("LLM_OK=1 not set. Run only after 00:05 UTC quota reset.")
        return 1
    log.info("D1 force re-extract — finding pre-D1 articles (max %d)...", TARGET_TOTAL)
    total_reset = 0
    while total_reset < TARGET_TOTAL:
        ids = await find_articles_missing_spo(BATCH)
        if not ids:
            break
        n = await reset_for_repass(ids)
        total_reset += n
        log.info("reset batch: %d (cumulative %d / target %d)", n, total_reset, TARGET_TOTAL)
        if n < BATCH:
            break
    log.info("D1 reset COMPLETE: %d articles queued for substrate re-extract", total_reset)
    log.info("Now run: docker exec rig-backend python -m backend.tasks.substrate.run_corpus_pass --limit %d", total_reset)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
