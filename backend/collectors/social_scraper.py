"""
Social media scrapers — raw collection only.

NO extraction, NO sentiment, NO entity matching.
Every function returns a list of post dicts in the common shape below.
Route collected posts through the substrate pipeline like articles.

Common post shape:
    platform          str
    platform_post_id  str
    author_username   str
    author_name       str | None
    post_text         str          (capped at 4000 chars)
    post_url          str
    posted_at         str          (ISO 8601 UTC)
    likes             int | None
    comments          int | None
    shares            int | None
    upvotes           int | None   (Reddit only)
    has_media         bool
    media_urls        list[str]
    raw               dict         (original platform payload, kept for forward-compat)

Dependencies (install what you need):
    pip install telethon            # Telegram
    pip install ntscraper           # Twitter via Nitter
    pip install instaloader         # Instagram
"""
from __future__ import annotations

import logging
import math
import urllib.parse
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ── common shape ─────────────────────────────────────────────────────────────

def _post(
    *,
    platform: str,
    platform_post_id: str,
    author_username: str,
    author_name: str | None = None,
    post_text: str,
    post_url: str,
    posted_at: str,
    likes: int | None = None,
    comments: int | None = None,
    shares: int | None = None,
    upvotes: int | None = None,
    has_media: bool = False,
    media_urls: list[str] | None = None,
    raw: dict | None = None,
) -> dict[str, Any]:
    return {
        "platform": platform,
        "platform_post_id": platform_post_id,
        "author_username": author_username,
        "author_name": author_name,
        "post_text": post_text[:4000],
        "post_url": post_url,
        "posted_at": posted_at,
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "upvotes": upvotes,
        "has_media": has_media,
        "media_urls": media_urls or [],
        "raw": raw or {},
    }


# ── Reddit ────────────────────────────────────────────────────────────────────
# Public JSON API — no credentials needed, just a User-Agent.
# Subreddit feed: reddit.com/r/{sub}/new.json
# Keyword search:  reddit.com/search.json?q=...

_REDDIT_UA = "RIGSurveillance/1.0 Intelligence Platform (contact: admin)"
_reddit_429_streak: int = 0
_reddit_429_total: int = 0
_REDDIT_429_ESCALATE_AFTER = 3


def reddit_throttle_metrics() -> dict[str, int]:
    return {
        "streak": _reddit_429_streak,
        "total": _reddit_429_total,
        "escalate_after": _REDDIT_429_ESCALATE_AFTER,
    }


def _reddit_child_to_post(child: dict[str, Any]) -> dict[str, Any] | None:
    data = child.get("data") or {}
    post_id = data.get("id")
    if not post_id:
        return None
    title = (data.get("title") or "").strip()
    selftext = (data.get("selftext") or "").strip()
    text = (title + (" — " + selftext if selftext else "")).strip()
    if not text:
        return None
    media_urls: list[str] = []
    dest = data.get("url_overridden_by_dest", "")
    if dest.startswith("https://i.") or dest.endswith((".jpg", ".png", ".gif", ".mp4")):
        media_urls.append(dest)
    return _post(
        platform="reddit",
        platform_post_id=post_id,
        author_username=data.get("author") or "",
        post_text=text,
        post_url="https://reddit.com" + (data.get("permalink") or ""),
        posted_at=datetime.fromtimestamp(
            float(data.get("created_utc") or 0), tz=timezone.utc
        ).isoformat(),
        upvotes=int(data.get("score") or 0),
        comments=int(data.get("num_comments") or 0),
        has_media=bool(media_urls),
        media_urls=media_urls,
        raw=data,
    )


async def _reddit_fetch(url: str) -> list[dict[str, Any]]:
    global _reddit_429_streak, _reddit_429_total
    try:
        async with httpx.AsyncClient(
            timeout=30, headers={"User-Agent": _REDDIT_UA}
        ) as client:
            r = await client.get(url)
        if r.status_code == 429:
            _reddit_429_streak += 1
            _reddit_429_total += 1
            log_fn = (
                logger.error
                if _reddit_429_streak >= _REDDIT_429_ESCALATE_AFTER
                else logger.warning
            )
            log_fn(
                "Reddit 429 streak=%s total=%s url=%s",
                _reddit_429_streak, _reddit_429_total, url,
            )
            return []
        if r.status_code != 200:
            logger.warning("Reddit %s -> %s", url, r.status_code)
            return []
        _reddit_429_streak = 0
        children = (r.json().get("data") or {}).get("children") or []
        return [p for p in (_reddit_child_to_post(c) for c in children) if p]
    except Exception as exc:
        logger.warning("Reddit fetch failed %s: %s", url, exc)
        return []


async def collect_reddit_subreddit(
    subreddit: str, *, limit: int = 25, category: str = "new"
) -> list[dict[str, Any]]:
    """Fetch posts from a subreddit via the public JSON API."""
    url = (
        f"https://www.reddit.com/r/{subreddit}/{category}.json"
        f"?limit={limit}"
    )
    return await _reddit_fetch(url)


async def search_reddit(
    keyword: str, *, limit: int = 25
) -> list[dict[str, Any]]:
    """Search Reddit for a keyword via the public JSON API."""
    q = urllib.parse.quote(keyword)
    url = f"https://www.reddit.com/search.json?q={q}&sort=new&limit={limit}"
    return await _reddit_fetch(url)


# ── Telegram (Telethon user session) ─────────────────────────────────────────
# Uses Telethon MTProto user session — NOT the Bot API.
#
# Why not Bot API getUpdates (the old approach):
#   - getUpdates is a forward-only polling stream; it can't fetch history
#   - the bot must be added to every private channel manually
#   - it silently misses posts if the poll interval is too long
#   Telethon user session reads any PUBLIC channel's full history directly.
#
# Required env vars: TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION_STRING
# Generate session once: python scripts/generate_telegram_session.py
#
# min_id: only fetch messages newer than this ID (set to last seen ID for
# incremental collection — avoids re-processing old posts on every run).

async def collect_telegram_channel(
    channel_username: str,
    *,
    api_id: int,
    api_hash: str,
    session_string: str,
    limit: int = 50,
    min_id: int = 0,
) -> list[dict[str, Any]]:
    """Fetch recent posts from a public Telegram channel via Telethon."""
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
    except ImportError:
        logger.error("telethon not installed — pip install telethon")
        return []

    posts: list[dict[str, Any]] = []
    async with TelegramClient(
        StringSession(session_string), api_id, api_hash
    ) as client:
        try:
            channel = await client.get_entity(channel_username)
        except Exception as exc:
            logger.warning(
                "Telegram: can't resolve entity %s: %s", channel_username, exc
            )
            return []

        async for msg in client.iter_messages(
            channel, limit=limit, min_id=min_id
        ):
            text = (msg.text or msg.caption or "").strip()
            if not text:
                continue

            media_urls: list[str] = []
            if isinstance(msg.media, (MessageMediaPhoto, MessageMediaDocument)):
                # file_id placeholder — actual download deferred to storage layer
                media_urls.append(f"tg://file/{msg.id}")

            forwarded_from = None
            if msg.forward and msg.forward.chat:
                chat = msg.forward.chat
                forwarded_from = getattr(chat, "title", None) or getattr(
                    chat, "username", None
                )

            posts.append(
                _post(
                    platform="telegram",
                    platform_post_id=str(msg.id),
                    author_username=channel_username.lstrip("@"),
                    author_name=getattr(channel, "title", None),
                    post_text=text,
                    post_url=(
                        f"https://t.me/{channel_username.lstrip('@')}/{msg.id}"
                    ),
                    posted_at=msg.date.astimezone(timezone.utc).isoformat(),
                    shares=msg.forwards or None,
                    has_media=bool(msg.media),
                    media_urls=media_urls,
                    raw={
                        "id": msg.id,
                        "views": msg.views,
                        "forwards": msg.forwards,
                        "replies": (
                            msg.replies.replies if msg.replies else None
                        ),
                        "forwarded_from": forwarded_from,
                        "grouped_id": msg.grouped_id,
                    },
                )
            )
    return posts


# ── Twitter (Nitter + syndication API) ───────────────────────────────────────
# Nitter: open-source Twitter frontend — many public instances, no auth needed.
# ntscraper wraps Nitter's HTML into clean dicts including basic engagement counts.
#
# Syndication API: Twitter's OWN public embed endpoint. Returns exact
# favorite_count / retweet_count / conversation_count for any public tweet ID.
# Used by the official tweet embed widget on news sites — Twitter can't kill it
# without breaking thousands of publisher embeds.
#
# Flow: Nitter search/profile → tweet list + rough counts → syndication API
# enriches each tweet with exact metrics.
#
# pip install ntscraper

_NITTER_INSTANCES = [
    "https://nitter.poast.org",
    "https://nitter.net",
    "https://nitter.it",
]

_SYNDICATION_BASE = "https://cdn.syndication.twimg.com/tweet-result"


def _syndication_token(tweet_id: str) -> str:
    """Compute the token Twitter's embed widget sends with each request.

    Reverse-engineered from Twitter's embed JS:
        ((Number(id) / 1e15) * Math.PI).toString(36).replace(/(0+|\\.)/g, '')
    """
    val = int((int(tweet_id) / 1e15) * math.pi)
    if val == 0:
        return "0"
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    result = ""
    while val:
        result = digits[val % 36] + result
        val //= 36
    return result


async def _enrich_tweet_metrics(
    tweet_id: str, client: httpx.AsyncClient
) -> dict[str, int | None]:
    """Fetch exact engagement counts from Twitter's syndication API."""
    try:
        r = await client.get(
            _SYNDICATION_BASE,
            params={"id": tweet_id, "token": _syndication_token(tweet_id), "lang": "en"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        if r.status_code != 200:
            return {"likes": None, "comments": None, "shares": None}
        d = r.json()
        return {
            "likes": d.get("favorite_count"),
            "comments": d.get("conversation_count"),
            "shares": d.get("retweet_count"),
        }
    except Exception:
        return {"likes": None, "comments": None, "shares": None}


def _nitter_tweet_to_post(tweet: dict[str, Any]) -> dict[str, Any] | None:
    link = (tweet.get("link") or "").rstrip("/")
    tweet_id = link.split("/")[-1]
    if not tweet_id or not tweet_id.isdigit():
        return None
    text = tweet.get("text") or ""
    if not text:
        return None
    user = tweet.get("user") or {}
    username = user.get("username") or ""
    stats = tweet.get("stats") or {}
    media_urls = [
        m["url"] for m in (tweet.get("pictures") or []) if m.get("url")
    ]
    epoch = tweet.get("date_epoch")
    posted_at = (
        datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()
        if epoch
        else (tweet.get("date") or "")
    )
    return _post(
        platform="twitter",
        platform_post_id=tweet_id,
        author_username=username,
        author_name=user.get("name"),
        post_text=text,
        post_url=f"https://x.com/{username}/status/{tweet_id}",
        posted_at=posted_at,
        likes=stats.get("likes"),
        comments=stats.get("comments"),
        shares=stats.get("retweets"),
        has_media=bool(media_urls),
        media_urls=media_urls,
        raw=tweet,
    )


async def _nitter_collect(
    fn_name: str,
    fn_kwargs: dict[str, Any],
    *,
    fetch_metrics: bool,
) -> list[dict[str, Any]]:
    try:
        from ntscraper import Nitter
    except ImportError:
        logger.error("ntscraper not installed — pip install ntscraper")
        return []

    scraper = Nitter(log_level=0, skip_instance_check=True)
    try:
        fn = getattr(scraper, fn_name)
        result = fn(**fn_kwargs, instance=_NITTER_INSTANCES[0]) or {}
        tweets_raw = result.get("tweets") or []
    except Exception as exc:
        logger.warning("Nitter %s failed: %s", fn_name, exc)
        # try next instance on failure
        try:
            result = fn(**fn_kwargs, instance=_NITTER_INSTANCES[1]) or {}
            tweets_raw = result.get("tweets") or []
        except Exception as exc2:
            logger.warning("Nitter fallback also failed: %s", exc2)
            return []

    posts = [p for p in (_nitter_tweet_to_post(t) for t in tweets_raw) if p]

    if fetch_metrics and posts:
        async with httpx.AsyncClient() as client:
            for post in posts:
                # Nitter sometimes has likes=None — fill from syndication
                if post["likes"] is None:
                    metrics = await _enrich_tweet_metrics(
                        post["platform_post_id"], client
                    )
                    post.update(metrics)

    return posts


async def search_twitter(
    keyword: str, *, limit: int = 40, fetch_metrics: bool = True
) -> list[dict[str, Any]]:
    """Search Twitter for a keyword via Nitter. Enriches likes/RT with syndication API."""
    return await _nitter_collect(
        "get_tweets",
        {"term": keyword, "mode": "search", "number": limit},
        fetch_metrics=fetch_metrics,
    )


async def collect_twitter_account(
    username: str, *, limit: int = 40, fetch_metrics: bool = True
) -> list[dict[str, Any]]:
    """Fetch recent tweets from a specific account via Nitter."""
    return await _nitter_collect(
        "get_profile_tweets",
        {"profile": username, "number": limit},
        fetch_metrics=fetch_metrics,
    )


# ── Instagram (instaloader) ───────────────────────────────────────────────────
# Requires a saved session file per account (one-time interactive login).
#
# Create a session:
#   python -c "
#   import instaloader
#   L = instaloader.Instaloader()
#   L.interactive_login('YOUR_USERNAME')
#   L.save_session_to_file()
#   "
#   Session saved to ~/.config/instaloader/session-YOUR_USERNAME
#
# Ban avoidance strategy:
#   - Prefer hashtag collection over profile sweeps (lower detection risk)
#   - Rotate between multiple session files (3-5 accounts)
#   - Instaloader handles per-request sleep automatically at ~3s/request
#   - Keep limit <= 50 per run per account; schedule runs hourly
#   - session_file: path to a saved .session file (or None to use default path)
#
# Note: instaloader is synchronous. Run in a thread if calling from async code:
#   import asyncio
#   posts = await asyncio.get_event_loop().run_in_executor(
#       None, collect_instagram_hashtag, "BJP", session_file="...", username="..."
#   )
#
# pip install instaloader

def _insta_post_to_dict(post: Any) -> dict[str, Any]:
    media_urls: list[str] = []
    try:
        if post.typename == "GraphSidecar":
            for node in post.get_sidecar_nodes():
                media_urls.append(
                    node.video_url if node.is_video else node.display_url
                )
        elif post.is_video:
            media_urls.append(post.video_url)
        else:
            media_urls.append(post.url)
    except Exception:
        pass

    return _post(
        platform="instagram",
        platform_post_id=str(post.mediaid),
        author_username=post.owner_username,
        author_name=(
            post.owner_profile.full_name
            if post.owner_profile
            else None
        ),
        post_text=(post.caption or "").strip(),
        post_url=f"https://www.instagram.com/p/{post.shortcode}/",
        posted_at=post.date_utc.replace(tzinfo=timezone.utc).isoformat(),
        likes=post.likes,
        comments=post.comments,
        has_media=bool(media_urls),
        media_urls=media_urls,
        raw={
            "shortcode": post.shortcode,
            "typename": post.typename,
            "is_video": post.is_video,
            "video_view_count": post.video_view_count if post.is_video else None,
            "location": str(post.location) if post.location else None,
            "hashtags": list(post.caption_hashtags or []),
        },
    )


def _insta_loader(username: str, session_file: str | None) -> Any:
    import instaloader
    L = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        quiet=True,
    )
    try:
        L.load_session_from_file(username, session_file)
    except Exception as exc:
        raise RuntimeError(
            f"Instagram: can't load session for {username!r}: {exc}"
        ) from exc
    return L


def collect_instagram_hashtag(
    hashtag: str,
    *,
    username: str,
    session_file: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Collect recent posts for a hashtag. Preferred over profile sweeps — lower ban risk."""
    try:
        import instaloader
        L = _insta_loader(username, session_file)
    except Exception as exc:
        logger.error("Instagram session load failed: %s", exc)
        return []

    posts: list[dict[str, Any]] = []
    try:
        tag = instaloader.Hashtag.from_name(L.context, hashtag.lstrip("#"))
        for i, post in enumerate(tag.get_posts()):
            if i >= limit:
                break
            try:
                posts.append(_insta_post_to_dict(post))
            except Exception as exc:
                logger.debug("Instagram post skip: %s", exc)
    except Exception as exc:
        logger.warning("Instagram #%s failed: %s", hashtag, exc)

    return posts


def collect_instagram_account(
    account_username: str,
    *,
    username: str,
    session_file: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Collect recent posts from a specific Instagram account."""
    try:
        import instaloader
        L = _insta_loader(username, session_file)
    except Exception as exc:
        logger.error("Instagram session load failed: %s", exc)
        return []

    posts: list[dict[str, Any]] = []
    try:
        profile = instaloader.Profile.from_username(
            L.context, account_username
        )
        for i, post in enumerate(profile.get_posts()):
            if i >= limit:
                break
            try:
                posts.append(_insta_post_to_dict(post))
            except Exception as exc:
                logger.debug("Instagram post skip: %s", exc)
    except Exception as exc:
        logger.warning("Instagram @%s failed: %s", account_username, exc)

    return posts
