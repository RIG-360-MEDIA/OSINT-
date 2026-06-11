"""GET /api/brief/mood — Mood Waveform panel.

Phase 4.5. Returns a sentiment time-series for the brief's atmospheric
waveform visualisation. Each bucket is an hour wide; the value is the
mean of `article_stances.intensity` for articles collected in that hour.

Response shape:
  {
    "now": -0.32,                    # avg intensity over the whole window
    "now_label": "Negative",
    "buckets": [
      {"hour": "2026-05-27T06:00:00Z", "value": -0.31, "n": 142},
      ...
    ],
    "filters": {...}
  }

Filters:
  ?since_hours=24    width (default 24, max 168)
  ?country=IN        ISO 3166-1 alpha-2 source-country filter
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import text

from db import get_db

router = APIRouter(prefix="/api/brief", tags=["brief"])


def _label(v: float) -> str:
    if v >= 0.10: return "Positive"
    if v <= -0.10: return "Negative"
    return "Neutral"


@router.get("/mood")
async def get_mood(
    since_hours: int = Query(default=24, ge=1, le=168),
    country: str | None = Query(default=None, pattern=r"^[A-Z]{2}$"),
) -> dict[str, Any]:
    """Hourly sentiment series + aggregate 'now' mood."""
    window = f"INTERVAL '{int(since_hours)} hours'"
    cc = "AND a.source_country = :country" if country else ""
    params: dict[str, Any] = {}
    if country:
        params["country"] = country

    async with get_db() as db:
        rows = (await db.execute(text(f"""
            SELECT date_trunc('hour', a.collected_at) AS h,
                   AVG(s.intensity) AS avg_i,
                   COUNT(*) AS n
              FROM article_stances s
              JOIN articles a ON a.id = s.article_id
             WHERE s.intensity IS NOT NULL
               AND a.collected_at >= analytics.now_sim() - {window}
               AND a.collected_at <= analytics.now_sim()
               {cc}
             GROUP BY 1
             ORDER BY 1
        """), params)).fetchall()

        agg = (await db.execute(text(f"""
            SELECT AVG(s.intensity) AS avg_i, COUNT(*) AS n
              FROM article_stances s
              JOIN articles a ON a.id = s.article_id
             WHERE s.intensity IS NOT NULL
               AND a.collected_at >= analytics.now_sim() - {window}
               AND a.collected_at <= analytics.now_sim()
               {cc}
        """), params)).fetchone()

    now_v = float(agg.avg_i) if agg and agg.avg_i is not None else 0.0
    buckets = [{
        "hour": r.h.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "value": round(float(r.avg_i), 3),
        "n": int(r.n),
    } for r in rows]

    return {
        "now": round(now_v, 3),
        "now_label": _label(now_v),
        "buckets": buckets,
        "total_n": int(agg.n) if agg else 0,
        "filters": {"since_hours": since_hours, "country": country},
    }
