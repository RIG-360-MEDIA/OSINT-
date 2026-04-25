"""
Brief router — generate, retrieve, and list daily intelligence briefs.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from backend.auth.auth_middleware import get_current_user
from backend.database import get_db
from backend.nlp.brief_generator import generate_brief

logger = logging.getLogger(__name__)

brief_router = APIRouter(prefix="/api/brief", tags=["brief"])


# ── Generate today's brief ────────────────────────────────────────────────────

@brief_router.post("/generate")
async def generate_today_brief(
    user: dict = Depends(get_current_user),
) -> dict:
    """
    Generate today's brief on demand. Takes 15-30 seconds.
    Stores result in briefs table (upsert by user+date).
    """
    user_id = user["id"]

    async with get_db() as db:
        # Ghost-row: ensure user exists locally before FK insert
        await db.execute(
            text(
                "INSERT INTO users (id, email) VALUES (:id, :email) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"id": user_id, "email": user["email"]},
        )

        # Fetch user profile + entities in one query
        profile_result = await db.execute(
            text("""
                SELECT
                    up.user_id,
                    up.role_type,
                    up.geo_primary,
                    up.geo_secondary,
                    up.signal_priorities,
                    up.role_context,
                    up.raw_description,
                    up.language_preferences,
                    up.brief_time,
                    up.brief_timezone,
                    up.organisation,
                    up.created_at,
                    up.updated_at,
                    COALESCE(
                        json_agg(
                            json_build_object(
                                'canonical_name', ue.canonical_name,
                                'priority', ue.priority
                            )
                        ) FILTER (WHERE ue.id IS NOT NULL),
                        '[]'::json
                    ) AS entities
                FROM user_profiles up
                LEFT JOIN user_entities ue ON ue.user_id = up.user_id
                WHERE up.user_id = :user_id
                GROUP BY
                    up.user_id, up.role_type, up.geo_primary,
                    up.geo_secondary, up.signal_priorities, up.role_context,
                    up.raw_description, up.language_preferences,
                    up.brief_time, up.brief_timezone, up.organisation,
                    up.created_at, up.updated_at
            """),
            {"user_id": user_id},
        )
        profile_row = profile_result.fetchone()

        if not profile_row:
            raise HTTPException(
                status_code=404,
                detail="User profile not found. Complete onboarding first.",
            )

        profile = dict(profile_row._mapping)

        entities_raw = profile.get("entities", [])
        if isinstance(entities_raw, str):
            entities = json.loads(entities_raw)
        else:
            entities = entities_raw or []

        # Fetch top 30 relevant articles (Tier 1 first, then Tier 2)
        articles_result = await db.execute(
            text("""
                SELECT
                    a.id,
                    a.title,
                    a.lead_text_translated,
                    a.lead_text_original,
                    a.topic_category,
                    a.geo_primary,
                    a.published_at,
                    a.thumbnail_url,
                    a.author_name,
                    s.name AS source_name,
                    s.domain,
                    uar.score_final,
                    uar.relevance_tier,
                    uar.relevance_explanation,
                    uar.matched_entity_names
                FROM user_article_relevance uar
                JOIN articles a ON a.id = uar.article_id
                JOIN sources s ON a.source_id = s.id
                WHERE uar.user_id = :user_id
                  AND uar.relevance_tier IN (1, 2)
                  AND a.nlp_confidence != 'error'
                ORDER BY uar.relevance_tier ASC, uar.score_final DESC
                LIMIT 30
            """),
            {"user_id": user_id},
        )
        articles = [dict(r._mapping) for r in articles_result.fetchall()]

        if not articles:
            raise HTTPException(
                status_code=404,
                detail="No relevant articles found.",
            )

        if len(articles) < 10:
            raise HTTPException(
                status_code=425,
                detail=(
                    f"Only {len(articles)} relevant articles found. "
                    "Your feed is still being prepared — "
                    "check back in a few minutes. "
                    "Currently processing your article backlog."
                ),
            )

        logger.info(
            "Generating brief for user %s with %d articles",
            user_id,
            len(articles),
        )

        result = await generate_brief(
            user_id=user_id,
            user_profile=profile,
            user_entities=entities,
            articles=articles,
        )

        if not result.get("content"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Brief generation failed"),
            )

        # Upsert — regeneration replaces today's brief
        today = date.today()
        await db.execute(
            text("""
                INSERT INTO briefs (
                    user_id, content, brief_date, articles_used, model_used
                ) VALUES (
                    :user_id, :content, :brief_date, :articles_used, :model_used
                )
                ON CONFLICT (user_id, brief_date) DO UPDATE SET
                    content = EXCLUDED.content,
                    articles_used = EXCLUDED.articles_used,
                    generated_at = NOW()
            """),
            {
                "user_id": user_id,
                "content": result["content"],
                "brief_date": today,
                "articles_used": result["articles_used"],
                "model_used": "llama-3.3-70b-versatile",
            },
        )
        await db.commit()

        return {
            "content": result["content"],
            "brief_date": today.isoformat(),
            "articles_used": result["articles_used"],
            "sections": result.get("sections", {}),
        }


# ── Get today's brief ─────────────────────────────────────────────────────────

@brief_router.get("/today")
async def get_today_brief(
    user: dict = Depends(get_current_user),
) -> dict:
    """Get today's brief if it exists. Returns 404 if not yet generated."""
    async with get_db() as db:
        result = await db.execute(
            text("""
                SELECT content, brief_date, articles_used, generated_at, model_used
                FROM briefs
                WHERE user_id = :user_id
                  AND brief_date = CURRENT_DATE
                ORDER BY generated_at DESC
                LIMIT 1
            """),
            {"user_id": user["id"]},
        )
        row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="No brief for today")

    r = row._mapping
    return {
        "content": r["content"],
        "brief_date": r["brief_date"].isoformat(),
        "articles_used": r["articles_used"],
        "generated_at": r["generated_at"].isoformat(),
    }


# ── Get brief by date ─────────────────────────────────────────────────────────

@brief_router.get("/{brief_date}")
async def get_brief_by_date(
    brief_date: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Fetch a specific date's brief by ISO date string (YYYY-MM-DD)."""
    import datetime as _dt
    try:
        parsed_date = _dt.date.fromisoformat(brief_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format — use YYYY-MM-DD")

    async with get_db() as db:
        result = await db.execute(
            text("""
                SELECT content, brief_date, articles_used, generated_at
                FROM briefs
                WHERE user_id = :user_id
                  AND brief_date = :brief_date
                LIMIT 1
            """),
            {"user_id": user["id"], "brief_date": parsed_date},
        )
        row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"No brief for {brief_date}")

    r = row._mapping
    return {
        "content": r["content"],
        "brief_date": r["brief_date"].isoformat(),
        "articles_used": r["articles_used"],
        "generated_at": r["generated_at"].isoformat(),
    }


# ── Brief history ─────────────────────────────────────────────────────────────

@brief_router.get("/history/list")
async def get_brief_history(
    user: dict = Depends(get_current_user),
) -> dict:
    """Return list of past brief dates (no content). Capped at 30 entries."""
    async with get_db() as db:
        result = await db.execute(
            text("""
                SELECT brief_date, articles_used, generated_at
                FROM briefs
                WHERE user_id = :user_id
                ORDER BY brief_date DESC
                LIMIT 30
            """),
            {"user_id": user["id"]},
        )
        rows = result.fetchall()

    return {
        "briefs": [
            {
                "date": r._mapping["brief_date"].isoformat(),
                "articles_used": r._mapping["articles_used"],
                "generated_at": r._mapping["generated_at"].isoformat(),
            }
            for r in rows
        ]
    }
