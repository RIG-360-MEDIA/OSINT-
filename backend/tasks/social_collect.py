"""
Celery tasks: social collection — run the 4 scrapers over the watchlist and land
raw posts into the social substrate (substrate_status='pending'), then enqueue
enrichment. Forward collection + ban-safe (the scrapers carry their own pacing;
this just walks the active watchlist).

One collect task per platform on the `social` queue. Each:
  1. reads active social_watchlist rows for its platform (priority order)
  2. calls the right scraper method per target_type
  3. upserts authors + communities, inserts posts (ON CONFLICT DO NOTHING)
  4. enqueues enrich_social_post for each NEW post
  5. advances the watchlist cursor (last_seen_id / last_run_at)

Maps the scrapers' common post shape -> social_authors / social_communities /
social_posts. Engagement differs by platform (see _engagement); views/upvote_ratio
are promoted out of raw into real columns.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any

from backend.celery_app import app

logger = logging.getLogger(__name__)

_MD = re.compile(r"(\*\*|__|\*|`)")
_EMOJI = re.compile(r"[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]")
_WS = re.compile(r"\s+")


# ── Celery entry points (one per platform) ────────────────────────────────────

# client defaults to 'india_govt' (current product); the corporate product fires
# these with client='tridel' (etc.) so each scrapes ONLY its own watchlist rows.

@app.task(name="tasks.social.collect_twitter", queue="social")
def collect_twitter(limit_per_target: int = 25, client: str = "india_govt") -> dict:
    return asyncio.run(_collect_platform("twitter", limit_per_target, client))


@app.task(name="tasks.social.collect_reddit", queue="social")
def collect_reddit(limit_per_target: int = 25, client: str = "india_govt") -> dict:
    return asyncio.run(_collect_platform("reddit", limit_per_target, client))


@app.task(name="tasks.social.collect_telegram", queue="social")
def collect_telegram(limit_per_target: int = 25, client: str = "india_govt") -> dict:
    return asyncio.run(_collect_platform("telegram", limit_per_target, client))


@app.task(name="tasks.social.collect_instagram", queue="social")
def collect_instagram(limit_per_target: int = 12, client: str = "india_govt") -> dict:
    return asyncio.run(_collect_platform("instagram", limit_per_target, client))


# ── Orchestration ─────────────────────────────────────────────────────────────

async def _collect_platform(platform: str, limit: int, client: str = "india_govt") -> dict:
    targets = await _active_targets(platform, client)
    if not targets:
        logger.info("social collect %s: no active watchlist targets", platform)
        return {"platform": platform, "targets": 0, "new_posts": 0}

    scraper = await _get_scraper(platform)
    if scraper is None:
        logger.warning("social collect %s: scraper unavailable (creds?)", platform)
        return {"platform": platform, "targets": len(targets), "new_posts": 0, "error": "no_scraper"}

    logger.info("social collect %s (client=%s): %d targets", platform, client, len(targets))
    total_new = 0
    for tgt in targets:
        try:
            posts = await _scrape_target(scraper, platform, tgt, limit)
        except Exception:
            logger.exception("social collect %s: scrape failed for %s", platform, tgt["target_value"])
            posts = []
        new_ids = await _land_posts(posts, tgt["id"])
        total_new += len(new_ids)
        for pid in new_ids:
            try:
                app.send_task("tasks.enrich_social_post", args=[pid], queue="social")
            except Exception:  # noqa: BLE001
                logger.debug("enrich dispatch failed for social post %s (drain will catch)", pid)
        await _advance_cursor(tgt["id"], posts)
    logger.info("social collect %s: %d targets, %d new posts", platform, len(targets), total_new)
    return {"platform": platform, "targets": len(targets), "new_posts": total_new}


async def _active_targets(platform: str, client: str) -> list[dict[str, Any]]:
    from sqlalchemy import text
    from backend.database import get_db
    async with get_db() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT id, target_type, target_value, last_seen_id, fetch_limit
                    FROM social_watchlist
                    WHERE client = :client AND platform = :p AND is_active = TRUE
                      AND (next_check_at IS NULL OR next_check_at <= NOW())
                    ORDER BY priority ASC, next_check_at ASC NULLS FIRST
                    LIMIT 200
                    """
                ),
                {"client": client, "p": platform},
            )
        ).fetchall()
    return [dict(r._mapping) for r in rows]


async def _get_scraper(platform: str):
    try:
        if platform == "twitter":
            from backend.collectors.twitter_scraper import TwitterScraper
            s = TwitterScraper(); await s.init(); return s
        if platform == "reddit":
            from backend.collectors.reddit_scraper import get_scraper
            return get_scraper()
        if platform == "telegram":
            from backend.collectors.telegram_scraper import get_scraper
            return get_scraper()
        if platform == "instagram":
            from backend.collectors.instagram_scraper import get_scraper
            return get_scraper()
    except Exception:
        logger.exception("social collect: cannot init %s scraper", platform)
    return None


async def _scrape_target(scraper, platform: str, tgt: dict, limit: int) -> list[dict]:
    ttype = tgt["target_type"]
    val = tgt["target_value"]
    n = tgt.get("fetch_limit") or limit

    if platform == "twitter":
        if ttype == "handle":
            return await scraper.user_tweets(val, limit=n)
        return await scraper.search(val, limit=n)          # keyword|hashtag
    if platform == "reddit":
        if ttype == "subreddit":
            return await scraper.subreddit(val, limit=n)
        return await scraper.search(val, limit=n)          # keyword|hashtag
    if platform == "telegram":
        min_id = int(tgt["last_seen_id"]) if (tgt.get("last_seen_id") or "").isdigit() else 0
        return await scraper.channel(val, limit=n, min_id=min_id)   # channel|handle
    if platform == "instagram":
        if ttype == "hashtag":
            return await scraper.hashtag(val, limit=n)     # gated until bearer login
        return await scraper.profile(val, limit=n)         # handle
    return []


# ── Landing: common-shape -> DB rows ──────────────────────────────────────────

def _clean_text(s: str) -> str:
    s = _MD.sub("", s or "")
    s = _EMOJI.sub("", s)
    return _WS.sub(" ", s).strip()


def _parse_dt(s: Any) -> datetime | None:
    """ISO string -> tz-aware datetime (asyncpg needs a datetime, not a str)."""
    if not s:
        return None
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


_IG_MEDIA = {1: "photo", 2: "video", 8: "carousel"}


def _engagement(post: dict) -> dict[str, Any]:
    raw = post.get("raw") or {}
    mt = raw.get("media_type")
    media_type = _IG_MEDIA.get(mt, str(mt)) if mt is not None else None
    return {
        "likes": post.get("likes"),
        "comments_count": post.get("comments"),
        "shares": post.get("shares"),
        "upvotes": post.get("upvotes"),
        "views": raw.get("views") or raw.get("view_count"),
        "upvote_ratio": raw.get("upvote_ratio"),
        "is_retweet": bool(raw.get("is_retweet", False)),
        "is_reply": bool(raw.get("is_reply", False)),
        "forwarded_from": raw.get("forwarded_from"),
        "lang": raw.get("lang"),
        "media_type": media_type,
    }


async def _land_posts(posts: list[dict], watchlist_id: int) -> list[int]:
    from sqlalchemy import text
    from backend.database import get_db

    new_ids: list[int] = []
    if not posts:
        return new_ids
    async with get_db() as db:
        for post in posts:
            if not isinstance(post, dict) or not post.get("platform_post_id"):
                continue
            author_id = await _upsert_author(db, post)
            community_id = await _upsert_community(db, post)
            eng = _engagement(post)
            row = (
                await db.execute(
                    text(
                        """
                        INSERT INTO social_posts
                          (platform, platform_post_id, author_id, community_id,
                           post_text, text_clean, post_url, posted_at,
                           posted_at_ist, likes, comments_count, shares, upvotes,
                           views, upvote_ratio, is_retweet, is_reply, forwarded_from,
                           lang, has_media, media_type, media_urls, watchlist_id, raw)
                        VALUES
                          (:platform, :ppid, :aid, :cid, :txt, :clean, :url,
                           :posted,
                           (:posted AT TIME ZONE 'Asia/Kolkata'),
                           :likes, :comments, :shares, :upvotes, :views, :ratio,
                           :rt, :rep, :fwd, :lang, :hasm, :mtype,
                           CAST(:murls AS JSONB), :wl, CAST(:raw AS JSONB))
                        ON CONFLICT (platform, platform_post_id) DO NOTHING
                        RETURNING id
                        """
                    ),
                    {
                        "platform": post["platform"],
                        "ppid": str(post["platform_post_id"]),
                        "aid": author_id, "cid": community_id,
                        "txt": (post.get("post_text") or "")[:8000],
                        "clean": _clean_text(post.get("post_text") or "")[:8000],
                        "url": post.get("post_url"),
                        "posted": _parse_dt(post.get("posted_at")),
                        "likes": eng["likes"], "comments": eng["comments_count"],
                        "shares": eng["shares"], "upvotes": eng["upvotes"],
                        "views": eng["views"], "ratio": eng["upvote_ratio"],
                        "rt": eng["is_retweet"], "rep": eng["is_reply"],
                        "fwd": eng["forwarded_from"], "lang": eng["lang"],
                        "hasm": bool(post.get("has_media")),
                        "mtype": eng["media_type"],
                        "murls": _json(post.get("media_urls") or []),
                        "wl": watchlist_id,
                        "raw": _json(post.get("raw") or {}),
                    },
                )
            ).fetchone()
            if row:
                new_ids.append(int(row.id))
        await db.commit()
    return new_ids


async def _upsert_author(db, post: dict) -> int | None:
    from sqlalchemy import text
    username = (post.get("author_username") or "").strip()
    if not username:
        return None
    raw = post.get("raw") or {}
    row = (
        await db.execute(
            text(
                """
                INSERT INTO social_authors (platform, platform_user_id, username, display_name, last_seen_at, raw)
                VALUES (:p, :uid, :un, :dn, NOW(), CAST(:raw AS JSONB))
                ON CONFLICT (platform, platform_user_id)
                DO UPDATE SET last_seen_at = NOW(),
                              display_name = COALESCE(EXCLUDED.display_name, social_authors.display_name)
                RETURNING id
                """
            ),
            {
                "p": post["platform"],
                "uid": str(raw.get("author_id") or username),
                "un": username[:200],
                "dn": (post.get("author_name") or None),
                "raw": _json({k: raw.get(k) for k in ("followers", "verified") if k in raw}),
            },
        )
    ).fetchone()
    return int(row.id) if row else None


async def _upsert_community(db, post: dict) -> int | None:
    from sqlalchemy import text
    platform = post["platform"]
    raw = post.get("raw") or {}
    if platform == "reddit":
        sub = (raw.get("subreddit") or "").strip()
        if not sub:
            return None
        uid, name, ctype = sub.lower(), "r/" + sub, "subreddit"
    elif platform == "telegram":
        handle = (post.get("author_username") or "").strip()
        if not handle:
            return None
        uid, name, ctype = handle.lower(), "@" + handle, "channel"
    else:
        return None  # twitter/instagram: the account IS the container
    row = (
        await db.execute(
            text(
                """
                INSERT INTO social_communities (platform, community_uid, name, ctype, last_seen_at)
                VALUES (:p, :uid, :nm, :ct, NOW())
                ON CONFLICT (platform, community_uid)
                DO UPDATE SET last_seen_at = NOW()
                RETURNING id
                """
            ),
            {"p": platform, "uid": uid, "nm": name, "ct": ctype},
        )
    ).fetchone()
    return int(row.id) if row else None


async def _advance_cursor(watchlist_id: int, posts: list[dict]) -> None:
    """Set last_seen_id to the newest platform_post_id; stamp last_run_at."""
    from sqlalchemy import text
    from backend.database import get_db
    newest = None
    for p in posts:
        pid = str(p.get("platform_post_id") or "")
        if pid.isdigit():
            newest = max(newest, int(pid)) if newest is not None else int(pid)
    async with get_db() as db:
        await db.execute(
            text(
                "UPDATE social_watchlist SET last_run_at = NOW(), "
                "last_seen_id = COALESCE(:ls, last_seen_id) WHERE id = :id"
            ),
            {"ls": (str(newest) if newest is not None else None), "id": watchlist_id},
        )
        await db.commit()


def _json(obj: Any) -> str:
    import json
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return "{}" if isinstance(obj, dict) else "[]"
