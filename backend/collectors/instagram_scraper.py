"""
Instagram scraper — dual-mode async client (relay or direct).

Raw collection only — no extraction, no sentiment, no entity matching.
Returns the common social post shape defined in social_scraper.py.

WHY A RELAY: Instagram hard-blocks datacenter IPs (instant 429 from Hetzner,
verified 2026-06-30). The sessionid cookie works only from a residential IP.
So production runs a small relay (instagram_relay.py, Flask) on a residential
box — like the YouTube transcript relay — and the backend calls it over HTTP.

    NOT instaloader — that library uses a stale doc_id, broken since mid-2025.
    This uses Instagram's own web + mobile private API with a sessionid cookie.

Two modes, auto-selected:
  - RELAY  (INSTAGRAM_RELAY_URL set): calls the residential relay. Use on Hetzner.
  - DIRECT (no relay URL): calls Instagram's API directly with INSTA_SESSIONID.
    Only works from a residential IP — for local dev / running on the relay box.

CAPABILITY LIMITS (validated 2026-06-30, cookie-only sessionid auth):
  WORKS cookie-only (web endpoints):
    - profile()       — account feed (posts, likes, comments)
    - profile_info()  — account metadata (followers, bio, verified)
  REQUIRES a mobile bearer token (Authorization: Bearer IGT:2:...), which the
  sessionid cookie alone cannot mint — these return [] / None cookie-only:
    - post(), comments(), hashtag(), location(), stories()
  Reconstructing the IGT:2 bearer is the fragile path that broke instaloader;
  the methods are kept (relay endpoints exist) for when a mobile token is wired,
  and degrade gracefully meanwhile. Unlike X, IG cookies unlock only account
  monitoring — discovery (hashtag/location/global search) is platform-gated.

Setup:
    # Residential relay box:
    export INSTA_SESSIONID=<sessionid cookie from a logged-in instagram.com>
    python backend/collectors/instagram_relay.py        # serves :8890

    # Backend (Hetzner):
    export INSTAGRAM_RELAY_URL=http://<relay-tailscale-ip>:8890

Usage:
    scraper = InstagramScraper()
    posts = await scraper.profile("natgeo", limit=12)
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_RELAY_URL = os.getenv("INSTAGRAM_RELAY_URL", "").rstrip("/")
_SESSIONID = os.getenv("INSTA_SESSIONID", "")

_WEB_APP_ID = "936619743392459"
_MOBILE_APP_ID = "567067343352427"
_WEB_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_MOBILE_UA = (
    "Instagram 325.0.0.35.90 Android (34/14; 420dpi; 1080x2400; "
    "samsung; SM-G998U1; p3q; qcom; en_US; 559682050)"
)

_SC_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def _shortcode_to_media_id(shortcode: str) -> int:
    """Convert an Instagram post shortcode (/p/<code>/) to its numeric media id."""
    mid = 0
    for ch in shortcode:
        mid = mid * 64 + _SC_ALPHABET.index(ch)
    return mid


def _comment_to_post(c: dict[str, Any], shortcode: str) -> dict[str, Any]:
    user = c.get("user") or {}
    ts = c.get("created_at", 0)
    return {
        "platform": "instagram",
        "platform_post_id": str(c.get("pk") or ""),
        "author_username": user.get("username", ""),
        "author_name": user.get("full_name"),
        "post_text": (c.get("text") or "").strip()[:4000],
        "post_url": f"https://www.instagram.com/p/{shortcode}/",
        "posted_at": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None,
        "likes": c.get("comment_like_count"),
        "comments": None,
        "shares": None,
        "upvotes": None,
        "has_media": False,
        "media_urls": [],
        "raw": {"parent_shortcode": shortcode},
    }


def _medias_from_sections(sections: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Flatten medias out of a hashtag/location 'sections' structure."""
    posts: list[dict[str, Any]] = []
    for sec in sections:
        medias = ((sec.get("layout_content") or {}).get("medias")) or []
        for m in medias:
            media = m.get("media") or {}
            posts.append(_item_to_post(media, (media.get("user") or {}).get("username", "")))
            if len(posts) >= limit:
                return posts
    return posts


# ── normaliser (direct mode) ──────────────────────────────────────────────────

def _item_to_post(item: dict[str, Any], username: str) -> dict[str, Any]:
    cap = item.get("caption") or {}
    text = cap.get("text", "") if isinstance(cap, dict) else ""
    ts = item.get("taken_at", 0)
    posted_at = (
        datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None
    )

    media_urls: list[str] = []
    if item.get("video_versions"):
        media_urls.append(item["video_versions"][0]["url"])
    if "image_versions2" in item:
        cands = item["image_versions2"].get("candidates", [])
        if cands:
            media_urls.append(cands[0]["url"])
    if "carousel_media" in item:
        for cm in item["carousel_media"][:5]:
            cands = cm.get("image_versions2", {}).get("candidates", [])
            if cands:
                media_urls.append(cands[0]["url"])

    shortcode = item.get("code") or item.get("shortcode") or ""
    return {
        "platform": "instagram",
        "platform_post_id": str(item.get("id") or item.get("pk") or ""),
        "author_username": username,
        "author_name": None,
        "post_text": (text or "").strip()[:4000],
        "post_url": f"https://www.instagram.com/p/{shortcode}/" if shortcode else "",
        "posted_at": posted_at,
        "likes": item.get("like_count"),
        "comments": item.get("comment_count"),
        "shares": None,
        "upvotes": None,
        "has_media": bool(media_urls),
        "media_urls": media_urls[:4],
        "raw": {
            "media_type": item.get("media_type"),
            "view_count": item.get("view_count"),
            "play_count": item.get("play_count"),
            "location": (item.get("location") or {}).get("name") if item.get("location") else None,
        },
    }


# ── scraper class ─────────────────────────────────────────────────────────────

class InstagramScraper:
    """
    Async Instagram client. Routes through the residential relay when
    INSTAGRAM_RELAY_URL is set, otherwise calls Instagram directly (residential
    IP only). Call methods directly; no init() needed.
    """

    def __init__(
        self,
        relay_url: str = _RELAY_URL,
        sessionid: str = _SESSIONID,
    ) -> None:
        self._relay_url = relay_url.rstrip("/")
        self._sessionid = sessionid
        self._uid_cache: dict[str, str] = {}

    @property
    def mode(self) -> str:
        return "relay" if self._relay_url else "direct"

    def _check(self) -> None:
        if not self._relay_url and not self._sessionid:
            raise RuntimeError(
                "Set INSTAGRAM_RELAY_URL (production) or INSTA_SESSIONID "
                "(residential direct mode)."
            )

    # ── relay mode ─────────────────────────────────────────────────────────────

    async def _profile_via_relay(self, username: str, limit: int) -> list[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=40) as client:
                r = await client.get(
                    f"{self._relay_url}/instagram/profile",
                    params={"username": username, "limit": limit},
                )
            if r.status_code != 200:
                logger.warning("IG relay @%s -> HTTP %s", username, r.status_code)
                return []
            body = r.json()
            if not body.get("ok"):
                logger.warning("IG relay @%s not ok: %s", username, body.get("error"))
                return []
            return body.get("posts") or []
        except Exception:
            logger.exception("IG relay call failed (@%s)", username)
            return []

    async def relay_healthy(self) -> bool:
        """Check the relay is up and its session is loaded (relay mode only)."""
        if not self._relay_url:
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{self._relay_url}/health")
            return r.status_code == 200 and bool(r.json().get("session_loaded"))
        except Exception:
            return False

    # ── direct mode ────────────────────────────────────────────────────────────

    async def _get_user_id(self, client: httpx.AsyncClient, username: str) -> str | None:
        if username in self._uid_cache:
            return self._uid_cache[username]
        r = await client.get(
            f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}",
            headers={"User-Agent": _WEB_UA, "X-IG-App-ID": _WEB_APP_ID,
                     "Accept-Language": "en-US,en;q=0.9"},
            cookies={"sessionid": self._sessionid},
        )
        if r.status_code != 200:
            logger.warning("IG web_profile_info @%s -> HTTP %s", username, r.status_code)
            return None
        uid = str(r.json()["data"]["user"]["id"])
        self._uid_cache[username] = uid
        return uid

    async def _profile_direct(self, username: str, limit: int) -> list[dict[str, Any]]:
        try:
            # follow_redirects: IG answers web_profile_info with a 302 self-redirect
            # that sets a cookie; the client must follow it (and persist the cookie)
            # to get the 200 JSON — exactly what requests.Session does implicitly.
            async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
                uid = await self._get_user_id(client, username)
                if uid is None:
                    return []
                r = await client.get(
                    f"https://i.instagram.com/api/v1/feed/user/{uid}/",
                    params={"count": min(limit, 12), "rank_token": uuid.uuid4().hex},
                    headers={
                        "User-Agent": _MOBILE_UA,
                        "X-IG-App-ID": _MOBILE_APP_ID,
                        "X-IG-Device-ID": str(uuid.uuid4()),
                        "X-IG-Android-ID": "android-" + uuid.uuid4().hex[:16],
                        "Accept-Language": "en-US",
                    },
                    cookies={"sessionid": self._sessionid},
                )
            if r.status_code != 200:
                logger.warning("IG feed @%s -> HTTP %s", username, r.status_code)
                return []
            items = r.json().get("items", [])[:limit]
            return [_item_to_post(it, username) for it in items]
        except Exception:
            logger.exception("IG direct fetch failed (@%s)", username)
            return []

    # ── public method ──────────────────────────────────────────────────────────

    async def profile(self, username: str, *, limit: int = 12) -> list[dict[str, Any]]:
        """
        Fetch recent posts from a public Instagram profile.
        Uses the relay if INSTAGRAM_RELAY_URL is set, else direct (residential).
        """
        self._check()
        handle = username.lstrip("@")
        if self._relay_url:
            return await self._profile_via_relay(handle, limit)
        return await self._profile_direct(handle, limit)

    # ── shared relay caller ────────────────────────────────────────────────────

    async def _relay_get(self, path: str, params: dict[str, Any]) -> Any:
        """Call a relay endpoint that returns the {ok, data} envelope."""
        try:
            async with httpx.AsyncClient(timeout=40) as client:
                r = await client.get(f"{self._relay_url}{path}", params=params)
            if r.status_code != 200:
                logger.warning("IG relay %s -> HTTP %s", path, r.status_code)
                return None
            body = r.json()
            if not body.get("ok"):
                logger.warning("IG relay %s not ok: %s", path, body.get("error"))
                return None
            return body.get("data")
        except Exception:
            logger.exception("IG relay call failed (%s)", path)
            return None

    async def _direct_web(self, url: str) -> dict[str, Any] | None:
        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
            r = await client.get(
                url,
                headers={"User-Agent": _WEB_UA, "X-IG-App-ID": _WEB_APP_ID,
                         "Accept-Language": "en-US,en;q=0.9"},
                cookies={"sessionid": self._sessionid},
            )
        if r.status_code != 200:
            logger.warning("IG web %s -> HTTP %s", url, r.status_code)
            return None
        if "application/json" not in r.headers.get("content-type", ""):
            logger.warning("IG web %s -> non-JSON (gated to browser?)", url)
            return None
        try:
            return r.json()
        except Exception:
            return None

    async def _direct_mobile(self, url: str, params: dict[str, Any] | None = None,
                             post: bool = False, data: dict[str, Any] | None = None) -> dict[str, Any] | None:
        headers = {
            "User-Agent": _MOBILE_UA, "X-IG-App-ID": _MOBILE_APP_ID,
            "X-IG-Device-ID": str(uuid.uuid4()),
            "X-IG-Android-ID": "android-" + uuid.uuid4().hex[:16],
            "Accept-Language": "en-US",
        }
        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
            if post:
                r = await client.post(url, data=data or {}, headers=headers,
                                      cookies={"sessionid": self._sessionid})
            else:
                r = await client.get(url, params=params or {}, headers=headers,
                                     cookies={"sessionid": self._sessionid})
        if r.status_code != 200:
            logger.warning("IG mobile %s -> HTTP %s", url, r.status_code)
            return None
        try:
            return r.json()
        except Exception:
            logger.warning("IG mobile %s -> non-JSON response", url)
            return None

    # ── parity methods ─────────────────────────────────────────────────────────

    async def profile_info(self, username: str) -> dict[str, Any] | None:
        """Profile metadata: followers, following, post count, bio, verified."""
        self._check()
        handle = username.lstrip("@")
        if self._relay_url:
            return await self._relay_get("/instagram/profile_info", {"username": handle})
        data = await self._direct_web(
            f"https://www.instagram.com/api/v1/users/web_profile_info/?username={handle}"
        )
        if not data:
            return None
        u = data["data"]["user"]
        return {
            "platform": "instagram",
            "username": u.get("username", handle),
            "full_name": u.get("full_name"),
            "bio": (u.get("biography") or "").strip(),
            "followers": (u.get("edge_followed_by") or {}).get("count"),
            "following": (u.get("edge_follow") or {}).get("count"),
            "posts": (u.get("edge_owner_to_timeline_media") or {}).get("count"),
            "verified": u.get("is_verified"),
            "private": u.get("is_private"),
            "profile_pic": u.get("profile_pic_url_hd") or u.get("profile_pic_url"),
            "external_url": u.get("external_url"),
            "category": u.get("category_name"),
            "id": u.get("id"),
        }

    async def post(self, shortcode: str) -> dict[str, Any] | None:
        """Fetch a single post by its shortcode (from /p/<shortcode>/)."""
        self._check()
        if self._relay_url:
            return await self._relay_get("/instagram/post", {"shortcode": shortcode})
        data = await self._direct_mobile(
            f"https://i.instagram.com/api/v1/media/{_shortcode_to_media_id(shortcode)}/info/"
        )
        items = (data or {}).get("items") or []
        if not items:
            return None
        it = items[0]
        return _item_to_post(it, (it.get("user") or {}).get("username", ""))

    async def comments(self, shortcode: str, *, limit: int = 25) -> list[dict[str, Any]]:
        """Fetch comments on a post."""
        self._check()
        if self._relay_url:
            return await self._relay_get("/instagram/comments", {"shortcode": shortcode, "limit": limit}) or []
        data = await self._direct_mobile(
            f"https://i.instagram.com/api/v1/media/{_shortcode_to_media_id(shortcode)}/comments/",
            params={"can_support_threading": "true", "permalink_enabled": "false"},
        )
        comments = (data or {}).get("comments") or []
        return [_comment_to_post(c, shortcode) for c in comments[:limit]]

    async def hashtag(self, tag: str, *, limit: int = 25) -> list[dict[str, Any]]:
        """Fetch top + recent posts for a hashtag (IG's closest thing to search)."""
        self._check()
        tag = tag.lstrip("#")
        if self._relay_url:
            return await self._relay_get("/instagram/hashtag", {"tag": tag, "limit": limit}) or []
        data = await self._direct_web(
            f"https://www.instagram.com/api/v1/tags/web_info/?tag_name={tag}"
        )
        if not data:
            return []
        d = data.get("data", {})
        posts: list[dict[str, Any]] = []
        for key in ("top", "recent"):
            sections = (d.get(key) or {}).get("sections") or []
            posts.extend(_medias_from_sections(sections, limit - len(posts)))
            if len(posts) >= limit:
                break
        return posts[:limit]

    async def location(self, location_id: str, *, limit: int = 25) -> list[dict[str, Any]]:
        """Fetch recent posts tagged at a location (IG's geo-search equivalent)."""
        self._check()
        if self._relay_url:
            return await self._relay_get("/instagram/location", {"location_id": location_id, "limit": limit}) or []
        data = await self._direct_mobile(
            f"https://i.instagram.com/api/v1/locations/{location_id}/sections/",
            post=True, data={"tab": "recent"},
        )
        sections = (data or {}).get("sections") or []
        return _medias_from_sections(sections, limit)

    async def stories(self, username: str) -> list[dict[str, Any]]:
        """Fetch a user's active 24h stories (no X equivalent)."""
        self._check()
        handle = username.lstrip("@")
        if self._relay_url:
            return await self._relay_get("/instagram/stories", {"username": handle}) or []
        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
            uid = await self._get_user_id(client, handle)
        if uid is None:
            return []
        data = await self._direct_mobile(
            "https://i.instagram.com/api/v1/feed/reels_media/", params={"reel_ids": uid}
        )
        reel = ((data or {}).get("reels") or {}).get(str(uid)) or {}
        out: list[dict[str, Any]] = []
        for it in reel.get("items", [])[:50]:
            ts = it.get("taken_at", 0)
            media_urls: list[str] = []
            if it.get("video_versions"):
                media_urls.append(it["video_versions"][0]["url"])
            elif it.get("image_versions2"):
                cands = it["image_versions2"].get("candidates", [])
                if cands:
                    media_urls.append(cands[0]["url"])
            out.append({
                "platform": "instagram",
                "platform_post_id": str(it.get("pk") or it.get("id") or ""),
                "author_username": handle,
                "author_name": None,
                "post_text": "",
                "post_url": f"https://www.instagram.com/stories/{handle}/{it.get('pk','')}/",
                "posted_at": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None,
                "likes": None, "comments": None, "shares": None, "upvotes": None,
                "has_media": bool(media_urls),
                "media_urls": media_urls,
                "raw": {"is_story": True, "expiring_at": it.get("expiring_at"),
                        "media_type": it.get("media_type")},
            })
        return out


# ── module-level singleton ────────────────────────────────────────────────────

_scraper: InstagramScraper | None = None


def get_scraper() -> InstagramScraper:
    global _scraper
    if _scraper is None:
        _scraper = InstagramScraper()
    return _scraper


# ── CLI smoke-test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio

    async def _smoke():
        s = InstagramScraper()
        print(f"mode: {s.mode}")
        for handle in ("natgeo", "narendramodi"):
            print(f"\n--- @{handle} (3) ---")
            for p in await s.profile(handle, limit=3):
                line = f"  [likes={p['likes']} cmt={p['comments']}] {p['post_text'][:60]}"
                print(line.encode("ascii", "replace").decode())

    asyncio.run(_smoke())
