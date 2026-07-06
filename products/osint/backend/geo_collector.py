"""Geo / Place collector — a non-social OSINT source for location keywords.

Given a place keyword, returns the top OpenStreetMap match via Nominatim:
coordinates, place type/class, country, and bounding box. Free, no auth —
but Nominatim's usage policy REQUIRES a descriptive User-Agent, so one is
always sent. This is the Tasking-brain 'geo' source made live: a location
keyword -> where it is on the map.
"""
from __future__ import annotations

from typing import Any

import httpx

_NOMINATIM = "https://nominatim.openstreetmap.org/search"
_HEADERS = {"User-Agent": "RIG-OSINT/1.0"}


def _to_float(value: Any) -> float | None:
    """Nominatim returns lat/lon as strings; coerce, tolerating junk."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_bbox(raw: Any) -> dict[str, float] | None:
    """boundingbox is ['south', 'north', 'west', 'east'] as strings."""
    if not isinstance(raw, list) or len(raw) != 4:
        return None
    south, north, west, east = (_to_float(v) for v in raw)
    if None in (south, north, west, east):
        return None
    return {"south": south, "north": north, "west": west, "east": east}


async def geo_lookup(q: str) -> dict[str, Any]:
    """Top OSM place match for a location keyword. Partial data on any failure."""
    q = (q or "").strip()
    if not q:
        return {"query": q, "error": "empty query (geo needs a place, e.g. 'Ahmedabad')"}

    out: dict[str, Any] = {"query": q, "match": None, "alternatives": []}
    params = {"q": q, "format": "json", "limit": 3, "addressdetails": 1}
    async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers=_HEADERS) as client:
        try:
            r = await client.get(_NOMINATIM, params=params)
            if r.status_code != 200:
                out["error"] = f"nominatim http {r.status_code}"
                return out
            results = r.json()
        except Exception as exc:
            out["error"] = type(exc).__name__
            return out

    if not isinstance(results, list) or not results:
        out["summary"] = {"found": False}
        return out

    top = results[0]
    address = top.get("address") or {}
    lat, lon = _to_float(top.get("lat")), _to_float(top.get("lon"))
    out["match"] = {
        "display_name": top.get("display_name"),
        "lat": lat,
        "lon": lon,
        "type": top.get("type"),
        "class": top.get("class"),
        "country": address.get("country"),
        "country_code": (address.get("country_code") or "").upper() or None,
        "boundingbox": _parse_bbox(top.get("boundingbox")),
    }
    out["alternatives"] = [
        {"display_name": alt.get("display_name"), "type": alt.get("type")}
        for alt in results[1:]
    ]

    # A small derived signal: primary coordinates + place kind.
    out["summary"] = {
        "found": True,
        "coordinates": f"{lat},{lon}" if lat is not None and lon is not None else None,
        "place_type": top.get("type"),
        "country": address.get("country"),
        "match_count": len(results),
    }
    return out
