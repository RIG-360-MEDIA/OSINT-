"""
Shared helpers for the CM Page v2 external-source collectors.

Every Phase 3 scraper:
  - records its run health to the ``source_run_health`` table so the
    atlas-layer endpoint can flag a layer as ``stale`` when last
    success > 24h.
  - reverse-resolves lat/lon (when present) to a Telangana district
    via simple containment-or-nearest-centroid lookup.
  - matches a place-name string to a district id via the ``aliases``
    column on ``districts``.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ── Run-health upsert ────────────────────────────────────────────────────


async def record_run_health(
    db: AsyncSession,
    source_id: str,
    *,
    success: bool,
    rows: int = 0,
    error: str | None = None,
) -> None:
    """Idempotent upsert into ``source_run_health``. Increments
    consecutive_failures on failure, resets to 0 on success."""
    sql = """
        INSERT INTO source_run_health (
            source_id, last_success_at, last_failure_at, last_failure,
            consecutive_failures, rows_last_run, updated_at
        ) VALUES (
            :sid,
            CASE WHEN :success THEN now() ELSE NULL END,
            CASE WHEN :success THEN NULL ELSE now() END,
            :error,
            CASE WHEN :success THEN 0 ELSE 1 END,
            :rows,
            now()
        )
        ON CONFLICT (source_id) DO UPDATE SET
            last_success_at = CASE WHEN :success THEN now()
                                   ELSE source_run_health.last_success_at END,
            last_failure_at = CASE WHEN :success THEN source_run_health.last_failure_at
                                   ELSE now() END,
            last_failure = CASE WHEN :success THEN source_run_health.last_failure
                                ELSE :error END,
            consecutive_failures = CASE WHEN :success THEN 0
                                        ELSE source_run_health.consecutive_failures + 1 END,
            rows_last_run = :rows,
            updated_at = now()
    """
    await db.execute(
        text(sql),
        {"sid": source_id, "success": success, "rows": rows, "error": (error or "")[:480]},
    )


# ── District resolution from a place-name string ─────────────────────────


_DISTRICT_LOOKUP_CACHE: list[dict[str, Any]] | None = None


async def _load_district_lookup(db: AsyncSession) -> list[dict[str, Any]]:
    global _DISTRICT_LOOKUP_CACHE
    if _DISTRICT_LOOKUP_CACHE is not None:
        return _DISTRICT_LOOKUP_CACHE
    rows = (await db.execute(
        text("SELECT id, name, hq_city, aliases, centroid_lat, centroid_lon FROM districts")
    )).all()
    _DISTRICT_LOOKUP_CACHE = [
        {
            "id": r.id,
            "candidates": [
                s.lower()
                for s in (
                    [r.name, r.hq_city] + list(r.aliases or [])
                )
                if s
            ],
            "centroid_lat": r.centroid_lat,
            "centroid_lon": r.centroid_lon,
        }
        for r in rows
    ]
    return _DISTRICT_LOOKUP_CACHE


def reset_district_lookup_cache() -> None:
    global _DISTRICT_LOOKUP_CACHE
    _DISTRICT_LOOKUP_CACHE = None


async def district_for_name(db: AsyncSession, name: str | None) -> str | None:
    """Best-effort name → district_id. Case-insensitive substring match
    against district name + hq_city + aliases. Returns the first match
    or None."""
    if not name:
        return None
    haystack = name.lower().strip()
    rows = await _load_district_lookup(db)
    for row in rows:
        for cand in row["candidates"]:
            if cand and cand in haystack:
                return row["id"]
    return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = p2 - p1
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


async def district_for_lat_lon(
    db: AsyncSession,
    lat: float | None,
    lon: float | None,
) -> str | None:
    """Nearest-centroid lookup (simple, good enough for sub-state events).
    Returns None when either coord is missing."""
    if lat is None or lon is None:
        return None
    rows = await _load_district_lookup(db)
    if not rows:
        return None
    best: tuple[float, str] | None = None
    for r in rows:
        if r["centroid_lat"] is None or r["centroid_lon"] is None:
            continue
        d = _haversine_km(lat, lon, r["centroid_lat"], r["centroid_lon"])
        if best is None or d < best[0]:
            best = (d, r["id"])
    if best is None:
        return None
    # If the nearest district is > 80 km away the point is probably
    # outside Telangana entirely; return None so the caller can skip
    # rather than mis-attribute.
    return best[1] if best[0] <= 80.0 else None


__all__ = [
    "district_for_lat_lon",
    "district_for_name",
    "record_run_health",
    "reset_district_lookup_cache",
]
