"""TikTok collector — swap-able methods.

Primary: tikwm 3rd-party free API (verified working). Fallback: parse the
__UNIVERSAL_DATA_FOR_REHYDRATION__ JSON blob from the profile HTML (works only
when TikTok doesn't drop the connection — often needs residential egress).
"""
from __future__ import annotations

import json as _json
import re
from typing import Optional

from .base import Collector, Egress, Method, ProfileResult
from .browser_fetch import fetch

_BLOB_RE = re.compile(
    r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">(.*?)</script>',
    re.DOTALL,
)


class TikwmMethod:
    """Primary: tikwm.com free API."""

    name = "tikwm_api"

    def fetch_profile(self, handle: str, egress: Egress) -> Optional[ProfileResult]:
        handle = handle.lstrip("@")
        result = fetch(
            "https://www.tikwm.com/api/user/info",
            params={"unique_id": handle},
            proxies=egress.proxies,
            timeout=25,
        )
        if not result.ok:
            return ProfileResult(platform="tiktok", handle=handle, ok=False,
                                 method=self.name, error=f"http {result.status}")
        try:
            payload = result.json
        except Exception as exc:
            return ProfileResult(platform="tiktok", handle=handle, ok=False,
                                 method=self.name, error=f"parse: {exc}")
        if str(payload.get("code")) != "0":
            return ProfileResult(platform="tiktok", handle=handle, ok=False,
                                 method=self.name, error=f"api code={payload.get('code')} {payload.get('msg')}")

        data = payload.get("data", {})
        user = data.get("user", {})
        stats = data.get("stats", {})
        return ProfileResult(
            platform="tiktok",
            handle=user.get("uniqueId") or handle,
            ok=True,
            method=self.name,
            display_name=user.get("nickname"),
            followers=stats.get("followerCount"),
            following=stats.get("followingCount"),
            posts_count=stats.get("videoCount"),
            bio=user.get("signature"),
            verified=user.get("verified"),
            extra={"id": user.get("id"), "hearts": stats.get("heartCount")},
        )


class UniversalDataMethod:
    """Fallback: parse the SSR JSON blob from the profile page."""

    name = "html_universal_data"

    def fetch_profile(self, handle: str, egress: Egress) -> Optional[ProfileResult]:
        handle = handle.lstrip("@")
        result = fetch(f"https://www.tiktok.com/@{handle}",
                       proxies=egress.proxies, timeout=25)
        if not result.ok:
            return ProfileResult(platform="tiktok", handle=handle, ok=False,
                                 method=self.name,
                                 error=f"http {result.status} (TikTok dropped conn?)")
        m = _BLOB_RE.search(result.text)
        if not m:
            return ProfileResult(platform="tiktok", handle=handle, ok=False,
                                 method=self.name, error="no SSR blob")
        try:
            blob = _json.loads(m.group(1))
            scope = blob["__DEFAULT_SCOPE__"]["webapp.user-detail"]["userInfo"]
            user, stats = scope["user"], scope["stats"]
        except Exception as exc:
            return ProfileResult(platform="tiktok", handle=handle, ok=False,
                                 method=self.name, error=f"blob parse: {exc}")
        return ProfileResult(
            platform="tiktok", handle=user.get("uniqueId") or handle, ok=True,
            method=self.name, display_name=user.get("nickname"),
            followers=stats.get("followerCount"), following=stats.get("followingCount"),
            posts_count=stats.get("videoCount"), bio=user.get("signature"),
            verified=user.get("verified"), extra={"id": user.get("id")},
        )


class TikTokCollector(Collector):
    platform = "tiktok"

    def __init__(self, methods: Optional[list[Method]] = None):
        super().__init__(methods or [TikwmMethod(), UniversalDataMethod()])
