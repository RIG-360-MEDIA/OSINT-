"""
Structural backfill tasks — safety nets for event-driven pipelines.

score_unscored_articles runs every 30 minutes via Celery beat and does TWO
independent sweeps:

1. Backfill sweep — articles that were NLP-processed before any user existed
   or that missed their `score_relevance_batch` event. Picks up to
   SWEEP_LIMIT articles ordered by `collected_at DESC`.

2. Re-score sweep (C-11) — UAR rows whose `scored_at` is older than
   STALE_AFTER_DAYS for relevance tiers we still surface in the feed
   (tier 1 + 2). This catches the case where the user changes their
   `user_entities` / `geo_*` profile and old scores no longer reflect their
   current interests. Capped at RESCORE_LIMIT to bound Groq cost.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from backend.celery_app import app

logger = logging.getLogger(__name__)

BATCH_SIZE = 100
SWEEP_LIMIT = 500       # backfill cap (unscored articles)
RESCORE_LIMIT = 200     # re-score cap (stale UAR rows) — bounded Groq cost
STALE_AFTER_DAYS = 7    # tier 1+2 rows older than this get re-scored


@app.task(
    name="tasks.score_unscored_articles",
    queue="relevance",
    max_retries=2,
)
def score_unscored_articles() -> None:
    """Run unscored backfill + stale-UAR re-score in one task tick."""
    asyncio.run(_do_backfill())


async def _do_backfill() -> None:
    from backend.database import get_db

    backfill_ids: list[str] = []
    rescore_ids: list[str] = []

    async with get_db() as db:
        # ── Sweep 1: articles never scored for some user ─────────────────
        result = await db.execute(
            text(
                """
                SELECT a.id::text
                FROM articles a
                WHERE a.nlp_processed = TRUE
                  AND a.nlp_confidence <> 'error'
                  AND EXISTS (
                      SELECT 1 FROM user_profiles up
                      WHERE NOT EXISTS (
                          SELECT 1 FROM user_article_relevance uar
                          WHERE uar.article_id = a.id
                            AND uar.user_id = up.user_id
                      )
                  )
                ORDER BY a.collected_at DESC
                LIMIT :lim
                """
            ),
            {"lim": SWEEP_LIMIT},
        )
        backfill_ids = [r[0] for r in result.fetchall()]

        # ── Sweep 2: tier 1+2 UAR rows older than STALE_AFTER_DAYS ───────
        # We rescore the *article*, not a single (user, article) pair —
        # `score_relevance_batch` already iterates all users for each id,
        # so this covers profile drift across the whole tenant.
        rescore_result = await db.execute(
            text(
                """
                SELECT DISTINCT uar.article_id::text
                FROM user_article_relevance uar
                JOIN articles a ON a.id = uar.article_id
                WHERE uar.relevance_tier IN (1, 2)
                  AND uar.scored_at < NOW() - (:stale_days || ' days')::interval
                  AND a.nlp_processed = TRUE
                  AND a.nlp_confidence <> 'error'
                ORDER BY uar.article_id::text
                LIMIT :lim
                """
            ),
            {"stale_days": STALE_AFTER_DAYS, "lim": RESCORE_LIMIT},
        )
        rescore_ids = [r[0] for r in rescore_result.fetchall()]

    # Dedup: an article can be in both lists (extremely rare, but defensive)
    pending = list(dict.fromkeys(backfill_ids + rescore_ids))

    if not pending:
        logger.info("Backfill sweep: nothing to score and no stale rows")
        return

    logger.info(
        "Backfill sweep: %d unscored + %d stale-UAR (>%dd) → %d unique dispatched",
        len(backfill_ids), len(rescore_ids), STALE_AFTER_DAYS, len(pending),
    )

    for i in range(0, len(pending), BATCH_SIZE):
        app.send_task(
            "tasks.score_relevance_batch",
            args=[pending[i : i + BATCH_SIZE]],
            queue="relevance",
        )
