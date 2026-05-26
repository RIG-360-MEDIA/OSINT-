"""entity_mention_task.py — T6: hourly entity-mention aggregation.

Aggregates the last 24 hours of article_claims.subject_text +
article_quotes.speaker_name + article_stances.actor into
entity_mention_daily, keyed by (LOWER(entity), collected_at::date).

Idempotent via ON CONFLICT — re-running an hour later just refreshes the
counts. Placeholder noise is filtered out at SQL time so we don't pollute
the table while T4 backfill is still in flight.

Schedule: every 60 minutes via Celery beat.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from celery import shared_task
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Filter list — keep in sync with quality_postfix_task.PLACEHOLDERS
PLACEHOLDER_NOUNS = (
    "article", "story", "report", "piece", "news",
    "we", "they", "officials", "the article", "this article",
    "the report", "the story", "the news",
)

# Single UPSERT that unions all three sources, then groups
SQL_AGG = """
WITH mentions AS (
  SELECT LOWER(TRIM(ac.subject_text)) AS entity,
         a.collected_at::date         AS dt,
         a.source_id                  AS source_id,
         'claim'                      AS kind
    FROM article_claims ac
    JOIN articles a ON a.id = ac.article_id
   WHERE a.collected_at >= NOW() - INTERVAL '24 hours'
     AND ac.subject_text IS NOT NULL
     AND LENGTH(TRIM(ac.subject_text)) BETWEEN 3 AND 80
     AND LOWER(TRIM(ac.subject_text)) NOT IN ('article','story','report','piece','news','we','they','officials','the article','this article','the report','the story','the news')
  UNION ALL
  SELECT LOWER(TRIM(aq.speaker_name)),
         a.collected_at::date,
         a.source_id, 'quote'
    FROM article_quotes aq
    JOIN articles a ON a.id = aq.article_id
   WHERE a.collected_at >= NOW() - INTERVAL '24 hours'
     AND aq.speaker_name IS NOT NULL
     AND LENGTH(TRIM(aq.speaker_name)) BETWEEN 3 AND 80
  UNION ALL
  SELECT LOWER(TRIM(asn.actor)),
         a.collected_at::date,
         a.source_id, 'stance'
    FROM article_stances asn
    JOIN articles a ON a.id = asn.article_id
   WHERE a.collected_at >= NOW() - INTERVAL '24 hours'
     AND asn.actor IS NOT NULL
     AND LENGTH(TRIM(asn.actor)) BETWEEN 3 AND 80
     AND LOWER(TRIM(asn.actor)) NOT IN ('article','story','report','piece','news','we','they','officials','the article','this article','the report','the story','the news')
),
agg AS (
  SELECT entity, dt,
         COUNT(*) FILTER (WHERE kind='claim')  AS n_claims,
         COUNT(*) FILTER (WHERE kind='quote')  AS n_quotes,
         COUNT(*) FILTER (WHERE kind='stance') AS n_stances,
         COUNT(DISTINCT source_id)             AS n_sources
    FROM mentions
   GROUP BY entity, dt
  HAVING COUNT(*) >= 2  -- drop one-off mentions to limit table growth
)
INSERT INTO entity_mention_daily
  (entity_text, date, n_claims, n_quotes, n_stances, n_sources, computed_at)
SELECT entity, dt, n_claims, n_quotes, n_stances, n_sources, NOW()
  FROM agg
ON CONFLICT (entity_text, date) DO UPDATE
   SET n_claims  = EXCLUDED.n_claims,
       n_quotes  = EXCLUDED.n_quotes,
       n_stances = EXCLUDED.n_stances,
       n_sources = EXCLUDED.n_sources,
       computed_at = NOW()
"""


async def _run() -> dict[str, Any]:
    from backend.database import get_db
    async with get_db() as db:
        # Use tuple-binding for placeholders
        result = await db.execute(text(SQL_AGG))
        await db.commit()
        # Quick summary
        summary = (await db.execute(text("""
            SELECT COUNT(*) AS rows_today,
                   COALESCE(MAX(n_mentions_total),0) AS max_mentions,
                   COALESCE(SUM(n_mentions_total),0) AS total_mentions
              FROM entity_mention_daily
             WHERE date >= CURRENT_DATE - 1
        """))).fetchone()
    return {
        "upserted": result.rowcount or 0,
        "rows_in_last_2d": int(summary.rows_today or 0),
        "max_mentions_for_one_entity": int(summary.max_mentions or 0),
        "total_mentions_in_window": int(summary.total_mentions or 0),
    }


@shared_task(
    name="tasks.quality.entity_mentions",
    bind=True,
    queue="nlp",
    soft_time_limit=180,
    time_limit=300,
)
def entity_mention_task(self) -> dict[str, Any]:
    try:
        out = asyncio.run(_run())
        logger.info("entity_mentions: %s", out)
        return out
    except Exception as exc:
        logger.exception("entity_mentions failed: %s", exc)
        return {"error": str(exc)[:200]}
