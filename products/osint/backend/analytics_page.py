"""Analytics — "The Instrument Panel": pure-data cards over the persona's coverage universe.

No LLM. Every card is a count/distribution/cross-tab with a source + n + an explain payload.
For speed we materialise the universe (articles mentioning ANY watchlist entity / the
principal, in window) into a TEMP table once, then each card aggregates from it.
Directional cards use article_stances (POL), never register_emotion (alarm = event-emotion).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from posture import POL, principal_of

WH = 1128  # 47-day window (~ whole corpus for this dataset)
_MONTHS = ["", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def _verify(definition, formula, source, underlying):
    return {"definition": definition, "formula": formula, "source": source,
            "window": f"{round(WH/24)}-day window", "underlying": underlying}


def _card(cid, band, viz, name, sub, source, data, n, conf, verify, span=1):
    return {"id": cid, "band": band, "viz": viz, "name": name, "sub": sub, "source": source,
            "span": span, "data": data,
            "metric": {"label": name, "value": str(n), "n": int(n), "confidence": conf, "verify": verify}}


async def _rows(db, sql, **p):
    return (await db.execute(text(sql), p)).fetchall()


async def build_analytics(db, prefs: dict[str, Any]) -> dict[str, Any]:
    pid, pname = principal_of(prefs)
    ids = list({*(prefs["watchlist"]["entity_ids"] or []), *( [pid] if pid else [])})

    # ── materialise the universe once ──
    await db.execute(text("DROP TABLE IF EXISTS _univ"))
    await db.execute(text("""
        CREATE TEMP TABLE _univ AS
        SELECT DISTINCT a.id, a.topic_category, a.language_iso, a.geo_primary, a.source_id,
               a.published_at, a.collected_at, a.register_emotion
          FROM article_entity_mentions m JOIN articles a ON a.id = m.article_id
         WHERE m.entity_id = ANY(CAST(:ids AS uuid[]))
           AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
    """), {"ids": ids, "wh": WH})
    await db.execute(text("CREATE INDEX ON _univ (id)"))
    base = (await db.execute(text("SELECT count(*) FROM _univ"))).scalar() or 0
    now = (await db.execute(text("SELECT analytics.now_sim() AS n"))).scalar()
    asof = f"AS OF {now.day:02d} {_MONTHS[now.month]} {now.year}" if now else ""

    mods: list[dict[str, Any]] = []

    # 1 — volume (area), last 14 days
    vol = await _rows(db, """
        SELECT d::date dd, COALESCE(c.n,0) n FROM generate_series(
                 (analytics.now_sim()-make_interval(days=>13))::date, analytics.now_sim()::date,'1 day') d
          LEFT JOIN (SELECT collected_at::date dd, count(*) n FROM _univ
                      WHERE collected_at >= analytics.now_sim()-make_interval(days=>13) GROUP BY 1) c ON c.dd=d::date
         ORDER BY d""")
    mods.append(_card("volume", "THE BIG PICTURE", "area", "Coverage Volume",
        "How many stories mention your watchlist each day", "articles.collected_at",
        {"labels": [str(r.dd.day) for r in vol], "series": [int(r.n) for r in vol],
         "note": f"{base:,} articles mention your watchlist in the {round(WH/24)}-day window."},
        base, "high", _verify("Articles mentioning any watchlist entity, per day.",
        "count(articles) grouped by collected_at::date", "article_entity_mentions ▸ articles",
        [f"{base:,} articles in-window", "deduplicated by article", "daily counts, last 14 days"]), span=2))

    # 2 — topics (rank)
    tp = await _rows(db, "SELECT COALESCE(topic_category,'OTHER') topic, count(*) n FROM _univ GROUP BY 1 ORDER BY 2 DESC")
    other = next((int(r.n) for r in tp if r.topic == "OTHER"), 0)
    items = [{"label": (r.topic or "—").title(), "value": int(r.n)} for r in tp if r.topic != "OTHER"][:10]
    mods.append(_card("topics", "THE BIG PICTURE", "rank", "What They're Talking About",
        "Your coverage, broken down by topic", "articles.topic_category",
        {"unit": "articles", "foot": f"Plus {other:,} uncategorised (OTHER), excluded from bars.", "items": items},
        base, "high", _verify("Share of coverage in each topic category.", "count grouped by topic_category",
        "articles.topic_category", [f"top topic {items[0]['label']} {items[0]['value']}" if items else "—"])))

    # 3 — rising (smallmult): top 4 topics across 5 weeks
    rw = await _rows(db, """
        SELECT COALESCE(topic_category,'OTHER') topic,
               floor(EXTRACT(EPOCH FROM (analytics.now_sim()-collected_at))/604800)::int wk, count(*) n
          FROM _univ WHERE topic_category IS NOT NULL AND topic_category<>'OTHER' GROUP BY 1,2""")
    by_t: dict[str, dict[int, int]] = {}
    tot: dict[str, int] = {}
    for r in rw:
        by_t.setdefault(r.topic, {})[int(r.wk)] = int(r.n); tot[r.topic] = tot.get(r.topic, 0) + int(r.n)
    top4 = sorted(tot, key=lambda k: -tot[k])[:4]
    rrows = []
    for t in top4:
        series = [by_t[t].get(w, 0) for w in range(4, -1, -1)]  # oldest→newest (wk4..wk0)
        dir_ = "up" if series[-1] >= series[0] else "down"
        rrows.append({"label": t.title(), "series": series,
                      "trend": "surging" if dir_ == "up" and series[-1] > series[0] else "cooling" if dir_ == "down" else "steady",
                      "dir": dir_})
    mods.append(_card("rising", "THE BIG PICTURE", "smallmult", "Issues Rising & Falling",
        "Which topics are climbing or fading, week by week", "topic_category × week",
        {"rows": rrows}, base, "medium", _verify("Weekly article volume per topic.",
        "count grouped by (week, topic_category)", "articles.collected_at × topic_category",
        ["5 weekly buckets, top 4 topics"])))

    # 4 — for vs against (stack)
    sm = await _rows(db, f"""
        SELECT count(*) FILTER (WHERE ({POL})>0) sup, count(*) FILTER (WHERE ({POL})=0) neu,
               count(*) FILTER (WHERE ({POL})<0) crit
          FROM _univ u JOIN article_stances st ON st.article_id=u.id""")
    r0 = sm[0]; tot_s = (int(r0.sup)+int(r0.neu)+int(r0.crit)) or 1
    pct = lambda x: round(100*int(x)/tot_s)
    mods.append(_card("forvsagainst", "THE BIG PICTURE", "stack", "For You vs Against You",
        "Supportive, neutral or critical — overall", "article_stances.stance",
        {"foot": "Directional stance, not emotion.", "segments": [
            {"label": "Supportive", "value": pct(r0.sup), "color": "supportive"},
            {"label": "Neutral", "value": pct(r0.neu), "color": "muted"},
            {"label": "Critical", "value": pct(r0.crit), "color": "hostile"}]},
        tot_s, "medium", _verify("Share of stance-tagged coverage supportive/neutral/critical.",
        "count grouped by stance ÷ total", "article_stances (POL map)",
        [f"{pct(r0.sup)}/{pct(r0.neu)}/{pct(r0.crit)}", "uses article_stances, not register_emotion"])))

    # 5 — battlefield (lean): topic × stance
    bf = await _rows(db, f"""
        SELECT COALESCE(u.topic_category,'OTHER') topic, count(*) FILTER (WHERE ({POL})>0) pos,
               count(*) FILTER (WHERE ({POL})<0) neg
          FROM _univ u JOIN article_stances st ON st.article_id=u.id
         WHERE u.topic_category IS NOT NULL AND u.topic_category<>'OTHER'
         GROUP BY 1 ORDER BY (count(*) FILTER (WHERE ({POL})>0)+count(*) FILTER (WHERE ({POL})<0)) DESC LIMIT 6""")
    mods.append(_card("battlefield", "THE BIG PICTURE", "lean", "Issues — Praised vs Attacked",
        "Which issues you're supported on vs hit on", "topic_category × article_stances",
        {"foot": "Net lean = supportive − critical, by issue.",
         "items": [{"label": r.topic.title(), "pos": int(r.pos), "neg": int(r.neg)} for r in bf]},
        sum(int(r.pos)+int(r.neg) for r in bf), "medium",
        _verify("Whether each issue skews supportive or critical.", "(sup−crit)÷(sup+crit) per topic",
        "topic_category × article_stances", ["stance-based, not emotion-based"])))

    # 6 — share of voice (rank), watchlist entities + principal
    sov = await _rows(db, """
        SELECT m.entity_id::text id, ed.canonical_name nm, count(DISTINCT m.article_id) n
          FROM article_entity_mentions m JOIN articles a ON a.id=m.article_id
          JOIN entity_dictionary ed ON ed.id=m.entity_id
         WHERE m.entity_id=ANY(CAST(:ids AS uuid[])) AND a.collected_at>=analytics.now_sim()-make_interval(hours=>:wh)
         GROUP BY 1,2 ORDER BY 3 DESC LIMIT 8""", ids=ids, wh=WH)
    mods.append(_card("sov", "THE BIG PICTURE", "rank", "You vs Your Rivals",
        "Share of the conversation across watched figures", "article_entity_mentions",
        {"unit": "articles", "foot": "Distinct articles mentioning each figure.",
         "items": [{"label": r.nm, "value": int(r.n), "you": r.id == pid} for r in sov]},
        sum(int(r.n) for r in sov), "high", _verify("Coverage per watched entity vs rivals.",
        "count(distinct article) per entity_id", "article_entity_mentions",
        ["counted by entity_id (deduped)"])))

    # ── BAND 2 ──
    # 7 — outlets (rank)
    ou = await _rows(db, """SELECT s.name nm, count(*) n FROM _univ u JOIN sources s ON s.id=u.source_id
                            GROUP BY 1 ORDER BY 2 DESC LIMIT 10""")
    mods.append(_card("outlets", "WHO & WHERE", "rank", "Who's Covering You",
        "The outlets writing about you, ranked", "articles.source_id ▸ sources",
        {"unit": "articles", "foot": "By article count.", "items": [{"label": r.nm, "value": int(r.n)} for r in ou]},
        base, "high", _verify("Which outlets cover you and how much.", "count grouped by source",
        "articles ▸ sources", [f"top {ou[0].nm} {int(ou[0].n)}" if ou else "—"])))

    # 8 — outlet lean (lean)
    ol = await _rows(db, f"""SELECT s.name nm, count(*) FILTER (WHERE ({POL})>0) pos, count(*) FILTER (WHERE ({POL})<0) neg
          FROM _univ u JOIN sources s ON s.id=u.source_id JOIN article_stances st ON st.article_id=u.id
         GROUP BY 1 HAVING count(*)>=5 ORDER BY count(*) DESC LIMIT 8""")
    mods.append(_card("outletlean", "WHO & WHERE", "lean", "Outlets — Friendly vs Hostile",
        "Which papers lean supportive vs critical of you", "sources × article_stances",
        {"foot": "Net lean by outlet (≥5 stance signals).", "items": [{"label": r.nm, "pos": int(r.pos), "neg": int(r.neg)} for r in ol]},
        sum(int(r.pos)+int(r.neg) for r in ol), "medium", _verify("Whether each outlet skews supportive or critical.",
        "(sup−crit)÷(sup+crit) per source", "sources × article_stances", ["stance-based"])))

    # 9 — language (donut)
    lg = await _rows(db, "SELECT COALESCE(language_iso,'?') lang, count(*) n FROM _univ GROUP BY 1")
    lgm = {r.lang: int(r.n) for r in lg}; tl = sum(lgm.values()) or 1
    en, te = lgm.get("en", 0), lgm.get("te", 0); other_l = tl - en - te
    mods.append(_card("language", "WHO & WHERE", "donut", "English vs Telugu",
        "The language split of your coverage", "articles.language_iso",
        {"centerLabel": "EN", "centerValue": f"{round(100*en/tl)}%", "foot": "Bilingual coverage split.",
         "segments": [{"label": "English", "value": round(100*en/tl), "color": "cool"},
                      {"label": "Telugu", "value": round(100*te/tl), "color": "gold"},
                      {"label": "Other / none", "value": round(100*other_l/tl), "color": "muted"}]},
        tl, "high", _verify("Share of coverage by detected language.", "count grouped by language_iso",
        "articles.language_iso", [f"en {en} · te {te}"])))

    # 10 — language by issue (groupbars)
    li = await _rows(db, """SELECT COALESCE(topic_category,'OTHER') topic,
            count(*) FILTER (WHERE language_iso='en') en, count(*) FILTER (WHERE language_iso='te') te
          FROM _univ WHERE topic_category IS NOT NULL AND topic_category<>'OTHER'
         GROUP BY 1 ORDER BY count(*) DESC LIMIT 6""")
    mods.append(_card("langbyissue", "WHO & WHERE", "groupbars", "Telugu vs English by Issue",
        "Which issues live in which language", "topic_category × language_iso",
        {"foot": "Article counts per issue, by language.", "items": [{"label": r.topic.title(), "en": int(r.en), "te": int(r.te)} for r in li]},
        base, "high", _verify("English vs Telugu volume per issue.", "count grouped by (topic, language)",
        "topic_category × language_iso", ["per-issue language split"])))

    # 11 — where it's landing (rank, geo_primary)
    geo = await _rows(db, """SELECT geo_primary place, count(*) n FROM _univ WHERE geo_primary IS NOT NULL AND geo_primary<>''
                             GROUP BY 1 ORDER BY 2 DESC LIMIT 10""")
    mods.append(_card("geo", "WHO & WHERE", "rank", "Where It's Landing",
        "Your coverage by place", "articles.geo_primary",
        {"unit": "articles", "foot": "Primary geo of each story.", "items": [{"label": r.place, "value": int(r.n)} for r in geo]},
        sum(int(r.n) for r in geo), "medium", _verify("Where coverage is geographically datelined.",
        "count grouped by geo_primary", "articles.geo_primary", ["primary geo tag per article"])))

    # 12 — who's being quoted (list)
    qd = await _rows(db, """SELECT COALESCE(q.speaker_name_en, q.speaker_name) nm, count(*) n
          FROM article_quotes q JOIN _univ u ON u.id=q.article_id
         WHERE COALESCE(q.speaker_name_en,q.speaker_name) IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 8""")
    mods.append(_card("quoted", "WHO & WHERE", "list", "Who's Being Quoted",
        "The voices quoted most in your coverage", "article_quotes.speaker_name",
        {"unit": "quotes", "foot": "By quote count.", "items": [{"label": r.nm, "value": int(r.n)} for r in qd]},
        sum(int(r.n) for r in qd), "high", _verify("Who is quoted most in your coverage.",
        "count grouped by speaker_name", "article_quotes", ["resolved speaker names"])))

    # 13 — writers (list)
    wr = await _rows(db, """SELECT author_name nm, count(*) n FROM _univ JOIN articles a USING (id)
          WHERE a.author_name IS NOT NULL AND a.author_name<>'' GROUP BY 1 ORDER BY 2 DESC LIMIT 8""")
    mods.append(_card("writers", "WHO & WHERE", "list", "Who's Writing",
        "The journalists bylined on your coverage", "articles.author_name",
        {"unit": "articles", "foot": "Most coverage is wire / unbylined.", "items": [{"label": r.nm, "value": int(r.n)} for r in wr]},
        sum(int(r.n) for r in wr), "medium", _verify("Journalists who bylined coverage of you.",
        "count grouped by author_name", "articles.author_name", ["bylined articles only"])))

    # ── BAND 3 ──
    # 14 — tone register (rank, descriptive)
    tn = await _rows(db, """SELECT register_emotion emo, count(*) n FROM _univ WHERE register_emotion IS NOT NULL
                            GROUP BY 1 ORDER BY 2 DESC LIMIT 7""")
    tnt = sum(int(r.n) for r in tn) or 1
    mods.append(_card("tone", "THE DETAIL", "rank", "Tone of Coverage",
        "How the stories sound — descriptive, not a verdict", "articles.register_emotion",
        {"unit": "%", "descriptive": True, "foot": "⚠ Register of coverage, NOT hostility — 'alarm' = alarming events.",
         "items": [{"label": (r.emo or "—").title(), "value": round(100*int(r.n)/tnt)} for r in tn]},
        tnt, "medium", _verify("Emotional register of the writing — descriptive, not stance.",
        "count grouped by register_emotion", "articles.register_emotion",
        ["'alarm' tags events, not hostility — for direction use For-vs-Against"])))

    # 15 — what's coming up (eventcal, future events)
    up = await _rows(db, """SELECT COALESCE(e.effective_event_date,e.event_date) d, e.event_description l, e.event_type ty
          FROM article_events e JOIN _univ u ON u.id=e.article_id
         WHERE e.is_future AND COALESCE(e.effective_event_date,e.event_date) >= analytics.now_sim()::date
           AND e.event_description IS NOT NULL
         ORDER BY 1 ASC LIMIT 6""")
    mods.append(_card("upcoming", "THE DETAIL", "eventcal", "What's Coming Up",
        "Upcoming dated events in your coverage", "article_events (is_future)",
        {"foot": "Future-dated events extracted from coverage.",
         "items": [{"date": f"{r.d.day:02d} {_MONTHS[r.d.month]}", "label": (r.l or '')[:80], "type": (r.ty or 'event')} for r in up]},
        len(up), "medium", _verify("Events with a future date extracted from coverage.",
        "article_events WHERE is_future", "article_events", ["forward calendar"])))

    # 16 — what's happening (rank, event types)
    ev = await _rows(db, """SELECT e.event_type ty, count(*) n FROM article_events e JOIN _univ u ON u.id=e.article_id
          WHERE e.event_type IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 7""")
    mods.append(_card("events", "THE DETAIL", "rank", "What's Happening",
        "Events in your coverage, by type", "article_events.event_type",
        {"unit": "events", "foot": "Extracted events across your coverage.", "items": [{"label": (r.ty or '—').title(), "value": int(r.n)} for r in ev]},
        sum(int(r.n) for r in ev), "high", _verify("What kinds of events your coverage describes.",
        "count grouped by event_type", "article_events", ["event typing"])))

    # 17 — quotes (quotes)
    qt = await _rows(db, """SELECT COALESCE(NULLIF(q.quote_text_en,''),q.quote_text) qx,
            COALESCE(q.speaker_name_en,q.speaker_name) who, s.name src
          FROM article_quotes q JOIN _univ u ON u.id=q.article_id JOIN sources s ON s.id=u.source_id
         WHERE length(COALESCE(q.quote_text_en,q.quote_text)) BETWEEN 24 AND 220 AND q.speaker_name IS NOT NULL
         ORDER BY u.collected_at DESC LIMIT 4""")
    mods.append(_card("quotes", "THE DETAIL", "quotes", "In Their Words",
        "Actual quotes from your coverage", "article_quotes.quote_text",
        {"foot": "Verbatim, latest first.", "items": [{"q": r.qx, "who": r.who or "—", "role": "", "src": r.src} for r in qt]},
        len(qt), "high", _verify("Verbatim quotes and their speakers.", "article_quotes.quote_text + speaker",
        "article_quotes", ["latest 4, English preferred"])))

    # 18 — claims (claims)
    cl = await _rows(db, """SELECT c.predicate pred, COALESCE(c.object_text,c.claim_text) tx, s.name src
          FROM article_claims c JOIN _univ u ON u.id=c.article_id JOIN sources s ON s.id=u.source_id
         WHERE COALESCE(c.object_text,c.claim_text) IS NOT NULL ORDER BY u.collected_at DESC LIMIT 4""")
    mods.append(_card("claims", "THE DETAIL", "claims", "What's Being Claimed",
        "Specific claims and statements in your coverage", "article_claims",
        {"foot": "Subject–predicate–object, verbatim.", "items": [{"pred": (r.pred or "claim"), "text": (r.tx or '')[:150], "src": r.src} for r in cl]},
        len(cl), "medium", _verify("Claims extracted from coverage.", "article_claims triples",
        "article_claims", ["no true/false verdict applied"])))

    # 19 — figures (figures)
    fg = await _rows(db, """SELECT n.value || COALESCE(' '||NULLIF(n.unit,''),'') val, n.context ctx
          FROM article_numbers n JOIN _univ u ON u.id=n.article_id
         WHERE n.value IS NOT NULL AND length(COALESCE(n.context,''))>8 ORDER BY u.collected_at DESC LIMIT 6""")
    mods.append(_card("figures", "THE DETAIL", "figures", "The Numbers in the News",
        "Figures mentioned in your coverage, with context", "article_numbers",
        {"foot": "Extracted figures with sentence context.", "items": [{"value": r.val, "ctx": (r.ctx or '')[:70]} for r in fg]},
        len(fg), "high", _verify("Numeric facts with context.", "article_numbers.value + unit + context",
        "article_numbers", ["verbatim"])))

    # 20 — pictures (images), real hero images
    pic = await _rows(db, """SELECT mu.url FROM (
            SELECT DISTINCT ON (u.id) md.url, u.collected_at
              FROM _univ u JOIN article_media md ON md.article_id=u.id
             WHERE md.is_hero AND md.url IS NOT NULL AND md.media_type='image'
             ORDER BY u.id, u.collected_at DESC) mu ORDER BY mu.collected_at DESC LIMIT 8""")
    tones = ["neutral", "supportive", "hostile", "gold", "neutral", "supportive", "neutral", "gold"]
    mods.append(_card("pictures", "THE DETAIL", "images", "The Picture Wall",
        "Images from your coverage", "article_media (is_hero)",
        {"foot": "Hero images from your coverage.", "items": [{"src": r.url, "tone": tones[i % len(tones)]} for i, r in enumerate(pic)]},
        len(pic), "high", _verify("Hero images attached to your coverage.", "article_media WHERE is_hero",
        "article_media", ["one hero image per article"])))

    await db.execute(text("DROP TABLE IF EXISTS _univ"))
    return {"personalized": True, "base": f"{base:,}", "window": f"{round(WH/24)}-DAY WINDOW",
            "asOf": asof, "modules": mods}
