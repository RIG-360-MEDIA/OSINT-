"""Country drill-down for the GLOBAL world map — a file on one country: summary +
coverage (stance, top stories, topics, outlets, language) + a paginated feed.
Universe = articles whose source_country = the ISO-2 code. Source-grounded; bilingual.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

import country_centroids
import i18n
from posture import POL

WH = 504  # 21-day window


async def build_country_file(db, iso: str) -> dict[str, Any]:
    iso = (iso or "").strip().upper()
    cc = country_centroids.centroid(iso)
    if not cc:
        return {"found": False}
    name = cc[2]
    p = {"c": iso, "wh": WH}

    st = (await db.execute(text(f"""
        WITH da AS (
          SELECT a.id, (SELECT avg(({POL}) * st.intensity) FROM article_stances st WHERE st.article_id = a.id) lean
            FROM articles a
           WHERE a.source_country = :c AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
        )
        SELECT count(*) articles,
               count(*) FILTER (WHERE lean >= 0.10) sup,
               count(*) FILTER (WHERE lean <= -0.10) crit,
               count(*) FILTER (WHERE lean > -0.10 AND lean < 0.10) neu
          FROM da
    """), p)).fetchone()
    sup, crit, neu = int(st.sup or 0), int(st.crit or 0), int(st.neu or 0)
    articles = int(st.articles or 0)
    if articles == 0:
        return {"found": False}

    n_sources = (await db.execute(text("""
        SELECT count(DISTINCT a.source_id) FROM articles a
         WHERE a.source_country = :c AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
    """), p)).scalar() or 0
    n_quotes = (await db.execute(text("""
        SELECT count(*) FROM article_quotes q JOIN articles a ON a.id = q.article_id
         WHERE a.source_country = :c AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
    """), p)).scalar() or 0

    top_stories = [{"id": r.id, "headline": r.title, "lang": r.lang, "source": r.src,
                    "thumbnail": r.thumb, "url": r.url,
                    "tone": "supportive" if (r.lean or 0) >= 0.1 else "hostile" if (r.lean or 0) <= -0.1 else "neutral"}
                   for r in (await db.execute(text(f"""
        SELECT a.id::text id, a.title, a.language_iso lang, s.name src, a.thumbnail_url thumb, a.url,
               (SELECT round(avg(({POL}) * st.intensity)::numeric, 2) FROM article_stances st WHERE st.article_id = a.id) lean
          FROM articles a JOIN sources s ON s.id = a.source_id
         WHERE a.source_country = :c AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
         ORDER BY a.collected_at DESC LIMIT 6
    """), p)).fetchall()]
    await i18n.attach_en(db, top_stories, "headline")

    topics = [{"label": (r.topic or "—").title(), "value": int(r.n)} for r in (await db.execute(text("""
        SELECT a.topic_category topic, count(DISTINCT a.id) n
          FROM articles a
         WHERE a.source_country = :c AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
           AND a.topic_category IS NOT NULL AND upper(a.topic_category) <> 'OTHER'
         GROUP BY 1 ORDER BY 2 DESC LIMIT 6
    """), p)).fetchall()]

    outlets = [{"name": r.nm, "pos": int(r.pos), "neg": int(r.neg)} for r in (await db.execute(text(f"""
        SELECT s.name nm, count(*) FILTER (WHERE ({POL}) > 0) pos, count(*) FILTER (WHERE ({POL}) < 0) neg
          FROM articles a JOIN sources s ON s.id = a.source_id JOIN article_stances st ON st.article_id = a.id
         WHERE a.source_country = :c AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
         GROUP BY s.name HAVING count(*) >= 3 ORDER BY count(DISTINCT a.id) DESC LIMIT 6
    """), p)).fetchall()]

    lang = {r.lang: int(r.n) for r in (await db.execute(text("""
        SELECT COALESCE(a.language_iso, '?') lang, count(DISTINCT a.id) n FROM articles a
         WHERE a.source_country = :c AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
         GROUP BY 1 ORDER BY 2 DESC LIMIT 4
    """), p)).fetchall()}

    rec = (await db.execute(text(f"""
        SELECT a.title, EXTRACT(EPOCH FROM (analytics.now_sim() - a.collected_at)) / 3600.0 age_h, s.name src,
               (SELECT avg(({POL}) * st.intensity) FROM article_stances st WHERE st.article_id = a.id) lean
          FROM articles a JOIN sources s ON s.id = a.source_id
         WHERE a.source_country = :c AND a.collected_at >= analytics.now_sim() - make_interval(hours => 168)
         ORDER BY a.collected_at DESC LIMIT 60
    """), {"c": iso})).fetchall()
    chosen, inwin = 168, list(rec)
    for whc in (24, 48, 72, 168):
        sub = [r for r in rec if r.age_h is not None and r.age_h <= whc]
        if len(sub) >= 3:
            chosen, inwin = whc, sub
            break
    if not inwin:
        summary = f"{name} has no fresh coverage in the last 7 days."
    else:
        wl = {24: "last 24 hours", 48: "last 48 hours", 72: "last 3 days", 168: "last 7 days"}[chosen]
        sr = sum(1 for r in inwin if (r.lean or 0) >= 0.1)
        cr = sum(1 for r in inwin if (r.lean or 0) <= -0.1)
        lead = inwin[0].title
        if not i18n.is_english(lead):
            lead = (await i18n.ensure_en(db, {inwin[0].title})).get(inwin[0].title) or lead
        tone = "supportive" if sr > cr else "critical" if cr > sr else "mixed"
        summary = (f"In the {wl}, {name} saw {len(inwin)} {'story' if len(inwin) == 1 else 'stories'} "
                   f"({sr} supportive, {cr} critical, {tone}). Latest: “{lead}” ({inwin[0].src}).")

    return {
        "found": True, "iso": iso, "name": name,
        "tiles": {"articles": articles, "sources": int(n_sources), "quotes": int(n_quotes), "net": sup - crit},
        "standing": {"sup": sup, "crit": crit, "neu": neu},
        "summary": summary, "top_stories": top_stories, "topics": topics, "outlets": outlets,
        "languages": lang, "window_days": round(WH / 24),
    }


async def country_articles(db, iso: str, cursor: str | None, limit: int) -> dict[str, Any]:
    iso = (iso or "").strip().upper()
    rows = (await db.execute(text(f"""
        SELECT a.id::text id, a.title, a.language_iso lang, s.name src, a.url, a.thumbnail_url thumb, a.collected_at,
               (SELECT round(avg(({POL}) * st.intensity)::numeric, 2) FROM article_stances st WHERE st.article_id = a.id) lean
          FROM articles a JOIN sources s ON s.id = a.source_id
         WHERE a.source_country = :c
           AND (CAST(:cursor AS timestamptz) IS NULL OR a.collected_at < CAST(:cursor AS timestamptz))
         ORDER BY a.collected_at DESC LIMIT :limit
    """), {"c": iso, "cursor": cursor, "limit": limit})).fetchall()
    items = [{"id": r.id, "headline": r.title, "lang": r.lang, "source": r.src, "url": r.url,
              "thumbnail": r.thumb, "collected_at": str(r.collected_at) if r.collected_at else None,
              "tone": "supportive" if (r.lean or 0) >= 0.1 else "hostile" if (r.lean or 0) <= -0.1 else "neutral"}
             for r in rows]
    await i18n.attach_en(db, items, "headline")
    return {"articles": items, "next_cursor": str(rows[-1].collected_at) if len(rows) == limit else None}
