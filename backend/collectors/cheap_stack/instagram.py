"""Instagram collector — swap-able methods, residential-egress-aware.

Primary: web_profile_info API + x-ig-app-id header (free, no login). Fragile by
design — IG rotates internals — so it's one method behind the interface; add more
(instagrapi session, 3rd-party viewer) as fallbacks without touching callers.

IMPORTANT: datacenter IPs get 403 on the first request. On Hetzner, pass an
Egress with a residential proxy. On a residential box, Egress() direct works.
"""
from __future__ import annotations

from typing import Optional

from .base import Collector, Egress, Method, ProfileResult
from .browser_fetch import fetch

IG_APP_ID = "936619743392459"  # constant public web app id; wrong value => 403


class WebProfileInfoMethod:
    """Primary: the internal web_profile_info JSON endpoint."""

    name = "web_profile_info+app_id"

    def fetch_profile(self, handle: str, egress: Egress) -> Optional[ProfileResult]:
        handle = handle.lstrip("@")
        result = fetch(
            "https://www.instagram.com/api/v1/users/web_profile_info/",
            params={"username": handle},
            headers={
                "x-ig-app-id": IG_APP_ID,
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
            },
            proxies=egress.proxies,
            timeout=20,
        )
        if not result.ok:
            return ProfileResult(
                platform="instagram", handle=handle, ok=False, method=self.name,
                error=f"http {result.status} (datacenter IP? needs residential egress)"
                if result.status in (401, 403, 0) else f"http {result.status}",
            )
        try:
            user = result.json.get("data", {}).get("user", {})
        except Exception as exc:
            return ProfileResult(platform="instagram", handle=handle, ok=False,
                                 method=self.name, error=f"parse: {exc}")
        if not user:
            return ProfileResult(platform="instagram", handle=handle, ok=False,
                                 method=self.name, error="empty user (private/removed?)")

        return ProfileResult(
            platform="instagram",
            handle=handle,
            ok=True,
            method=self.name,
            display_name=user.get("full_name"),
            followers=user.get("edge_followed_by", {}).get("count"),
            following=user.get("edge_follow", {}).get("count"),
            posts_count=user.get("edge_owner_to_timeline_media", {}).get("count"),
            bio=user.get("biography"),
            verified=user.get("is_verified"),
            external_url=user.get("external_url"),
            extra={
                "id": user.get("id"),
                "is_private": user.get("is_private"),
                "is_business": user.get("is_business_account"),
            },
        )


class InstagramCollector(Collector):
    platform = "instagram"

    def __init__(self, methods: Optional[list[Method]] = None):
        super().__init__(methods or [WebProfileInfoMethod()])
