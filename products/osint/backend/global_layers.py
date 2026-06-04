"""External world-monitor data layers for the GLOBAL map.

- ACLED  — armed-conflict / political-violence events (uses ACLED_ACCESS_TOKEN).
- NASA EONET — open natural events (wildfires, severe storms, volcanoes); KEYLESS.
- Ships (AIS) — not wired: needs a paid AIS key (no credential available).

All fetched live and cached in-process for 30 min so the Hetzner host makes at most
a couple of light API calls per cycle.
"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

_TTL = 1800  # 30 min
_TIMEOUT = 12.0
_cache: dict[str, tuple[float, Any]] = {}

ACLED_ENDPOINT = "https://api.acleddata.com/acled/read"
EONET_ENDPOINT = "https://eonet.gsfc.nasa.gov/api/v3/events"


def _f(v: Any) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (ValueError, TypeError):
        return None


async def _fetch_acled(client: httpx.AsyncClient, days: int = 7) -> list[dict[str, Any]]:
    token = os.getenv("ACLED_ACCESS_TOKEN", "").strip()
    if not token:
        return []
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    today = datetime.now(timezone.utc).date().isoformat()
    params = {
        "event_date": f"{since}|{today}", "event_date_where": "BETWEEN",
        "limit": 800, "terms": "accept", "access_token": token,
    }
    try:
        r = await client.get(ACLED_ENDPOINT, params=params, timeout=_TIMEOUT)
        r.raise_for_status()
        rows = (r.json() or {}).get("data") or []
    except (httpx.HTTPError, ValueError):
        return []
    out = []
    for d in rows:
        lat, lon = _f(d.get("latitude")), _f(d.get("longitude"))
        if lat is None or lon is None:
            continue
        out.append({
            "lat": lat, "lon": lon,
            "type": d.get("event_type") or "Event",
            "fatalities": int(_f(d.get("fatalities")) or 0),
            "date": d.get("event_date"),
            "country": d.get("country"),
            "actors": " vs ".join(x for x in (d.get("actor1"), d.get("actor2")) if x) or None,
            "notes": (d.get("notes") or "")[:240] or None,
        })
    return out


async def _fetch_eonet(client: httpx.AsyncClient, days: int = 20) -> list[dict[str, Any]]:
    try:
        r = await client.get(EONET_ENDPOINT, params={"status": "open", "days": days, "limit": 300}, timeout=_TIMEOUT)
        r.raise_for_status()
        events = (r.json() or {}).get("events") or []
    except (httpx.HTTPError, ValueError):
        return []
    out = []
    for e in events:
        geoms = e.get("geometry") or []
        if not geoms:
            continue
        g = geoms[-1]  # latest position
        coords = g.get("coordinates")
        if g.get("type") != "Point" or not isinstance(coords, list) or len(coords) < 2:
            continue
        cats = e.get("categories") or [{}]
        out.append({
            "lat": _f(coords[1]), "lon": _f(coords[0]),
            "title": e.get("title"),
            "category": (cats[0] or {}).get("title") or "Event",
            "date": g.get("date"),
        })
    return [x for x in out if x["lat"] is not None and x["lon"] is not None]


async def get_layers() -> dict[str, Any]:
    hit = _cache.get("layers")
    if hit and (time.monotonic() - hit[0]) < _TTL:
        return hit[1]
    async with httpx.AsyncClient() as client:
        acled, natural = await asyncio.gather(_fetch_acled(client), _fetch_eonet(client))
    payload = {
        "acled": acled,
        "natural": natural,
        "ships": [],  # needs a paid AIS feed key — not available
        "notes": {"ships": "AIS/ships layer needs a marine-traffic API key (none configured)."},
    }
    if acled or natural:
        _cache["layers"] = (time.monotonic(), payload)
    return payload
