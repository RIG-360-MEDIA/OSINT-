"""District drill-down — a file on one district: summary + every kind of coverage we
hold for it (stance, top stories, who's in the news there, topics, quotes, claims,
events, outlets, language) + a live paginated article feed. Universe = articles
datelined to the district via article_districts. Source-grounded; bilingual.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

import i18n
from posture import POL

WH = 2160  # 90-day window (~ whole corpus for this dataset)


def _tone(sup: int, crit: int) -> str:
    if crit > sup * 1.25:
        return "hostile"
    if sup > crit * 1.25:
        return "supportive"
    return "neutral"


async def build_district_file(db, did: str) -> dict[str, Any]:
    ident = (await db.execute(text(
        "SELECT id::text id, name, state_code, hq_city FROM districts WHERE id = :d"
    ), {"d": did})).fetchone()
    if not ident:
        return {"found": False}
    p = {"d": did, "wh": WH}

    st = (await db.execute(text(f"""
        WITH da AS (
          SELECT a.id, (SELECT avg(({POL}) * st.intensity) FROM article_stances st WHERE st.article_id = a.id) lean
            FROM article_districts ad JOIN articles a ON a.id = ad.article_id
           WHERE ad.district_id = :d AND a.source_country = 'IN' AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh))
        SELECT count(*) articles,
               count(*) FILTER (WHERE lean >= 0.10) sup,
               count(*) FILTER (WHERE lean <= -0.10) crit,
               count(*) FILTER (WHERE lean > -0.10 AND lean < 0.10) neu
          FROM da
    """), p)).fetchone()
    sup, crit, neu = int(st.sup or 0), int(st.crit or 0), int(st.neu or 0)
    articles = int(st.articles or 0)

    n_quotes = (await db.execute(text("""
        SELECT count(*) FROM article_quotes q
         WHERE q.article_id IN (SELECT article_id FROM article_districts WHERE district_id = :d)
    """), {"d": did})).scalar() or 0

    top_stories = [{"id": r.id, "headline": r.title, "lang": r.lang, "source": r.src,
                    "thumbnail": r.thumb, "url": r.url,
                    "tone": "supportive" if (r.lean or 0) >= 0.1 else "hostile" if (r.lean or 0) <= -0.1 else "neutral"}
                   for r in (await db.execute(text(f"""
        SELECT a.id::text id, a.title, a.language_iso lang, s.name src, a.thumbnail_url thumb, a.url,
               (SELECT round(avg(({POL}) * st.intensity)::numeric, 2) FROM article_stances st WHERE st.article_id = a.id) lean
          FROM article_districts ad JOIN articles a ON a.id = ad.article_id JOIN sources s ON s.id = a.source_id
         WHERE ad.district_id = :d AND a.source_country = 'IN' AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
         ORDER BY a.collected_at DESC LIMIT 6
    """), p)).fetchall()]
    await i18n.attach_en(db, top_stories, "headline")

    entities = [{"name": r.nm, "type": r.et, "n": int(r.n)} for r in (await db.execute(text("""
        SELECT ed.canonical_name nm, ed.entity_type et, count(DISTINCT m.article_id) n
          FROM article_districts ad JOIN article_entity_mentions m ON m.article_id = ad.article_id
          JOIN entity_dictionary ed ON ed.id = m.entity_id JOIN articles a ON a.id = ad.article_id
         WHERE ad.district_id = :d AND a.source_country = 'IN' AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
           AND ed.entity_type IN ('person', 'organization')
         GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 8
    """), p)).fetchall()]

    topics = [{"label": (r.topic or "—").title(), "value": int(r.n)} for r in (await db.execute(text("""
        SELECT a.topic_category topic, count(DISTINCT a.id) n
          FROM article_districts ad JOIN articles a ON a.id = ad.article_id
         WHERE ad.district_id = :d AND a.source_country = 'IN' AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
           AND a.topic_category IS NOT NULL
         GROUP BY 1 ORDER BY 2 DESC LIMIT 6
    """), p)).fetchall()]

    quotes = [{"q": r.q, "q_en": (r.qen if (r.qen and r.qen != r.q) else None), "who": r.who or "—", "src": r.src}
              for r in (await db.execute(text("""
        SELECT q.quote_text q, NULLIF(q.quote_text_en, '') qen, COALESCE(q.speaker_name_en, q.speaker_name) who, s.name src
          FROM article_quotes q JOIN articles a ON a.id = q.article_id JOIN sources s ON s.id = a.source_id
         WHERE a.id IN (SELECT article_id FROM article_districts WHERE district_id = :d) AND a.source_country = 'IN'
           AND length(COALESCE(q.quote_text_en, q.quote_text)) BETWEEN 16 AND 280 AND q.speaker_name IS NOT NULL
         ORDER BY a.collected_at DESC LIMIT 4
    """), {"d": did})).fetchall()]
    await i18n.attach_en(db, quotes, "q")

    outlets = [{"name": r.nm, "pos": int(r.pos), "neg": int(r.neg)} for r in (await db.execute(text(f"""
        SELECT s.name nm, count(*) FILTER (WHERE ({POL}) > 0) pos, count(*) FILTER (WHERE ({POL}) < 0) neg
          FROM article_districts ad JOIN articles a ON a.id = ad.article_id
          JOIN sources s ON s.id = a.source_id JOIN article_stances st ON st.article_id = a.id
         WHERE ad.district_id = :d AND a.source_country = 'IN' AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
         GROUP BY s.name HAVING count(*) >= 3 ORDER BY count(DISTINCT a.id) DESC LIMIT 6
    """), p)).fetchall()]

    lang = {r.lang: int(r.n) for r in (await db.execute(text("""
        SELECT COALESCE(a.language_iso, '?') lang, count(DISTINCT a.id) n
          FROM article_districts ad JOIN articles a ON a.id = ad.article_id
         WHERE ad.district_id = :d AND a.source_country = 'IN' AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
         GROUP BY 1
    """), p)).fetchall()}

    # recent-activity narrative (adaptive 24h -> 7d), same shape as the entity file
    rec = (await db.execute(text(f"""
        SELECT a.title, EXTRACT(EPOCH FROM (analytics.now_sim() - a.collected_at)) / 3600.0 age_h, s.name src,
               (SELECT avg(({POL}) * st.intensity) FROM article_stances st WHERE st.article_id = a.id) lean
          FROM article_districts ad JOIN articles a ON a.id = ad.article_id JOIN sources s ON s.id = a.source_id
         WHERE ad.district_id = :d AND a.source_country = 'IN' AND a.collected_at >= analytics.now_sim() - make_interval(hours => 168)
         ORDER BY a.collected_at DESC LIMIT 60
    """), {"d": did})).fetchall()
    chosen, inwin = 168, list(rec)
    for whc in (24, 48, 72, 168):
        sub = [r for r in rec if r.age_h is not None and r.age_h <= whc]
        if len(sub) >= 3:
            chosen, inwin = whc, sub
            break
    name = ident.name.title()
    if not inwin:
        summary = f"{name} district has no fresh coverage in the last 7 days."
    else:
        wl = {24: "last 24 hours", 48: "last 48 hours", 72: "last 3 days", 168: "last 7 days"}[chosen]
        sr = sum(1 for r in inwin if (r.lean or 0) >= 0.1)
        cr = sum(1 for r in inwin if (r.lean or 0) <= -0.1)
        lead = inwin[0].title
        if not i18n.is_english(lead):
            lead = (await i18n.ensure_en(db, {inwin[0].title})).get(inwin[0].title) or lead
        tone = "supportive" if sr > cr else "critical" if cr > sr else "mixed"
        summary = (f"In the {wl}, {name} district saw {len(inwin)} {'story' if len(inwin) == 1 else 'stories'} "
                   f"({sr} supportive, {cr} critical, {tone}). Latest: “{lead}” ({inwin[0].src}).")

    return {
        "found": True, "id": did, "name": name, "state": ident.state_code, "hq": ident.hq_city,
        "tiles": {"articles": articles, "entities": len(entities), "quotes": int(n_quotes), "net": sup - crit},
        "standing": {"sup": sup, "crit": crit, "neu": neu},
        "summary": summary, "top_stories": top_stories, "entities": entities, "topics": topics,
        "quotes": quotes, "outlets": outlets,
        "reach": {"en": lang.get("en", 0), "te": lang.get("te", 0)},
        "window_days": round(WH / 24),
    }


async def district_articles(db, did: str, cursor: str | None, limit: int) -> dict[str, Any]:
    rows = (await db.execute(text(f"""
        SELECT a.id::text id, a.title, a.language_iso lang, s.name src, a.url, a.thumbnail_url thumb,
               a.collected_at,
               (SELECT round(avg(({POL}) * st.intensity)::numeric, 2) FROM article_stances st WHERE st.article_id = a.id) lean
          FROM article_districts ad JOIN articles a ON a.id = ad.article_id JOIN sources s ON s.id = a.source_id
         WHERE ad.district_id = :d AND a.source_country = 'IN'
           AND (CAST(:cursor AS timestamptz) IS NULL OR a.collected_at < CAST(:cursor AS timestamptz))
         ORDER BY a.collected_at DESC LIMIT :limit
    """), {"d": did, "cursor": cursor, "limit": limit})).fetchall()
    items = [{"id": r.id, "headline": r.title, "lang": r.lang, "source": r.src, "url": r.url,
              "thumbnail": r.thumb, "collected_at": str(r.collected_at) if r.collected_at else None,
              "tone": "supportive" if (r.lean or 0) >= 0.1 else "hostile" if (r.lean or 0) <= -0.1 else "neutral"}
             for r in rows]
    await i18n.attach_en(db, items, "headline")
    return {"articles": items, "next_cursor": str(rows[-1].collected_at) if len(rows) == limit else None}
