"""
Thread formation Celery tasks.

assign_new_article_threads: runs every 5 minutes, assigns nlp-processed
articles that have embeddings but no thread_id yet.

nightly_thread_recluster: runs at 02:00 UTC, merges near-duplicate threads,
deactivates stale threads, refreshes all momentum scores.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from backend.celery_app import app

logger = logging.getLogger(__name__)


@app.task(
    name="tasks.assign_new_article_threads",
    queue="nlp",
    max_retries=2,
)
def assign_new_article_threads() -> dict:
    """
    Assign recently NLP-processed articles to story threads.

    Processes articles that have:
      - labse_embedding (required)
      - nlp_processed = TRUE
      - thread_id IS NULL (not yet assigned)
    """
    return asyncio.run(_assign_threads())


async def _assign_threads() -> dict:
    from backend.database import get_db
    from backend.nlp.thread_engine import assign_article_to_thread

    async with get_db() as db:
        result = await db.execute(
            text("""
            SELECT id::text as article_id
            FROM articles
            WHERE labse_embedding IS NOT NULL
            AND nlp_processed = TRUE
            AND nlp_confidence != 'error'
            AND thread_id IS NULL
            ORDER BY collected_at DESC
            LIMIT 200
            """)
        )
        unassigned = [r.article_id for r in result.fetchall()]

        if not unassigned:
            logger.debug("Thread assignment: all articles assigned")
            return {"assigned": 0, "skipped": 0}

        logger.info("Thread assignment: processing %d unassigned articles", len(unassigned))

        assigned = 0
        skipped = 0

        for article_id in unassigned:
            try:
                thread_id = await assign_article_to_thread(article_id, db)
                if thread_id:
                    assigned += 1
            except Exception as exc:
                logger.warning("Thread assignment failed for %s: %s", article_id, exc)
                skipped += 1

        await db.commit()
        logger.info("Thread assignment complete: %d assigned, %d skipped", assigned, skipped)
        return {"assigned": assigned, "skipped": skipped}


@app.task(
    name="tasks.nightly_thread_recluster",
    queue="nlp",
)
def nightly_thread_recluster() -> dict:
    """
    Nightly maintenance: merge similar threads, deactivate stale ones,
    refresh all momentum scores. Runs daily at 02:00 UTC.
    """
    return asyncio.run(_nightly_recluster())


async def _nightly_recluster() -> dict:
    from backend.database import get_db
    from backend.nlp.thread_engine import nightly_recluster

    async with get_db() as db:
        summary = await nightly_recluster(db)
        await db.commit()
        logger.info("Nightly recluster: %s", summary)
        return summary
