"""
Reddit scraper via logged-in session cookie + curl_cffi (no API key, no OAuth app).

Reddit blocks the anonymous public .json API behind a Cloudflare JS challenge
(403 from all IPs, datacenter and residential alike). The free, durable bypass
— proven working from both residential and the Hetzner datacenter IP — is:

    reddit_session cookie (from a logged-in browser)
        + curl_cffi with impersonate="chrome" (real Chrome TLS/JA3 fingerprint)

This mirrors the Twitter approach: reuse the browser's authenticated session
rather than fighting the bot wall. The reddit_session JWT lasts ~6 months.

Raw collection only — no extraction, no sentiment, no entity matching.
Returns the common social post shape defined in social_scraper.py.

Setup (one-time):
    1. Log into reddit.com in a browser.
    2. F12 -> Application -> Cookies -> https://www.reddit.com
    3. Copy the value of `reddit_session`.

    export REDDIT_SESSION=<reddit_session cookie value>

    The cookie is account-bound, not IP-bound, so the same value works from
    any host. Refresh it (repeat steps) roughly every 6 months, or if calls
    start returning 403 / login redirects.

Usage:
    scraper = RedditScraper()
    posts = await scraper.subreddit("india", limit=25)
    posts = await scraper.search("Modi", limit=25, time_filter="day")
    posts = await scraper.post_comments("india", "abc123", limit=25)
"""
from __future__ import annotations

import base64
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_SESSION = os.getenv("REDDIT_SESSION", "")
_IMPERSONATE = os.getenv("REDDIT_IMPERSONATE", "chrome")


# ── session-token introspection ───────────────────────────────────────────────

def session_expiry(session_token: str = _SESSION) -> datetime | None:
    """Decode the reddit_session JWT and return its expiry as a UTC datetime.

    Returns None if the token can't be parsed. Used to warn before the
    ~6-month cookie lapses; does NOT verify the signature (read-only).
    """
    try:
        payload_b64 = session_token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)  # pad base64
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        exp = payload.get("exp")
        return datetime.fromtimestamp(float(exp), tz=timezone.utc) if exp else None
    except Exception:
        return None


# ── normaliser ────────────────────────────────────────────────────────────────

def _child_to_post(child: dict[str, Any]) -> dict[str, Any] | None:
    data = child.get("data") or {}
    post_id = data.get("id")
    if not post_id:
        return None

    title = (data.get("title") or "").strip()
    selftext = (data.get("selftext") or "").strip()
    if selftext in ("[removed]", "[deleted]"):
        selftext = ""
    text = (title + (" — " + selftext if selftext else "")).strip()
    if not text:
        return None

    media_urls: list[str] = []
    dest = data.get("url_overridden_by_dest", "")
    if dest and (
        dest.startswith("https://i.")
        or dest.endswith((".jpg", ".png", ".gif", ".mp4", ".gifv"))
    ):
        media_urls.append(dest)
    if data.get("is_gallery") and data.get("gallery_data"):
        for item in (data["gallery_data"].get("items") or []):
            mid = item.get("media_id")
            if mid:
                media_urls.append(f"https://i.redd.it/{mid}.jpg")
    # Reddit-hosted video: the mp4 fallback lives under (secure_)media.reddit_video.
    reddit_video = (
        (data.get("secure_media") or data.get("media") or {}) or {}
    ).get("reddit_video") or {}
    fallback = reddit_video.get("fallback_url")
    if fallback:
        media_urls.append(fallback)

    return {
        "platform": "reddit",
        "platform_post_id": post_id,
        "author_username": data.get("author") or "",
        "author_name": None,
        "post_text": text[:4000],
        "post_url": "https://reddit.com" + (data.get("permalink") or ""),
        "posted_at": datetime.fromtimestamp(
            float(data.get("created_utc") or 0), tz=timezone.utc
        ).isoformat(),
        "likes": None,
        "comments": int(data.get("num_comments") or 0),
        "shares": None,
        "upvotes": int(data.get("score") or 0),
        "has_media": bool(media_urls),
        "media_urls": media_urls,
        "raw": {
            "subreddit": data.get("subreddit", ""),
            "flair": data.get("link_flair_text"),
            "is_self": data.get("is_self"),
            "is_video": data.get("is_video"),
            "upvote_ratio": data.get("upvote_ratio"),
            "awards": data.get("total_awards_received"),
            "crossposts": data.get("num_crossposts"),
            # OSINT context: the shared link, community size, stable author id, flags.
            "external_url": data.get("url"),
            "domain": data.get("domain"),
            "over_18": data.get("over_18"),
            "subreddit_subscribers": data.get("subreddit_subscribers"),
            "author_fullname": data.get("author_fullname"),
            "edited": data.get("edited"),
        },
    }


# ── scraper class ─────────────────────────────────────────────────────────────

class RedditScraper:
    """
    Async Reddit scraper using a logged-in session cookie + Chrome TLS
    impersonation. No init() needed — call methods directly.
    """

    def __init__(
        self,
        session_token: str = _SESSION,
        impersonate: str = _IMPERSONATE,
    ) -> None:
        self._session_token = session_token
        self._impersonate = impersonate
        self._warned_expiry = False

    def _check(self) -> None:
        if not self._session_token:
            raise RuntimeError(
                "Set REDDIT_SESSION env var (reddit_session cookie from a "
                "logged-in browser)."
            )
        if not self._warned_expiry:
            exp = session_expiry(self._session_token)
            if exp is not None:
                days = (exp - datetime.now(timezone.utc)).days
                if days < 14:
                    logger.warning(
                        "Reddit session cookie expires in %d days (%s) — refresh soon.",
                        days, exp.date(),
                    )
            self._warned_expiry = True

    async def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any] | list[Any] | None:
        from curl_cffi.requests import AsyncSession

        params.setdefault("raw_json", 1)
        async with AsyncSession() as session:
            r = await session.get(
                url,
                params=params,
                cookies={"reddit_session": self._session_token},
                impersonate=self._impersonate,
                timeout=25,
            )
        if r.status_code == 403:
            logger.error(
                "Reddit 403 on %s — session cookie likely expired or invalid.", url
            )
            return None
        if r.status_code != 200:
            logger.warning("Reddit %s -> HTTP %s", url, r.status_code)
            return None
        try:
            return r.json()
        except Exception:
            logger.warning("Reddit %s -> non-JSON response", url)
            return None

    def _parse_listing(self, data: Any) -> list[dict[str, Any]]:
        if not isinstance(data, dict):
            return []
        children = (data.get("data") or {}).get("children") or []
        return [p for p in (_child_to_post(c) for c in children) if p]

    # ── public methods ────────────────────────────────────────────────────────

    async def subreddit(
        self,
        name: str,
        *,
        limit: int = 25,
        category: str = "new",
        after: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch posts from a subreddit.
        category: 'new' | 'hot' | 'top' | 'rising'
        after: fullname cursor for pagination (e.g. 't3_abc123')
        """
        self._check()
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if after:
            params["after"] = after
        try:
            data = await self._get(
                f"https://www.reddit.com/r/{name}/{category}.json", params
            )
            return self._parse_listing(data)
        except Exception:
            logger.exception("Reddit subreddit failed (r/%s)", name)
            return []

    async def search(
        self,
        query: str,
        *,
        subreddit: str | None = None,
        limit: int = 25,
        sort: str = "new",
        time_filter: str = "day",
    ) -> list[dict[str, Any]]:
        """
        Search Reddit posts.
        subreddit: restrict to a specific subreddit (None = all of Reddit)
        sort: 'new' | 'hot' | 'top' | 'relevance' | 'comments'
        time_filter: 'hour' | 'day' | 'week' | 'month' | 'year' | 'all'
        """
        self._check()
        if subreddit:
            url = f"https://www.reddit.com/r/{subreddit}/search.json"
        else:
            url = "https://www.reddit.com/search.json"
        params: dict[str, Any] = {
            "q": query,
            "sort": sort,
            "t": time_filter,
            "limit": min(limit, 100),
        }
        if subreddit:
            params["restrict_sr"] = "true"
        try:
            data = await self._get(url, params)
            return self._parse_listing(data)
        except Exception:
            logger.exception("Reddit search failed (q=%r)", query)
            return []

    async def post_comments(
        self,
        subreddit: str,
        post_id: str,
        *,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """
        Fetch top-level comments on a post.
        Returns the common post shape with post_text = comment body.
        """
        self._check()
        try:
            data = await self._get(
                f"https://www.reddit.com/r/{subreddit}/comments/{post_id}.json",
                {"limit": min(limit, 100), "depth": 1},
            )
            # comments endpoint returns [post_listing, comments_listing]
            if not isinstance(data, list) or len(data) < 2:
                return []
            out: list[dict[str, Any]] = []
            for child in (data[1].get("data") or {}).get("children") or []:
                d = child.get("data") or {}
                body = (d.get("body") or "").strip()
                if not body or body in ("[removed]", "[deleted]"):
                    continue
                out.append({
                    "platform": "reddit",
                    "platform_post_id": d.get("id", ""),
                    "author_username": d.get("author") or "",
                    "author_name": None,
                    "post_text": body[:4000],
                    "post_url": f"https://reddit.com/r/{subreddit}/comments/{post_id}/_/{d.get('id','')}",
                    "posted_at": datetime.fromtimestamp(
                        float(d.get("created_utc") or 0), tz=timezone.utc
                    ).isoformat(),
                    "likes": None,
                    "comments": None,
                    "shares": None,
                    "upvotes": int(d.get("score") or 0),
                    "has_media": False,
                    "media_urls": [],
                    "raw": {"parent_post_id": post_id, "subreddit": subreddit},
                })
            return out
        except Exception:
            logger.exception("Reddit post_comments failed (%s/%s)", subreddit, post_id)
            return []


# ── module-level singleton ────────────────────────────────────────────────────

_scraper: RedditScraper | None = None


def get_scraper() -> RedditScraper:
    global _scraper
    if _scraper is None:
        _scraper = RedditScraper()
    return _scraper


# ── CLI smoke-test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio

    async def _smoke():
        s = RedditScraper()
        exp = session_expiry()
        print(f"session expires: {exp}")

        print("\n--- r/india (new, 5) ---")
        for p in await s.subreddit("india", limit=5):
            line = f"  [{p['upvotes']}up {p['comments']}c] {p['post_text'][:70]}"
            print(line.encode("ascii", "replace").decode())

        print("\n--- search: Modi (5) ---")
        for p in await s.search("Modi", limit=5, time_filter="day"):
            line = f"  r/{p['raw']['subreddit']}: {p['post_text'][:60]}"
            print(line.encode("ascii", "replace").decode())

    asyncio.run(_smoke())
