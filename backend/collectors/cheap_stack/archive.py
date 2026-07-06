"""Historical collection from web archives — zero blocking, no proxy.

Wayback Machine and Common Crawl already crawled the web. For *historical* data,
query them instead of hitting (and getting blocked by) the live platform. This is
the literal implementation of the product's "scrape historically" requirement.
"""
from __future__ import annotations

from typing import Optional

from .browser_fetch import fetch

_WAYBACK_AVAILABLE = "https://archive.org/wayback/available"
_WAYBACK_CDX = "https://web.archive.org/cdx/search/cdx"
_CC_COLLINFO = "https://index.commoncrawl.org/collinfo.json"


def wayback_latest(url: str) -> Optional[dict]:
    """Return the most recent Wayback snapshot metadata for a URL, or None."""
    result = fetch(_WAYBACK_AVAILABLE, params={"url": url})
    if not result.ok:
        return None
    try:
        snap = result.json.get("archived_snapshots", {}).get("closest")
        return snap or None
    except Exception:
        return None


def wayback_history(url: str, *, limit: int = 50) -> list[dict]:
    """List historical captures of a URL (timestamp + original) via the CDX API."""
    result = fetch(
        _WAYBACK_CDX,
        params={
            "url": url,
            "output": "json",
            "limit": str(limit),
            "fl": "timestamp,original,statuscode,mimetype",
            "collapse": "digest",
        },
        timeout=30,
    )
    if not result.ok:
        return []
    try:
        rows = result.json
    except Exception:
        return []
    if not rows or len(rows) < 2:
        return []
    header, *data = rows
    return [dict(zip(header, row)) for row in data]


def commoncrawl_latest_index() -> Optional[str]:
    """Return the id of the most recent Common Crawl index (e.g. CC-MAIN-2026-...)."""
    result = fetch(_CC_COLLINFO, timeout=30)
    if not result.ok:
        return None
    try:
        collections = result.json
        return collections[0].get("id") if collections else None
    except Exception:
        return None


def commoncrawl_lookup(domain_or_url: str, *, index_id: Optional[str] = None,
                       limit: int = 20) -> list[dict]:
    """Look up captured pages for a domain/URL in Common Crawl. Returns records."""
    index_id = index_id or commoncrawl_latest_index()
    if not index_id:
        return []
    endpoint = f"https://index.commoncrawl.org/{index_id}-index"
    result = fetch(
        endpoint,
        params={"url": domain_or_url, "output": "json", "limit": str(limit)},
        timeout=45,
    )
    if not result.ok:
        return []
    records = []
    import json as _json

    for line in result.text.splitlines():  # CC returns JSON-lines
        line = line.strip()
        if not line:
            continue
        try:
            records.append(_json.loads(line))
        except Exception:
            continue
    return records
