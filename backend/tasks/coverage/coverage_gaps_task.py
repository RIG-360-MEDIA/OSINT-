"""
tasks.refresh_coverage_gaps

Daily at 05:00 UTC. For every entity with social mentions in the last
7 days, computes (social_volume / article_volume). If ratio > 3.0,
flags as 'under-covered': social is talking but mainstream press isn't.

Persists to coverage_gaps_daily with a 1-line Groq summary explaining
what social is saying.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db
from backend.nlp.groq_client import (
    FAST_MODEL,
    GroqCallFailed,
    GroqQuotaExhausted,
    call_groq,
)

logger = logging.getLogger(__name__)


_RATIO_THRESHOLD = 3.0
_MIN_SOCIAL_VOLUME = 5  # avoid noise
_MAX_GAPS = 10


_SUMMARY_SYSTEM = (
    "You write a one-sentence summary (max 25 words) describing what "
    "social media is saying about a subject that mainstream articles "
    "are missing. Plain prose. No quotes. No fluff."
)


async def _candidate_gaps() -> list[dict[str, Any]]:
    """Compute social/article ratio per entity over 7 days."""
    async with get_db() as db:
        # Guard against missing tables: social_posts has 'matched_entities'
        # array column; entity_dictionary has canonical_name.
        result = await db.execute(
            text(
                """
                WITH social AS (
                    SELECT unnest(matched_entities) AS entity_name,
                           COUNT(*) AS volume
                    FROM social_posts
                    WHERE collected_at > NOW() - interval '7 days'
                      AND matched_entities IS NOT NULL
                    GROUP BY 1
                ),
                articles_volume AS (
                    SELECT elt->>'name' AS entity_name,
                           COUNT(DISTINCT a.id) AS volume
                    FROM articles a,
                         jsonb_array_elements(a.entities_extracted) elt
                    WHERE a.collected_at > NOW() - interval '7 days'
                      AND a.is_duplicate IS NOT TRUE
                    GROUP BY 1
                ),
                merged AS (
                    SELECT s.entity_name,
                           s.volume AS social_volume,
                           COALESCE(av.volume, 0) AS article_volume,
                           CASE WHEN COALESCE(av.volume, 0) = 0 THEN s.volume::float
                                ELSE s.volume::float / av.volume
                           END AS ratio
                    FROM social s LEFT JOIN articles_volume av USING (entity_name)
                    WHERE s.volume >= :min_social
                )
                SELECT m.entity_name,
                       m.social_volume::int,
                       m.article_volume::int,
                       m.ratio::real,
                       e.id::text AS entity_id,
                       e.canonical_name
                FROM merged m
                JOIN entity_dictionary e
                  ON LOWER(e.canonical_name) = LOWER(m.entity_name)
                WHERE m.ratio >= :threshold
                ORDER BY m.ratio DESC
                LIMIT :limit
                """
            ),
            {
                "min_social": _MIN_SOCIAL_VOLUME,
                "threshold": _RATIO_THRESHOLD,
                "limit": _MAX_GAPS,
            },
        )
        rows = result.fetchall()
    return [
        {
            "entity_id": r.entity_id,
            "name": r.canonical_name,
            "social_volume": r.social_volume,
            "article_volume": r.article_volume,
            "ratio": r.ratio,
        }
        for r in rows
    ]


async def _sample_social_posts(entity_name: str, limit: int = 8) -> list[str]:
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT post_text_translated, post_text
                FROM social_posts
                WHERE :name = ANY(matched_entities)
                  AND collected_at > NOW() - interval '7 days'
                ORDER BY collected_at DESC
                LIMIT :limit
                """
            ),
            {"name": entity_name, "limit": limit},
        )
        rows = result.fetchall()
    return [
        (r.post_text_translated or r.post_text or "")[:240]
        for r in rows
    ]


async def _generate_summary(name: str, samples: list[str]) -> str:
    if not samples:
        return ""
    block = "\n".join(f"- {s}" for s in samples[:6])
    try:
        out = await call_groq(
            system=_SUMMARY_SYSTEM,
            user=f"Subject: {name}\n\nRecent social posts:\n{block}\n\nSummary:",
            task_type="classification",
            model=FAST_MODEL,
        )
    except (GroqQuotaExhausted, GroqCallFailed):
        return ""
    return out.strip()[:300]


async def _persist_gap(gap: dict[str, Any], summary: str) -> None:
    async with get_db() as db:
        await db.execute(
            text(
                """
                INSERT INTO coverage_gaps_daily
                  (detected_for_date, entity_id, social_volume_7d,
                   article_volume_7d, ratio, summary)
                VALUES (CURRENT_DATE, :eid, :s, :a, :r, :sum)
                ON CONFLICT (detected_for_date, entity_id) DO UPDATE SET
                  social_volume_7d = EXCLUDED.social_volume_7d,
                  article_volume_7d = EXCLUDED.article_volume_7d,
                  ratio = EXCLUDED.ratio,
                  summary = EXCLUDED.summary,
                  detected_at = NOW()
                """
            ),
            {
                "eid": gap["entity_id"],
                "s": gap["social_volume"],
                "a": gap["article_volume"],
                "r": gap["ratio"],
                "sum": summary,
            },
        )
        await db.commit()


async def _run() -> dict[str, Any]:
    gaps = await _candidate_gaps()
    if not gaps:
        return {"flagged": 0}

    flagged = 0
    for gap in gaps:
        try:
            samples = await _sample_social_posts(gap["name"])
            summary = await _generate_summary(gap["name"], samples)
            await _persist_gap(gap, summary)
            flagged += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("coverage_gap persist failed for %s: %s",
                             gap["name"], exc)

    return {"flagged": flagged, "scanned": len(gaps)}


def _flag(name: str) -> bool:
    raw = os.getenv(name, "").strip().lower()
    return raw in ("1", "true", "yes", "on")


@app.task(
    name="tasks.refresh_coverage_gaps",
    bind=True,
    max_retries=0,
)
def refresh_coverage_gaps(self) -> dict:  # type: ignore[no-untyped-def]
    if not _flag("FEATURE_COVERAGE_GAPS"):
        return {"skipped": "feature flag off"}
    return asyncio.run(_run())
