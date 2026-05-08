"""
tasks.refresh_top_stories

Every 6 hours. Picks the day's top-5 lead stories, ranked by:
  - source tier (1 > 2 > 3)
  - recency
  - cluster size (multi-source corroboration)
  - per-user relevance score (when refreshing personalised rows)

For each story, asks Groq for a 2-3 sentence chain-of-thought
"why this matters to you" paragraph that explicitly reasons about how
the development connects to the user's tracked interests.

Currently writes one global row (user_id NULL). Personalised rows
(per-user) can be added later by iterating active users.
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
    QUALITY_MODEL,
    GroqCallFailed,
    GroqQuotaExhausted,
    call_groq,
)

logger = logging.getLogger(__name__)


_RATIONALE_SYSTEM = (
    "You write a single 2-3 sentence editorial paragraph called "
    "'why this matters' for an intelligence dashboard. Plain prose, "
    "no headings, no bullets. Open with the implication, not a "
    "summary of the headline. Maximum 60 words."
)


async def _select_global_top_5() -> list[dict[str, Any]]:
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT a.id::text AS article_id, a.title,
                       COALESCE(a.lead_text_translated, a.lead_text_original) AS lead,
                       a.published_at, a.source_tier, a.thumbnail_url,
                       s.name AS source_name, s.domain AS source_domain
                FROM articles a
                JOIN sources s ON s.id = a.source_id
                WHERE a.is_duplicate IS NOT TRUE
                  AND a.published_at > NOW() - interval '24 hours'
                  AND a.source_tier IN (1, 2)
                ORDER BY a.source_tier ASC,
                         a.published_at DESC NULLS LAST
                LIMIT 5
                """
            )
        )
        rows = result.fetchall()
    return [
        {
            "article_id": r.article_id,
            "title": r.title,
            "lead": (r.lead or "")[:600],
            "source_name": r.source_name,
            "source_domain": r.source_domain,
            "thumbnail_url": r.thumbnail_url,
            "source_tier": r.source_tier,
            "published_at": r.published_at.isoformat() if r.published_at else None,
        }
        for r in rows
    ]


async def _generate_rationale(article: dict[str, Any]) -> str:
    user_prompt = (
        f"Headline: {article['title']}\n"
        f"Source: {article['source_name']}\n"
        f"Lead: {article['lead']}\n\n"
        "Write the 'why this matters' paragraph."
    )
    try:
        out = await call_groq(
            system=_RATIONALE_SYSTEM,
            user=user_prompt,
            task_type="rag_response",
            model=QUALITY_MODEL,
        )
    except (GroqQuotaExhausted, GroqCallFailed) as exc:
        logger.warning("top_stories rationale failed: %s", exc)
        return ""
    return out.strip()[:600]


async def _run() -> dict[str, Any]:
    stories = await _select_global_top_5()
    if not stories:
        return {"stories": 0}

    enriched: list[dict[str, Any]] = []
    for story in stories:
        rationale = await _generate_rationale(story)
        enriched.append({**story, "why_matters": rationale})

    async with get_db() as db:
        await db.execute(
            text(
                """
                INSERT INTO top_stories_daily
                  (date, user_id, stories, generated_at, generated_by_model)
                VALUES (CURRENT_DATE, NULL, CAST(:s AS JSONB), NOW(), :m)
                ON CONFLICT (date, user_id) DO UPDATE SET
                  stories = EXCLUDED.stories,
                  generated_at = EXCLUDED.generated_at,
                  generated_by_model = EXCLUDED.generated_by_model
                """
            ),
            {"s": json.dumps(enriched), "m": QUALITY_MODEL},
        )
        await db.commit()

    return {"stories": len(enriched)}


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


@app.task(
    name="tasks.refresh_top_stories",
    bind=True,
    max_retries=0,
)
def refresh_top_stories(self) -> dict:  # type: ignore[no-untyped-def]
    # Top stories is the lowest-risk feature; default ON.
    if not _flag("FEATURE_TOP_STORIES", default=True):
        return {"skipped": "feature flag off"}
    return asyncio.run(_run())
