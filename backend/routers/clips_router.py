"""
Clips router — serves the Clip Room feed.

GET  /api/clips/feed     — paginated ranked clip feed for current user
GET  /api/clips/channels — list monitored channels
POST /api/clips/channels — add a channel to monitor
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from backend.auth.auth_middleware import get_current_user
from backend.database import get_db

logger = logging.getLogger(__name__)

clips_router = APIRouter(prefix="/api/clips", tags=["clips"])


@clips_router.get("/feed")
async def get_clips_feed(
    entity:  str = Query(default=""),
    channel: str = Query(default=""),
    days:    int = Query(default=7),
    limit:   int = Query(default=20, le=50),
    cursor:  str = Query(default=""),
    user:   dict = Depends(get_current_user),
) -> dict:
    """Ranked clip feed filtered to the user's tracked entities."""
    async with get_db() as db:
        entities_result = await db.execute(
            text("""
                SELECT canonical_name
                FROM user_entities
                WHERE user_id = :uid
                ORDER BY priority DESC
            """),
            {"uid": user["id"]},
        )
        user_entities = [r.canonical_name for r in entities_result.fetchall()]

        if not user_entities:
            return {"clips": [], "has_more": False, "total": 0, "channels": [], "user_entities": []}

        conditions = [
            "yc.processed = TRUE",
            "yc.matched_entity = ANY(:entities)",
            "yc.collected_at > NOW() - (:days * INTERVAL '1 day')",
        ]
        params: dict = {
            "entities": user_entities,
            "days":     days,
            "limit":    limit + 1,
        }

        if entity:
            conditions.append("yc.matched_entity = :entity")
            params["entity"] = entity

        if channel:
            conditions.append("yc.channel_id = :channel")
            params["channel"] = channel

        if cursor:
            conditions.append("yc.collected_at < :cursor_time::timestamptz")
            params["cursor_time"] = cursor

        where_clause = " AND ".join(conditions)

        result = await db.execute(
            text(f"""
                WITH ents AS (
                    SELECT video_id, clip_start_seconds,
                           ARRAY_AGG(DISTINCT matched_entity) AS all_entities
                    FROM youtube_clips
                    GROUP BY video_id, clip_start_seconds
                ),
                ranked AS (
                    SELECT yc.*,
                        ROW_NUMBER() OVER (
                            PARTITION BY yc.video_id, yc.clip_start_seconds
                            ORDER BY COALESCE(yc.relevance_score, 0) DESC, yc.collected_at DESC
                        ) AS rn
                    FROM youtube_clips yc
                    WHERE {where_clause}
                )
                SELECT
                    r.id::text             AS clip_id,
                    r.video_id,
                    r.video_title,
                    r.channel_id,
                    r.channel_name,
                    r.video_published_at,
                    r.video_url,
                    r.clip_start_seconds,
                    r.clip_end_seconds,
                    r.embed_url,
                    r.transcript_segment,
                    r.transcript_language,
                    r.transcript_translated,
                    r.matched_entity,
                    e.all_entities,
                    r.relevance_score,
                    (r.clip_start_seconds > 0 OR COALESCE(LENGTH(r.transcript_segment), 0) > 30) AS has_transcript,
                    r.collected_at
                FROM ranked r
                LEFT JOIN ents e
                  ON e.video_id = r.video_id
                 AND e.clip_start_seconds = r.clip_start_seconds
                WHERE r.rn = 1
                ORDER BY
                    (r.clip_start_seconds > 0) DESC,
                    COALESCE(r.relevance_score, 0) DESC,
                    r.collected_at DESC
                LIMIT :limit
            """),
            params,
        )
        rows = result.fetchall()

        has_more   = len(rows) > limit
        clips_page = rows[:limit]

        next_cursor = (
            clips_page[-1].collected_at.isoformat() if has_more and clips_page else None
        )

        count_result = await db.execute(
            text("""
                SELECT COUNT(*) AS total
                FROM youtube_clips
                WHERE matched_entity = ANY(:entities)
                  AND collected_at > NOW() - INTERVAL '7 days'
                  AND processed = TRUE
            """),
            {"entities": user_entities},
        )
        total = count_result.fetchone().total

        channels_result = await db.execute(
            text("""
                SELECT
                    channel_id,
                    channel_name,
                    COUNT(*) AS clip_count
                FROM youtube_clips
                WHERE matched_entity = ANY(:entities)
                  AND collected_at > NOW() - INTERVAL '7 days'
                GROUP BY channel_id, channel_name
                ORDER BY clip_count DESC
            """),
            {"entities": user_entities},
        )
        channels = channels_result.fetchall()

        return {
            "clips": [
                {
                    "clip_id":               c.clip_id,
                    "video_id":              c.video_id,
                    "video_title":           c.video_title,
                    "channel_name":          c.channel_name,
                    "channel_id":            c.channel_id,
                    "video_url":             c.video_url,
                    "embed_url":             c.embed_url,
                    "clip_start_seconds":    c.clip_start_seconds,
                    "clip_end_seconds":      c.clip_end_seconds,
                    "transcript_segment":    c.transcript_segment,
                    "transcript_translated": c.transcript_translated,
                    "matched_entity":        c.matched_entity,
                    "all_entities":          list(c.all_entities or []) if hasattr(c, "all_entities") else [c.matched_entity],
                    "relevance_score":       float(c.relevance_score) if c.relevance_score is not None else None,
                    "has_transcript":        bool(c.has_transcript) if hasattr(c, "has_transcript") else (c.clip_start_seconds > 0),
                    "transcript_language":   c.transcript_language,
                    "video_published_at":    (
                        c.video_published_at.isoformat() if c.video_published_at else None
                    ),
                    "collected_at":          c.collected_at.isoformat(),
                }
                for c in clips_page
            ],
            "has_more":      has_more,
            "next_cursor":   next_cursor,
            "total":         total,
            "channels":      [
                {
                    "channel_id":   ch.channel_id,
                    "channel_name": ch.channel_name,
                    "clip_count":   ch.clip_count,
                }
                for ch in channels
            ],
            "user_entities": user_entities,
        }


@clips_router.get("/channels")
async def list_channels(user: dict = Depends(get_current_user)) -> dict:
    """List all monitored YouTube channels."""
    async with get_db() as db:
        result = await db.execute(text("""
            SELECT
                ch.channel_id,
                ch.channel_name,
                ch.channel_url,
                ch.is_active,
                ch.last_checked_at,
                (
                    SELECT COUNT(*) FROM youtube_clips yc
                    WHERE yc.channel_id = ch.channel_id
                ) AS total_clips
            FROM youtube_channels ch
            ORDER BY ch.channel_name
        """))
        channels = result.fetchall()
        return {
            "channels": [
                {
                    "channel_id":      c.channel_id,
                    "channel_name":    c.channel_name,
                    "channel_url":     c.channel_url,
                    "is_active":       c.is_active,
                    "last_checked_at": (
                        c.last_checked_at.isoformat() if c.last_checked_at else None
                    ),
                    "total_clips":     c.total_clips,
                }
                for c in channels
            ]
        }


@clips_router.post("/channels")
async def add_channel(
    channel_id:   str,
    channel_name: str,
    user:        dict = Depends(get_current_user),
) -> dict:
    """Add or re-enable a YouTube channel to monitor."""
    async with get_db() as db:
        await db.execute(
            text("""
                INSERT INTO youtube_channels (channel_id, channel_name, channel_url, is_active)
                VALUES (:cid, :name, :url, TRUE)
                ON CONFLICT (channel_id) DO UPDATE SET is_active = TRUE
            """),
            {
                "cid":  channel_id,
                "name": channel_name,
                "url":  f"https://youtube.com/channel/{channel_id}",
            },
        )
        await db.commit()
        return {"success": True, "channel_id": channel_id}
