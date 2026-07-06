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

def collect_instagram_posts(
    username: str, *, egress: Optional[Egress] = None, limit: int = 12,
) -> list[dict[str, Any]]:
    """Recent public posts for an IG handle. Datacenter IP may need residential egress."""
    egress = egress or Egress()
    username = username.lstrip("@")
    try:
        r = fetch(
            "https://www.instagram.com/api/v1/users/web_profile_info/",
            params={"username": username},
            headers={"x-ig-app-id": IG_APP_ID, "Accept": "application/json"},
            proxies=egress.proxies, timeout=20,
        )
        if not r.ok:
            logger.warning("IG posts %s: http %s", username, r.status)
            return []
        user = r.json.get("data", {}).get("user", {}) or {}
        edges = user.get("edge_owner_to_timeline_media", {}).get("edges", []) or []
    except Exception as exc:
        logger.warning("IG posts failed %s: %s", username, exc)
        return []

    posts: list[dict[str, Any]] = []
    for edge in edges[:limit]:
        node = edge.get("node", {}) or {}
        pid = node.get("shortcode") or node.get("id")
        if not pid:
            continue
        cap_edges = node.get("edge_media_to_caption", {}).get("edges", []) or []
        caption = cap_edges[0]["node"]["text"] if cap_edges else ""
        posts.append({
            "platform": "instagram",
            "platform_post_id": pid,
            "author_username": username,
            "post_text": (caption or "").strip()[:3000],
            "post_url": f"https://www.instagram.com/p/{node.get('shortcode', pid)}/",
            "upvotes": int(node.get("edge_liked_by", {}).get("count") or
                           node.get("edge_media_preview_like", {}).get("count") or 0),
            "comment_count": int(node.get("edge_media_to_comment", {}).get("count") or 0),
            "posted_at": _iso(node.get("taken_at_timestamp")),
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
