"""Video discovery via the public YouTube RSS Atom feed.

Runs on Hetzner. RSS is the one path that is NOT IP-blocked from a datacenter
(confirmed in the rebuild spike), so discovery is decoupled from the risky
transcript fetch: a transcript block never stalls discovery.

No API key, no quota, no auth. The feed carries the latest ~15 videos per
channel. Keep call volume gentle — heavy probing degraded even RSS during the
spike (see memory project_youtube_rebuild_ipblock).
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx

from .models import DiscoveredVideo

logger = logging.getLogger("youtube_v2")

_ATOM = "{http://www.w3.org/2005/Atom}"
_YT = "{http://www.youtube.com/xml/schemas/2015}"
_MEDIA = "{http://search.yahoo.com/mrss/}"

_FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
_UA = "Mozilla/5.0 (compatible; RIG-Surveillance/2.0; +https://rig)"


class DiscoveryError(RuntimeError):
    """Raised when the feed cannot be fetched or parsed — never swallowed."""


async def discover_channel_videos(
    channel_id: str,
    *,
    since: datetime | None = None,
    max_results: int = 10,
    timeout: float = 15.0,
) -> list[DiscoveredVideo]:
    """Return recent videos for a channel, newest first.

    Args:
        channel_id:  UC… channel id.
        since:       if given, only videos published at/after this instant.
        max_results: cap on returned videos.

    Raises:
        DiscoveryError: on HTTP error or unparseable feed. Callers decide
            whether to retry — we do not silently return [].
    """
    if not channel_id.startswith("UC"):
        raise DiscoveryError(f"not a channel id: {channel_id!r}")

    url = _FEED_URL.format(channel_id=channel_id)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers={"User-Agent": _UA})
    except httpx.HTTPError as exc:
        raise DiscoveryError(f"feed fetch failed for {channel_id}: {exc}") from exc

    if resp.status_code != 200:
        raise DiscoveryError(
            f"feed HTTP {resp.status_code} for {channel_id} "
            f"(IP may be rate-limited — back off)"
        )

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as exc:
        raise DiscoveryError(f"feed parse failed for {channel_id}: {exc}") from exc

    channel_name = _text(root.find(f"{_ATOM}title")) or channel_id
    videos: list[DiscoveredVideo] = []
    for entry in root.findall(f"{_ATOM}entry"):
        video_id = _text(entry.find(f"{_YT}videoId"))
        title = _text(entry.find(f"{_ATOM}title"))
        published = _text(entry.find(f"{_ATOM}published"))
        if not video_id or not title:
            continue
        if since and published and _parse_dt(published) < since:
            continue
        videos.append(
            DiscoveredVideo(
                video_id=video_id,
                title=title,
                channel_id=channel_id,
                channel_name=channel_name,
                published_at=published or "",
            )
        )
        if len(videos) >= max_results:
            break

    logger.info(
        "youtube_v2 discovery channel=%s name=%s found=%d",
        channel_id, channel_name, len(videos),
    )
    return videos


def _text(el: ET.Element | None) -> str | None:
    return el.text.strip() if el is not None and el.text else None


def _parse_dt(value: str) -> datetime:
    """Parse an Atom timestamp; fall back to epoch on failure so a bad date
    never crashes discovery."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
