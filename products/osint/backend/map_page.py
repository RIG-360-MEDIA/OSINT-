"""Situation-Map data — persona-scoped district/state bubbles for the Map page.

scope='mine'   -> districts of the persona's PRIMARY state (centroid bubbles: volume + stance),
                  plus a bbox to fly-zoom into (world -> e.g. Andhra Pradesh).
scope='global' -> per-state rollup across the whole corpus (+ later fused with World Monitor layers).

Bubbles use districts.centroid_lat/lon (present for all Indian districts) — no external GeoJSON
needed, and it matches the World-Monitor dot aesthetic. Stance via the vetted POL map.
"""
from __future__ import annotations

from typing import Any

from collections import Counter

from sqlalchemy import text

import country_centroids
import i18n
from posture import POL, principal_of

WH = 504  # 21-day window
FEED_WH = 168  # live feed: last 7 days, newest first

# Indian state name -> districts.state_code (extend as personas grow).
STATE_CODE = {
    "andhra pradesh": "AP", "telangana": "TG", "karnataka": "KA", "tamil nadu": "TN",
    "kerala": "KL", "maharashtra": "MH", "delhi": "DL", "uttar pradesh": "UP",
    "west bengal": "WB", "gujarat": "GJ", "rajasthan": "RJ", "madhya pradesh": "MP",
    "bihar": "BR", "odisha": "OD", "punjab": "PB", "haryana": "HR", "goa": "GA",
}


def _primary_state_code(prefs: dict[str, Any]) -> str | None:
    states = (prefs.get("regions") or {}).get("states") or []
    for s in states:
        code = STATE_CODE.get((s or "").strip().lower())
        if code:
            return code
    return None


def _tone(sup: int, crit: int) -> str:
    if crit > sup * 1.25:
        return "hostile"
    if sup > crit * 1.25:
        return "supportive"
    return "neutral"


async def _district_bubbles(db, state_code: str) -> list[dict[str, Any]]:
    rows = (await db.execute(text(f"""
        WITH da AS (
          SELECT d.id did, d.name dist, d.centroid_lat lat, d.centroid_lon lon, a.id,
                 a.topic_category topic,
                 (SELECT avg(({POL}) * st.intensity) FROM article_stances st WHERE st.article_id = a.id) lean
            FROM districts d
            JOIN article_districts ad ON ad.district_id = d.id
            JOIN articles a ON a.id = ad.article_id
           WHERE d.state_code = :sc
             AND a.source_country = 'IN'  -- drop foreign false-positive geo-tags
             AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
        )
        SELECT did, dist, lat, lon, count(*) articles,
               count(*) FILTER (WHERE lean >= 0.10) sup,
               count(*) FILTER (WHERE lean <= -0.10) crit,
               mode() WITHIN GROUP (ORDER BY topic) top_topic
          FROM da WHERE lat IS NOT NULL
         GROUP BY did, dist, lat, lon ORDER BY articles DESC
    """), {"sc": state_code, "wh": WH})).fetchall()
    out = []
    for r in rows:
        sup, crit = int(r.sup), int(r.crit)
        out.append({
            "id": r.did, "name": r.dist.title(), "lat": float(r.lat), "lon": float(r.lon),
            "articles": int(r.articles), "sup": sup, "crit": crit,
            "net": sup - crit, "tone": _tone(sup, crit), "topic": r.top_topic,
        })
    return out


async def _state_bubbles(db) -> list[dict[str, Any]]:
    """Global rollup: one bubble per state (centroid = mean of its district centroids)."""
    rows = (await db.execute(text(f"""
        WITH da AS (
          SELECT d.state_code sc, d.centroid_lat lat, d.centroid_lon lon, a.id,
                 (SELECT avg(({POL}) * st.intensity) FROM article_stances st WHERE st.article_id = a.id) lean
            FROM districts d
            JOIN article_districts ad ON ad.district_id = d.id
            JOIN articles a ON a.id = ad.article_id
           WHERE a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
        )
        SELECT sc, avg(lat) lat, avg(lon) lon, count(*) articles,
               count(*) FILTER (WHERE lean >= 0.10) sup,
               count(*) FILTER (WHERE lean <= -0.10) crit
          FROM da WHERE lat IS NOT NULL
         GROUP BY sc ORDER BY articles DESC
    """), {"wh": WH})).fetchall()
    out = []
    for r in rows:
        sup, crit = int(r.sup), int(r.crit)
        out.append({
            "name": r.sc, "lat": float(r.lat), "lon": float(r.lon),
            "articles": int(r.articles), "sup": sup, "crit": crit,
            "net": sup - crit, "tone": _tone(sup, crit),
        })
    return out


def _lean_tone(lean: float | None) -> str:
    if (lean or 0) >= 0.1:
        return "supportive"
    if (lean or 0) <= -0.1:
        return "hostile"
    return "neutral"


async def _region_feed(db, state_code: str | None) -> list[dict[str, Any]]:
    """Newest geo-tagged stories — for the persona's state (mine) or corpus-wide (global)."""
    if state_code:
        sql = f"""
            SELECT DISTINCT a.id::text id, a.title, a.language_iso lang, s.name src, a.url,
                   a.thumbnail_url thumb, a.collected_at,
                   (SELECT round(avg(({POL}) * st.intensity)::numeric, 2) FROM article_stances st WHERE st.article_id = a.id) lean
              FROM article_districts ad JOIN districts d ON d.id = ad.district_id
              JOIN articles a ON a.id = ad.article_id JOIN sources s ON s.id = a.source_id
             WHERE d.state_code = :sc AND a.source_country = 'IN'
               AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
             ORDER BY a.collected_at DESC LIMIT 12
        """
        params = {"sc": state_code, "wh": FEED_WH}
    else:
        # Global feed: newest stories from anywhere in the world (any known country).
        sql = f"""
            SELECT a.id::text id, a.title, a.language_iso lang, s.name src, a.url,
                   a.thumbnail_url thumb, a.collected_at,
                   (SELECT round(avg(({POL}) * st.intensity)::numeric, 2) FROM article_stances st WHERE st.article_id = a.id) lean
              FROM articles a JOIN sources s ON s.id = a.source_id
             WHERE a.source_country IS NOT NULL AND a.source_country <> 'XX'
               AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
             ORDER BY a.collected_at DESC LIMIT 12
        """
        params = {"wh": FEED_WH}
    rows = (await db.execute(text(sql), params)).fetchall()
    feed = [{"id": r.id, "headline": r.title, "lang": r.lang, "source": r.src, "url": r.url,
             "thumbnail": r.thumb, "collected_at": str(r.collected_at) if r.collected_at else None,
             "tone": _lean_tone(r.lean)} for r in rows]
    await i18n.attach_en(db, feed, "headline")
    return feed


def _situation(bubbles: list[dict[str, Any]], region: str, window_days: int, unit: str = "district") -> str:
    """A factual restatement of the aggregate — no inference beyond what the data says."""
    if not bubbles:
        return f"No mapped coverage for {region} in the last {window_days} days."
    total = sum(b["articles"] for b in bubbles)
    sup = sum(b["sup"] for b in bubbles)
    crit = sum(b["crit"] for b in bubbles)
    top = max(bubbles, key=lambda b: b["articles"])
    topics = Counter(b["topic"] for b in bubbles
                     if b.get("topic") and str(b["topic"]).upper() != "OTHER")
    tone = "supportive" if sup > crit * 1.25 else "critical" if crit > sup * 1.25 else "mixed"
    units = unit if len(bubbles) == 1 else f"{unit}s"
    parts = [f"Across {region}, {total:,} stories landed in the last {window_days} days "
             f"from {len(bubbles)} {units} ({sup} supportive, {crit} critical — {tone})."]
    parts.append(f"{top['name']} leads with {top['articles']:,} stories.")
    if topics:
        parts.append(f"Coverage skews toward {topics.most_common(1)[0][0]}.")
    return " ".join(parts)


async def _country_bubbles(db) -> list[dict[str, Any]]:
    """Whole-corpus rollup: one bubble per country (source_country), placed at the
    country centroid. This is the TRUE global/world view — spans the whole world."""
    rows = (await db.execute(text(f"""
        WITH win AS (
          SELECT a.id, a.source_country sc
            FROM articles a
           WHERE a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
             AND a.source_country IS NOT NULL AND a.source_country NOT IN ('XX')
        ), sl AS (
          SELECT st.article_id, avg(({POL}) * st.intensity) lean
            FROM article_stances st JOIN win ON win.id = st.article_id
           GROUP BY st.article_id
        )
        SELECT w.sc, count(*) articles,
               count(*) FILTER (WHERE sl.lean >= 0.10) sup,
               count(*) FILTER (WHERE sl.lean <= -0.10) crit
          FROM win w LEFT JOIN sl ON sl.article_id = w.id
         GROUP BY w.sc ORDER BY 2 DESC
    """), {"wh": WH})).fetchall()
    out = []
    for r in rows:
        c = country_centroids.centroid(r.sc)
        if not c:
            continue
        lat, lon, name = c
        sup, crit = int(r.sup), int(r.crit)
        out.append({"id": r.sc, "name": name, "lat": lat, "lon": lon,
                    "articles": int(r.articles), "sup": sup, "crit": crit,
                    "net": sup - crit, "tone": _tone(sup, crit), "topic": None})
    return out


def _bbox(bubbles: list[dict[str, Any]]) -> dict[str, float] | None:
    pts = [(b["lat"], b["lon"]) for b in bubbles if b.get("lat") is not None]
    if not pts:
        return None
    lats = [p[0] for p in pts]
    lons = [p[1] for p in pts]
    return {"minLat": min(lats), "maxLat": max(lats), "minLon": min(lons), "maxLon": max(lons),
            "centerLat": sum(lats) / len(lats), "centerLon": sum(lons) / len(lons)}


async def build_map(db, prefs: dict[str, Any], scope: str = "mine") -> dict[str, Any]:
    pid, pname = principal_of(prefs)
    wd = round(WH / 24)
    if scope == "global":
        bubbles = await _country_bubbles(db)
        return {"scope": "global", "level": "country", "region": "The whole world",
                "bubbles": bubbles, "bbox": _bbox(bubbles), "window_days": wd,
                "feed": await _region_feed(db, None),
                "situation": _situation(bubbles, "the whole world", wd, unit="country")}

    sc = _primary_state_code(prefs)
    if not sc:
        # no mapped primary state — fall back to global
        bubbles = await _state_bubbles(db)
        return {"scope": "mine", "level": "state", "region": "All coverage",
                "bubbles": bubbles, "bbox": _bbox(bubbles), "window_days": wd,
                "feed": await _region_feed(db, None),
                "situation": _situation(bubbles, "all coverage", wd),
                "note": "No mapped primary state; showing all."}
    region = next((s for s in (prefs.get("regions") or {}).get("states", [])
                   if STATE_CODE.get((s or "").lower()) == sc), sc)
    bubbles = await _district_bubbles(db, sc)
    return {"scope": "mine", "level": "district", "region": region, "state_code": sc,
            "principal": pname, "bubbles": bubbles, "bbox": _bbox(bubbles),
            "window_days": wd, "feed": await _region_feed(db, sc),
            "situation": _situation(bubbles, region, wd)}
