"""Official no-auth oEmbed collectors.

oEmbed endpoints return structured post/video metadata with NO authentication,
NO API key, and effectively no rate-limit for modest use. The cleanest legal
side-door on the whole cheap stack.
"""
from __future__ import annotations

from typing import Optional

from .browser_fetch import fetch

# provider -> oEmbed endpoint template ({url} filled in)
_ENDPOINTS = {
    "youtube": "https://www.youtube.com/oembed?format=json&url={url}",
    "twitter": "https://publish.twitter.com/oembed?url={url}",
    "vimeo": "https://vimeo.com/api/oembed.json?url={url}",
    "tiktok": "https://www.tiktok.com/oembed?url={url}",
    "flickr": "https://www.flickr.com/services/oembed?format=json&url={url}",
}


def oembed(provider: str, content_url: str) -> Optional[dict]:
    """Fetch oEmbed metadata for a content URL. Returns dict or None on failure."""
    provider = provider.lower()
    if provider not in _ENDPOINTS:
        raise ValueError(f"unsupported oembed provider: {provider!r}")
    from urllib.parse import quote

    endpoint = _ENDPOINTS[provider].format(url=quote(content_url, safe=""))
    result = fetch(endpoint)
    if not result.ok:
        return None
    try:
        return result.json
    except Exception:
        return None
