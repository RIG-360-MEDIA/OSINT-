"""
Signal Room API — unified feed across Reddit / Twitter / Telegram plus
sentiment aggregation and monitor listing.

All endpoints require a valid Supabase session (Bearer token).
"""
from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from backend.auth.auth_middleware import get_current_user, require_page
from backend.database import get_db

logger = logging.getLogger(__name__)

signals_router = APIRouter(
    prefix="/api/signals",
    tags=["signals"],
    dependencies=[Depends(require_page("signals"))],
)

# UI-visible platforms. Twitter is data-active but UI-hidden (see CLAUDE.md).
_UI_PLATFORMS: frozenset[str] = frozenset({"reddit", "telegram"})
_PLATFORM_QUERY_VALUES: frozenset[str] = _UI_PLATFORMS | {"all"}
_TOPIC_KINDS: frozenset[str] = frozenset({"entity", "cluster", "subject"})
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _require_uuid(value: str, field: str) -> str:
    if not _UUID_RE.match(value):
        raise HTTPException(status_code=422, detail=f"Invalid {field}")
    return value


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

    A post surfaces when either:
      (a) it came from an explicitly-monitored source (monitor_id set) —
          the user's decision to monitor that subreddit / account /
          channel is itself the relevance signal, OR
      (b) for any un-monitored post (future keyword-search firehose),
          it matches a user-tracked entity OR has high engagement
          (upvotes > 100).

    Ordered by collection time; paginated via ISO-timestamp cursor on
    `collected_at`.
    """
    if platform not in _PLATFORM_QUERY_VALUES:
        raise HTTPException(status_code=422, detail="Invalid platform")

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
            "sp.platform IN ('reddit', 'telegram')",
        ]
        params: dict[str, Any] = {"days": days, "limit": limit + 1}

        if user_entities:
            # Show everything from monitored sources OR anything
            # un-monitored that matches an entity / high engagement.
            conditions.append(
                "("
                "sp.monitor_id IS NOT NULL "
                "OR sp.matched_entities && CAST(:entities AS text[]) "
                "OR sp.upvotes > 100"
                ")"
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
                  AND sp.platform IN ('reddit', 'telegram')
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
    """List every monitor with its current post count.

    SIG-4: single LEFT JOIN + GROUP BY instead of a correlated COUNT
    sub-query per monitor row (N+1 → 1).
    """
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
                    COUNT(sp.id) AS post_count
                FROM social_monitors sm
                LEFT JOIN social_posts sp ON sp.monitor_id = sm.id
                GROUP BY sm.id
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


# ── Briefing + Timeline (Signal Room redesign) ─────────────────────────────


@signals_router.get("/briefing")
async def get_signals_briefing(
    limit: int = Query(default=12, ge=1, le=30),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Top auto-clustered "stories" for the front-page briefing.

    Twitter is filtered out of `platforms` for the user UI freeze.
    """
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT
                    id::text AS id,
                    window_start,
                    window_end,
                    headline,
                    summary,
                    post_count,
                    platforms,
                    monitor_names,
                    top_entities,
                    avg_sentiment,
                    sentiment_tone,
                    representative_post_ids,
                    sample_languages,
                    created_at
                FROM social_clusters
                ORDER BY post_count DESC, window_end DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
        rows = result.fetchall()
        return {
            "as_of": (
                rows[0].window_end.isoformat() if rows else None
            ),
            "clusters": [
                {
                    "id": r.id,
                    "headline": r.headline,
                    "summary": r.summary,
                    "post_count": int(r.post_count or 0),
                    "platforms": [
                        p for p in (r.platforms or []) if p != "twitter"
                    ],
                    "monitor_names": list(r.monitor_names or []),
                    "top_entities": list(r.top_entities or []),
                    "avg_sentiment": (
                        float(r.avg_sentiment)
                        if r.avg_sentiment is not None
                        else None
                    ),
                    "sentiment_tone": r.sentiment_tone,
                    "sample_languages": list(r.sample_languages or []),
                    "representative_post_ids": [
                        str(p) for p in (r.representative_post_ids or [])
                    ],
                }
                for r in rows
            ],
        }


@signals_router.get("/timeline")
async def get_signals_timeline(
    hours: int = Query(default=24, ge=1, le=72),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Hourly volume + sentiment buckets for the timeline strip.

    Returned shape lets the frontend draw a stacked bar (post volume)
    coloured by net sentiment.
    """
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT
                    date_trunc('hour', collected_at) AS bucket,
                    platform,
                    COUNT(*) AS posts,
                    AVG(sentiment_score) AS avg_sentiment,
                    COUNT(*) FILTER (WHERE sentiment_score >= 0.15)
                        AS positive,
                    COUNT(*) FILTER (WHERE sentiment_score <= -0.15)
                        AS negative
                FROM social_posts
                WHERE collected_at > NOW() - (:hours * INTERVAL '1 hour')
                  AND platform IN ('reddit', 'telegram')
                GROUP BY 1, 2
                ORDER BY 1
                """
            ),
            {"hours": hours},
        )
        rows = result.fetchall()
        return {
            "buckets": [
                {
                    "hour": r.bucket.isoformat(),
                    "platform": r.platform,
                    "posts": int(r.posts or 0),
                    "avg_sentiment": (
                        float(r.avg_sentiment)
                        if r.avg_sentiment is not None
                        else None
                    ),
                    "positive": int(r.positive or 0),
                    "negative": int(r.negative or 0),
                }
                for r in rows
            ],
        }


@signals_router.get("/uncategorised")
async def get_uncategorised(
    hours: int = Query(default=36, ge=1, le=72),
    limit: int = Query(default=40, ge=1, le=100),
    cursor: str = Query(default=""),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Posts in the window that are NOT in any cluster — "solo dispatches".

    These are the long tail of posts that didn't have a near-duplicate
    inside the briefing window. Cursor paginated by `collected_at`.
    Twitter is filtered out for the user UI.
    """
    async with get_db() as db:
        params: dict[str, Any] = {
            "hours": hours,
            "limit": limit + 1,
        }
        cursor_clause = ""
        if cursor:
            cursor_clause = "AND sp.collected_at < :cursor"
            params["cursor"] = cursor

        result = await db.execute(
            text(
                f"""
                SELECT
                    sp.id::text AS post_id,
                    sp.platform,
                    sp.author_username,
                    sp.post_text,
                    sp.post_text_translated,
                    sp.post_language,
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
                WHERE sp.collected_at > NOW() - (:hours * INTERVAL '1 hour')
                  AND sp.platform IN ('reddit', 'telegram')
                  AND NOT EXISTS (
                      SELECT 1 FROM social_cluster_posts cp
                      WHERE cp.post_id = sp.id
                  )
                  {cursor_clause}
                ORDER BY sp.collected_at DESC
                LIMIT :limit
                """
            ),
            params,
        )
        rows = result.fetchall()
        has_more = len(rows) > limit
        page = rows[:limit]
        next_cursor: str | None = (
            page[-1].collected_at.isoformat()
            if has_more and page
            else None
        )
        return {
            "posts": [
                {
                    "post_id": p.post_id,
                    "platform": p.platform,
                    "author_username": p.author_username,
                    "post_text": p.post_text,
                    "post_text_translated": p.post_text_translated,
                    "post_language": p.post_language,
                    "post_url": p.post_url,
                    "upvotes": int(p.upvotes or 0),
                    "comment_count": int(p.comment_count or 0),
                    "share_count": int(p.share_count or 0),
                    "forward_count": int(p.forward_count or 0),
                    "forwarded_from": p.forwarded_from,
                    "has_document": bool(p.has_document),
                    "sentiment_score": (
                        float(p.sentiment_score)
                        if p.sentiment_score is not None
                        else None
                    ),
                    "matched_entities": list(p.matched_entities or []),
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


@signals_router.get("/cluster/{cluster_id}/posts")
async def get_cluster_posts(
    cluster_id: str,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Drilldown — every post in a cluster (translated where available)."""
    _require_uuid(cluster_id, "cluster_id")
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT
                    sp.id::text AS post_id,
                    sp.platform,
                    sp.author_username,
                    sp.post_text,
                    sp.post_text_translated,
                    sp.post_language,
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
                FROM social_cluster_posts cp
                JOIN social_posts sp ON sp.id = cp.post_id
                LEFT JOIN social_monitors sm ON sm.id = sp.monitor_id
                WHERE cp.cluster_id = CAST(:cid AS uuid)
                ORDER BY (sp.upvotes + 2 * sp.comment_count) DESC,
                         sp.collected_at DESC
                """
            ),
            {"cid": cluster_id},
        )
        rows = result.fetchall()
        return {
            "posts": [
                {
                    "post_id": p.post_id,
                    "platform": p.platform,
                    "author_username": p.author_username,
                    "post_text": p.post_text,
                    "post_text_translated": p.post_text_translated,
                    "post_language": p.post_language,
                    "post_url": p.post_url,
                    "upvotes": int(p.upvotes or 0),
                    "comment_count": int(p.comment_count or 0),
                    "share_count": int(p.share_count or 0),
                    "forward_count": int(p.forward_count or 0),
                    "forwarded_from": p.forwarded_from,
                    "has_document": bool(p.has_document),
                    "sentiment_score": (
                        float(p.sentiment_score)
                        if p.sentiment_score is not None
                        else None
                    ),
                    "matched_entities": list(p.matched_entities or []),
                    "monitor_name": p.monitor_name,
                    "posted_at": (
                        p.posted_at.isoformat() if p.posted_at else None
                    ),
                    "collected_at": p.collected_at.isoformat(),
                }
                for p in rows
                if p.platform != "twitter"
            ],
        }


# ── Intel layer endpoints (typewriter daily summary + topic drilldown) ────


@signals_router.get("/summary/latest")
async def get_latest_summary(
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the most recent composed daily summary."""
    async with get_db() as db:
        row = (
            await db.execute(
                text(
                    """
                    SELECT id::text, edition, classification,
                           generated_at, window_hours, body,
                           sources_used, event_ids
                    FROM social_summaries
                    ORDER BY generated_at DESC
                    LIMIT 1
                    """
                )
            )
        ).fetchone()
        if not row:
            return {"summary": None}
        return {
            "summary": {
                "id": row.id,
                "edition": row.edition,
                "classification": row.classification,
                "generated_at": row.generated_at.isoformat(),
                "window_hours": row.window_hours,
                "body": row.body,
                "sources_used": list(row.sources_used or []),
                "event_count": len(row.event_ids or []),
            }
        }


@signals_router.get("/summary/editions")
async def get_summary_editions(
    limit: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """List past editions for the navigation rail."""
    async with get_db() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT id::text, edition, classification,
                           generated_at, window_hours
                    FROM social_summaries
                    ORDER BY generated_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            )
        ).fetchall()
        return {
            "editions": [
                {
                    "id": r.id,
                    "edition": r.edition,
                    "classification": r.classification,
                    "generated_at": r.generated_at.isoformat(),
                    "window_hours": r.window_hours,
                }
                for r in rows
            ]
        }


@signals_router.get("/summary/{summary_id}")
async def get_summary_by_id(
    summary_id: str,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Fetch a specific past edition."""
    _require_uuid(summary_id, "summary_id")
    async with get_db() as db:
        row = (
            await db.execute(
                text(
                    """
                    SELECT id::text, edition, classification,
                           generated_at, window_hours, body,
                           sources_used, event_ids
                    FROM social_summaries
                    WHERE id = CAST(:sid AS uuid)
                    """
                ),
                {"sid": summary_id},
            )
        ).fetchone()
        if not row:
            return {"summary": None}
        return {
            "summary": {
                "id": row.id,
                "edition": row.edition,
                "classification": row.classification,
                "generated_at": row.generated_at.isoformat(),
                "window_hours": row.window_hours,
                "body": row.body,
                "sources_used": list(row.sources_used or []),
                "event_count": len(row.event_ids or []),
            }
        }


@signals_router.get("/topic/{kind}/{key}")
async def get_topic(
    kind: str,
    key: str,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Drilldown: posts for an entity / cluster / subject.

    `kind` ∈ {entity, cluster, subject}.
    `key` is the entity name, cluster uuid, or subject phrase.
    """
    if kind not in _TOPIC_KINDS:
        raise HTTPException(status_code=422, detail="Invalid kind")
    if kind == "cluster":
        _require_uuid(key, "cluster key")
    elif not key.strip():
        raise HTTPException(status_code=422, detail="Empty key")

    async with get_db() as db:
        if kind == "cluster":
            rows = (
                await db.execute(
                    text(
                        """
                        SELECT
                            sp.id::text AS post_id,
                            sp.platform,
                            sp.author_username,
                            sp.post_text,
                            sp.post_text_translated,
                            sp.post_language,
                            sp.post_url,
                            sp.upvotes,
                            sp.comment_count,
                            sp.share_count,
                            sp.forward_count,
                            sp.forwarded_from,
                            sp.has_document,
                            sp.sentiment_score,
                            sp.matched_entities,
                            sp.relevance_score,
                            sp.posted_at,
                            sp.collected_at,
                            sm.display_name AS monitor_name
                        FROM social_cluster_posts cp
                        JOIN social_posts sp ON sp.id = cp.post_id
                        LEFT JOIN social_monitors sm ON sm.id = sp.monitor_id
                        WHERE cp.cluster_id = CAST(:k AS uuid)
                          AND sp.platform <> 'twitter'
                        ORDER BY sp.relevance_score DESC,
                                 (sp.upvotes + 2 * sp.comment_count) DESC,
                                 sp.collected_at DESC
                        """
                    ),
                    {"k": key},
                )
            ).fetchall()
        else:
            # entity OR subject — substring match against translated body
            if kind == "entity":
                where = ":k = ANY(sp.matched_entities)"
            else:
                where = (
                    "(LOWER(sp.post_text) LIKE LOWER(:like) "
                    "OR LOWER(COALESCE(sp.post_text_translated,'')) "
                    "LIKE LOWER(:like))"
                )
            rows = (
                await db.execute(
                    text(
                        f"""
                        SELECT
                            sp.id::text AS post_id,
                            sp.platform,
                            sp.author_username,
                            sp.post_text,
                            sp.post_text_translated,
                            sp.post_language,
                            sp.post_url,
                            sp.upvotes,
                            sp.comment_count,
                            sp.share_count,
                            sp.forward_count,
                            sp.forwarded_from,
                            sp.has_document,
                            sp.sentiment_score,
                            sp.matched_entities,
                            sp.relevance_score,
                            sp.posted_at,
                            sp.collected_at,
                            sm.display_name AS monitor_name
                        FROM social_posts sp
                        LEFT JOIN social_monitors sm ON sm.id = sp.monitor_id
                        WHERE sp.platform <> 'twitter'
                          AND sp.collected_at > NOW() - INTERVAL '7 days'
                          AND {where}
                        ORDER BY sp.relevance_score DESC,
                                 sp.collected_at DESC
                        LIMIT 200
                        """
                    ),
                    {"k": key, "like": f"%{key}%"},
                )
            ).fetchall()

        return {
            "kind": kind,
            "key": key,
            "posts": [
                {
                    "post_id": p.post_id,
                    "platform": p.platform,
                    "author_username": p.author_username,
                    "post_text": p.post_text,
                    "post_text_translated": p.post_text_translated,
                    "post_language": p.post_language,
                    "post_url": p.post_url,
                    "upvotes": int(p.upvotes or 0),
                    "comment_count": int(p.comment_count or 0),
                    "share_count": int(p.share_count or 0),
                    "forward_count": int(p.forward_count or 0),
                    "forwarded_from": p.forwarded_from,
                    "has_document": bool(p.has_document),
                    "sentiment_score": (
                        float(p.sentiment_score)
                        if p.sentiment_score is not None
                        else None
                    ),
                    "matched_entities": list(p.matched_entities or []),
                    "relevance_score": int(p.relevance_score or 0),
                    "monitor_name": p.monitor_name,
                    "posted_at": (
                        p.posted_at.isoformat() if p.posted_at else None
                    ),
                    "collected_at": p.collected_at.isoformat(),
                }
                for p in rows
            ],
        }


@signals_router.get("/seeds")
async def get_seeds(
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the geo + topic seed lists (for the seeds editor UI)."""
    async with get_db() as db:
        geo = (
            await db.execute(
                text("SELECT id, term, kind, weight FROM social_geo_seeds ORDER BY term")
            )
        ).fetchall()
        topic = (
            await db.execute(
                text("SELECT id, term, weight, note FROM social_topic_seeds ORDER BY term")
            )
        ).fetchall()
        return {
            "geo": [
                {"id": r.id, "term": r.term, "kind": r.kind, "weight": r.weight}
                for r in geo
            ],
            "topic": [
                {
                    "id": r.id,
                    "term": r.term,
                    "weight": r.weight,
                    "note": r.note,
                }
                for r in topic
            ],
        }
