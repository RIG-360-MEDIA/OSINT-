"""Adapter: cheap-stack collectors -> the `social_posts` post-dict shape.

Emits the SAME dict shape as social_collector.collect_reddit_posts /
collect_telegram_channel, so the existing social_task can drop these in with no
schema change. Network errors are swallowed and logged (return []) to match the
pipeline's "one platform failure must not poison the task" contract.

Post dict shape (matches social_posts):
  platform, platform_post_id, author_username, post_text, post_url,
  upvotes, comment_count, posted_at (ISO8601 UTC)
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from html import unescape
from typing import Any, Optional

from .base import Egress
from .browser_fetch import fetch
from .instagram import IG_APP_ID

logger = logging.getLogger(__name__)

_STRIP_TAGS = re.compile(r"<[^>]+>")


def _iso(ts: Optional[float]) -> str:
    try:
        return datetime.fromtimestamp(float(ts or 0), tz=timezone.utc).isoformat()
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc).isoformat()


# ── Instagram (recent posts via web_profile_info edges) ─────────────────────

def _ig_auth_cookies() -> Optional[dict[str, str]]:
    """Authenticated IG cookies from INSTA_SESSIONID env. Cookie-free web_profile_info
    is rate-limited + login-gating (igweb_rollout); a session cookie lifts that.
    ds_user_id is the numeric prefix of the sessionid ('<uid>:...' or '<uid>%3A...')."""
    import os

    sid = os.getenv("INSTA_SESSIONID", "").strip()
    if not sid:
        return None
    uid = re.split(r"%3A|:", sid, maxsplit=1)[0]
    return {"sessionid": sid, "ds_user_id": uid}


_ig_id_cache: dict[str, str] = {}   # username -> numeric pk (stable; safe to cache)


def _ig_user_id(username: str, headers: dict, cookies: Optional[dict],
                egress: Egress) -> Optional[str]:
    """Resolve an IG handle to its numeric pk via web_profile_info (cached).

    web_profile_info still returns profile metadata (incl. `id`) reliably; it just
    no longer carries the timeline-media edges (IG stripped those). We use it only
    to get the pk, then read posts from the feed endpoint below."""
    if username in _ig_id_cache:
        return _ig_id_cache[username]
    r = fetch(
        "https://www.instagram.com/api/v1/users/web_profile_info/",
        params={"username": username},
        headers=headers, cookies=cookies, proxies=egress.proxies, timeout=20,
    )
    if not r.ok:
        logger.warning("IG id %s: http %s", username, r.status)
        return None
    uid = (r.json.get("data", {}).get("user", {}) or {}).get("id")
    if uid:
        _ig_id_cache[username] = str(uid)
    return str(uid) if uid else None


def collect_instagram_posts(
    username: str, *, egress: Optional[Egress] = None, limit: int = 12,
) -> list[dict[str, Any]]:
    """Recent public posts for an IG handle. Requires INSTA_SESSIONID (the feed
    endpoint is auth-gated). web_profile_info no longer returns timeline edges, so
    we resolve the pk from it, then read real posts from feed/user/<pk>."""
    egress = egress or Egress()
    username = username.lstrip("@")
    cookies = _ig_auth_cookies()
    headers = {"x-ig-app-id": IG_APP_ID, "Accept": "application/json"}
    try:
        uid = _ig_user_id(username, headers, cookies, egress)
        if not uid:
            return []
        r = fetch(
            f"https://www.instagram.com/api/v1/feed/user/{uid}/",
            params={"count": str(limit)},
            headers=headers, cookies=cookies, proxies=egress.proxies, timeout=20,
        )
        if not r.ok:
            logger.warning("IG feed %s: http %s", username, r.status)
            return []
        items = r.json.get("items", []) if isinstance(r.json, dict) else []
    except Exception as exc:
        logger.warning("IG posts failed %s: %s", username, exc)
        return []

    posts: list[dict[str, Any]] = []
    for it in items[:limit]:
        code = it.get("code")
        pid = code or it.get("pk") or it.get("id")
        if not pid:
            continue
        caption = ((it.get("caption") or {}) or {}).get("text", "") or ""
        posts.append({
            "platform": "instagram",
            "platform_post_id": str(pid),
            "author_username": (it.get("user", {}) or {}).get("username") or username,
            "post_text": caption.strip()[:3000],
            "post_url": f"https://www.instagram.com/p/{code or pid}/",
            "upvotes": int(it.get("like_count") or 0),
            "comment_count": int(it.get("comment_count") or 0),
            "posted_at": _iso(it.get("taken_at")),
        })
    return posts


# ── TikTok (recent videos via tikwm) ────────────────────────────────────────

def collect_tiktok_posts(
    username: str, *, egress: Optional[Egress] = None, limit: int = 15,
) -> list[dict[str, Any]]:
    """Recent videos for a TikTok handle via the tikwm free API."""
    egress = egress or Egress()
    username = username.lstrip("@")
    try:
        r = fetch("https://www.tikwm.com/api/user/posts",
                  params={"unique_id": username, "count": str(limit)},
                  proxies=egress.proxies, timeout=25)
        if not r.ok or str(r.json.get("code")) != "0":
            logger.warning("TikTok posts %s: code=%s", username,
                           (r.json.get("code") if r.ok else r.status))
            return []
        videos = r.json.get("data", {}).get("videos", []) or []
    except Exception as exc:
        logger.warning("TikTok posts failed %s: %s", username, exc)
        return []

    posts: list[dict[str, Any]] = []
    for v in videos[:limit]:
        vid = v.get("video_id") or v.get("id")
        if not vid:
            continue
        posts.append({
            "platform": "tiktok",
            "platform_post_id": str(vid),
            "author_username": username,
            "post_text": (v.get("title") or "").strip()[:3000],
            "post_url": f"https://www.tiktok.com/@{username}/video/{vid}",
            "upvotes": int(v.get("digg_count") or 0),
            "comment_count": int(v.get("comment_count") or 0),
            "posted_at": _iso(v.get("create_time")),
        })
    return posts


# ── Telegram (public channel via t.me/s — NO bot token needed) ──────────────

_TG_MSG_RE = re.compile(
    r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.DOTALL)
_TG_ID_RE = re.compile(r'data-post="([^"]+)"')
_TG_TIME_RE = re.compile(r'<time[^>]*datetime="([^"]+)"')


def collect_telegram_web(
    channel: str, *, egress: Optional[Egress] = None, limit: int = 20,
) -> list[dict[str, Any]]:
    """Public channel posts via t.me/s preview — no bot token, no membership.

    A free upgrade over the bot-API path (which only sees channels the bot joined).
    """
    egress = egress or Egress()
    channel = channel.lstrip("@")
    try:
        r = fetch(f"https://t.me/s/{channel}", proxies=egress.proxies, timeout=20)
        if not r.ok:
            logger.warning("Telegram web %s: http %s", channel, r.status)
            return []
        text = r.text
    except Exception as exc:
        logger.warning("Telegram web failed %s: %s", channel, exc)
        return []

    ids = _TG_ID_RE.findall(text)
    bodies = _TG_MSG_RE.findall(text)
    times = _TG_TIME_RE.findall(text)
    posts: list[dict[str, Any]] = []
    for i, body in enumerate(bodies[:limit]):
        clean = unescape(_STRIP_TAGS.sub(" ", body)).strip()
        if not clean:
            continue
        pid = ids[i] if i < len(ids) else f"{channel}/{i}"
        posts.append({
            "platform": "telegram",
            "platform_post_id": pid,
            "author_username": channel,
            "post_text": clean[:3000],
            "post_url": f"https://t.me/{pid}",
            "upvotes": 0,
            "comment_count": 0,
            "posted_at": (times[i] if i < len(times) else _iso(0)),
        })
    return posts
