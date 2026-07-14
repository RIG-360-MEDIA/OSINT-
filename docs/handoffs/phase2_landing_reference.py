"""
REFERENCE (not imported anywhere) — the exact landing contract for Phase 2.
Hand this to the collector chat so `land_keyword_posts()` writes against the real,
verified social_posts schema (migration 142_keyword_posts_reshape.sql, applied).

Validated end-to-end against the live DB 2026-07-08: dedup, engagement refresh,
matched_keyword COALESCE, and raw-merge all proven.
"""
from psycopg2.extras import execute_values, Json

# Column order MUST match the tuple built in _row(). 22 columns.
_COLS = (
    "platform", "platform_post_id", "author_username", "channel",
    "post_text", "full_content", "post_url", "posted_at", "matched_keyword", "source",
    "likes", "upvotes", "comments_count", "shares", "views", "upvote_ratio",
    "is_retweet", "is_reply", "lang", "has_media", "media_urls", "raw",
)

# Collector-dict keys that map to TYPED columns — everything else falls to raw.
# NOTE the spelling bridge: collector emits `comment_count`, column is `comments_count`.
_TYPED_KEYS = {
    "platform", "platform_post_id", "author_username", "channel",
    "post_text", "full_content", "post_url", "posted_at", "matched_keyword", "source",
    "likes", "upvotes", "comment_count", "comments_count", "shares", "views",
    "upvote_ratio", "is_retweet", "is_reply", "lang", "has_media", "media_urls",
}

# Do NOT list substrate_status / collected_at — they default to 'pending' / now(),
# so new rows auto-enter enrichment. The DO UPDATE deliberately skips enrichment
# columns so a re-search refreshes engagement + merges raw WITHOUT re-enriching.
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


def _row(p: dict, keyword: str) -> tuple:
    # extras = every key not mapped to a typed column -> raw jsonb catch-all
    extras = {k: v for k, v in p.items() if k not in _TYPED_KEYS}
    return (
        p["platform"],                                       # varchar(16)
        str(p["platform_post_id"]),                          # text, required
        p.get("author_username"),
        p.get("channel"),
        p.get("post_text"),
        p.get("full_content"),                               # wechat body / yt transcript; else None
        p.get("post_url"),
        p.get("posted_at"),                                  # datetime or ISO8601 str (PG casts)
        p.get("matched_keyword") or keyword,                 # fall back to the search term
        p.get("source"),
        p.get("likes"),
        p.get("upvotes"),
        p.get("comments_count", p.get("comment_count")),     # <-- spelling bridge
        p.get("shares"),
        p.get("views"),
        p.get("upvote_ratio"),
        bool(p.get("is_retweet", False)),
        bool(p.get("is_reply", False)),
        p.get("lang"),
        bool(p.get("has_media", False)),
        Json(p.get("media_urls") or []),                     # jsonb  (wrap!)
        Json(extras),                                        # jsonb  (wrap!)
    )


def land_keyword_posts(conn, posts: list[dict], keyword: str, platform: str,
                       took_ms: int | None = None, client: str = "keyword_search") -> int:
    """Upsert one platform's keyword-search results + write the audit row.
    Returns the number of posts landed. Call once per (keyword, platform) search."""
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
