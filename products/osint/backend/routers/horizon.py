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

import re
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from auth.middleware import get_optional_user
from brief_prefs import load_prefs
from db import get_db
from relevance import score_relevant

router = APIRouter(prefix="/api/brief", tags=["brief"])


# Visual tone hints per event type — overrideable per-design later.
TYPE_TONE = {
    "cabinet": "amber", "approval": "cyan", "release": "green",
    "announcement": "amber", "election": "rose", "court": "violet",
    "hearing": "violet", "ruling": "violet", "sports_result": "green",
    "press_briefing": "cyan", "summit": "amber", "rally": "rose",
    "policy_launch": "amber", "budget": "cyan",
}


_NOISE_TYPES = {"sports_result", "sports", "entertainment", "film", "celebrity"}


@router.get("/horizon")
async def get_horizon(
    window_days: int = Query(default=14, ge=3, le=30),
    limit: int = Query(default=14, ge=1, le=40),
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    """Genuinely-scheduled upcoming items, gated to THIS user's coverage.

    Pulls strictly-future events (article_events.effective_event_date > today)
    only from the user's relevant, score-floored articles — so a Telangana CM
    gets Telangana's calendar, not corpus-wide noise. This is NOT a forecast:
    every item is something the coverage has already put on the record.
    """
    async with get_db() as db:
        prefs = await load_prefs(db, user["id"]) if user else None
        ids: list[str] = []
        if prefs:
            scored = await score_relevant(db, prefs, window_hours=120, limit=160)
            # Floor on relevance to drop the marginal articles that drag in
            # crime / entertainment noise.
            ids = [r["id"] for r in scored if r["score"] >= 1.5]

        common = """
            ae.effective_event_date dt, ae.event_type, ae.event_description, ae.actors,
            s.name source, a.url
        """
        if ids:
            rows = (await db.execute(text(f"""
                SELECT {common}
                  FROM article_events ae
                  JOIN articles a ON a.id = ae.article_id
                  JOIN sources s  ON s.id = a.source_id
                 WHERE ae.article_id = ANY(CAST(:ids AS uuid[]))
                   AND ae.effective_event_date >  analytics.now_sim_date()
                   AND ae.effective_event_date <= analytics.now_sim_date() + CAST(:wd AS INTEGER)
                   AND ae.event_description IS NOT NULL AND LENGTH(ae.event_description) >= 14
                   AND LOWER(COALESCE(ae.event_type, '')) <> ALL(CAST(:noise AS text[]))
                 ORDER BY ae.effective_event_date, ae.confidence DESC NULLS LAST
                 LIMIT 120
            """), {"ids": ids, "wd": int(window_days), "noise": list(_NOISE_TYPES)})).fetchall()
            personalized = True
        else:
            rows = (await db.execute(text(f"""
                SELECT {common}
                  FROM article_events ae
                  JOIN articles a ON a.id = ae.article_id
                  JOIN sources s  ON s.id = a.source_id
                 WHERE ae.effective_event_date >  analytics.now_sim_date()
                   AND ae.effective_event_date <= analytics.now_sim_date() + CAST(:wd AS INTEGER)
                   AND a.source_country = 'IN'
                   AND ae.event_description IS NOT NULL AND LENGTH(ae.event_description) >= 14
                   AND LOWER(COALESCE(ae.event_type, '')) <> ALL(CAST(:noise AS text[]))
                 ORDER BY ae.effective_event_date, ae.confidence DESC NULLS LAST
                 LIMIT 120
            """), {"wd": int(window_days), "noise": list(_NOISE_TYPES)})).fetchall()
            personalized = False

    seen: set[str] = set()
    events: list[dict[str, Any]] = []
    for r in rows:
        key = re.sub(r"[^a-z0-9]+", " ", (r.event_description or "").lower()).strip()[:60]
        if not key or key in seen:
            continue
        seen.add(key)
        etype = (r.event_type or "event").lower()
        events.append({
            "date": r.dt.strftime("%Y-%m-%d"),
            "day_label": r.dt.strftime("%a · %d %b"),
            "type": etype.replace("_", " "),
            "tone": TYPE_TONE.get(etype, "amber"),
            "title": (r.event_description or "").strip()[:140],
            "actors": list(r.actors)[:3] if r.actors else [],
            "source": r.source or "—",
            "url": r.url,
        })
        if len(events) >= int(limit):
            break

    return {"personalized": personalized, "events": events, "window_days": window_days}
