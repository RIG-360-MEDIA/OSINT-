"""Generic personalization engine (Category-6).

All pure functions of the user's prefs + corpus, reusing the persona-agnostic
relevance core. New user => new prefs row => these work immediately.

Features:
  - watchlist_relevance : the overload-killer ranked feed (relevance core)
  - auto_expand_watchlist : rising entities co-occurring with the user's world
                            but not yet on their watchlist -> suggested adds
  - morning_ritual : the single highest-signal thing to see today
(Personalized horizon + watchlist-driven scoring already ship via horizon.py /
relevance.py; this module adds the missing two and the daily hero card.)
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from posture import compute_posture
from relevance import score_relevant


async def watchlist_relevance(db, prefs: dict[str, Any], window_hours: int = 96,
                              limit: int = 10) -> dict[str, Any]:
    """Overload-killer: rank the user's relevant articles to a defensible top-N."""
    scored = await score_relevant(db, prefs, window_hours=window_hours, limit=limit)
    items = [{"id": r["id"], "title": r["title"], "source": r["source"], "topic": r["topic"],
              "matched": r["matched"], "score": r["score"]} for r in scored]
    return {"items": items, "n": len(items), "from_pool_window_h": window_hours}


async def auto_expand_watchlist(db, prefs: dict[str, Any], window_hours: int = 504,
                                limit: int = 8) -> dict[str, Any]:
    """Suggest entities that frequently co-occur with the user's watchlist in
    recent coverage but are NOT yet on it — candidate additions."""
    pid = prefs.get("primary_subject_id")
    meta = (prefs.get("watchlist") or {}).get("entity_meta") or []
    have = {m["id"] for m in meta if m.get("id")}
    if pid:
        have.add(pid)
    if not have:
        return {"suggestions": [], "n": 0}
    rows = (await db.execute(text("""
        SELECT e.entity_id::text id, max(e.canonical_name) name, e.entity_type, count(DISTINCT a.id) co
          FROM article_entity_mentions seed
          JOIN articles a ON a.id=seed.article_id
          JOIN article_entity_mentions e ON e.article_id=a.id AND e.entity_id<>seed.entity_id
         WHERE seed.entity_id = ANY(CAST(:have AS uuid[]))
           AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
           AND NOT (e.entity_id = ANY(CAST(:have AS uuid[])))
           AND e.entity_type IS NOT NULL
           AND lower(e.entity_type) NOT LIKE '%loc%' AND lower(e.entity_type) NOT LIKE '%gpe%'
           AND lower(e.entity_type) NOT LIKE '%place%' AND lower(e.entity_type) NOT LIKE '%fac%'
           AND lower(e.entity_type) NOT LIKE '%date%' AND lower(e.entity_type) NOT LIKE '%event%'
         GROUP BY e.entity_id, e.entity_type
        HAVING count(DISTINCT a.id) >= 5
         ORDER BY co DESC LIMIT :lim
    """), {"have": list(have), "wh": int(window_hours), "lim": int(limit)})).fetchall()
    sugg = [{"entity_id": r.id, "name": r.name, "type": r.entity_type, "co_mentions": int(r.co)} for r in rows]
    return {"suggestions": sugg, "n": len(sugg)}


async def morning_ritual(db, prefs: dict[str, Any], window_hours: int = 504,
                         textual: dict[str, Any] | None = None) -> dict[str, Any]:
    """The one card: the single highest-signal thing for this user today."""
    p = await compute_posture(db, prefs, window_hours)
    if not p.get("personalized"):
        return {"personalized": False, "headline": None}
    m = p["metrics"]
    foes = m["friend_foe_fence"]["hostile"]
    heat = m["target_heat"]["items"]
    pressure = m["weighted_pressure"]
    clg = m["cross_language_gap"]
    # priority: a hostile front > a top opposition target > a cross-language gap
    if foes:
        top = foes[0]
        headline = f"{top['outlet']} is your most hostile outlet ({top['favourability']:+}) this window."
        kind = "hostile_outlet"
    elif clg.get("gap") and clg["gap"] > 15:
        headline = f"Coverage of you is {clg['gap']} pts harsher in regional language than English."
        kind = "cross_language"
    elif heat:
        headline = f"{heat[0]['name']} is under the most fire (heat {heat[0]['heat']})."
        kind = "target_heat"
    else:
        headline = "Quiet window — no hostile fronts or pressure spikes on your watch."
        kind = "calm"
    bluf = (textual or {}).get("situation_room", {}).get("text") if textual else None
    return {"personalized": True, "subject": p["subject"], "kind": kind,
            "headline": headline, "pressure": pressure["pressure"],
            "detail": bluf}
