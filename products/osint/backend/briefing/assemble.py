"""Assemble the report JSON from stored briefing.items (pure aggregation).

Covers the data-driven sections that need no event-merge:
  strip (total / biggest subject / sentiment / top outlet per medium),
  §3 by topic, §6 media compare, §9 by outlet, overall sentiment.
Event-merge sections (§1 Daily Brief, §2 Big Story) are added later.

net sentiment = round(100 * (fav - crit) / (fav + crit)); denominator always
the government-relevant, non-unclear, position-taking items.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from db import get_db


def _net(fav: int, crit: int) -> int:
    d = fav + crit
    return round(100 * (fav - crit) / d) if d else 0


async def assemble(org_id: str, cover_date) -> dict[str, Any]:
    async with get_db() as db:
        run = (await db.execute(text("""
            SELECT id, cover_date, counts FROM briefing.runs
             WHERE org_id=CAST(:o AS uuid) AND cover_date=:d
        """), {"o": org_id, "d": cover_date})).fetchone()
        if not run:
            return {"error": "no run for date"}
        rid = run.id

        # ── strip: totals by pillar (GOVERNMENT-relevant only) ──
        # "Total stories" = stories that actually concern the government, not the
        # full scanned corpus (which includes cricket / national / ads). The
        # per-pillar split and headline total are both gov-relevant.
        tot = (await db.execute(text("""
            SELECT pillar, count(*) n FROM briefing.items
             WHERE run_id=:r AND about_government AND NOT unclear GROUP BY 1
        """), {"r": rid})).fetchall()
        by_pillar = {p: 0 for p in ("web", "tv", "newspaper")}
        for row in tot:
            by_pillar[row.pillar] = int(row.n)
        total = sum(by_pillar.values())
        # full scanned volume kept for context (how loud the day was overall)
        scanned = int((await db.execute(text(
            "SELECT count(*) FROM briefing.items WHERE run_id=:r"), {"r": rid})).scalar() or 0)

        # ── sentiment (gov-relevant, not unclear) ──
        s = (await db.execute(text("""
            SELECT count(*) FILTER (WHERE verdict='favourable') fav,
                   count(*) FILTER (WHERE verdict='critical') crit,
                   count(*) FILTER (WHERE verdict='neutral') neu
              FROM briefing.items
             WHERE run_id=:r AND about_government AND NOT unclear
        """), {"r": rid})).fetchone()
        fav, crit, neu = int(s.fav), int(s.crit), int(s.neu)
        net = _net(fav, crit)

        # ── biggest subject (topic among gov-relevant) ──
        topics = (await db.execute(text("""
            SELECT topic, count(*) n,
                   count(*) FILTER (WHERE verdict='favourable') fav,
                   count(*) FILTER (WHERE verdict='critical') crit
              FROM briefing.items
             WHERE run_id=:r AND about_government AND NOT unclear AND topic IS NOT NULL
             GROUP BY 1 ORDER BY 2 DESC
        """), {"r": rid})).fetchall()
        topic_rows = [{"topic": t.topic, "items": int(t.n),
                       "favourable": int(t.fav), "critical": int(t.crit),
                       "net": _net(int(t.fav), int(t.crit))} for t in topics]
        biggest = topic_rows[0]["topic"] if topic_rows else None
        biggest_n = topic_rows[0]["items"] if topic_rows else 0

        # ── media compare (net per pillar) ──
        media = (await db.execute(text("""
            SELECT pillar,
                   count(*) FILTER (WHERE verdict='favourable') fav,
                   count(*) FILTER (WHERE verdict='critical') crit
              FROM briefing.items
             WHERE run_id=:r AND about_government AND NOT unclear GROUP BY 1
        """), {"r": rid})).fetchall()
        media_rows = [{"pillar": m.pillar, "favourable": int(m.fav),
                       "critical": int(m.crit), "net": _net(int(m.fav), int(m.crit))}
                      for m in media]

        # ── by outlet (top by gov-relevant volume) ──
        outlets = (await db.execute(text("""
            SELECT source_ref, pillar, count(*) n,
                   count(*) FILTER (WHERE verdict='favourable') fav,
                   count(*) FILTER (WHERE verdict='critical') crit
              FROM briefing.items
             WHERE run_id=:r AND about_government AND NOT unclear
             GROUP BY 1,2 ORDER BY 3 DESC LIMIT 12
        """), {"r": rid})).fetchall()
        outlet_rows = [{"outlet": o.source_ref, "pillar": o.pillar, "on_govt": int(o.n),
                        "favourable": int(o.fav), "critical": int(o.crit),
                        "net": _net(int(o.fav), int(o.crit))} for o in outlets]

        # top outlet per medium
        top_by_medium = {}
        for p in ("web", "tv", "newspaper"):
            row = (await db.execute(text("""
                SELECT source_ref, count(*) n FROM briefing.items
                 WHERE run_id=:r AND about_government AND pillar=:p
                 GROUP BY 1 ORDER BY 2 DESC LIMIT 1
            """), {"r": rid, "p": p})).fetchone()
            if row:
                top_by_medium[p] = {"outlet": row.source_ref, "n": int(row.n)}

        gov_total = fav + crit + neu

        # ── §1 daily brief: strongest gov-relevant items (real, cited) ──
        brief = (await db.execute(text("""
            SELECT i.pillar, i.source_ref, i.verdict, i.topic, i.department, i.lands_on,
                   i.evidence, i.event_action, i.item_ref,
                   COALESCE(
                     (SELECT a.title FROM articles a WHERE a.id::text=i.item_ref),
                     (SELECT c.headline FROM clippings c WHERE c.id::text=i.item_ref),
                     (SELECT max(v.video_title) FROM youtube_clips_v2 v WHERE v.video_id=i.item_ref)
                   ) title
              FROM briefing.items i
             WHERE i.run_id=:r AND i.about_government AND NOT i.unclear
             ORDER BY (i.strength='strong') DESC NULLS LAST,
                      (i.verdict='critical') DESC, i.confidence DESC NULLS LAST
             LIMIT 8
        """), {"r": rid})).fetchall()
        brief_rows = [{"pillar": b.pillar, "source": b.source_ref, "verdict": b.verdict,
                       "topic": b.topic, "department": b.department, "lands_on": b.lands_on,
                       "title": b.title, "evidence": b.evidence, "action": b.event_action}
                      for b in brief]

        # ── §8 figures from gov-relevant web+print items ──
        figures = (await db.execute(text("""
            SELECT n.value, n.unit, left(n.context,130) context, a.url url, a.title title
              FROM briefing.items i
              JOIN article_numbers n ON n.article_id::text=i.item_ref
              JOIN articles a ON a.id::text=i.item_ref
             WHERE i.run_id=:r AND i.about_government AND i.pillar IN ('web','newspaper')
               AND n.unit IS NOT NULL AND length(n.context) BETWEEN 12 AND 100
               AND (n.context ILIKE '%crore%' OR n.context ILIKE '%lakh%' OR n.unit ILIKE '%crore%'
                    OR n.context ILIKE '%scheme%' OR n.context ILIKE '%farmer%' OR n.context ILIKE '%beneficiar%')
             LIMIT 8
        """), {"r": rid})).fetchall()
        def _fig_group(unit, ctx):
            u = (unit or "").lower(); c = (ctx or "").lower()
            if any(w in u+c for w in ("crore", "lakh crore", "rupee", "₹", "budget", "fund")):
                return "Money"
            if any(w in c for w in ("beneficiar", "farmer", "people", "families", "students", "houses", "jobs", "lakh")):
                return "People"
            return "Other"
        figure_rows = [{"value": str(f.value), "unit": f.unit, "context": f.context,
                        "url": f.url, "title": f.title,
                        "group": _fig_group(f.unit, f.context),
                        "alleged": any(w in (f.context or "").lower() for w in ("alleg", "scam", "irregular"))}
                       for f in figures]

        # ── §1 events (top by importance) + §2 big story (#1) ──
        ev_rows = (await db.execute(text("""
            SELECT id, label, spread_web, spread_tv, spread_np, net_tone, importance,
                   member_item_ids, top_web_item, top_tv_item, top_np_item
              FROM briefing.events WHERE run_id=:r
             ORDER BY importance DESC LIMIT 8
        """), {"r": rid})).fetchall()

        async def _item_detail(item_id):
            if not item_id:
                return None
            row = (await db.execute(text("""
                SELECT pillar, source_ref, verdict, topic, department, lands_on, evidence, item_ref
                  FROM briefing.items WHERE id=:i
            """), {"i": item_id})).fetchone()
            return dict(row._mapping) if row else None

        events_out = []
        for e in ev_rows:
            top = await _item_detail(e.top_web_item or e.top_tv_item or e.top_np_item)
            events_out.append({
                "label": e.label, "spread_web": e.spread_web, "spread_tv": e.spread_tv,
                "spread_np": e.spread_np, "net": e.net_tone, "size": len(e.member_item_ids or []),
                "topic": (top or {}).get("topic"), "department": (top or {}).get("department"),
                "lands_on": (top or {}).get("lands_on"), "evidence": (top or {}).get("evidence"),
                "verdict": (top or {}).get("verdict"),
            })

        # §2 big story: richest detail for the #1 event
        big = None
        if ev_rows:
            e0 = ev_rows[0]
            members = (await db.execute(text("""
                SELECT DISTINCT ON (i.id) i.id, i.pillar, i.source_ref, i.verdict,
                       i.evidence, i.lands_on, i.item_ref,
                       COALESCE(a.url, CASE WHEN i.pillar='tv'
                                            THEN 'https://youtu.be/'||i.item_ref END) url,
                       COALESCE((a.published_at AT TIME ZONE 'Asia/Kolkata'),
                                (v.video_published_at AT TIME ZONE 'Asia/Kolkata')) ts
                  FROM briefing.items i
                  LEFT JOIN articles a ON a.id::text=i.item_ref
                  LEFT JOIN youtube_clips_v2 v ON v.video_id=i.item_ref
                 WHERE i.id = ANY(:ids) ORDER BY i.id
            """), {"ids": list(e0.member_item_ids or [])})).fetchall()
            gov_q = [dict(m._mapping) for m in members if m.evidence]
            dominant = max((("web", e0.spread_web), ("tv", e0.spread_tv),
                            ("newspaper", e0.spread_np)), key=lambda x: x[1] or 0)[0]
            big = {
                "label": e0.label,
                "spread": {"web": e0.spread_web, "tv": e0.spread_tv, "newspaper": e0.spread_np},
                "net": e0.net_tone, "size": len(e0.member_item_ids or []),
                "dominant_pillar": {"web": "online", "tv": "television",
                                    "newspaper": "newspapers"}[dominant],
                "evidence": [{"source": q["source_ref"], "pillar": q["pillar"],
                              "verdict": q["verdict"], "text": q["evidence"],
                              "lands_on": q["lands_on"]} for q in gov_q[:6]],
                # web member refs → resolved to gov/opp quotes once the roster loads (§7)
                "_web_refs": [m.item_ref for m in members if m.pillar == "web"],
            }
            # ── coverage through the day: members bucketed by hour × pillar ──
            _HB = ["6am", "9am", "12pm", "3pm", "6pm", "9pm", "next"]
            hourly = {k: {"web": 0, "tv": 0, "print": 0} for k in _HB}

            def _hbucket(ts, pillar):
                if pillar == "newspaper" or ts is None:
                    return "next" if pillar == "newspaper" else "9pm"
                h = ts.hour
                return ("6am" if h < 8 else "9am" if h < 11 else "12pm" if h < 14
                        else "3pm" if h < 17 else "6pm" if h < 20 else "9pm")

            def _tod(ts, pillar):
                if pillar == "newspaper":
                    return "Next morning"
                if ts is None:
                    return "Evening"
                h = ts.hour
                return ("Morning" if h < 11 else "Midday" if h < 15
                        else "Evening" if h < 19 else "Late evening")

            for m in members:
                col = "print" if m.pillar == "newspaper" else m.pillar
                hourly[_hbucket(m.ts, m.pillar)][col] += 1
            big["hourly"] = [{"label": k, **hourly[k]} for k in _HB]
            # ── beats: time-ordered evidence for the narrative + timeline (LLM) ──
            _order = {"Morning": 0, "Midday": 1, "Evening": 2, "Late evening": 3, "Next morning": 4}
            beats = sorted(
                [{"when": _tod(m.ts, m.pillar), "pillar": m.pillar, "verdict": m.verdict,
                  "text": m.evidence, "source": m.source_ref}
                 for m in members if m.evidence],
                key=lambda b: _order.get(b["when"], 5))
            big["beats"] = beats
            # citation line — every outlet that ran it, deduped, linked
            _bsrc: dict = {}
            for m in members:
                if not m.source_ref:
                    continue
                if m.source_ref not in _bsrc or (m.url and not _bsrc[m.source_ref].get("url")):
                    _bsrc[m.source_ref] = {"outlet": m.source_ref, "pillar": m.pillar, "url": m.url}
            big["sources"] = sorted(_bsrc.values(), key=lambda s: (s.get("url") is None, s["outlet"]))
            # tone across the media that ran it
            tbp = {}
            for m in members:
                d = tbp.setdefault(m.pillar, {"fav": 0, "crit": 0})
                if m.verdict == "favourable":
                    d["fav"] += 1
                elif m.verdict == "critical":
                    d["crit"] += 1
            big["tone_by_pillar"] = [{"pillar": p, "favourable": v["fav"], "critical": v["crit"],
                                      "net": _net(v["fav"], v["crit"])} for p, v in tbp.items()]
            # numbers cited in the big story (from its member web items)
            web_ids = [m.item_ref for m in members if m.pillar == "web"] if False else []
            web_ids = (await db.execute(text("""
                SELECT item_ref FROM briefing.items WHERE id = ANY(:ids) AND pillar IN ('web','newspaper')
            """), {"ids": list(e0.member_item_ids or [])})).fetchall()
            wids = [w.item_ref for w in web_ids]
            big_numbers = []
            if wids:
                rows = (await db.execute(text("""
                    SELECT value, unit, left(context,90) context FROM article_numbers
                     WHERE article_id = ANY(CAST(:ids AS uuid[])) AND unit IS NOT NULL
                       AND length(context) BETWEEN 10 AND 100 LIMIT 40
                """), {"ids": wids})).fetchall()

                def _rupees(v: str, u: str) -> float:
                    try:
                        n = float(str(v).replace(",", ""))
                    except (TypeError, ValueError):
                        return 0.0
                    ul = (u or "").lower()
                    return n * 1e7 if "crore" in ul else n * 1e5 if "lakh" in ul else n

                _MONEY = ("crore", "lakh", "rupee", "₹", " rs")
                seen, cand = set(), []
                for n in rows:
                    is_money = any(m in (n.unit or "").lower() for m in _MONEY)
                    rup = _rupees(n.value, n.unit)
                    # dedupe: crore-scale money figures collapse to the nearest
                    # whole crore (so "28.14 crore" and "28 crore" count once);
                    # sub-crore money and non-money keep exact value+unit.
                    key = ("cr", round(rup / 1e7)) if is_money and rup >= 1e7 else (str(n.value), (n.unit or "").lower())
                    if key in seen:
                        continue
                    seen.add(key)
                    cand.append((is_money, rup,
                                 {"value": str(n.value), "unit": n.unit, "context": n.context}))
                # money figures first, ranked by real rupee magnitude (so ₹200cr
                # leads ₹25,000); then any non-money figures.
                cand.sort(key=lambda c: (not c[0], -c[1]))
                big_numbers = [c[2] for c in cand[:4]]
            big["numbers"] = big_numbers

        # ══ EDITORIAL PROSE — clean headlines + detailed paragraphs (LLM) ══
        # Turns the top events into the depth the design mockup shows. Runs the
        # top-6 events + the big story concurrently. Falls back silently to the
        # raw label/evidence if a call fails.
        import asyncio as _aio
        from briefing import prose as _prose
        ev_member_ids = {i: list(e.member_item_ids or []) for i, e in enumerate(ev_rows[:6])}
        all_member_ids = sorted({x for ids in ev_member_ids.values() for x in ids})
        ev_by_item: dict = {}
        if all_member_ids:
            for m in (await db.execute(text(
                "SELECT id, evidence FROM briefing.items WHERE id = ANY(:ids)"
            ), {"ids": all_member_ids})).fetchall():
                ev_by_item[m.id] = m.evidence

        # ── citations: real outlet + link per member item, so every story is
        # verifiable. web + newspaper-web-editions carry articles.url; TV resolves
        # to youtu.be/<video_id>; only true scanned cuttings have no link. ──
        src_by_item: dict = {}
        if all_member_ids:
            for m in (await db.execute(text("""
                SELECT i.id, i.source_ref, i.pillar,
                       COALESCE(a.url, CASE WHEN i.pillar='tv'
                                            THEN 'https://youtu.be/'||i.item_ref END) url
                  FROM briefing.items i
                  LEFT JOIN articles a ON a.id::text=i.item_ref
                 WHERE i.id = ANY(:ids)
            """), {"ids": all_member_ids})).fetchall():
                src_by_item[m.id] = {"outlet": m.source_ref, "pillar": m.pillar, "url": m.url}

        def _event_sources(idx):
            """Deduped outlet list for one event (prefer the row that has a link)."""
            best: dict = {}
            for mid in ev_member_ids.get(idx, []):
                s = src_by_item.get(mid)
                if not s or not s.get("outlet"):
                    continue
                k = s["outlet"]
                if k not in best or (s.get("url") and not best[k].get("url")):
                    best[k] = s
            # links first, then alphabetical for stable output
            return sorted(best.values(), key=lambda s: (s.get("url") is None, s["outlet"]))

        _psem = _aio.Semaphore(2)  # gpt-oss-120b rate-limits under high concurrency

        async def _enrich_event(idx, eo):
            eo["sources"] = _event_sources(idx)  # always attached, even if prose fails
            evs = [ev_by_item.get(mid) for mid in ev_member_ids.get(idx, [])]
            evs = [e for e in evs if e]
            if not evs and eo.get("evidence"):
                evs = [eo["evidence"]]
            async with _psem:
                pr = await _prose.write_event(eo, evs)
            if pr.get("headline"):
                eo["headline"] = pr["headline"]
            if pr.get("paragraph"):
                eo["paragraph"] = pr["paragraph"]

        tasks = [_enrich_event(i, eo) for i, eo in enumerate(events_out[:6])]
        if big:
            async def _enrich_big():
                pr = {}
                for _ in range(2):  # the lead deserves a retry
                    async with _psem:
                        pr = await _prose.write_big_story(big, big.get("beats", []))
                    if pr.get("narrative"):
                        break
                for k in ("headline", "standfirst", "narrative", "timeline", "silence", "angle"):
                    if pr.get(k):
                        big[k] = pr[k]
            tasks.append(_enrich_big())
        try:
            await _aio.gather(*tasks)
        except Exception:  # noqa: BLE001
            pass

        # ══ §3 media cards: top item per pillar per topic, with images ══
        # Pick the representative card per (topic, pillar). Prefer an item that
        # actually carries an image (article thumbnail / scanned cutting) so the
        # card isn't a blank placeholder, THEN by strength/confidence. TV always
        # has a YouTube frame, so the image-preference is a no-op there.
        card_sel = (await db.execute(text("""
            SELECT DISTINCT ON (topic, pillar) topic, pillar, item_ref, source_ref, verdict
              FROM briefing.items i
              LEFT JOIN articles a ON a.id::text = i.item_ref
              LEFT JOIN clippings cl ON cl.id::text = i.item_ref
             WHERE run_id=:r AND about_government AND NOT unclear AND topic IS NOT NULL
             ORDER BY topic, pillar,
                      (COALESCE(length(cl.clipping_image_b64), 0) > 100) DESC, (COALESCE(cl.headline, a.title, '') !~ '[अ-ह]') DESC,
                      (a.thumbnail_url IS NOT NULL AND a.thumbnail_url <> '') DESC,
                      (strength='strong') DESC NULLS LAST, confidence DESC NULLS LAST
        """), {"r": rid})).fetchall()
        web_ids = [c.item_ref for c in card_sel if c.pillar == "web"]
        np_ids = [c.item_ref for c in card_sel if c.pillar == "newspaper"]
        tv_ids = [c.item_ref for c in card_sel if c.pillar == "tv"]
        imgmap: dict[str, dict] = {}
        if web_ids:
            for a in (await db.execute(text(
                "SELECT id::text ref, title, thumbnail_url thumb, url FROM articles WHERE id=ANY(CAST(:i AS uuid[]))"
            ), {"i": web_ids})).fetchall():
                imgmap[a.ref] = {"title": a.title, "thumb": a.thumb, "url": a.url, "kind": "web"}
        if np_ids:
            for c in (await db.execute(text(
                "SELECT id::text ref, headline title, clipping_image_b64 img FROM clippings WHERE id=ANY(CAST(:i AS uuid[]))"
            ), {"i": np_ids})).fetchall():
                imgmap[c.ref] = {"title": c.title, "img": c.img, "kind": "newspaper"}
            # print papers collected via web edition: item_ref is an article id
            np_miss = [x for x in np_ids if x not in imgmap]
            if np_miss:
                for a in (await db.execute(text(
                    "SELECT id::text ref, title, thumbnail_url thumb, url FROM articles WHERE id=ANY(CAST(:i AS uuid[]))"
                ), {"i": np_miss})).fetchall():
                    imgmap[a.ref] = {"title": a.title, "thumb": a.thumb, "url": a.url, "kind": "newspaper"}
        if tv_ids:
            for v in (await db.execute(text(
                "SELECT video_id ref, max(video_title) title FROM youtube_clips_v2 WHERE video_id=ANY(:i) GROUP BY video_id"
            ), {"i": tv_ids})).fetchall():
                imgmap[v.ref] = {"title": v.title, "video_id": v.ref, "url": "https://youtu.be/" + v.ref, "kind": "tv"}
        topic_cards: dict[str, dict] = {}
        for c in card_sel:
            d = imgmap.get(c.item_ref, {})
            topic_cards.setdefault(c.topic, {})[c.pillar] = {
                "source": c.source_ref, "verdict": c.verdict, "title": d.get("title", ""),
                "thumb": d.get("thumb"), "img": d.get("img"), "video_id": d.get("video_id"),
                "url": d.get("url")}

        # ══ §5 districts ══
        dist = (await db.execute(text("""
            SELECT d.name, count(*) n,
                   count(*) FILTER (WHERE i.verdict='favourable') fav,
                   count(*) FILTER (WHERE i.verdict='critical') crit
              FROM briefing.items i
              JOIN article_districts ad ON ad.article_id = CAST(i.item_ref AS uuid)
              JOIN districts d ON d.id = ad.district_id AND d.state_code='TG'
             WHERE i.run_id=:r AND i.pillar IN ('web','newspaper') AND i.about_government AND NOT i.unclear
             GROUP BY d.name ORDER BY n DESC LIMIT 14
        """), {"r": rid})).fetchall()
        district_rows = [{"district": d.name, "items": int(d.n), "favourable": int(d.fav),
                          "critical": int(d.crit), "net": _net(int(d.fav), int(d.crit))} for d in dist]
        # top critical + top positive story per district
        dnames = [d["district"] for d in district_rows[:12]]
        if dnames:
            tops = (await db.execute(text("""
                SELECT DISTINCT ON (d.name, i.verdict) d.name dn, i.verdict v, i.evidence ev, i.source_ref src
                  FROM briefing.items i
                  JOIN article_districts ad ON ad.article_id = CAST(i.item_ref AS uuid)
                  JOIN districts d ON d.id = ad.district_id AND d.state_code='TG'
                 WHERE i.run_id=:r AND i.pillar IN ('web','newspaper') AND i.about_government AND NOT i.unclear
                   AND d.name = ANY(:names) AND i.verdict IN ('critical','favourable')
                 ORDER BY d.name, i.verdict, (i.strength='strong') DESC NULLS LAST, i.confidence DESC NULLS LAST
            """), {"r": rid, "names": dnames})).fetchall()
            dmap: dict = {}
            for t in tops:
                dmap.setdefault(t.dn, {})[t.v] = {"text": t.ev, "source": t.src}
            for d in district_rows:
                dd = dmap.get(d["district"], {})
                d["top_critical"] = dd.get("critical")
                d["top_positive"] = dd.get("favourable")

        # ══ §7 quote contrast (gov vs opposition) — roster-classified AND
        # speaker-verified. We keep a quote only if the attributed speaker matches
        # a roster person AND that person's name/variant actually appears in the
        # article (title / URL slug / translated body). This catches NLP
        # mis-attributions (e.g. a BJP quote tagged to the wrong BJP leader)
        # before they reach the report. ══
        roster = (await db.execute(text("""
            SELECT lower(canonical_name) nm, side, name_variants FROM briefing.roster
             WHERE org_id=CAST(:o AS uuid) AND active
        """), {"o": org_id})).fetchall()
        people = []  # (variants:set[str], side:'gov'|'opp') — per-person, for verification
        for rr in roster:
            variants = {rr.nm} | {str(x).lower() for x in (rr.name_variants or [])}
            # require a non-empty NORMALISED form: a variant that _norm()s to ''
            # (pure vernacular script — the matcher strips non-Latin) makes
            # `'' in speaker` true for EVERY speaker, misclassifying the whole
            # report. Vernacular names live in telugu_names, not here.
            variants = {v for v in variants if len(v) >= 3 and any(c.isascii() and c.isalnum() for c in v)}
            if variants:
                people.append((variants, "gov" if rr.side in ("government", "institution") else "opp"))

        import re as _re

        def _norm(s: str) -> str:
            # collapse punctuation so "revanth-reddy" (URL slug) == "revanth reddy"
            return " " + _re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip() + " "

        def _verify_side(speaker: str, hay: str, near: str = ""):
            """'gov'/'opp' if the attributed speaker matches a roster person AND
            that person is corroborated by the article — either as its PRIMARY
            subject (name in headline/URL) or named NEAR the quote itself.

            Whole-body matching is deliberately NOT used: a body names several
            leaders in passing, which is how a Ramchander Rao quote got tagged to
            Bandi Sanjay. Headline/slug or local proximity are both strong; either
            one is enough, which keeps legitimate secondary speakers (a minister
            quoted in a story headlined about someone else) instead of dropping
            them wholesale."""
            sp = _norm(speaker)
            # single-word variants must match the WHOLE attributed name — a bare
            # "Anand" variant substring-matched "Sumitra Anand" and put an
            # opposition-toned quote under the government column
            for variants, side in people:
                if any((_norm(v).strip() == sp.strip()) if " " not in v.strip()
                       else (_norm(v).strip() in sp) for v in variants):
                    hayn = _norm(hay) + " " + _norm(near)
                    return side if any(_norm(v).strip() in hayn for v in variants) else None
            return None

        _HAY = "lower(COALESCE(a.title,'')||' '||COALESCE(a.url,''))"
        # ~400 chars either side of the quote — "is the speaker named next to
        # their own quote?" (article_quotes.context averages 9 chars, unusable)
        _NEAR = ("lower(substr(COALESCE(a.full_text_translated, a.full_text_scraped, ''),"
                 " GREATEST(COALESCE(q.char_offset_start,1) - 400, 1), 900))")
        qrows = (await db.execute(text(f"""
            SELECT q.speaker_name sp, q.quote_text qt, q.quote_text_en en,
                   s.name src, a.url url, {_HAY} hay, {_NEAR} near
              FROM briefing.items i
              JOIN article_quotes q ON q.article_id = CAST(i.item_ref AS uuid)
              JOIN articles a ON a.id = CAST(i.item_ref AS uuid)
              JOIN sources s ON s.id = a.source_id
             WHERE i.run_id=:r AND i.pillar IN ('web','newspaper') AND i.about_government
               AND q.is_direct AND q.speaker_name IS NOT NULL
               AND q.quote_text NOT LIKE '%@%' AND length(q.quote_text) BETWEEN 40 AND 240
             LIMIT 300
        """), {"r": rid})).fetchall()
        gov_q, opp_q, seen_q = [], [], set()
        for q in qrows:
            key = (q.qt or "")[:60]
            if key in seen_q:
                continue
            seen_q.add(key)
            side = _verify_side(q.sp, q.hay or "", q.near or "")
            rec = {"speaker": q.sp, "text": q.qt, "en": q.en, "source": q.src, "url": q.url}
            if side == "gov" and len(gov_q) < 7:
                gov_q.append(rec)
            elif side == "opp" and len(opp_q) < 7:
                opp_q.append(rec)
        quotes = {"government": gov_q, "opposition": opp_q}

        # ── §2 "what each side said": same source + same speaker verification. ──
        if big and big.get("_web_refs"):
            brows = (await db.execute(text(f"""
                SELECT q.speaker_name sp, q.quote_text qt, q.quote_text_en en,
                       s.name src, a.url url, {_HAY} hay, {_NEAR} near
                  FROM article_quotes q
                  JOIN articles a ON a.id = q.article_id
                  JOIN sources s ON s.id = a.source_id
                 WHERE q.article_id = ANY(CAST(:ids AS uuid[]))
                   AND q.is_direct AND q.speaker_name IS NOT NULL
                   AND length(q.quote_text) BETWEEN 30 AND 260
            """), {"ids": big["_web_refs"]})).fetchall()
            bg = bo = None
            for q in brows:
                side = _verify_side(q.sp, q.hay or "", q.near or "")
                if side == "gov" and not bg:
                    bg = {"speaker": q.sp, "text": q.qt, "en": q.en, "source": q.src, "url": q.url}
                elif side == "opp" and not bo:
                    bo = {"speaker": q.sp, "text": q.qt, "en": q.en, "source": q.src, "url": q.url}
            big["gov_side"], big["opp_side"] = bg, bo

        # translate the Telugu quotes we actually show to English (one batched
        # call) — quote_text_en is unpopulated in the corpus.
        _tq = list(gov_q) + list(opp_q)
        if big:
            _tq += [x for x in (big.get("gov_side"), big.get("opp_side")) if x]
        _tr = await _prose.translate_te_en([q["text"] for q in _tq if q.get("text")])
        for q in _tq:
            if not q.get("en"):
                q["en"] = _tr.get(q.get("text"))

        # rewrite each figure's caption into one clear line: what the amount is
        # and which scheme / project / case it belongs to (from context + title).
        _figexp = await _prose.explain_figures(figure_rows)
        for f, ex in zip(figure_rows, _figexp):
            if ex:
                f["context"] = ex

        if big:
            big.pop("_web_refs", None)
            big.pop("beats", None)  # internal raw material — keep it out of stored JSON

        # ══ §10 annexure — all three media (web url, TV url, newspaper: no url) ══
        anx_web = (await db.execute(text("""
            SELECT i.pillar, i.source_ref src, i.lang, i.verdict, a.title, a.url
              FROM briefing.items i JOIN articles a ON a.id = CAST(i.item_ref AS uuid)
             WHERE i.run_id=:r AND i.pillar IN ('web','newspaper') AND i.about_government AND NOT i.unclear
             ORDER BY (i.strength='strong') DESC NULLS LAST, i.confidence DESC NULLS LAST LIMIT 18
        """), {"r": rid})).fetchall()
        anx_tv = (await db.execute(text("""
            SELECT i.pillar, i.source_ref src, i.lang, i.verdict,
                   max(v.video_title) title, 'https://youtu.be/'||i.item_ref url
              FROM briefing.items i JOIN youtube_clips_v2 v ON v.video_id = i.item_ref
             WHERE i.run_id=:r AND i.pillar='tv' AND i.about_government AND NOT i.unclear
             GROUP BY i.pillar, i.source_ref, i.lang, i.verdict, i.item_ref, i.strength, i.confidence
             ORDER BY (i.strength='strong') DESC NULLS LAST, i.confidence DESC NULLS LAST LIMIT 8
        """), {"r": rid})).fetchall()
        anx_np = (await db.execute(text("""
            SELECT i.pillar, i.source_ref src, i.lang, i.verdict,
                   COALESCE(c.headline, a.title) title, a.url
              FROM briefing.items i
              LEFT JOIN clippings c ON c.id = CAST(i.item_ref AS uuid)
              LEFT JOIN articles a ON a.id = CAST(i.item_ref AS uuid)
             WHERE i.run_id=:r AND i.pillar='newspaper' AND i.about_government AND NOT i.unclear
             ORDER BY (i.strength='strong') DESC NULLS LAST, i.confidence DESC NULLS LAST LIMIT 10
        """), {"r": rid})).fetchall()
        annexure = [{"pillar": a.pillar, "source": a.src, "lang": a.lang, "verdict": a.verdict,
                     "title": a.title, "url": a.url} for a in list(anx_web) + list(anx_tv) + list(anx_np)]

        # ══ §4 scheme scorecard — per-scheme block: 3-media split + net + a top
        # article/TV/newspaper card (like §3). The spec's 7-day tone trend is
        # deferred until dated verdict history accrues ("empty at launch"). ══
        sch = (await db.execute(text("""
            SELECT scheme, count(*) n,
                   count(*) FILTER (WHERE pillar='web') web,
                   count(*) FILTER (WHERE pillar='tv') tv,
                   count(*) FILTER (WHERE pillar='newspaper') np,
                   count(*) FILTER (WHERE verdict='favourable') fav,
                   count(*) FILTER (WHERE verdict='critical') crit
              FROM briefing.items
             WHERE run_id=:r AND about_government AND NOT unclear AND scheme IS NOT NULL
             GROUP BY 1 ORDER BY 2 DESC
        """), {"r": rid})).fetchall()
        # representative card per (scheme, pillar), preferring items with an image
        scard_sel = (await db.execute(text("""
            SELECT DISTINCT ON (scheme, pillar) scheme, pillar, item_ref, source_ref, verdict
              FROM briefing.items i
              LEFT JOIN articles a ON a.id::text = i.item_ref
              LEFT JOIN clippings cl ON cl.id::text = i.item_ref
             WHERE run_id=:r AND about_government AND NOT unclear AND scheme IS NOT NULL
             ORDER BY scheme, pillar,
                      (COALESCE(length(cl.clipping_image_b64), 0) > 100) DESC, (COALESCE(cl.headline, a.title, '') !~ '[अ-ह]') DESC,
                      (a.thumbnail_url IS NOT NULL AND a.thumbnail_url <> '') DESC,
                      (strength='strong') DESC NULLS LAST, confidence DESC NULLS LAST
        """), {"r": rid})).fetchall()
        s_web = [c.item_ref for c in scard_sel if c.pillar == "web"]
        s_np = [c.item_ref for c in scard_sel if c.pillar == "newspaper"]
        s_tv = [c.item_ref for c in scard_sel if c.pillar == "tv"]
        s_img: dict = {}
        if s_web:
            for a in (await db.execute(text(
                "SELECT id::text ref, title, thumbnail_url thumb, url FROM articles WHERE id=ANY(CAST(:i AS uuid[]))"
            ), {"i": s_web})).fetchall():
                s_img[a.ref] = {"title": a.title, "thumb": a.thumb, "url": a.url}
        if s_np:
            for c in (await db.execute(text(
                "SELECT id::text ref, headline title, clipping_image_b64 img FROM clippings WHERE id=ANY(CAST(:i AS uuid[]))"
            ), {"i": s_np})).fetchall():
                s_img[c.ref] = {"title": c.title, "img": c.img}
            miss = [x for x in s_np if x not in s_img]
            if miss:
                for a in (await db.execute(text(
                    "SELECT id::text ref, title, thumbnail_url thumb, url FROM articles WHERE id=ANY(CAST(:i AS uuid[]))"
                ), {"i": miss})).fetchall():
                    s_img[a.ref] = {"title": a.title, "thumb": a.thumb, "url": a.url}
        if s_tv:
            for v in (await db.execute(text(
                "SELECT video_id ref, max(video_title) title FROM youtube_clips_v2 WHERE video_id=ANY(:i) GROUP BY video_id"
            ), {"i": s_tv})).fetchall():
                s_img[v.ref] = {"title": v.title, "video_id": v.ref, "url": "https://youtu.be/" + v.ref}
        scards: dict = {}
        for c in scard_sel:
            d = s_img.get(c.item_ref, {})
            scards.setdefault(c.scheme, {})[c.pillar] = {
                "source": c.source_ref, "verdict": c.verdict, "title": d.get("title", ""),
                "thumb": d.get("thumb"), "img": d.get("img"), "video_id": d.get("video_id"),
                "url": d.get("url")}
        scheme_rows = [{"scheme": sc.scheme, "items": int(sc.n),
                        "web": int(sc.web), "tv": int(sc.tv), "np": int(sc.np),
                        "favourable": int(sc.fav), "critical": int(sc.crit),
                        "net": _net(int(sc.fav), int(sc.crit)),
                        "cards": scards.get(sc.scheme, {})} for sc in sch]

        # ══ §6 divergence readout ══
        divergence = None
        if len(media_rows) >= 2:
            ordm = sorted(media_rows, key=lambda m: m["net"])
            lo, hi = ordm[0], ordm[-1]
            gap = hi["net"] - lo["net"]
            if gap >= 20:
                lab = {"web": "online", "tv": "television", "newspaper": "newspapers"}
                divergence = {"gap": gap, "hostile": lab.get(lo["pillar"], lo["pillar"]),
                              "hostile_net": lo["net"], "soft": lab.get(hi["pillar"], hi["pillar"]),
                              "soft_net": hi["net"]}

        report = {
            "org_id": org_id,
            "cover_date": str(cover_date),
            "events": events_out,
            "big_story": big,
            "topic_cards": topic_cards,
            "districts": district_rows,
            "schemes": scheme_rows,
            "divergence": divergence,
            "quotes": quotes,
            "annexure": annexure,
            "strip": {
                "total": total, "by_pillar": by_pillar,
                "about_government": gov_total, "scanned": scanned,
                "biggest_subject": {"topic": biggest, "items": biggest_n},
                "sentiment": {"net": net, "favourable": fav, "critical": crit, "neutral": neu},
                "top_outlet_by_medium": top_by_medium,
            },
            "sentiment": {"net": net, "favourable": fav, "critical": crit, "neutral": neu},
            "topics": topic_rows,
            "media_compare": media_rows,
            "outlets": outlet_rows,
            "brief": brief_rows,
            "figures": figure_rows,
        }

        # store immutable report JSON
        import json
        await db.execute(text("""
            INSERT INTO briefing.report (run_id, org_id, json)
            VALUES (:r, CAST(:o AS uuid), CAST(:j AS jsonb))
            ON CONFLICT (run_id) DO UPDATE SET json=EXCLUDED.json, created_at=now(),
                                               pdf=NULL, html=NULL
        """), {"r": rid, "o": org_id, "j": json.dumps(report)})
        await db.commit()
        return report
