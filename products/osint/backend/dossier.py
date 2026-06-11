"""Dossier — a file on every watched entity, plus a live whole-corpus article feed.

  * build_roster(db, prefs)         — every watchlist entity: name, role, alignment,
                                       lifetime mention count, portrait (analytics.entity_image).
  * build_entity_file(db, eid, prefs) — the open file: identity, tiles, standing, share-of-voice,
                                       issues, pulse, quotes-by, claims-about, network, outlets,
                                       reach, timeline, an auto summary. Windowed (90d ~ corpus here).
  * entity_articles(db, eid, cursor, limit) — paginated, NEWEST-FIRST, WHOLE corpus. The "all
                                       articles related to them, latest on top, updates daily" feed.

Source-grounded only. Stance maths reuse posture's POL map + _BODY_PRESENT hallucination filter,
so a mention counts only when the entity's surface form is actually in the article text.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

import i18n
from posture import POL, _BODY_PRESENT

STATS_WH = 2160  # 90 days — the corpus only spans ~7 weeks, so this is effectively all-time
PULSE_DAYS = 21

_TYPE_MAP = {"organization": "org", "location": "place", "person": "person"}


def _ui_type(t: str | None) -> str:
    return _TYPE_MAP.get((t or "").lower(), "person")


def _tone(sup: int, crit: int) -> str:
    if crit > sup * 1.25:
        return "hostile"
    if sup > crit * 1.25:
        return "supportive"
    return "neutral"


def _align(sup: int, crit: int) -> str:
    if crit > sup * 1.25:
        return "against"
    if sup > crit * 1.25:
        return "for"
    return "neutral"


# ───────────────────────── ROSTER ─────────────────────────
async def build_roster(db, prefs: dict[str, Any]) -> dict[str, Any]:
    meta = list(prefs["watchlist"]["entity_meta"])
    pid = prefs.get("primary_subject_id")
    # The principal is the primary_subject, NOT a watchlist entry — ensure they
    # always have a file in their own registry (pinned first below).
    if pid and not any(m.get("id") == pid for m in meta):
        prow = (await db.execute(text("""
            SELECT canonical_name, entity_type, party, state FROM entity_dictionary WHERE id = CAST(:p AS uuid)
        """), {"p": pid})).fetchone()
        pname = ((prefs.get("primary_subject_meta") or {}).get("name")
                 or (prow.canonical_name if prow else "Principal"))
        meta.insert(0, {"id": pid, "name": pname,
                        "type": (prow.entity_type if prow else "person"),
                        "party": (prow.party if prow else ""),
                        "state": (prow.state if prow else ""), "principal": True})
    ids = [m["id"] for m in meta]
    if not ids:
        return {"roster": [], "window_days": round(STATS_WH / 24)}

    counts = {r.id: int(r.n) for r in (await db.execute(text("""
        SELECT entity_id::text id, count(DISTINCT article_id) n
          FROM article_entity_mentions WHERE entity_id = ANY(CAST(:ids AS uuid[]))
         GROUP BY 1
    """), {"ids": ids})).fetchall()}

    lean = {r.id: r for r in (await db.execute(text(f"""
        SELECT m.entity_id::text id,
               count(*) FILTER (WHERE ({POL}) > 0) sup,
               count(*) FILTER (WHERE ({POL}) < 0) crit
          FROM article_entity_mentions m
          JOIN articles a ON a.id = m.article_id
          JOIN article_stances st ON st.article_id = m.article_id AND st.actor_entity_id = m.entity_id
         WHERE m.entity_id = ANY(CAST(:ids AS uuid[]))
           AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
         GROUP BY 1
    """), {"ids": ids, "wh": STATS_WH})).fetchall()}

    imgs = {r.eid: r.image_url for r in (await db.execute(text("""
        SELECT entity_id::text eid, image_url FROM analytics.entity_image
         WHERE entity_id = ANY(CAST(:ids AS uuid[])) AND ok AND image_url IS NOT NULL
    """), {"ids": ids})).fetchall()}

    roster = []
    for m in meta:
        s = lean.get(m["id"])
        sup, crit = (int(s.sup), int(s.crit)) if s else (0, 0)
        role = " · ".join([x for x in [(m.get("party") or "").strip(), (m.get("state") or "").strip()] if x])
        # Flag the principal by id (not the insert-guard) so they pin first even
        # when they're also in the watchlist meta.
        is_principal = bool(pid) and m["id"] == pid
        roster.append({
            "id": m["id"], "name": m["name"], "type": _ui_type(m.get("type")),
            "role": ("★ your principal" if is_principal else (role or m.get("type") or "watched")),
            "align": _align(sup, crit), "mentions": counts.get(m["id"], 0),
            "img": imgs.get(m["id"]), "principal": is_principal,
        })
    # principal pinned first, then by mention volume
    roster.sort(key=lambda x: (not x.get("principal"), -x["mentions"]))
    return {"roster": roster, "window_days": round(STATS_WH / 24)}


# ───────────────────────── ENTITY FILE ─────────────────────────
async def build_entity_file(db, eid: str, prefs: dict[str, Any]) -> dict[str, Any]:
    wl_ids = prefs["watchlist"]["entity_ids"]
    p = {"eid": eid, "wh": STATS_WH}

    ident = (await db.execute(text("""
        SELECT canonical_name, entity_type, party, state, aliases
          FROM entity_dictionary WHERE id = CAST(:eid AS uuid)
    """), {"eid": eid})).fetchone()
    if not ident:
        return {"found": False}

    img = (await db.execute(text("""
        SELECT image_url FROM analytics.entity_image
         WHERE entity_id = CAST(:eid AS uuid) AND ok AND image_url IS NOT NULL
         LIMIT 1
    """), {"eid": eid})).scalar()

    mentions = (await db.execute(text("""
        SELECT count(DISTINCT article_id) n FROM article_entity_mentions WHERE entity_id = CAST(:eid AS uuid)
    """), {"eid": eid})).scalar() or 0
    n_quotes = (await db.execute(text("""
        SELECT count(*) FROM article_quotes WHERE speaker_entity_id = CAST(:eid AS uuid)
    """), {"eid": eid})).scalar() or 0
    n_claims = (await db.execute(text("""
        SELECT count(*) FROM article_claims WHERE subject_entity_id = CAST(:eid AS uuid)
    """), {"eid": eid})).scalar() or 0

    st = (await db.execute(text(f"""
        SELECT count(*) FILTER (WHERE ({POL}) > 0) sup,
               count(*) FILTER (WHERE ({POL}) < 0) crit,
               count(*) FILTER (WHERE ({POL}) = 0) neu
          FROM article_entity_mentions m
          JOIN articles a ON a.id = m.article_id
          JOIN article_stances st ON st.article_id = m.article_id AND st.actor_entity_id = CAST(:eid AS uuid)
         WHERE m.entity_id = CAST(:eid AS uuid)
           AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
    """), p)).fetchone()
    sup, crit, neu = int(st.sup or 0), int(st.crit or 0), int(st.neu or 0)

    # Share of voice vs SAME-TYPE peers (so a person ranks against rivals, not RBI),
    # always including the subject and flagging it.
    sov_ids = list({*wl_ids, eid})
    sov = [{"label": r.nm, "value": int(r.n), "you": r.id == eid} for r in (await db.execute(text("""
        SELECT m.entity_id::text id, ed.canonical_name nm, count(DISTINCT m.article_id) n
          FROM article_entity_mentions m
          JOIN articles a ON a.id = m.article_id
          JOIN entity_dictionary ed ON ed.id = m.entity_id
         WHERE m.entity_id = ANY(CAST(:ids AS uuid[]))
           AND ed.entity_type = :etype
           AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
         GROUP BY 1, 2 ORDER BY (m.entity_id::text = :eid) DESC, 3 DESC LIMIT 6
    """), {"ids": sov_ids, "etype": ident.entity_type, "eid": eid, "wh": STATS_WH})).fetchall()]

    issues = [{"label": r.topic or "—", "value": int(r.cnt)} for r in (await db.execute(text(f"""
        SELECT a.topic_category AS topic, count(DISTINCT a.id) AS cnt
          FROM article_entity_mentions m JOIN articles a ON a.id = m.article_id
         WHERE m.entity_id = CAST(:eid AS uuid)
           AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
           AND {_BODY_PRESENT}
         GROUP BY 1 ORDER BY 2 DESC LIMIT 6
    """), p)).fetchall()]

    pulse = [int(r.n) for r in (await db.execute(text(f"""
        SELECT d::date, COALESCE(c.n, 0) n FROM generate_series(
                 (analytics.now_sim() - make_interval(days => :days))::date,
                 analytics.now_sim()::date, '1 day') d
          LEFT JOIN (
            SELECT date_trunc('day', a.collected_at)::date dd, count(DISTINCT a.id) n
              FROM article_entity_mentions m JOIN articles a ON a.id = m.article_id
             WHERE m.entity_id = CAST(:eid AS uuid)
               AND a.collected_at >= analytics.now_sim() - make_interval(days => :days)
               AND {_BODY_PRESENT}
             GROUP BY 1) c ON c.dd = d::date
         ORDER BY d
    """), {"eid": eid, "days": PULSE_DAYS})).fetchall()]

    quotes = [{"q": r.q, "q_en": (r.qen if (r.qen and r.qen != r.q) else None),
               "src": r.src, "date": str(r.d.date()) if r.d else ""}
              for r in (await db.execute(text("""
        SELECT q.quote_text q, NULLIF(q.quote_text_en, '') qen, s.name src, a.published_at d
          FROM article_quotes q JOIN articles a ON a.id = q.article_id
          JOIN sources s ON s.id = a.source_id
         WHERE q.speaker_entity_id = CAST(:eid AS uuid) AND length(COALESCE(q.quote_text_en, q.quote_text)) > 12
         ORDER BY a.collected_at DESC LIMIT 4
    """), {"eid": eid})).fetchall()]

    await i18n.attach_en(db, quotes, "q")

    claims = [{"pred": (r.predicate or "claim"), "text": (r.object_text or r.claim_text or "")[:160], "src": r.src}
              for r in (await db.execute(text("""
        SELECT c.predicate, c.object_text, c.claim_text, s.name src
          FROM article_claims c JOIN articles a ON a.id = c.article_id
          JOIN sources s ON s.id = a.source_id
         WHERE c.subject_entity_id = CAST(:eid AS uuid)
         ORDER BY a.collected_at DESC LIMIT 4
    """), {"eid": eid})).fetchall()]

    await i18n.attach_en(db, claims, "text")

    network = [{"name": r.nm, "rel": "co-appears", "n": int(r.shared)} for r in (await db.execute(text(f"""
        SELECT m2.entity_id::text id, ed.canonical_name nm, count(DISTINCT m1.article_id) shared
          FROM article_entity_mentions m1
          JOIN article_entity_mentions m2 ON m2.article_id = m1.article_id AND m2.entity_id <> m1.entity_id
          JOIN articles a ON a.id = m1.article_id
          JOIN entity_dictionary ed ON ed.id = m2.entity_id
         WHERE m1.entity_id = CAST(:eid AS uuid)
           AND ed.entity_type = 'person'
           AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
         GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 6
    """), p)).fetchall()]

    outlets = [{"name": r.nm, "pos": int(r.pos), "neg": int(r.neg)} for r in (await db.execute(text(f"""
        SELECT s.name nm, count(*) FILTER (WHERE ({POL}) > 0) pos, count(*) FILTER (WHERE ({POL}) < 0) neg
          FROM article_entity_mentions m JOIN articles a ON a.id = m.article_id
          JOIN sources s ON s.id = a.source_id JOIN article_stances st ON st.article_id = a.id AND st.actor_entity_id = CAST(:eid AS uuid)
         WHERE m.entity_id = CAST(:eid AS uuid)
           AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
           AND {_BODY_PRESENT}
         GROUP BY s.name HAVING count(*) >= 3 ORDER BY count(*) DESC LIMIT 6
    """), p)).fetchall()]

    lang = {r.l: int(r.n) for r in (await db.execute(text("""
        SELECT COALESCE(a.language_iso, '?') l, count(DISTINCT a.id) n
          FROM article_entity_mentions m JOIN articles a ON a.id = m.article_id
         WHERE m.entity_id = CAST(:eid AS uuid)
           AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
         GROUP BY 1
    """), {"eid": eid, "wh": STATS_WH})).fetchall()}

    timeline = [{"date": str(r.d), "what": (r.what or "")[:120],
                 "url": r.url, "src": r.src, "article_id": str(r.aid) if r.aid else None}
                for r in (await db.execute(text("""
        SELECT COALESCE(e.effective_event_date, e.event_date) d, e.event_description what,
               a.id aid, a.url url, s.name src
          FROM article_events e
          JOIN article_entity_mentions m ON m.article_id = e.article_id
          JOIN articles a ON a.id = e.article_id
          JOIN sources s ON s.id = a.source_id
         WHERE m.entity_id = CAST(:eid AS uuid)
           AND COALESCE(e.effective_event_date, e.event_date) IS NOT NULL
           AND e.event_description IS NOT NULL
         ORDER BY d DESC LIMIT 8
    """), {"eid": eid})).fetchall()]

    await i18n.attach_en(db, timeline, "what")

    name = ident.canonical_name
    fn = name.split()[0]
    net = sup - crit  # lifetime standing net (used in the identity tiles)

    # ── RECENT ACTIVITY (adaptive window: 24h, widening to 48h/3d/7d only if thin) ──
    rec = (await db.execute(text(f"""
        SELECT a.title, EXTRACT(EPOCH FROM (analytics.now_sim() - a.collected_at)) / 3600.0 age_h,
               s.name src,
               (SELECT round(avg(({POL}) * st.intensity)::numeric, 2)
                  FROM article_stances st WHERE st.article_id = a.id AND st.actor_entity_id = CAST(:eid AS uuid)) lean
          FROM article_entity_mentions m JOIN articles a ON a.id = m.article_id
          JOIN sources s ON s.id = a.source_id
         WHERE m.entity_id = CAST(:eid AS uuid)
           AND a.collected_at >= analytics.now_sim() - make_interval(hours => 168)
           AND {_BODY_PRESENT}
         ORDER BY a.collected_at DESC LIMIT 60
    """), {"eid": eid})).fetchall()
    chosen, inwin = 168, list(rec)
    for whc in (24, 48, 72, 168):
        sub = [r for r in rec if r.age_h is not None and r.age_h <= whc]
        if len(sub) >= 3:
            chosen, inwin = whc, sub
            break
    n_rec = len(inwin)
    sup_r = sum(1 for r in inwin if (r.lean or 0) >= 0.10)
    crit_r = sum(1 for r in inwin if (r.lean or 0) <= -0.10)
    wlabel = {24: "last 24 hours", 48: "last 48 hours", 72: "last 3 days", 168: "last 7 days"}[chosen]
    if n_rec == 0:
        summary = f"{name} has had no fresh coverage in the last 7 days — quiet on the wire, nothing to brief."
    else:
        pos = next((r for r in inwin if (r.lean or 0) >= 0.10), None)
        neg = next((r for r in inwin if (r.lean or 0) <= -0.10), None)
        qrow = (await db.execute(text("""
            SELECT q.quote_text q, NULLIF(q.quote_text_en, '') qen
              FROM article_quotes q JOIN articles a ON a.id = q.article_id
             WHERE q.speaker_entity_id = CAST(:eid AS uuid)
               AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
               AND length(COALESCE(q.quote_text_en, q.quote_text)) BETWEEN 16 AND 300
             ORDER BY a.collected_at DESC LIMIT 1
        """), {"eid": eid, "wh": chosen})).fetchone()
        crow = (await db.execute(text("""
            SELECT COALESCE(c.object_text, c.claim_text) tx, c.predicate pred
              FROM article_claims c JOIN articles a ON a.id = c.article_id
             WHERE c.subject_entity_id = CAST(:eid AS uuid)
               AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
               AND COALESCE(c.object_text, c.claim_text) IS NOT NULL
             ORDER BY a.collected_at DESC LIMIT 1
        """), {"eid": eid, "wh": chosen})).fetchone()

        qtext = (qrow.qen or qrow.q) if qrow else None
        ctext = crow.tx if crow else None
        to_tr = {t for t in [pos.title if pos else None, neg.title if neg else None, qtext, ctext]
                 if t and not i18n.is_english(t)}
        enm = await i18n.ensure_en(db, to_tr) if to_tr else {}
        en = lambda t: (enm.get(t, t) if t else t)

        tone = "supportive" if sup_r > crit_r else "critical" if crit_r > sup_r else "evenly split"
        parts = [f"In the {wlabel}, {name} drew {n_rec} {'story' if n_rec == 1 else 'stories'} — "
                 f"{sup_r} supportive, {crit_r} critical, reading {tone} overall"
                 + (" (window widened — coverage was light)." if chosen >= 72 else ".")]
        if pos:
            parts.append(f"The favourable coverage centres on “{en(pos.title)}” ({pos.src}).")
        if neg:
            parts.append(f"The critical line is “{en(neg.title)}” ({neg.src}).")
        if not pos and not neg:
            parts.append("Coverage is largely neutral — reporting rather than taking sides.")
        if qtext:
            parts.append(f"In their own words: “{en(qtext)[:220]}”.")
        if ctext:
            parts.append(f"On the record about them — {(crow.pred + ': ') if crow.pred else ''}“{en(ctext)[:180]}”.")
        summary = " ".join(parts)

    return {
        "found": True,
        "id": eid, "name": name, "type": _ui_type(ident.entity_type),
        "img": img,
        "party": ident.party, "state": ident.state,
        "aliases": list(ident.aliases or [])[:6],
        "tiles": {"mentions": int(mentions), "quotes": int(n_quotes), "claims": int(n_claims), "net": net},
        "standing": {"sup": sup, "crit": crit, "neu": neu},
        "sov": sov, "issues": issues, "pulse": pulse,
        "quotes": quotes, "claims": claims, "network": network,
        "outlets": outlets,
        "reach": {"en": lang.get("en", 0), "te": lang.get("te", 0)},
        "timeline": timeline,
        "summary": summary,
        "window_days": round(STATS_WH / 24),
    }


# ───────────────────────── LIVE ARTICLE FEED ─────────────────────────
async def entity_articles(db, eid: str, cursor: str | None, limit: int) -> dict[str, Any]:
    """Whole-corpus articles mentioning the entity, NEWEST FIRST, cursor-paginated."""
    rows = (await db.execute(text(f"""
        SELECT a.id::text id, a.title, s.name src, a.url, a.thumbnail_url,
               a.collected_at, a.published_at, a.language_iso, a.topic_category,
               (SELECT round(avg(({POL}) * st.intensity)::numeric, 2)
                  FROM article_stances st WHERE st.article_id = a.id AND st.actor_entity_id = CAST(:eid AS uuid)) AS lean
          FROM article_entity_mentions m
          JOIN articles a ON a.id = m.article_id
          JOIN sources s ON s.id = a.source_id
         WHERE m.entity_id = CAST(:eid AS uuid)
           AND (CAST(:cursor AS timestamptz) IS NULL OR a.collected_at < CAST(:cursor AS timestamptz))
           AND {_BODY_PRESENT}
         ORDER BY a.collected_at DESC
         LIMIT :limit
    """), {"eid": eid, "cursor": cursor, "limit": limit})).fetchall()

    items = []
    for r in rows:
        lean = float(r.lean) if r.lean is not None else None
        tone = "supportive" if (lean or 0) >= 0.10 else "hostile" if (lean or 0) <= -0.10 else "neutral"
        items.append({
            "id": r.id, "headline": r.title, "source": r.src, "url": r.url,
            "thumbnail": r.thumbnail_url, "tone": tone,
            "published_at": str(r.published_at) if r.published_at else None,
            "collected_at": str(r.collected_at) if r.collected_at else None,
            "lang": r.language_iso, "topic": r.topic_category,
        })
    await i18n.attach_en(db, items, "headline")
    next_cursor = str(rows[-1].collected_at) if len(rows) == limit else None
    return {"articles": items, "next_cursor": next_cursor, "count": len(items)}
