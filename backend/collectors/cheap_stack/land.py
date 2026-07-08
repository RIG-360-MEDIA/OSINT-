"""Phase 2 — land keyword-collector output into `social_posts` (reshaped).

Bridges the cheap_stack keyword collectors (KeywordSearchResult) to the DB
landing contract from `docs/handoffs/phase2_landing_reference.py` (migration
142_keyword_posts_reshape.sql). New rows default `substrate_status='pending'` so
they auto-enter the existing enrichment pipeline; re-search refreshes engagement
+ merges `raw` WITHOUT re-enriching (the DO UPDATE skips enrichment columns).

Fixed typed core + one `raw` jsonb catch-all: each platform maps its engagement
to the shared columns; everything not in the 22 typed columns falls into `raw`.

    conn = get_conn()
    await collect_and_land("Tridel", ["tiktok", "youtube"], conn=conn)
"""
from __future__ import annotations

import os
import time
from typing import Any, Optional

from .keyword_search import REGISTRY, KeywordSearchResult

DSN = os.environ.get("DATABASE_URL_SYNC", "postgresql://rig:@rig-postgres:5432/rig")

# ── landing contract (from phase2_landing_reference.py — 22 typed columns) ────

_COLS = (
    "platform", "platform_post_id", "author_username", "channel",
    "post_text", "full_content", "post_url", "posted_at", "matched_keyword", "source",
    "likes", "upvotes", "comments_count", "shares", "views", "upvote_ratio",
    "is_retweet", "is_reply", "lang", "has_media", "media_urls", "raw",
)
_TYPED_KEYS = {
    "platform", "platform_post_id", "author_username", "channel",
    "post_text", "full_content", "post_url", "posted_at", "matched_keyword", "source",
    "likes", "upvotes", "comment_count", "comments_count", "shares", "views",
    "upvote_ratio", "is_retweet", "is_reply", "lang", "has_media", "media_urls",
}
_UPSERT = f"""
INSERT INTO social_posts ({", ".join(_COLS)}) VALUES %s
ON CONFLICT (platform, platform_post_id) DO UPDATE SET
    likes           = EXCLUDED.likes,
    upvotes         = EXCLUDED.upvotes,
    comments_count  = EXCLUDED.comments_count,
    shares          = EXCLUDED.shares,
    views           = EXCLUDED.views,
    upvote_ratio    = EXCLUDED.upvote_ratio,
    has_media       = EXCLUDED.has_media,
    media_urls      = EXCLUDED.media_urls,
    matched_keyword = COALESCE(social_posts.matched_keyword, EXCLUDED.matched_keyword),
    raw             = COALESCE(social_posts.raw,'{{}}'::jsonb) || COALESCE(EXCLUDED.raw,'{{}}'::jsonb)
"""


def _row(p: dict[str, Any], keyword: str) -> tuple:
    from psycopg2.extras import Json

    extras = {k: v for k, v in p.items() if k not in _TYPED_KEYS}
    return (
        p["platform"],
        str(p["platform_post_id"]),
        p.get("author_username"),
        p.get("channel"),
        p.get("post_text"),
        p.get("full_content"),
        p.get("post_url"),
        p.get("posted_at") or None,
        p.get("matched_keyword") or keyword,
        p.get("source"),
        p.get("likes"),
        p.get("upvotes"),
        p.get("comments_count", p.get("comment_count")),   # spelling bridge
        p.get("shares"),
        p.get("views"),
        p.get("upvote_ratio"),
        bool(p.get("is_retweet", False)),
        bool(p.get("is_reply", False)),
        p.get("lang"),
        bool(p.get("has_media", False)),
        Json(p.get("media_urls") or []),
        Json(extras),
    )


def land_keyword_posts(conn, posts: list[dict[str, Any]], keyword: str,
                       platform: str, took_ms: Optional[int] = None,
                       client: str = "keyword_search") -> int:
    """Upsert one platform's keyword-search results + write the audit row."""
    from psycopg2.extras import execute_values

    rows = [_row(p, keyword) for p in posts]
    with conn.cursor() as cur:
        if rows:
            execute_values(cur, _UPSERT, rows, page_size=200)
        cur.execute(
            "INSERT INTO keyword_searches (keyword, platform, n_results, took_ms, client) "
            "VALUES (%s, %s, %s, %s, %s)",
            (keyword, platform, len(rows), took_ms, client),
        )
    conn.commit()
    return len(rows)


# ── per-platform field adaptation (promote to typed columns before landing) ──

_SOURCE = {
    "reddit": "reddit_session_search", "tiktok": "tikwm_feed_search",
    "youtube": "youtube_innertube", "twitter": "twscrape",
    "telegram": "tme_channel_set", "instagram": "ig_hybrid",
    "wechat": "sogou_weixin",
}


def _adapt(post: dict[str, Any], platform: str) -> dict[str, Any]:
    """Map a collector dict's platform-specific fields onto the shared typed
    columns (`channel`, `full_content`, `source`). Non-mutating. Everything else
    is left in place and falls into `raw` by the landing contract."""
    p = dict(post)
    p.setdefault("source", _SOURCE.get(platform, platform))
    if platform == "reddit":
        p["channel"] = p.get("channel") or p.get("subreddit")
    elif platform == "youtube":
        p["channel"] = p.get("channel") or p.get("author_username")
    elif platform == "wechat":
        p["channel"] = p.get("channel") or p.get("account")
        # promote the big body to its dedicated column; drop the dup from raw
        p["full_content"] = p.get("full_content") or p.pop("content", None)
    return p


def get_conn():
    import psycopg2
    return psycopg2.connect(DSN)


def land_result(result: KeywordSearchResult, *, conn=None,
                client: str = "keyword_search") -> int:
    """Land one KeywordSearchResult (adapting per-platform fields). Opens a
    connection if none given. Skips landing when the collector failed (ok=False)."""
    if not result.ok:
        return 0
    own = conn is None
    conn = conn or get_conn()
    try:
        posts = [_adapt(p, result.platform) for p in result.posts]
        return land_keyword_posts(
            conn, posts, result.query, result.platform,
            took_ms=int(result.elapsed_s * 1000), client=client,
        )
    finally:
        if own:
            conn.close()


async def collect_and_land(keyword: str, platforms: list[str], *, limit: int = 25,
                           conn=None, client: str = "keyword_search") -> dict[str, int]:
    """Run the given platforms' collectors for a keyword and land each result.
    Returns {platform: n_landed}. Reuses one connection across platforms."""
    own = conn is None
    conn = conn or get_conn()
    landed: dict[str, int] = {}
    try:
        for platform in platforms:
            fn = REGISTRY.get(platform)
            if fn is None:
                continue
            try:
                result = await fn(keyword, limit=limit)
            except Exception:
                landed[platform] = 0
                continue
            landed[platform] = land_result(result, conn=conn, client=client)
    finally:
        if own:
            conn.close()
    return landed
