"""
Structural backfill tasks — safety nets for event-driven pipelines.

score_unscored_articles: scores articles that were NLP-processed before any
user existed (or when score_relevance_batch events were missed). Runs every
30 minutes via Celery beat.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from backend.celery_app import app

logger = logging.getLogger(__name__)

BATCH_SIZE = 100
SWEEP_LIMIT = 500  # raised: 200 was too small for multi-user gaps


@app.task(
    name="tasks.score_unscored_articles",
    queue="relevance",
    max_retries=2,
)
def score_unscored_articles() -> None:
    """Dispatch up to SWEEP_LIMIT unscored NLP-processed articles for scoring."""
    asyncio.run(_do_backfill())


async def _do_backfill() -> None:
    from backend.database import get_db

    async with get_db() as db:
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
        ids = [r[0] for r in result.fetchall()]

    if not ids:
        logger.info("Backfill sweep: all articles scored — nothing to do")
        return

    logger.info("Backfill sweep: dispatching %d unscored articles", len(ids))

    for i in range(0, len(ids), BATCH_SIZE):
        app.send_task(
            "tasks.score_relevance_batch",
            args=[ids[i : i + BATCH_SIZE]],
            queue="relevance",
        )
