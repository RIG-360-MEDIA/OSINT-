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
    "summary of the headline. Maximum 60 words. The dashboard belongs "
    "to a specific analyst — when the user-context block is provided, "
    "tie the implication to their tracked interests (entities, geo, "
    "topics) WITHOUT addressing them in second person and WITHOUT "
    "mentioning that you were given context. Just write as if you "
    "knew the analyst's beat."
)


# Maximum users to refresh per task fire. Bounds Groq spend at
# (max users × 5 stories) calls per 6-hour cycle. With 20 users:
# 100 calls/cycle × 4 cycles/day = 400 calls/day on QUALITY_MODEL.
_MAX_USERS_PER_RUN = 30


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


async def _generate_rationale(
    article: dict[str, Any],
    user_context: str | None = None,
) -> str:
    """
    Groq call producing the 'why this matters' line for one story. If
    user_context is provided (a 1-3 line description of the analyst's
    beat — tracked entities, primary geo, topic mix), Groq is told to
    tie the implication to those interests.
    """
    user_prompt_parts = [
        f"Headline: {article['title']}",
        f"Source: {article['source_name']}",
        f"Lead: {article['lead']}",
    ]
    if user_context:
        user_prompt_parts.append("\nAnalyst context (do NOT quote back):")
        user_prompt_parts.append(user_context)
    user_prompt_parts.append("\nWrite the 'why this matters' paragraph.")
    user_prompt = "\n".join(user_prompt_parts)
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


async def _select_user_top_5(user_id: str) -> list[dict[str, Any]]:
    """User's top 5 tier-1/2 articles in last 24h, ordered by score."""
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT a.id::text AS article_id, a.title,
                       COALESCE(a.lead_text_translated, a.lead_text_original) AS lead,
                       a.published_at, a.source_tier, a.thumbnail_url,
                       s.name AS source_name, s.domain AS source_domain
                FROM user_article_relevance uar
                JOIN articles a ON a.id = uar.article_id
                JOIN sources s ON s.id = a.source_id
                WHERE uar.user_id = :uid
                  AND uar.relevance_tier IN (1, 2)
                  AND uar.scored_at > NOW() - interval '24 hours'
                  AND a.is_duplicate IS NOT TRUE
                ORDER BY uar.score_final DESC
                LIMIT 5
                """
            ),
            {"uid": user_id},
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


async def _build_user_context(user_id: str) -> str:
    """
    Compact 2-3 line description of the user's beat for Groq. Pulls
    from user_article_relevance: top tracked entities, primary geo,
    most-engaged topic categories. Cached implicitly because each
    refresh-cycle reuses it across 5 stories.
    """
    async with get_db() as db:
        # Top 6 tracked entities by frequency across tier-1/2 last 14d.
        ent_result = await db.execute(
            text(
                """
                SELECT LOWER(unnest(uar.matched_entity_names)) AS name,
                       COUNT(*) AS n
                FROM user_article_relevance uar
                WHERE uar.user_id = :uid
                  AND uar.relevance_tier IN (1, 2)
                  AND uar.scored_at > NOW() - interval '14 days'
                  AND uar.matched_entity_names IS NOT NULL
                GROUP BY 1
                ORDER BY n DESC
                LIMIT 6
                """
            ),
            {"uid": user_id},
        )
        top_entities = [r.name for r in ent_result.fetchall() if r.name]

        # Most-frequent geo in their strong feed.
        geo_result = await db.execute(
            text(
                """
                SELECT a.geo_primary
                FROM user_article_relevance uar
                JOIN articles a ON a.id = uar.article_id
                WHERE uar.user_id = :uid
                  AND uar.relevance_tier IN (1, 2)
                  AND uar.scored_at > NOW() - interval '14 days'
                  AND a.geo_primary IS NOT NULL
                GROUP BY a.geo_primary
                ORDER BY COUNT(*) DESC
                LIMIT 1
                """
            ),
            {"uid": user_id},
        )
        geo_row = geo_result.fetchone()
        primary_geo = geo_row.geo_primary if geo_row else None

        # Top 3 topic categories by strong-engagement RATE (not raw count).
        topic_result = await db.execute(
            text(
                """
                SELECT a.topic_category AS topic,
                       COUNT(*) FILTER (WHERE uar.relevance_tier IN (1, 2))::float
                         / NULLIF(COUNT(*), 0)::float AS rate
                FROM user_article_relevance uar
                JOIN articles a ON a.id = uar.article_id
                WHERE uar.user_id = :uid
                  AND uar.scored_at > NOW() - interval '14 days'
                  AND a.topic_category IS NOT NULL
                GROUP BY a.topic_category
                HAVING COUNT(*) >= 20
                ORDER BY rate DESC NULLS LAST
                LIMIT 3
                """
            ),
            {"uid": user_id},
        )
        top_topics = [r.topic for r in topic_result.fetchall() if r.topic]

    parts = []
    if primary_geo:
        parts.append(f"Primary geography: {primary_geo}.")
    if top_topics:
        parts.append(
            "Strongest topical interests: " + ", ".join(top_topics) + "."
        )
    if top_entities:
        parts.append(
            "Tracked entities (sample): " + ", ".join(top_entities[:6]) + "."
        )
    return " ".join(parts) if parts else ""


async def _active_user_ids(limit: int) -> list[str]:
    """
    Users with coverage-page access AND a recent strong-relevance feed.
    The feed-presence check skips brand-new users whose profile would
    produce a meaningless rationale.
    """
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT u.id::text AS uid
                FROM users u
                WHERE EXISTS (
                    SELECT 1 FROM user_article_relevance uar
                    WHERE uar.user_id = u.id
                      AND uar.relevance_tier IN (1, 2)
                      AND uar.scored_at > NOW() - interval '14 days'
                  )
                ORDER BY u.last_active_at DESC NULLS LAST
                LIMIT :lim
                """
            ),
            {"lim": limit},
        )
        return [r.uid for r in result.fetchall()]


async def _run_for_user(user_id: str) -> int:
    """
    Build personalised top-5 + rationales for one user. Returns count
    of stories successfully written (0 if user has no top-5).
    """
    stories = await _select_user_top_5(user_id)
    if not stories:
        return 0
    user_ctx = await _build_user_context(user_id)
    enriched: list[dict[str, Any]] = []
    for story in stories:
        rationale = await _generate_rationale(story, user_context=user_ctx)
        enriched.append({**story, "why_matters": rationale})

    async with get_db() as db:
        await db.execute(
            text(
                """
                INSERT INTO top_stories_daily
                  (date, user_id, stories, generated_at, generated_by_model)
                VALUES (CURRENT_DATE, CAST(:uid AS uuid),
                        CAST(:s AS JSONB), NOW(), :m)
                ON CONFLICT (date, user_id) DO UPDATE SET
                  stories = EXCLUDED.stories,
                  generated_at = EXCLUDED.generated_at,
                  generated_by_model = EXCLUDED.generated_by_model
                """
            ),
            {"uid": user_id, "s": json.dumps(enriched), "m": QUALITY_MODEL},
        )
        await db.commit()
    return len(enriched)


async def _run() -> dict[str, Any]:
    """
    Main task entry. Refreshes per-user top-5 for every active user
    (capped at _MAX_USERS_PER_RUN). Also writes a global fallback row
    so brand-new users without a relevance feed still get something
    on first page load.
    """
    user_ids = await _active_user_ids(_MAX_USERS_PER_RUN)
    total_stories = 0
    users_done = 0
    for uid in user_ids:
        try:
            n = await _run_for_user(uid)
            total_stories += n
            if n > 0:
                users_done += 1
        except Exception as exc:  # noqa: BLE001 — never crash the run
            logger.warning("top_stories per-user run failed for %s: %s",
                           uid, exc)

    # Global fallback (user_id NULL) — for users without a relevance
    # feed yet, or as a safety net if their per-user row is missing.
    global_stories = await _select_global_top_5()
    if global_stories:
        enriched_global: list[dict[str, Any]] = []
        for story in global_stories:
            r = await _generate_rationale(story, user_context=None)
            enriched_global.append({**story, "why_matters": r})
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
                {"s": json.dumps(enriched_global), "m": QUALITY_MODEL},
            )
            await db.commit()

    return {
        "users_processed": users_done,
        "total_stories": total_stories,
        "global_fallback_written": bool(global_stories),
    }


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
