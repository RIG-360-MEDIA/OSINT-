"""Alternative-frontend collectors (Nitter / Invidious / Redlib).

These open-source mirrors extract clean content from social platforms with no
auth. Public instances are flaky/dying (Nitter is officially "abandoned") — so
this module is INSTANCE-DRIVEN: pass your own self-hosted instance for reliable
production use. Public instances are used only as best-effort fallbacks.
"""
from __future__ import annotations

from typing import Optional

from .browser_fetch import fetch_with_fallback

# Best-effort public instances. In production, put a SELF-HOSTED instance first.
DEFAULT_INSTANCES = {
    "invidious": ["https://yewtu.be", "https://invidious.nerdvpn.de"],
    "nitter": ["https://nitter.net", "https://nitter.poast.org"],
    "redlib": ["https://redlib.catsarch.com", "https://safereddit.com"],
}


def _try_instances(instances: list[str], path: str, *, timeout: int = 20):
    for base in instances:
        result = fetch_with_fallback(base.rstrip("/") + path, timeout=timeout)
        if result.ok and result.text:
            return result
    return None


def invidious_video(video_id: str, *, instances: Optional[list[str]] = None) -> Optional[dict]:
    """Fetch YouTube video metadata via Invidious API (no Google, no PO token)."""
    instances = instances or DEFAULT_INSTANCES["invidious"]
    result = _try_instances(instances, f"/api/v1/videos/{video_id}")
    if not result:
        return None
    try:
        return result.json
    except Exception:
        return None


def nitter_profile_rss(handle: str, *, instances: Optional[list[str]] = None) -> Optional[str]:
    """Fetch a Twitter/X profile timeline as RSS via Nitter (feeds RSS pipeline)."""
    instances = instances or DEFAULT_INSTANCES["nitter"]
    result = _try_instances(instances, f"/{handle}/rss")
    return result.text if result else None


def redlib_subreddit_rss(subreddit: str, *, instances: Optional[list[str]] = None) -> Optional[str]:
    """Fetch a subreddit as RSS via Redlib (no Reddit auth)."""
    instances = instances or DEFAULT_INSTANCES["redlib"]
    result = _try_instances(instances, f"/r/{subreddit}.rss")
    return result.text if result else None
