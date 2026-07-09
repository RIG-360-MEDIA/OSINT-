"""Web-archive collector — domain -> Wayback Machine history.

Given a domain, returns first-seen, latest snapshot, total capture count, a
YEARLY snapshot timeline (clickable — see how the site changed over time), and
GAP years (spans with no captures — a site going dark then relaunching is a
rebrand / concealment signal). Free, no auth.
"""
from __future__ import annotations

import asyncio
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


async def _count_and_first(client: httpx.AsyncClient, domain: str) -> tuple[str | None, int | None, str | None]:
    """Earliest capture + total count via a cheap timestamp-only CDX scan."""
    try:
        rr = await client.get(
            _CDX,
            params={"url": domain, "output": "json", "limit": str(_CDX_LIMIT), "fl": "timestamp"},
            timeout=25,
        )
        if rr.status_code != 200:
            return None, None, f"cdx_status:{rr.status_code}"
        rows = rr.json() or []
        data = rows[1:] if rows and rows[0] == ["timestamp"] else rows
        if data:
            return data[0][0], len(data), None
        return None, 0, None
    except Exception as exc:
        return None, None, type(exc).__name__


async def _timeline(client: httpx.AsyncClient, domain: str) -> list[dict[str, Any]]:
    """One representative snapshot per YEAR (CDX collapse=timestamp:4)."""
    try:
        rr = await client.get(
            _CDX,
            params={"url": domain, "output": "json", "fl": "timestamp,original,statuscode",
                    "collapse": "timestamp:4"},
            timeout=25,
        )
        if rr.status_code != 200:
            return []
        rows = rr.json() or []
        data = rows[1:] if rows and isinstance(rows[0], list) and rows[0] and rows[0][0] == "timestamp" else rows
        out: list[dict[str, Any]] = []
        for row in data:
            ts = row[0] if row else ""
            original = row[1] if len(row) > 1 else domain
            status = row[2] if len(row) > 2 else None
            if not ts:
                continue
            out.append({
                "year": ts[:4],
                "date": ts[:8],
                "status": status,
                "url": f"https://web.archive.org/web/{ts}/{original}",
            })
        return out
    except Exception:
        return []


async def web_archive(domain: str) -> dict[str, Any]:
    """Wayback history for a domain. Returns partial data on any failure."""
    domain = (domain or "").strip().lower()
    if domain.startswith("www."):
        domain = domain[4:]
    if not _looks_like_domain(domain):
        return {"domain": domain, "error": "not a valid domain (archive needs a domain, e.g. ril.com)"}

    out: dict[str, Any] = {"domain": domain, "latest_snapshot": None,
                           "first_seen": None, "capture_count": None, "timeline": []}
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        avail_task = client.get(_AVAILABLE, params={"url": domain})
        first_seen, count, cdx_err, timeline = None, None, None, []
        try:
            r, (first_seen, count, cdx_err), timeline = await asyncio.gather(
                avail_task, _count_and_first(client, domain), _timeline(client, domain),
            )
            if r.status_code == 200:
                closest = (r.json().get("archived_snapshots") or {}).get("closest") or {}
                if closest.get("available"):
                    out["latest_snapshot"] = {
                        "url": closest.get("url"),
                        "timestamp": closest.get("timestamp"),
                        "status": closest.get("status"),
                    }
        except Exception as exc:
            out["fetch_error"] = type(exc).__name__

    out["first_seen"] = first_seen
    out["capture_count"] = count
    out["timeline"] = timeline
    if cdx_err:
        out["cdx_note"] = cdx_err

    # Derived: presence span + dark-year gaps (rebrand / relaunch signal).
    years = sorted({int(t["year"]) for t in timeline if t["year"].isdigit()})
    gap_years: list[int] = []
    if len(years) >= 2:
        present = set(years)
        gap_years = [y for y in range(years[0], years[-1] + 1) if y not in present]
    out["summary"] = {
        "first_seen_year": _year(out.get("first_seen")) or (years[0] if years else None),
        "last_seen_year": years[-1] if years else None,
        "years_with_captures": len(years),
        "gap_years": gap_years,
        "total_snapshots": out.get("capture_count"),
        "archived": bool(out.get("latest_snapshot") or out.get("capture_count")),
    }
    return out
