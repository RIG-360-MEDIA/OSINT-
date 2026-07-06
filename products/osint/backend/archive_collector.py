"""Web-archive collector — domain -> Wayback Machine history.

Given a domain, returns first-seen capture, latest snapshot, and a rough
capture count from the Internet Archive's Wayback Machine. Free, no auth.
This is the Tasking-brain 'archive' source made live for org/domain keywords.
"""
from __future__ import annotations

from typing import Any

import httpx

_AVAILABLE = "http://archive.org/wayback/available"
_CDX = "http://web.archive.org/cdx/search/cdx"
# CDX can be slow to compute large result sets; cap rows so count stays cheap.
_CDX_LIMIT = 50000


def _looks_like_domain(s: str) -> bool:
    s = (s or "").strip().lower()
    return "." in s and " " not in s and len(s) <= 253


def _year(ts: str | None) -> int | None:
    """Extract the 4-digit year from a Wayback YYYYMMDDhhmmss timestamp."""
    if ts and len(ts) >= 4 and ts[:4].isdigit():
        return int(ts[:4])
    return None


async def web_archive(domain: str) -> dict[str, Any]:
    """Wayback history for a domain. Returns partial data on any failure."""
    domain = (domain or "").strip().lower()
    if domain.startswith("www."):
        domain = domain[4:]
    if not _looks_like_domain(domain):
        return {"domain": domain, "error": "not a valid domain (archive needs a domain, e.g. ril.com)"}

    out: dict[str, Any] = {
        "domain": domain,
        "latest_snapshot": None,
        "first_seen": None,
        "capture_count": None,
    }
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        # Closest / latest available snapshot.
        try:
            r = await client.get(_AVAILABLE, params={"url": domain})
            if r.status_code == 200:
                closest = (r.json().get("archived_snapshots") or {}).get("closest") or {}
                if closest.get("available"):
                    out["latest_snapshot"] = {
                        "url": closest.get("url"),
                        "timestamp": closest.get("timestamp"),
                        "status": closest.get("status"),
                    }
            else:
                out["available_status"] = r.status_code
        except Exception as exc:
            out["available_error"] = type(exc).__name__

        # Full capture list (oldest-first): row 0 is the header, so the first
        # data row is the earliest capture and the row count is the total.
        try:
            rr = await client.get(
                _CDX,
                params={"url": domain, "output": "json", "limit": str(_CDX_LIMIT), "fl": "timestamp"},
                timeout=25,
            )
            if rr.status_code == 200:
                rows = rr.json() or []
                data = rows[1:] if rows and rows[0] == ["timestamp"] else rows
                if data:
                    out["first_seen"] = data[0][0]
                    out["capture_count"] = len(data)
            else:
                out["cdx_status"] = rr.status_code
        except Exception as exc:
            out["cdx_error"] = type(exc).__name__

    # a small derived signal: how long the domain has had a web presence
    first_year = _year(out.get("first_seen"))
    out["summary"] = {
        "first_seen_year": first_year,
        "total_snapshots": out.get("capture_count"),
        "archived": bool(out.get("latest_snapshot") or out.get("capture_count")),
    }
    return out
