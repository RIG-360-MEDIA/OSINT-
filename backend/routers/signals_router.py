"""
Signal Room API — unified feed across Reddit / Twitter / Telegram plus
sentiment aggregation and monitor listing.

All endpoints require a valid Supabase session (Bearer token).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from backend.auth.auth_middleware import get_current_user
from backend.database import get_db

logger = logging.getLogger(__name__)

signals_router = APIRouter(prefix="/api/signals", tags=["signals"])


@signals_router.get("/feed")
async def get_signals_feed(
    platform: str = Query(default="all"),
    days: int = Query(default=3, ge=1, le=30),
    limit: int = Query(default=30, ge=1, le=100),
    cursor: str = Query(default=""),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Unified social signal feed.

    Shows posts that either (a) mention a user-tracked entity, or
    (b) have high engagement (upvotes > 100). Ordered by collection time,
    paginated via an ISO-timestamp cursor on `collected_at`.
    """
    async with get_db() as db:
        ent_rows = (
            await db.execute(
                text(
                    "SELECT canonical_name FROM user_entities "
                    "WHERE user_id = :uid"
                ),
                {"uid": user["id"]},
            )
        ).fetchall()
        user_entities = [r.canonical_name for r in ent_rows if r.canonical_name]

        conditions = [
            "sp.collected_at > NOW() - (:days * INTERVAL '1 day')",
        ]
        params: dict[str, Any] = {"days": days, "limit": limit + 1}

        if user_entities:
            conditions.append(
                "(sp.matched_entities && CAST(:entities AS text[]) "
                "OR sp.upvotes > 100)"
            )
            params["entities"] = user_entities

        if platform != "all":
            conditions.append("sp.platform = :platform")
            params["platform"] = platform

        if cursor:
            conditions.append(
                "sp.collected_at < CAST(:cursor AS timestamptz)"
            )
            params["cursor"] = cursor

        where_clause = " AND ".join(conditions)

        result = await db.execute(
            text(
                f"""
                SELECT
                    sp.id::text AS post_id,
                    sp.platform,
                    sp.author_username,
                    sp.post_text,
                    sp.post_text_translated,
                    sp.post_url,
                    sp.upvotes,
                    sp.comment_count,
                    sp.share_count,
                    sp.forward_count,
                    sp.forwarded_from,
                    sp.has_document,
                    sp.sentiment_score,
                    sp.matched_entities,
                    sp.posted_at,
                    sp.collected_at,
                    sm.display_name AS monitor_name
                FROM social_posts sp
                LEFT JOIN social_monitors sm ON sm.id = sp.monitor_id
                WHERE {where_clause}
                ORDER BY sp.collected_at DESC
                LIMIT :limit
                """
            ),
            params,
        )
        rows = result.fetchall()

        has_more = len(rows) > limit
        page = rows[:limit]

        next_cursor: str | None = None
        if has_more and page:
            next_cursor = page[-1].collected_at.isoformat()

        return {
            "posts": [
                {
                    "post_id": p.post_id,
                    "platform": p.platform,
                    "author_username": p.author_username,
                    "post_text": p.post_text,
                    "post_text_translated": p.post_text_translated,
                    "post_url": p.post_url,
                    "upvotes": p.upvotes,
                    "comment_count": p.comment_count,
                    "share_count": p.share_count,
                    "forward_count": p.forward_count,
                    "forwarded_from": p.forwarded_from,
                    "has_document": p.has_document,
                    "sentiment_score": (
                        float(p.sentiment_score)
                        if p.sentiment_score is not None
                        else None
                    ),
                    "matched_entities": p.matched_entities or [],
                    "monitor_name": p.monitor_name,
                    "posted_at": (
                        p.posted_at.isoformat() if p.posted_at else None
                    ),
                    "collected_at": p.collected_at.isoformat(),
                }
                for p in page
            ],
            "has_more": has_more,
            "next_cursor": next_cursor,
        }


@signals_router.get("/sentiment")
async def get_sentiment_summary(
    days: int = Query(default=7, ge=1, le=60),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Per-monitor sentiment aggregation over the last N days."""
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT
                    sm.platform,
                    sm.display_name,
                    sm.identifier,
                    COUNT(*) AS post_count,
                    ROUND(AVG(sp.sentiment_score)::numeric, 3)
                        AS avg_sentiment,
                    COUNT(*) FILTER (WHERE sp.sentiment_score > 0.1)
                        AS positive_count,
                    COUNT(*) FILTER (WHERE sp.sentiment_score < -0.1)
                        AS negative_count,
                    COUNT(*) FILTER (
                        WHERE sp.sentiment_score BETWEEN -0.1 AND 0.1
                    ) AS neutral_count
                FROM social_posts sp
                JOIN social_monitors sm ON sm.id = sp.monitor_id
                WHERE sp.collected_at > NOW() - (:days * INTERVAL '1 day')
                GROUP BY sm.platform, sm.display_name, sm.identifier
                ORDER BY sm.platform, post_count DESC
                """
            ),
            {"days": days},
        )
        rows = result.fetchall()

        return {
            "sentiment_by_monitor": [
                {
                    "platform": r.platform,
                    "display_name": r.display_name,
                    "identifier": r.identifier,
                    "post_count": int(r.post_count or 0),
                    "avg_sentiment": float(r.avg_sentiment or 0),
                    "positive_count": int(r.positive_count or 0),
                    "negative_count": int(r.negative_count or 0),
                    "neutral_count": int(r.neutral_count or 0),
                }
                for r in rows
            ]
        }


@signals_router.get("/monitors")
async def get_monitors(
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """List every monitor with its current post count."""
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT
                    sm.id::text AS id,
                    sm.platform,
                    sm.monitor_type,
                    sm.identifier,
                    sm.display_name,
                    sm.is_active,
                    sm.last_collected_at,
                    (
                        SELECT COUNT(*)
                        FROM social_posts sp
                        WHERE sp.monitor_id = sm.id
                    ) AS post_count
                FROM social_monitors sm
                ORDER BY sm.platform, sm.display_name
                """
            )
        )
        rows = result.fetchall()
        return {
            "monitors": [
                {
                    "id": m.id,
                    "platform": m.platform,
                    "monitor_type": m.monitor_type,
                    "identifier": m.identifier,
                    "display_name": m.display_name,
                    "is_active": m.is_active,
                    "last_collected_at": (
                        m.last_collected_at.isoformat()
                        if m.last_collected_at
                        else None
                    ),
                    "post_count": int(m.post_count or 0),
                }
                for m in rows
            ]
        }
