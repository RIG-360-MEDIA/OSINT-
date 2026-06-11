"""Celery wrappers for the story_clustering pipeline.

Two tasks:
  * tasks.story_cluster_new_articles — every 5 min, picks up articles
    that have a labse_embedding but no thread_id yet (cluster_version 2).
  * tasks.story_cluster_consolidate  — nightly merge + deactivate sweep.

Route: nlp queue (LLM-heavy work).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from celery import shared_task
from sqlalchemy import text

from backend.database import get_db
from backend.nlp.story_clustering import cluster_article, consolidate

logger = logging.getLogger(__name__)

# How many uncluster articles to drain per run. Keep small enough that
# one task instance finishes well under the 5-min Beat interval.
BATCH_LIMIT = 200


@shared_task(name="tasks.story_cluster_new_articles", bind=True, max_retries=3)
def story_cluster_new_articles(self: Any) -> dict[str, int]:
    """Pull up to BATCH_LIMIT articles with no thread_id and cluster them."""
    return asyncio.run(_run_new_articles())


@shared_task(name="tasks.story_cluster_consolidate", bind=True, max_retries=1)
def story_cluster_consolidate(self: Any) -> dict[str, int]:
    """Nightly merge low-confidence neighbours + deactivate stale."""
    return asyncio.run(_run_consolidate())


async def _run_new_articles() -> dict[str, int]:
    counts = {"processed": 0, "assigned": 0, "spawned": 0, "skipped": 0, "errors": 0}
    async with get_db() as db:
        rows = await db.execute(
            text(
                """
                SELECT id::text
                  FROM articles
                 WHERE thread_id        IS NULL
                   AND labse_embedding  IS NOT NULL
                 ORDER BY collected_at DESC
                 LIMIT :n
                """
            ),
            {"n": BATCH_LIMIT},
        )
        article_ids: list[str] = [r.id for r in rows.fetchall()]

        for aid in article_ids:
            try:
                result = await cluster_article(aid, db)
                counts["processed"] += 1
                if result is None:
                    counts["skipped"] += 1
                elif result.spawned_new:
                    counts["spawned"] += 1
                else:
                    counts["assigned"] += 1
                # Commit per article so partial failures don't roll back
                # the whole batch.
                await db.commit()
            except Exception:  # pragma: no cover  (logged + counted)
                logger.exception("clustering article %s failed", aid)
                counts["errors"] += 1
                await db.rollback()

    logger.info("story_cluster_new_articles complete: %s", counts)
    return counts


async def _run_consolidate() -> dict[str, int]:
    async with get_db() as db:
        summary = await consolidate(db)
        await db.commit()
    return summary
