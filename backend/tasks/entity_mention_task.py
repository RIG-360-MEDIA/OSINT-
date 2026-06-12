"""entity_mention_task.py — T6: hourly CROSS-PILLAR entity-mention aggregation.

Aggregates, per (LOWER(entity), date), the mention signals from ALL THREE pillars
into entity_mention_daily:
  - claims  : *_claims.subject_text
  - quotes  : *_quotes.speaker_name
  - stances : *_stances.actor
  - entities: entities_extracted[].name   (the multi-entity list per item)
for articles + clippings (newspapers) + youtube_clips_v2 (clips).

Until migration 113 this was articles-only, so the Mission Control Entity page
showed no newspaper/clip entities. n_entities is a separate column; consumers rank
by n_mentions_total + n_entities.

Idempotent via ON CONFLICT. Schedule: every 60 min via Celery beat (24h window).
Backfill: call _run(window="3650 days") to rebuild history once.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from celery import shared_task
from sqlalchemy import text

logger = logging.getLogger(__name__)

# entity surface forms that are noise, not entities
_PLACEHOLDERS = (
    "article", "story", "report", "piece", "news", "we", "they", "officials",
    "the article", "this article", "the report", "the story", "the news",
    "speaker", "anchor", "host", "unknown", "presenter", "reporter",
)
_PLACEHOLDER_SQL = ",".join(f"'{p}'" for p in _PLACEHOLDERS)

# {window} is an interval literal e.g. "24 hours" / "3650 days" (internal, not user input)
SQL_AGG = """
WITH mentions AS (
  -- ARTICLES
  SELECT LOWER(TRIM(ac.subject_text)) AS entity, a.collected_at::date AS dt, a.source_id::text AS src, 'claim' AS kind
    FROM article_claims ac JOIN articles a ON a.id = ac.article_id
   WHERE a.collected_at >= NOW() - INTERVAL '{window}' AND LENGTH(TRIM(COALESCE(ac.subject_text,''))) BETWEEN 3 AND 80
  UNION ALL
  SELECT LOWER(TRIM(aq.speaker_name)), a.collected_at::date, a.source_id::text, 'quote'
    FROM article_quotes aq JOIN articles a ON a.id = aq.article_id
   WHERE a.collected_at >= NOW() - INTERVAL '{window}' AND LENGTH(TRIM(COALESCE(aq.speaker_name,''))) BETWEEN 3 AND 80
  UNION ALL
  SELECT LOWER(TRIM(asn.actor)), a.collected_at::date, a.source_id::text, 'stance'
    FROM article_stances asn JOIN articles a ON a.id = asn.article_id
   WHERE a.collected_at >= NOW() - INTERVAL '{window}' AND LENGTH(TRIM(COALESCE(asn.actor,''))) BETWEEN 3 AND 80
  UNION ALL
  SELECT LOWER(TRIM(ae->>'name')), a.collected_at::date, a.source_id::text, 'entity'
    FROM articles a, jsonb_array_elements(CASE WHEN jsonb_typeof(a.entities_extracted)='array' THEN a.entities_extracted ELSE '[]'::jsonb END) ae
   WHERE a.collected_at >= NOW() - INTERVAL '{window}' AND jsonb_typeof(a.entities_extracted)='array'
     AND LENGTH(TRIM(COALESCE(ae->>'name',''))) BETWEEN 2 AND 80
  -- CLIPPINGS (newspapers)
  UNION ALL
  SELECT LOWER(TRIM(cc.subject_text)), c.collected_at::date, c.newspaper_source_id::text, 'claim'
    FROM clipping_claims cc JOIN clippings c ON c.id = cc.clipping_id
   WHERE c.collected_at >= NOW() - INTERVAL '{window}' AND LENGTH(TRIM(COALESCE(cc.subject_text,''))) BETWEEN 3 AND 80
  UNION ALL
  SELECT LOWER(TRIM(cq.speaker_name)), c.collected_at::date, c.newspaper_source_id::text, 'quote'
    FROM clipping_quotes cq JOIN clippings c ON c.id = cq.clipping_id
   WHERE c.collected_at >= NOW() - INTERVAL '{window}' AND LENGTH(TRIM(COALESCE(cq.speaker_name,''))) BETWEEN 3 AND 80
  UNION ALL
  SELECT LOWER(TRIM(cs.actor)), c.collected_at::date, c.newspaper_source_id::text, 'stance'
    FROM clipping_stances cs JOIN clippings c ON c.id = cs.clipping_id
   WHERE c.collected_at >= NOW() - INTERVAL '{window}' AND LENGTH(TRIM(COALESCE(cs.actor,''))) BETWEEN 3 AND 80
  UNION ALL
  SELECT LOWER(TRIM(ce->>'name')), c.collected_at::date, c.newspaper_source_id::text, 'entity'
    FROM clippings c, jsonb_array_elements(CASE WHEN jsonb_typeof(c.entities_extracted)='array' THEN c.entities_extracted ELSE '[]'::jsonb END) ce
   WHERE c.collected_at >= NOW() - INTERVAL '{window}' AND jsonb_typeof(c.entities_extracted)='array'
     AND LENGTH(TRIM(COALESCE(ce->>'name',''))) BETWEEN 2 AND 80
  -- YOUTUBE CLIPS
  UNION ALL
  SELECT LOWER(TRIM(yc2.subject_text)), yc.created_at::date, yc.channel_id::text, 'claim'
    FROM youtube_clip_claims yc2 JOIN youtube_clips_v2 yc ON yc.id = yc2.clip_id
   WHERE yc.created_at >= NOW() - INTERVAL '{window}' AND LENGTH(TRIM(COALESCE(yc2.subject_text,''))) BETWEEN 3 AND 80
  UNION ALL
  SELECT LOWER(TRIM(yq.speaker_name)), yc.created_at::date, yc.channel_id::text, 'quote'
    FROM youtube_clip_quotes yq JOIN youtube_clips_v2 yc ON yc.id = yq.clip_id
   WHERE yc.created_at >= NOW() - INTERVAL '{window}' AND LENGTH(TRIM(COALESCE(yq.speaker_name,''))) BETWEEN 3 AND 80
  UNION ALL
  SELECT LOWER(TRIM(ys.actor)), yc.created_at::date, yc.channel_id::text, 'stance'
    FROM youtube_clip_stances ys JOIN youtube_clips_v2 yc ON yc.id = ys.clip_id
   WHERE yc.created_at >= NOW() - INTERVAL '{window}' AND LENGTH(TRIM(COALESCE(ys.actor,''))) BETWEEN 3 AND 80
  UNION ALL
  SELECT LOWER(TRIM(ye->>'name')), yc.created_at::date, yc.channel_id::text, 'entity'
    FROM youtube_clips_v2 yc, jsonb_array_elements(CASE WHEN jsonb_typeof(yc.entities_extracted)='array' THEN yc.entities_extracted ELSE '[]'::jsonb END) ye
   WHERE yc.created_at >= NOW() - INTERVAL '{window}' AND jsonb_typeof(yc.entities_extracted)='array'
     AND LENGTH(TRIM(COALESCE(ye->>'name',''))) BETWEEN 2 AND 80
),
filt AS (
  SELECT * FROM mentions
   WHERE entity IS NOT NULL AND entity <> '' AND entity NOT IN (%PLACEHOLDERS%)
),
agg AS (
  SELECT entity, dt,
         COUNT(*) FILTER (WHERE kind='claim')  AS n_claims,
         COUNT(*) FILTER (WHERE kind='quote')  AS n_quotes,
         COUNT(*) FILTER (WHERE kind='stance') AS n_stances,
         COUNT(*) FILTER (WHERE kind='entity') AS n_entities,
         COUNT(DISTINCT src)                   AS n_sources
    FROM filt GROUP BY entity, dt
  HAVING COUNT(*) >= 2
)
INSERT INTO entity_mention_daily
  (entity_text, date, n_claims, n_quotes, n_stances, n_entities, n_sources, computed_at)
SELECT entity, dt, n_claims, n_quotes, n_stances, n_entities, n_sources, NOW()
  FROM agg
ON CONFLICT (entity_text, date) DO UPDATE
   SET n_claims=EXCLUDED.n_claims, n_quotes=EXCLUDED.n_quotes, n_stances=EXCLUDED.n_stances,
       n_entities=EXCLUDED.n_entities, n_sources=EXCLUDED.n_sources, computed_at=NOW()
""".replace("%PLACEHOLDERS%", _PLACEHOLDER_SQL)


async def _run(window: str = "24 hours") -> dict[str, Any]:
    from backend.database import get_db
    async with get_db() as db:
        result = await db.execute(text(SQL_AGG.format(window=window)))
        await db.commit()
        summary = (await db.execute(text("""
            SELECT COUNT(*) AS rows_today,
                   COALESCE(MAX(n_mentions_total + n_entities), 0) AS max_mentions,
                   COALESCE(SUM(n_entities), 0) AS total_entity_mentions
              FROM entity_mention_daily WHERE date >= CURRENT_DATE - 1
        """))).fetchone()
    return {
        "window": window,
        "upserted": result.rowcount or 0,
        "rows_in_last_2d": int(summary.rows_today or 0),
        "max_mentions_for_one_entity": int(summary.max_mentions or 0),
        "entity_signal_in_window": int(summary.total_entity_mentions or 0),
    }


@shared_task(
    name="tasks.quality.entity_mentions",
    bind=True,
    queue="nlp",
    soft_time_limit=240,
    time_limit=420,
)
def entity_mention_task(self) -> dict[str, Any]:
    try:
        out = asyncio.run(_run())
        logger.info("entity_mentions: %s", out)
        return out
    except Exception as exc:  # noqa: BLE001
        logger.exception("entity_mentions failed: %s", exc)
        return {"error": str(exc)[:200]}
