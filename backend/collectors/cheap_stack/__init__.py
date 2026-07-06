"""Cheap collection stack — proxy-free OSINT collection.

Techniques (cheapest → last-resort):
  1. browser_fetch  — curl_cffi TLS impersonation (beats network-layer bot walls)
  2. oembed         — official no-auth structured metadata
  3. archive        — Wayback + Common Crawl (historical, unblockable)
  4. frontends      — self-hosted Nitter/Invidious/Redlib mirrors

Proxies + aged accounts are only needed for last-mile live private data
(Instagram/TikTok), not for the bulk of collection.
"""
from .browser_fetch import FetchResult, fetch, fetch_with_fallback
from . import oembed, archive, frontends

__all__ = [
    "FetchResult",
    "fetch",
    "fetch_with_fallback",
    "oembed",
    "archive",
    "frontends",
]
