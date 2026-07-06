"""On-demand social — keyword-driven TikTok + WeChat, fetched live per query.

Implements the Phase-3 architecture (social = keyword-driven on-demand, not
store-everything) for the two platforms the standing pipeline doesn't cover.
Isolated in osint-backend (httpx only) — does NOT touch the live rig-backend
social pipeline. Results are fetched fresh on each search; persistence-from-use
can be layered on later.

- TikTok: tikwm keyword feed search (free, no key).
- WeChat: DuckDuckGo site-dork discovery of public Official-Account articles
  (mp.weixin.qq.com) — no China IP needed. Public accounts only.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote

import httpx

_UA = {"User-Agent": "Mozilla/5.0 (compatible; RIG-OSINT/1.0)"}
_DDG_LINK = re.compile(r'class="result__a"[^>]*href="([^"]*uddg=[^"]*)"[^>]*>(.*?)</a>', re.DOTALL)
_TAGS = re.compile(r"<[^>]+>")


def _iso(ts: Any) -> str | None:
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    except Exception:
        return None


async def tiktok_search(q: str, limit: int = 10) -> list[dict[str, Any]]:
    """Keyword search TikTok via tikwm; returns normalized post dicts."""
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get("https://www.tikwm.com/api/feed/search",
                            params={"keywords": q, "count": limit})
            if r.status_code != 200 or str(r.json().get("code")) != "0":
                return []
            vids = r.json().get("data", {}).get("videos", []) or []
    except Exception:
        return []
    out = []
    for v in vids[:limit]:
        vid = v.get("video_id") or v.get("aweme_id")
        author = (v.get("author") or {}).get("unique_id") or ""
        if not vid:
            continue
        out.append({
            "platform": "tiktok", "platform_post_id": str(vid),
            "author_username": author, "post_text": (v.get("title") or "").strip()[:500],
            "post_url": f"https://www.tiktok.com/@{author}/video/{vid}",
            "likes": v.get("digg_count"), "views": v.get("play_count"),
            "comments_count": v.get("comment_count"),
            "posted_at": _iso(v.get("create_time")),
        })
    return out


async def wechat_search(q: str, limit: int = 10) -> list[dict[str, Any]]:
    """Discover public WeChat Official-Account articles via a DDG site-dork."""
    try:
        async with httpx.AsyncClient(timeout=20, headers=_UA, follow_redirects=True) as c:
            r = await c.get("https://html.duckduckgo.com/html/",
                            params={"q": f"site:mp.weixin.qq.com {q}"})
            html = r.text if r.status_code == 200 else ""
    except Exception:
        return []
    out, seen = [], set()
    for href, title in _DDG_LINK.findall(html):
        m = re.search(r"uddg=([^&\"]+)", href)
        if not m:
            continue
        url = unquote(m.group(1))
        if "mp.weixin.qq.com/s" not in url or url in seen:
            continue
        seen.add(url)
        out.append({
            "platform": "wechat", "platform_post_id": url.rsplit("/", 1)[-1][:40],
            "author_username": None,
            "post_text": _TAGS.sub("", title).strip()[:300],
            "post_url": url, "posted_at": None,
        })
        if len(out) >= limit:
            break
    return out


async def social_live(q: str, limit: int = 10) -> dict[str, Any]:
    """Keyword-driven on-demand social across TikTok + WeChat (public)."""
    q = (q or "").strip()
    if not q:
        return {"query": q, "tiktok": [], "wechat": [], "summary": {}}
    tiktok = await tiktok_search(q, limit)
    wechat = await wechat_search(q, limit)
    return {
        "query": q,
        "tiktok": tiktok,
        "wechat": wechat,
        "summary": {
            "tiktok_results": len(tiktok),
            "wechat_results": len(wechat),
            "total": len(tiktok) + len(wechat),
            "note": "on-demand, keyword-driven; TikTok=tikwm, WeChat=public Official Accounts",
        },
    }
