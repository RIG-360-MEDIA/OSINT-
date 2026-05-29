"""GET /api/brief/horizon — Horizon 7-day calendar panel.

Phase 4.4. Returns an array of `days` (default 7) starting at sim_today,
each with a list of upcoming events on that date pulled from
`article_events.effective_event_date`. Each event carries its type,
source outlet, confidence score (from the LLM extractor), description
preview, and the originating cluster id when joinable.

Filter params:
  ?days=7                  width of the look-ahead in days (1-30)
  ?country=IN              ISO alpha-2 source-country filter on articles
  ?event_types=cabinet,court,election  comma-list to restrict
  ?min_confidence=0.5      drop low-confidence extractions
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import text

from db import get_db

router = APIRouter(prefix="/api/brief", tags=["brief"])


# Visual tone hints per event type — overrideable per-design later.
TYPE_TONE = {
    "cabinet": "amber", "approval": "cyan", "release": "green",
    "announcement": "amber", "election": "rose", "court": "violet",
    "hearing": "violet", "ruling": "violet", "sports_result": "green",
    "press_briefing": "cyan", "summit": "amber", "rally": "rose",
    "policy_launch": "amber", "budget": "cyan",
}


@router.get("/horizon")
async def get_horizon(
    days: int = Query(default=7, ge=1, le=30),
    country: str | None = Query(default=None, pattern=r"^[A-Z]{2}$"),
    event_types: str | None = Query(default=None, max_length=400),
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
    per_day_limit: int = Query(default=5, ge=1, le=20),
) -> dict[str, Any]:
    """Return upcoming events grouped by date for the next `days` days."""
    cc_clause = "AND a.source_country = :country" if country else ""
    et_clause = ""
    params: dict[str, Any] = {
        "days": int(days),
        "min_conf": float(min_confidence),
    }
    if country:
        params["country"] = country
    if event_types:
        types = [t.strip().lower() for t in event_types.split(",") if t.strip()]
        if types:
            placeholders = ", ".join(f":et{i}" for i in range(len(types)))
            et_clause = f"AND LOWER(ae.event_type) IN ({placeholders})"
            for i, t in enumerate(types):
                params[f"et{i}"] = t

    async with get_db() as db:
        rows = (await db.execute(text(f"""
            SELECT ae.effective_event_date AS dt,
                   ae.event_type,
                   ae.event_description,
                   ae.confidence,
                   ae.actors,
                   ae.event_cluster_id::text AS cluster_id,
                   s.name AS source
              FROM article_events ae
              JOIN articles a ON a.id = ae.article_id
              JOIN sources s  ON s.id = a.source_id
             WHERE ae.effective_event_date >= analytics.now_sim_date()
               AND ae.effective_event_date <= analytics.now_sim_date() + CAST(:days AS INTEGER)
               AND ae.effective_event_date <= '2030-12-31'   -- guard vs hallucinated far-future
               AND ae.event_description IS NOT NULL
               AND LENGTH(ae.event_description) >= 10
               AND COALESCE(ae.confidence, 1.0) >= :min_conf
               {cc_clause}
               {et_clause}
             ORDER BY ae.effective_event_date, ae.confidence DESC NULLS LAST
             LIMIT 400
        """), params)).fetchall()

    # Bucket by date, cap per day
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        key = r.dt.strftime("%Y-%m-%d")
        if len(by_day[key]) >= per_day_limit:
            continue
        etype = (r.event_type or "event").lower()
        by_day[key].append({
            "type": etype,
            "tone": TYPE_TONE.get(etype, "amber"),
            "description": (r.event_description or "")[:160],
            "actors": (list(r.actors)[:3] if r.actors else []),
            "confidence": round(float(r.confidence or 0), 2),
            "source": r.source or "—",
            "cluster_id": r.cluster_id,
        })

    # Emit a row PER DAY for the next `days` so the frontend can render the
    # calendar even on quiet days (empty events list).
    async with get_db() as db:
        start_row = (await db.execute(text(
            "SELECT analytics.now_sim_date() AS d"
        ))).fetchone()
    today = start_row.d

    from datetime import timedelta
    out_days = []
    for i in range(int(days)):
        d = today + timedelta(days=i)
        key = d.strftime("%Y-%m-%d")
        events = by_day.get(key, [])
        out_days.append({
            "date": key,
            "day_label": d.strftime("%a · %d %b"),
            "is_today": i == 0,
            "events_count": len(events),
            "events": events,
        })

    total_events = sum(d["events_count"] for d in out_days)
    return {
        "days": out_days,
        "total_events": total_events,
        "filters": {
            "days": days,
            "country": country,
            "event_types": event_types,
            "min_confidence": min_confidence,
            "per_day_limit": per_day_limit,
        },
    }
