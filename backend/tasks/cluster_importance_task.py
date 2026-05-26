"""cluster_importance_task.py — T5: refresh importance_score for event_clusters.

Runs every 30 min. Single SQL UPDATE — no LLM, no per-row Python.

Formula (each component normalised to 0-10, then weighted):
  0.4  * source_count component   — log10(source_count+1) / log10(31) * 10
  0.3  * article_count component  — log10(article_count+1) / log10(101) * 10
  0.2  * novelty component        — (1 - exp(-days_since_first_seen / 3)) * 10
  0.1  * velocity component       — least(articles_in_last_6h /
                                         greatest(prior_18h, 1), 1) * 10

Caps:
  - 31 sources saturates the source component (rare)
  - 101 articles saturates the article-count component
  - Stories older than 7 days drift toward 10 on novelty (then plateau)

All components in [0, 10]. Weighted sum in [0, 10]. Stored in
event_clusters.importance_score, with the refresh timestamp in
event_clusters.importance_updated_at.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from celery import shared_task
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Single UPDATE — computes velocity sub-counts via a CTE, then the score.
SQL = """
WITH velocity AS (
  SELECT ec.id AS cluster_id,
         COUNT(*) FILTER (WHERE a.collected_at >= NOW() - INTERVAL '6 hours') AS n_recent,
         COUNT(*) FILTER (WHERE a.collected_at >= NOW() - INTERVAL '24 hours'
                            AND a.collected_at <  NOW() - INTERVAL '6 hours') AS n_prior
    FROM event_clusters ec
    JOIN article_events ae ON ae.event_cluster_id = ec.id
    JOIN articles a ON a.id = ae.article_id
   WHERE ec.is_active = TRUE
   GROUP BY ec.id
)
UPDATE event_clusters ec
   SET importance_score = LEAST(10.0, GREATEST(0.0,
         0.4 * LEAST(10.0, 10 * LN(ec.source_count + 1) / LN(31))
       + 0.3 * LEAST(10.0, 10 * LN(ec.article_count + 1) / LN(101))
       + 0.2 * (1 - EXP(-GREATEST(0, EXTRACT(EPOCH FROM (NOW() - ec.first_seen_at)) / 86400.0) / 3.0)) * 10
       + 0.1 * LEAST(10.0,
                     10.0 * LEAST(1.0,
                                  COALESCE(v.n_recent, 0)::float
                                  / GREATEST(COALESCE(v.n_prior, 0), 1)::float))
       )),
       importance_updated_at = NOW()
  FROM velocity v
 WHERE v.cluster_id = ec.id
   AND ec.is_active = TRUE
"""

# Catch clusters with no recent articles (velocity CTE empty for them) — set
# velocity component to 0 for those by running a fallback UPDATE without the join.
SQL_FALLBACK = """
UPDATE event_clusters ec
   SET importance_score = LEAST(10.0, GREATEST(0.0,
         0.4 * LEAST(10.0, 10 * LN(ec.source_count + 1) / LN(31))
       + 0.3 * LEAST(10.0, 10 * LN(ec.article_count + 1) / LN(101))
       + 0.2 * (1 - EXP(-GREATEST(0, EXTRACT(EPOCH FROM (NOW() - ec.first_seen_at)) / 86400.0) / 3.0)) * 10
       )),
       importance_updated_at = NOW()
 WHERE is_active = TRUE
   AND (importance_updated_at IS NULL
        OR importance_updated_at < NOW() - INTERVAL '5 minutes')
"""


async def _run() -> dict[str, Any]:
    from backend.database import get_db
    async with get_db() as db:
        # Pass 1: all active clusters (fallback formula — quick, no joins)
        r1 = await db.execute(text(SQL_FALLBACK))
        # Pass 2: clusters with recent articles — refine velocity component
        r2 = await db.execute(text(SQL))
        await db.commit()
    return {"clusters_scored": r1.rowcount or 0,
            "with_velocity_refined": r2.rowcount or 0}


@shared_task(
    name="tasks.quality.cluster_importance",
    bind=True,
    queue="nlp",
    soft_time_limit=60,
    time_limit=120,
)
def cluster_importance_task(self) -> dict[str, Any]:
    try:
        out = asyncio.run(_run())
        logger.info("cluster_importance: %s", out)
        return out
    except Exception as exc:
        logger.exception("cluster_importance failed: %s", exc)
        return {"error": str(exc)[:200]}
