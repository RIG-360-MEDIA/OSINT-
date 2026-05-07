"""
Clips router — serves the Clip Room feed.

GET  /api/clips/feed     — paginated ranked clip feed for current user
GET  /api/clips/channels — list monitored channels
POST /api/clips/channels — add a channel to monitor
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from backend.auth.auth_middleware import get_current_principal, get_current_user, require_page
from backend.database import get_db

logger = logging.getLogger(__name__)

clips_router = APIRouter(
    prefix="/api/clips",
    tags=["clips"],
    dependencies=[Depends(require_page("clips"))],
)

# YouTube channel IDs are always 24 chars: "UC" + 22 base64url-ish chars.
_CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")


class AddChannelRequest(BaseModel):
    channel_id:   str = Field(..., min_length=24, max_length=24)
    channel_name: str = Field(..., min_length=1, max_length=200)


@clips_router.get("/feed")
async def get_clips_feed(
    entity:  str = Query(default=""),
    channel: str = Query(default=""),
    days:    int = Query(default=7,  ge=1, le=90),
    limit:   int = Query(default=20, ge=1, le=50),
    cursor:  str = Query(default=""),
    user:   dict = Depends(get_current_principal),
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
            return {
                "clips": [], "has_more": False, "next_cursor": None,
                "total": 0, "channels": [], "user_entities": [],
            }

        # Build a shared filter clause used by feed, total, and channels —
        # so they all reflect the same view (B1, B2 fix).
        base_conditions = [
            "matched_entity = ANY(:entities)",
            "collected_at > NOW() - (:days * INTERVAL '1 day')",
        ]
        base_params: dict = {"entities": user_entities, "days": days}

        if entity:
            base_conditions.append("matched_entity = :entity")
            base_params["entity"] = entity

        if channel:
            base_conditions.append("channel_id = :channel")
            base_params["channel"] = channel

        # Feed query adds processed=TRUE + cursor + alias prefix.
        feed_conditions = ["yc.processed = TRUE"] + [
            f"yc.{c}" for c in base_conditions
        ]
        feed_params: dict = dict(base_params, limit=limit + 1)

        if cursor:
            try:
                cursor_dt = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail="cursor must be an ISO-8601 timestamp",
                ) from exc
            feed_conditions.append("yc.collected_at < :cursor_time")
            feed_params["cursor_time"] = cursor_dt

        # ents CTE filtered by entities + window so it doesn't scan whole table (B8).
        ents_where = " AND ".join(base_conditions)
        feed_where = " AND ".join(feed_conditions)

        result = await db.execute(
            text(f"""
                WITH ents AS (
                    SELECT video_id, clip_start_seconds,
                           ARRAY_AGG(DISTINCT matched_entity) AS all_entities
                    FROM youtube_clips
                    WHERE {ents_where}
                    GROUP BY video_id, clip_start_seconds
                ),
                ranked AS (
                    SELECT yc.*,
                        ROW_NUMBER() OVER (
                            PARTITION BY yc.video_id, yc.clip_start_seconds
                            ORDER BY COALESCE(yc.relevance_score, 0) DESC, yc.collected_at DESC
                        ) AS rn
                    FROM youtube_clips yc
                    WHERE {feed_where}
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
                    -- Recency-day first, then quality preferences. The old
                    -- order had `(clip_start>0) DESC` as the top key — which
                    -- floated every caption-source clip above every metadata-
                    -- only clip regardless of date, so a 17 h-old captioned
                    -- clip outranked all of today's metadata-only clips on
                    -- Whisper-failing days. Bucket by day first to avoid that.
                    DATE_TRUNC('day', r.collected_at) DESC,
                    COALESCE(r.relevance_score, 0) DESC,
                    (r.clip_start_seconds > 0) DESC,
                    r.collected_at DESC,
                    r.id DESC
                LIMIT :limit
            """),
            feed_params,
        )
        rows = result.fetchall()

        has_more   = len(rows) > limit
        clips_page = rows[:limit]

        next_cursor = (
            clips_page[-1].collected_at.isoformat() if has_more and clips_page else None
        )

        # Total + channels share the same base filter (B1, B2 fix).
        total_result = await db.execute(
            text(f"""
                SELECT COUNT(*) AS total
                FROM youtube_clips
                WHERE processed = TRUE AND {ents_where}
            """),
            base_params,
        )
        total = total_result.fetchone().total

        channels_result = await db.execute(
            text(f"""
                SELECT
                    channel_id,
                    channel_name,
                    COUNT(*) AS clip_count
                FROM youtube_clips
                WHERE processed = TRUE AND {ents_where}
                GROUP BY channel_id, channel_name
                ORDER BY clip_count DESC
            """),
            base_params,
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
                    "all_entities":          list(c.all_entities or []),
                    "relevance_score":       float(c.relevance_score) if c.relevance_score is not None else None,
                    "has_transcript":        bool(c.has_transcript),
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
async def list_channels(user: dict = Depends(get_current_principal)) -> dict:
    """List all monitored YouTube channels."""
    async with get_db() as db:
        result = await db.execute(text("""
            SELECT
                ch.channel_id,
                ch.channel_name,
                ch.channel_url,
                ch.is_active,
                ch.last_checked_at,
                COALESCE(yc_counts.total_clips, 0) AS total_clips
            FROM youtube_channels ch
            LEFT JOIN (
                SELECT channel_id, COUNT(*) AS total_clips
                FROM youtube_clips
                GROUP BY channel_id
            ) yc_counts ON yc_counts.channel_id = ch.channel_id
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
    payload: AddChannelRequest,
    user:    dict = Depends(get_current_principal),
) -> dict:
    """Add or re-enable a YouTube channel to monitor."""
    if not _CHANNEL_ID_RE.match(payload.channel_id):
        raise HTTPException(status_code=422, detail="Invalid YouTube channel_id format")

    async with get_db() as db:
        await db.execute(
            text("""
                INSERT INTO youtube_channels (channel_id, channel_name, channel_url, is_active)
                VALUES (:cid, :name, :url, TRUE)
                ON CONFLICT (channel_id) DO UPDATE SET is_active = TRUE
            """),
            {
                "cid":  payload.channel_id,
                "name": payload.channel_name,
                "url":  f"https://youtube.com/channel/{payload.channel_id}",
            },
        )
        await db.commit()
        return {"success": True, "channel_id": payload.channel_id}
