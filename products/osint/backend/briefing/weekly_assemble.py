"""Assemble a MULTI-DAY (weekly) report from stored briefing.items/events across
several already-judged runs. Same underlying engine as assemble.py (same tables,
same net-sentiment formula, same event/scheme/quote logic) — but every query is
scoped to `run_id = ANY(:runs)` instead of a single day, and the sections that
only make sense with history (sentiment trend, scheme tone-over-time, outlet
lean-over-time) are now real instead of the daily report's "deferred" placeholder.

net sentiment = round(100 * (fav - crit) / (fav + crit)), same as the daily report.
"""
from __future__ import annotations

import re as _re
from typing import Any

from sqlalchemy import text
from db import get_db


def _net(fav: int, crit: int) -> int:
    d = fav + crit
    return round(100 * (fav - crit) / d) if d else 0


def _day_label_iso(d) -> str:
    return d.strftime("%a %d %b")  # e.g. "Mon 20 Jul" — used as write_big_story's "when"


async def _get_runs(db, org_id: str, start_date, end_date):
    rows = (await db.execute(text("""
        SELECT id, cover_date FROM briefing.runs
         WHERE org_id=CAST(:o AS uuid) AND cover_date BETWEEN :s AND :e
           AND status = 'merged'
         ORDER BY cover_date
    """), {"o": org_id, "s": start_date, "e": end_date})).fetchall()
    return rows


_SOV_PARTY_ENTS = {"congress": "gov", "telanganacongress": "gov", "inc": "gov",
                   "indiannationalcongress": "gov",
                   "brs": "opp", "trs": "opp", "bjp": "opp", "aimim": "opp",
                   "telanganabjp": "opp"}
_SOV_PARTY_CHANNEL_MARKERS = ("party", "congress", "brs", "aimim", "bjp", "police")


async def tv_share_of_voice(db, org_id: str, run_ids: list) -> dict[str, Any]:
    """TV share of voice: government-side vs opposition figures, per channel.

    A video counts toward a side if ANY of its extracted entities resolves to a
    roster person/institution of that side (normalised-name match) or a party
    (_SOV_PARTY_ENTS). Party/politician-owned channels are split out of the news
    table. NOTE: featuring != favourable — per-channel gov_crit carries how much
    of the government-featuring coverage was critical (attack coverage).
    """
    import json as _json
    rows = (await db.execute(text("""
        WITH wk AS (
          SELECT DISTINCT i.item_ref vid, i.verdict FROM briefing.items i
           WHERE i.run_id = ANY(:runs) AND i.pillar='tv'
             AND i.about_government AND NOT i.unclear
        ),
        roster AS (
          SELECT regexp_replace(lower(n), '[^a-z0-9]', '', 'g') norm,
                 CASE WHEN side='opposition' THEN 'opp' ELSE 'gov' END side
            FROM briefing.roster, LATERAL unnest(name_variants || ARRAY[canonical_name]) n
           WHERE org_id=CAST(:o AS uuid) AND active AND length(n) >= 4
        )
        SELECT t.vid, t.verdict, t.channel_name,
               COALESCE(bool_or(t.side='gov'), false) has_gov,
               COALESCE(bool_or(t.side='opp'), false) has_opp
          FROM (
            SELECT wk.vid, wk.verdict, v.channel_name,
                   COALESCE(r.side, CAST(:party_map AS jsonb) ->> e.ent) side
              FROM wk
              JOIN youtube_clips_v2 v ON v.video_id = wk.vid
              CROSS JOIN LATERAL (SELECT regexp_replace(lower(v.matched_entity),
                                         '[^a-z0-9]', '', 'g') ent) e
              LEFT JOIN roster r ON r.norm = e.ent
             WHERE v.matched_entity IS NOT NULL
          ) t
         GROUP BY t.vid, t.verdict, t.channel_name
    """), {"runs": run_ids, "o": org_id,
           "party_map": _json.dumps(_SOV_PARTY_ENTS)})).fetchall()

    roster_norms = {r.norm for r in (await db.execute(text("""
        SELECT regexp_replace(lower(canonical_name), '[^a-z0-9]', '', 'g') norm
          FROM briefing.roster WHERE org_id=CAST(:o AS uuid) AND active
    """), {"o": org_id})).fetchall()}

    def _party_owned(channel: str) -> bool:
        cn = _re.sub(r"[^a-z0-9]", "", (channel or "").lower())
        cl = (channel or "").lower()
        return (any(m in cl for m in _SOV_PARTY_CHANNEL_MARKERS)
                or any(n and n in cn for n in roster_norms))

    per: dict[str, dict] = {}
    tot = {"total": 0, "gov": 0, "opp": 0, "both": 0, "unattributed": 0}
    for r in rows:
        tot["total"] += 1
        if r.has_gov:
            tot["gov"] += 1
        if r.has_opp:
            tot["opp"] += 1
        if r.has_gov and r.has_opp:
            tot["both"] += 1
        if not r.has_gov and not r.has_opp:
            tot["unattributed"] += 1
        c = per.setdefault(r.channel_name or "?", {
            "channel": r.channel_name or "?", "items": 0, "gov": 0, "opp": 0,
            "both": 0, "gov_crit": 0})
        c["items"] += 1
        if r.has_gov:
            c["gov"] += 1
            if r.verdict == "critical":
                c["gov_crit"] += 1
        if r.has_opp:
            c["opp"] += 1
        if r.has_gov and r.has_opp:
            c["both"] += 1

    news = sorted((c for c in per.values()
                   if c["items"] >= 5 and not _party_owned(c["channel"])),
                  key=lambda c: c["items"], reverse=True)
    tail = [c for c in per.values()
            if c["items"] < 5 and not _party_owned(c["channel"])]
    party = [c for c in per.values() if _party_owned(c["channel"])]
    other = {"items": sum(c["items"] for c in tail),
             "gov": sum(c["gov"] for c in tail),
             "opp": sum(c["opp"] for c in tail)}
    party_owned = {"items": sum(c["items"] for c in party),
                   "gov": sum(c["gov"] for c in party),
                   "opp": sum(c["opp"] for c in party),
                   "n_channels": len(party)}
    ratio = round(tot["gov"] / tot["opp"], 1) if tot["opp"] else None
    return {**tot, "ratio": ratio, "channels": news, "other": other,
            "party_owned": party_owned}


async def assemble_weekly(org_id: str, start_date, end_date) -> dict[str, Any]:
    async with get_db() as db:
        runs = await _get_runs(db, org_id, start_date, end_date)
        if not runs:
            return {"error": "no judged runs in range"}
        run_ids = [r.id for r in runs]
        day_by_run = {r.id: str(r.cover_date) for r in runs}
        days = [str(r.cover_date) for r in runs]

        # ── strip: totals by pillar (gov-relevant only), across the whole week ──
        tot = (await db.execute(text("""
            SELECT pillar, count(*) n FROM briefing.items
             WHERE run_id = ANY(:runs) AND about_government AND NOT unclear GROUP BY 1
        """), {"runs": run_ids})).fetchall()
        by_pillar = {p: 0 for p in ("web", "tv", "newspaper")}
        for row in tot:
            by_pillar[row.pillar] = int(row.n)
        total = sum(by_pillar.values())
        scanned = int((await db.execute(text(
            "SELECT count(*) FROM briefing.items WHERE run_id = ANY(:runs)"
        ), {"runs": run_ids})).scalar() or 0)

        # ── sentiment (week total) ──
        s = (await db.execute(text("""
            SELECT count(*) FILTER (WHERE verdict='favourable') fav,
                   count(*) FILTER (WHERE verdict='critical') crit,
                   count(*) FILTER (WHERE verdict='neutral') neu
              FROM briefing.items WHERE run_id = ANY(:runs) AND about_government AND NOT unclear
        """), {"runs": run_ids})).fetchone()
        fav, crit, neu = int(s.fav), int(s.crit), int(s.neu)
        net = _net(fav, crit)
        gov_total = fav + crit + neu

        # ── NEW: day-by-day totals + net (the trend line daily reports can't show) ──
        daily_rows = (await db.execute(text("""
            SELECT i.run_id, count(*) n,
                   count(*) FILTER (WHERE i.verdict='favourable') fav,
                   count(*) FILTER (WHERE i.verdict='critical') crit
              FROM briefing.items i
             WHERE i.run_id = ANY(:runs) AND i.about_government AND NOT i.unclear
             GROUP BY i.run_id
        """), {"runs": run_ids})).fetchall()
        daily_map = {r.run_id: r for r in daily_rows}
        daily_totals = [{
            "date": day_by_run[rid],
            "items": int(daily_map[rid].n) if rid in daily_map else 0,
            "favourable": int(daily_map[rid].fav) if rid in daily_map else 0,
            "critical": int(daily_map[rid].crit) if rid in daily_map else 0,
            "net": _net(int(daily_map[rid].fav), int(daily_map[rid].crit)) if rid in daily_map else 0,
        } for rid in run_ids]

        # ── NEW: previous-week comparison (same aggregates, prior 7 days) — the
        # deltas the client actually reads first: is tone better or worse than
        # last week, and which subjects swung. Skipped cleanly when the prior
        # week has no judged runs. ──
        import datetime as _dt
        prev_start = start_date - _dt.timedelta(days=7)
        prev_end = start_date - _dt.timedelta(days=1)
        prev_runs = await _get_runs(db, org_id, prev_start, prev_end)
        prev = None
        prev_topic_map: dict[str, dict] = {}
        if prev_runs:
            prev_ids = [r.id for r in prev_runs]
            ps = (await db.execute(text("""
                SELECT count(*) FILTER (WHERE verdict='favourable') fav,
                       count(*) FILTER (WHERE verdict='critical') crit,
                       count(*) n
                  FROM briefing.items
                 WHERE run_id = ANY(:runs) AND about_government AND NOT unclear
            """), {"runs": prev_ids})).fetchone()
            prev_topics = (await db.execute(text("""
                SELECT topic, count(*) n,
                       count(*) FILTER (WHERE verdict='favourable') fav,
                       count(*) FILTER (WHERE verdict='critical') crit
                  FROM briefing.items
                 WHERE run_id = ANY(:runs) AND about_government AND NOT unclear AND topic IS NOT NULL
                 GROUP BY 1
            """), {"runs": prev_ids})).fetchall()
            prev_topic_map = {t.topic: {"items": int(t.n), "net": _net(int(t.fav), int(t.crit))}
                              for t in prev_topics}
            prev = {"start": str(prev_start), "end": str(prev_end), "days": len(prev_runs),
                    "total": int(ps.n), "favourable": int(ps.fav), "critical": int(ps.crit),
                    "net": _net(int(ps.fav), int(ps.crit))}

        # ── biggest subject of the week ──
        topics = (await db.execute(text("""
            SELECT topic, count(*) n,
                   count(*) FILTER (WHERE verdict='favourable') fav,
                   count(*) FILTER (WHERE verdict='critical') crit
              FROM briefing.items
             WHERE run_id = ANY(:runs) AND about_government AND NOT unclear AND topic IS NOT NULL
             GROUP BY 1 ORDER BY 2 DESC
        """), {"runs": run_ids})).fetchall()
        topic_rows = [{"topic": t.topic, "items": int(t.n),
                       "favourable": int(t.fav), "critical": int(t.crit),
                       "net": _net(int(t.fav), int(t.crit))} for t in topics]
        biggest = topic_rows[0]["topic"] if topic_rows else None
        biggest_n = topic_rows[0]["items"] if topic_rows else 0

        # per-topic daily breakdown (small "sparkline" data for the topic table)
        topic_daily = (await db.execute(text("""
            SELECT i.run_id, i.topic, count(*) n,
                   count(*) FILTER (WHERE i.verdict='favourable') fav,
                   count(*) FILTER (WHERE i.verdict='critical') crit
              FROM briefing.items i
             WHERE i.run_id = ANY(:runs) AND i.about_government AND NOT i.unclear AND i.topic IS NOT NULL
             GROUP BY i.run_id, i.topic
        """), {"runs": run_ids})).fetchall()
        topic_daily_map: dict[str, dict] = {}
        for r in topic_daily:
            topic_daily_map.setdefault(r.topic, {})[day_by_run[r.run_id]] = {
                "items": int(r.n), "net": _net(int(r.fav), int(r.crit))}
        for t in topic_rows:
            t["daily"] = [{"date": d, **topic_daily_map.get(t["topic"], {}).get(
                d, {"items": 0, "net": 0})} for d in days]
            pt = prev_topic_map.get(t["topic"])
            t["prev_net"] = pt["net"] if pt else None
            t["prev_items"] = pt["items"] if pt else None

        # ── NEW: topic movers — biggest week-over-week tone swings among topics
        # substantial in BOTH weeks (small samples make ±100 swings meaningless) ──
        movers = sorted(
            ({"topic": t["topic"], "items": t["items"], "net": t["net"],
              "prev_net": t["prev_net"], "swing": t["net"] - t["prev_net"]}
             for t in topic_rows
             if t["prev_net"] is not None and t["items"] >= 8
             and (prev_topic_map.get(t["topic"], {}).get("items") or 0) >= 8),
            key=lambda m: abs(m["swing"]), reverse=True)
        movers = [m for m in movers if abs(m["swing"]) >= 10][:6]

        # ── media compare (week total + day-by-day per pillar) ──
        media = (await db.execute(text("""
            SELECT pillar, count(*) FILTER (WHERE verdict='favourable') fav,
                   count(*) FILTER (WHERE verdict='critical') crit
              FROM briefing.items WHERE run_id = ANY(:runs) AND about_government AND NOT unclear
             GROUP BY 1
        """), {"runs": run_ids})).fetchall()
        media_rows = [{"pillar": m.pillar, "favourable": int(m.fav), "critical": int(m.crit),
                       "net": _net(int(m.fav), int(m.crit))} for m in media]
        media_daily = (await db.execute(text("""
            SELECT i.run_id, i.pillar, count(*) FILTER (WHERE i.verdict='favourable') fav,
                   count(*) FILTER (WHERE i.verdict='critical') crit
              FROM briefing.items i
             WHERE i.run_id = ANY(:runs) AND i.about_government AND NOT i.unclear
             GROUP BY i.run_id, i.pillar
        """), {"runs": run_ids})).fetchall()
        md_map: dict[str, dict] = {}
        for r in media_daily:
            md_map.setdefault(r.pillar, {})[day_by_run[r.run_id]] = _net(int(r.fav), int(r.crit))
        for m in media_rows:
            m["daily"] = [{"date": d, "net": md_map.get(m["pillar"], {}).get(d, 0)} for d in days]

        # ── outlets (week total, top 12 by volume) + daily lean trend ──
        outlets = (await db.execute(text("""
            SELECT source_ref, pillar, count(*) n,
                   count(*) FILTER (WHERE verdict='favourable') fav,
                   count(*) FILTER (WHERE verdict='critical') crit
              FROM briefing.items WHERE run_id = ANY(:runs) AND about_government AND NOT unclear
             GROUP BY 1,2 ORDER BY 3 DESC LIMIT 12
        """), {"runs": run_ids})).fetchall()
        outlet_rows = [{"outlet": o.source_ref, "pillar": o.pillar, "on_govt": int(o.n),
                        "favourable": int(o.fav), "critical": int(o.crit),
                        "net": _net(int(o.fav), int(o.crit))} for o in outlets]
        onames = [o["outlet"] for o in outlet_rows]
        if onames:
            outlet_daily = (await db.execute(text("""
                SELECT run_id, source_ref, count(*) n,
                       count(*) FILTER (WHERE verdict='favourable') fav,
                       count(*) FILTER (WHERE verdict='critical') crit
                  FROM briefing.items
                 WHERE run_id = ANY(:runs) AND about_government AND NOT unclear
                   AND source_ref = ANY(:names)
                 GROUP BY run_id, source_ref
            """), {"runs": run_ids, "names": onames})).fetchall()
            od_map: dict[str, dict] = {}
            for r in outlet_daily:
                # BUG FIXED: "items" was never included here, so the trend
                # sparkline's height calc (which scales bar height by volume)
                # always fell back to a flat minimum bar — every outlet's 7-day
                # graph looked identical regardless of real volume.
                od_map.setdefault(r.source_ref, {})[day_by_run[r.run_id]] = {
                    "items": int(r.n), "net": _net(int(r.fav), int(r.crit))}
            for o in outlet_rows:
                o["daily"] = [{"date": d, **od_map.get(o["outlet"], {}).get(d, {"items": 0, "net": 0})}
                              for d in days]

        top_by_medium = {}
        for p in ("web", "tv", "newspaper"):
            row = (await db.execute(text("""
                SELECT source_ref, count(*) n FROM briefing.items
                 WHERE run_id = ANY(:runs) AND about_government AND pillar=:p
                 GROUP BY 1 ORDER BY 2 DESC LIMIT 1
            """), {"runs": run_ids, "p": p})).fetchone()
            if row:
                top_by_medium[p] = {"outlet": row.source_ref, "n": int(row.n)}

        # ══ week in brief — 2 strongest gov items per day, most-recent day first ══
        week_brief = []
        for r in reversed(runs):
            rows = (await db.execute(text("""
                SELECT i.pillar, i.source_ref, i.verdict, i.topic, i.department,
                       i.evidence, i.item_ref,
                       COALESCE(
                         (SELECT a.title FROM articles a WHERE a.id::text=i.item_ref),
                         (SELECT c.headline FROM clippings c WHERE c.id::text=i.item_ref),
                         (SELECT max(v.video_title) FROM youtube_clips_v2 v WHERE v.video_id=i.item_ref)
                       ) title,
                       COALESCE(
                         (SELECT a.url FROM articles a WHERE a.id::text=i.item_ref),
                         CASE WHEN i.pillar='tv' THEN 'https://youtu.be/'||i.item_ref END
                       ) url
                  FROM briefing.items i
                 WHERE i.run_id=:r AND i.about_government AND NOT i.unclear
                 ORDER BY (i.strength='strong') DESC NULLS LAST,
                          (i.verdict='critical') DESC, i.confidence DESC NULLS LAST
                 LIMIT 2
            """), {"r": r.id})).fetchall()
            for b in rows:
                week_brief.append({"date": str(r.cover_date), "pillar": b.pillar, "source": b.source_ref,
                                   "verdict": b.verdict, "topic": b.topic, "department": b.department,
                                   "title": b.title, "evidence": b.evidence, "url": b.url})

        # ══ week's big story: highest-volume, most-critical topic. Beats = the
        # TOP 3 items per day (not 1), day-labeled, so the LLM narrative has
        # real week-long material to work with — matching the depth of the
        # daily report's §2, stretched across 7 days instead of 1. ══
        big = None
        if topic_rows:
            lead_topic = sorted(topic_rows, key=lambda t: (t["critical"], t["items"]), reverse=True)[0]["topic"]
            per_day = []
            for r in runs:
                rows = (await db.execute(text("""
                    SELECT i.pillar, i.source_ref, i.verdict, i.evidence, i.item_ref
                      FROM briefing.items i
                     WHERE i.run_id=:r AND i.about_government AND NOT i.unclear AND i.topic=:t
                     ORDER BY (i.strength='strong') DESC NULLS LAST, i.confidence DESC NULLS LAST
                     LIMIT 3
                """), {"r": r.id, "t": lead_topic})).fetchall()
                for row in rows:
                    if row.evidence:
                        per_day.append({"date": str(r.cover_date), "when": _day_label_iso(r.cover_date),
                                        "pillar": row.pillar, "source": row.source_ref,
                                        "verdict": row.verdict, "text": row.evidence})
            tsum = next(t for t in topic_rows if t["topic"] == lead_topic)
            spread = (await db.execute(text("""
                SELECT count(*) FILTER (WHERE pillar='web') web,
                       count(*) FILTER (WHERE pillar='tv') tv,
                       count(*) FILTER (WHERE pillar='newspaper') np
                  FROM briefing.items
                 WHERE run_id = ANY(:runs) AND about_government AND NOT unclear AND topic=:t
            """), {"runs": run_ids, "t": lead_topic})).fetchone()
            dominant = max((("web", spread.web), ("tv", spread.tv), ("newspaper", spread.np)),
                          key=lambda x: x[1] or 0)[0]

            # ── 3-media cards: the single best web/TV/newspaper item for this
            # topic across the WHOLE week, with real images — "images from all
            # three sources" for the lead story. ──
            bcard_sel = (await db.execute(text("""
                SELECT DISTINCT ON (pillar) pillar, item_ref, source_ref, verdict
                  FROM briefing.items i
                  LEFT JOIN articles a ON a.id::text = i.item_ref
                  LEFT JOIN clippings cl ON cl.id::text = i.item_ref
                 WHERE run_id = ANY(:runs) AND about_government AND NOT unclear AND topic=:t
                 ORDER BY pillar, (COALESCE(length(cl.clipping_image_b64), 0) > 100) DESC, (COALESCE(cl.headline, a.title, '') !~ '[अ-ह]') DESC,
                          (a.thumbnail_url IS NOT NULL AND a.thumbnail_url <> '') DESC,
                          (strength='strong') DESC NULLS LAST, confidence DESC NULLS LAST
            """), {"runs": run_ids, "t": lead_topic})).fetchall()
            bweb = [c.item_ref for c in bcard_sel if c.pillar == "web"]
            bnp = [c.item_ref for c in bcard_sel if c.pillar == "newspaper"]
            btv = [c.item_ref for c in bcard_sel if c.pillar == "tv"]
            bimg: dict = {}
            if bweb:
                for a in (await db.execute(text(
                    "SELECT id::text ref, title, thumbnail_url thumb, url FROM articles WHERE id=ANY(CAST(:i AS uuid[]))"
                ), {"i": bweb})).fetchall():
                    bimg[a.ref] = {"title": a.title, "thumb": a.thumb, "url": a.url}
            if bnp:
                for c in (await db.execute(text(
                    "SELECT id::text ref, headline title, clipping_image_b64 img FROM clippings WHERE id=ANY(CAST(:i AS uuid[]))"
                ), {"i": bnp})).fetchall():
                    bimg[c.ref] = {"title": c.title, "img": c.img}
                miss = [x for x in bnp if x not in bimg]
                if miss:
                    for a in (await db.execute(text(
                        "SELECT id::text ref, title, thumbnail_url thumb, url FROM articles WHERE id=ANY(CAST(:i AS uuid[]))"
                    ), {"i": miss})).fetchall():
                        bimg[a.ref] = {"title": a.title, "thumb": a.thumb, "url": a.url}
            if btv:
                for v in (await db.execute(text(
                    "SELECT video_id ref, max(video_title) title FROM youtube_clips_v2 WHERE video_id=ANY(:i) GROUP BY video_id"
                ), {"i": btv})).fetchall():
                    bimg[v.ref] = {"title": v.title, "video_id": v.ref, "url": "https://youtu.be/" + v.ref}
            bcards: dict = {}
            for c in bcard_sel:
                d = bimg.get(c.item_ref, {})
                bcards[c.pillar] = {"source": c.source_ref, "verdict": c.verdict,
                                    "title": d.get("title", ""), "thumb": d.get("thumb"),
                                    "img": d.get("img"), "video_id": d.get("video_id"), "url": d.get("url")}

            # ── figures cited within the lead topic, across the week ──
            bnum_rows = (await db.execute(text("""
                SELECT n.value, n.unit, left(n.context,90) context FROM briefing.items i
                  JOIN article_numbers n ON n.article_id::text=i.item_ref
                 WHERE i.run_id = ANY(:runs) AND i.about_government AND i.pillar='web' AND i.topic=:t
                   AND n.unit IS NOT NULL AND length(n.context) BETWEEN 10 AND 100 LIMIT 20
            """), {"runs": run_ids, "t": lead_topic})).fetchall()
            seen_bn, big_numbers = set(), []
            for n in bnum_rows:
                key = (str(n.value), (n.unit or "").lower())
                if key in seen_bn:
                    continue
                seen_bn.add(key)
                big_numbers.append({"value": str(n.value), "unit": n.unit, "context": n.context})
            big_numbers = big_numbers[:4]

            big = {
                "label": lead_topic, "topic": lead_topic,
                "spread": {"web": int(spread.web), "tv": int(spread.tv), "newspaper": int(spread.np)},
                "dominant_pillar": {"web": "online", "tv": "television", "newspaper": "newspapers"}[dominant],
                "net": tsum["net"], "size": tsum["items"],
                "daily": [{"date": d, **topic_daily_map.get(lead_topic, {}).get(d, {"items": 0, "net": 0})}
                          for d in days],
                "beats": per_day,
                "cards": bcards,
                "numbers": big_numbers,
                "evidence": [{"source": p["source"], "pillar": p["pillar"], "verdict": p["verdict"],
                              "text": p["text"]} for p in per_day if p.get("text")][:8],
                "_topic_ref": lead_topic,
            }

        # ══ topic media cards (top item per topic per pillar, across the week,
        # preferring items with an image) ══
        card_sel = (await db.execute(text("""
            SELECT DISTINCT ON (topic, pillar) topic, pillar, item_ref, source_ref, verdict
              FROM briefing.items i
              LEFT JOIN articles a ON a.id::text = i.item_ref
              LEFT JOIN clippings cl ON cl.id::text = i.item_ref
             WHERE run_id = ANY(:runs) AND about_government AND NOT unclear AND topic IS NOT NULL
             ORDER BY topic, pillar,
                      (COALESCE(length(cl.clipping_image_b64), 0) > 100) DESC, (COALESCE(cl.headline, a.title, '') !~ '[अ-ह]') DESC,
                      (a.thumbnail_url IS NOT NULL AND a.thumbnail_url <> '') DESC,
                      (strength='strong') DESC NULLS LAST, confidence DESC NULLS LAST
        """), {"runs": run_ids})).fetchall()
        web_ids = [c.item_ref for c in card_sel if c.pillar == "web"]
        np_ids = [c.item_ref for c in card_sel if c.pillar == "newspaper"]
        tv_ids = [c.item_ref for c in card_sel if c.pillar == "tv"]
        imgmap: dict[str, dict] = {}
        if web_ids:
            for a in (await db.execute(text(
                "SELECT id::text ref, title, thumbnail_url thumb, url FROM articles WHERE id=ANY(CAST(:i AS uuid[]))"
            ), {"i": web_ids})).fetchall():
                imgmap[a.ref] = {"title": a.title, "thumb": a.thumb, "url": a.url}
        if np_ids:
            for c in (await db.execute(text(
                "SELECT id::text ref, headline title, clipping_image_b64 img FROM clippings WHERE id=ANY(CAST(:i AS uuid[]))"
            ), {"i": np_ids})).fetchall():
                imgmap[c.ref] = {"title": c.title, "img": c.img}
            miss = [x for x in np_ids if x not in imgmap]
            if miss:
                for a in (await db.execute(text(
                    "SELECT id::text ref, title, thumbnail_url thumb, url FROM articles WHERE id=ANY(CAST(:i AS uuid[]))"
                ), {"i": miss})).fetchall():
                    imgmap[a.ref] = {"title": a.title, "thumb": a.thumb, "url": a.url}
        if tv_ids:
            for v in (await db.execute(text(
                "SELECT video_id ref, max(video_title) title FROM youtube_clips_v2 WHERE video_id=ANY(:i) GROUP BY video_id"
            ), {"i": tv_ids})).fetchall():
                imgmap[v.ref] = {"title": v.title, "video_id": v.ref, "url": "https://youtu.be/" + v.ref}
        topic_cards: dict[str, dict] = {}
        for c in card_sel:
            d = imgmap.get(c.item_ref, {})
            topic_cards.setdefault(c.topic, {})[c.pillar] = {
                "source": c.source_ref, "verdict": c.verdict, "title": d.get("title", ""),
                "thumb": d.get("thumb"), "img": d.get("img"), "video_id": d.get("video_id"),
                "url": d.get("url")}

        # ══ scheme scorecard WITH THE REAL 7-DAY TONE TREND (the daily report's
        # deferred feature — now genuinely populated from real dated verdicts) ══
        sch = (await db.execute(text("""
            SELECT scheme, count(*) n,
                   count(*) FILTER (WHERE pillar='web') web,
                   count(*) FILTER (WHERE pillar='tv') tv,
                   count(*) FILTER (WHERE pillar='newspaper') np,
                   count(*) FILTER (WHERE verdict='favourable') fav,
                   count(*) FILTER (WHERE verdict='critical') crit
              FROM briefing.items
             WHERE run_id = ANY(:runs) AND about_government AND NOT unclear AND scheme IS NOT NULL
             GROUP BY 1 ORDER BY 2 DESC
        """), {"runs": run_ids})).fetchall()
        scheme_daily = (await db.execute(text("""
            SELECT i.run_id, i.scheme, count(*) n,
                   count(*) FILTER (WHERE i.verdict='favourable') fav,
                   count(*) FILTER (WHERE i.verdict='critical') crit
              FROM briefing.items i
             WHERE i.run_id = ANY(:runs) AND i.about_government AND NOT i.unclear AND i.scheme IS NOT NULL
             GROUP BY i.run_id, i.scheme
        """), {"runs": run_ids})).fetchall()
        sd_map: dict[str, dict] = {}
        for r in scheme_daily:
            sd_map.setdefault(r.scheme, {})[day_by_run[r.run_id]] = {
                "items": int(r.n), "net": _net(int(r.fav), int(r.crit))}
        scard_sel = (await db.execute(text("""
            SELECT DISTINCT ON (scheme, pillar) scheme, pillar, item_ref, source_ref, verdict
              FROM briefing.items i
              LEFT JOIN articles a ON a.id::text = i.item_ref
              LEFT JOIN clippings cl ON cl.id::text = i.item_ref
             WHERE run_id = ANY(:runs) AND about_government AND NOT unclear AND scheme IS NOT NULL
             ORDER BY scheme, pillar,
                      (COALESCE(length(cl.clipping_image_b64), 0) > 100) DESC, (COALESCE(cl.headline, a.title, '') !~ '[अ-ह]') DESC,
                      (a.thumbnail_url IS NOT NULL AND a.thumbnail_url <> '') DESC,
                      (strength='strong') DESC NULLS LAST, confidence DESC NULLS LAST
        """), {"runs": run_ids})).fetchall()
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
                        "cards": scards.get(sc.scheme, {}),
                        "daily": [{"date": d, **sd_map.get(sc.scheme, {}).get(d, {"items": 0, "net": 0})}
                                  for d in days]} for sc in sch]

        # ══ districts (week total) ══
        dist = (await db.execute(text("""
            SELECT d.name, count(*) n,
                   count(*) FILTER (WHERE i.verdict='favourable') fav,
                   count(*) FILTER (WHERE i.verdict='critical') crit
              FROM briefing.items i
              JOIN article_districts ad ON ad.article_id = CAST(i.item_ref AS uuid)
              JOIN districts d ON d.id = ad.district_id AND d.state_code='TG'
             WHERE i.run_id = ANY(:runs) AND i.pillar='web' AND i.about_government AND NOT i.unclear
             GROUP BY d.name ORDER BY n DESC LIMIT 14
        """), {"runs": run_ids})).fetchall()
        district_rows = [{"district": d.name, "items": int(d.n), "favourable": int(d.fav),
                          "critical": int(d.crit), "net": _net(int(d.fav), int(d.crit))} for d in dist]
        dnames = [d["district"] for d in district_rows[:12]]
        if dnames:
            tops = (await db.execute(text("""
                SELECT DISTINCT ON (d.name, i.verdict) d.name dn, i.verdict v, i.evidence ev, i.source_ref src
                  FROM briefing.items i
                  JOIN article_districts ad ON ad.article_id = CAST(i.item_ref AS uuid)
                  JOIN districts d ON d.id = ad.district_id AND d.state_code='TG'
                 WHERE i.run_id = ANY(:runs) AND i.pillar='web' AND i.about_government AND NOT i.unclear
                   AND d.name = ANY(:names) AND i.verdict IN ('critical','favourable')
                 ORDER BY d.name, i.verdict, (i.strength='strong') DESC NULLS LAST, i.confidence DESC NULLS LAST
            """), {"runs": run_ids, "names": dnames})).fetchall()
            dmap: dict = {}
            for t in tops:
                dmap.setdefault(t.dn, {})[t.v] = {"text": t.ev, "source": t.src}
            for d in district_rows:
                dd = dmap.get(d["district"], {})
                d["top_critical"] = dd.get("critical")
                d["top_positive"] = dd.get("favourable")

        # ══ quotes (week, deduped by text prefix, capped) — same roster/proximity
        # verification as the daily report, just widened to run_id = ANY(:runs) ══
        roster = (await db.execute(text("""
            SELECT lower(canonical_name) nm, side, name_variants FROM briefing.roster
             WHERE org_id=CAST(:o AS uuid) AND active
        """), {"o": org_id})).fetchall()
        people = []
        for rr in roster:
            variants = {rr.nm} | {str(x).lower() for x in (rr.name_variants or [])}
            # require a non-empty NORMALISED form: a variant that _norm()s to ''
            # (e.g. pure Kannada/Telugu script — the matcher strips non-Latin)
            # would make `'' in speaker` true for EVERY speaker, so one vernacular
            # variant in name_variants silently misclassifies the whole report.
            # Vernacular names live in telugu_names for text matching, not here.
            variants = {v for v in variants if len(v) >= 3 and _re.sub(r"[^a-z0-9]+", "", v)}
            if variants:
                people.append((variants, "gov" if rr.side in ("government", "institution") else "opp"))

        def _norm(s: str) -> str:
            return " " + _re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip() + " "

        def _verify_side(speaker: str, hay: str, near: str = ""):
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
        _NEAR = ("lower(substr(COALESCE(a.full_text_translated, a.full_text_scraped, ''),"
                 " GREATEST(COALESCE(q.char_offset_start,1) - 400, 1), 900))")
        qrows = (await db.execute(text(f"""
            SELECT q.speaker_name sp, q.quote_text qt, q.quote_text_en en,
                   s.name src, a.url url, {_HAY} hay, {_NEAR} near
              FROM briefing.items i
              JOIN article_quotes q ON q.article_id = CAST(i.item_ref AS uuid)
              JOIN articles a ON a.id = CAST(i.item_ref AS uuid)
              JOIN sources s ON s.id = a.source_id
             WHERE i.run_id = ANY(:runs) AND i.pillar='web' AND i.about_government
               AND q.is_direct AND q.speaker_name IS NOT NULL
               AND q.quote_text NOT LIKE '%@%' AND length(q.quote_text) BETWEEN 40 AND 240
             LIMIT 600
        """), {"runs": run_ids})).fetchall()
        gov_q, opp_q, seen_q = [], [], set()
        for q in qrows:
            key = (q.qt or "")[:60]
            if key in seen_q:
                continue
            seen_q.add(key)
            side = _verify_side(q.sp, q.hay or "", q.near or "")
            rec = {"speaker": q.sp, "text": q.qt, "en": q.en, "source": q.src, "url": q.url}
            if side == "gov" and len(gov_q) < 10:
                gov_q.append(rec)
            elif side == "opp" and len(opp_q) < 10:
                opp_q.append(rec)
        quotes = {"government": gov_q, "opposition": opp_q}

        from briefing import prose as _prose
        import asyncio as _aio

        # ── gov/opp quotes for the WEEK'S BIG STORY specifically (same roster
        # verification, scoped to the lead topic's own web items) ──
        big_gov_side = big_opp_side = None
        if big:
            brows = (await db.execute(text(f"""
                SELECT q.speaker_name sp, q.quote_text qt, q.quote_text_en en,
                       s.name src, a.url url, {_HAY} hay, {_NEAR} near
                  FROM briefing.items i
                  JOIN article_quotes q ON q.article_id = CAST(i.item_ref AS uuid)
                  JOIN articles a ON a.id = CAST(i.item_ref AS uuid)
                  JOIN sources s ON s.id = a.source_id
                 WHERE i.run_id = ANY(:runs) AND i.pillar='web' AND i.about_government
                   AND i.topic=:t AND q.is_direct AND q.speaker_name IS NOT NULL
                   AND length(q.quote_text) BETWEEN 30 AND 260
            """), {"runs": run_ids, "t": big["_topic_ref"]})).fetchall()
            for q in brows:
                side = _verify_side(q.sp, q.hay or "", q.near or "")
                rec = {"speaker": q.sp, "text": q.qt, "en": q.en, "source": q.src, "url": q.url}
                if side == "gov" and not big_gov_side:
                    big_gov_side = rec
                elif side == "opp" and not big_opp_side:
                    big_opp_side = rec
            big["gov_side"], big["opp_side"] = big_gov_side, big_opp_side
            big.pop("_topic_ref", None)

        # ── translate every Telugu quote actually shown (week quotes + big story
        # sides) in one batched call ──
        _tq = list(gov_q) + list(opp_q) + ([big_gov_side, big_opp_side] if big else [])
        _tq = [q for q in _tq if q]
        _tr = await _prose.translate_te_en([q["text"] for q in _tq if q.get("text")])
        for q in _tq:
            if not q.get("en"):
                q["en"] = _tr.get(q.get("text"))

        # ══ EDITORIAL PROSE (LLM) — the depth pass. The week's Big Story gets
        # the full daily-report-style package (headline/standfirst/narrative/
        # timeline/silence/angle) from its day-by-day beats; the top Week-in-
        # Brief stories each get a clean headline + paragraph, same as the
        # daily report's §1 — this was previously MISSING entirely from the
        # weekly report (raw evidence sentences only), which is why it read
        # as one-liners with no real detail. ══
        _psem = _aio.Semaphore(2)

        async def _enrich_big():
            pr = {}
            for _ in range(2):
                async with _psem:
                    pr = await _prose.write_big_story(big, big.get("beats", []))
                if pr.get("narrative"):
                    break
            for k in ("headline", "standfirst", "narrative", "timeline", "silence", "angle"):
                if pr.get(k):
                    big[k] = pr[k]

        async def _enrich_brief(item):
            evs = [item["evidence"]] if item.get("evidence") else []
            ev_dict = {"topic": item.get("topic"), "department": item.get("department"),
                      "net": 20 if item["verdict"] == "favourable" else -20 if item["verdict"] == "critical" else 0}
            async with _psem:
                pr = await _prose.write_event(ev_dict, evs)
            if pr.get("headline"):
                item["headline"] = pr["headline"]
            if pr.get("paragraph"):
                item["paragraph"] = pr["paragraph"]

        # ── TV share of voice (gov vs opposition figures on television) ──
        sov = await tv_share_of_voice(db, org_id, run_ids)

        _glance_box = {"text": ""}

        async def _enrich_sov():
            async with _psem:
                sov["analysis"] = await _prose.write_tv_sov(sov)

        async def _enrich_glance():
            strip_for_glance = {
                "about_government": gov_total, "by_pillar": by_pillar,
                "sentiment": {"net": net, "favourable": fav, "critical": crit}}
            async with _psem:
                _glance_box["text"] = await _prose.write_week_glance(
                    strip_for_glance, topic_rows, big["label"] if big else biggest,
                    prev, movers)

        _tasks = [_enrich_glance(), _enrich_sov()]
        if big:
            _tasks.append(_enrich_big())
        _tasks += [_enrich_brief(item) for item in week_brief[:10] if item.get("evidence")]
        try:
            await _aio.gather(*_tasks)
        except Exception:  # noqa: BLE001
            pass
        big.pop("beats", None) if big else None

        # ══ figures (week, deduped) ══
        figures = (await db.execute(text("""
            SELECT n.value, n.unit, left(n.context,130) context, a.url url, a.title title
              FROM briefing.items i
              JOIN article_numbers n ON n.article_id::text=i.item_ref
              JOIN articles a ON a.id::text=i.item_ref
             WHERE i.run_id = ANY(:runs) AND i.about_government AND i.pillar='web'
               AND n.unit IS NOT NULL AND length(n.context) BETWEEN 12 AND 100
               AND (n.context ILIKE '%crore%' OR n.context ILIKE '%lakh%' OR n.unit ILIKE '%crore%'
                    OR n.context ILIKE '%scheme%' OR n.context ILIKE '%farmer%' OR n.context ILIKE '%beneficiar%')
             LIMIT 16
        """), {"runs": run_ids})).fetchall()

        def _fig_group(unit, ctx):
            u = (unit or "").lower(); c = (ctx or "").lower()
            if any(w in u + c for w in ("crore", "lakh crore", "rupee", "₹", "budget", "fund")):
                return "Money"
            if any(w in c for w in ("beneficiar", "farmer", "people", "families", "students", "houses", "jobs", "lakh")):
                return "People"
            return "Other"

        seen_fig, figure_rows = set(), []
        for f in figures:
            key = (str(f.value), (f.unit or "").lower())
            if key in seen_fig:
                continue
            seen_fig.add(key)
            figure_rows.append({"value": str(f.value), "unit": f.unit, "context": f.context,
                                "url": f.url, "title": f.title, "group": _fig_group(f.unit, f.context),
                                "alleged": any(w in (f.context or "").lower() for w in ("alleg", "scam", "irregular"))})
        figure_rows = figure_rows[:8]
        _figexp = await _prose.explain_figures(figure_rows)
        for f, ex in zip(figure_rows, _figexp):
            if ex:
                f["context"] = ex

        # ══ annexure — top items per day, dated. Rank+cap FIRST (window function),
        # THEN bulk-resolve title/url by item_ref set — a correlated subquery per
        # row (the daily report's pattern, fine for one day) times out at a week's
        # row count; bulk lookup is the same fix used elsewhere in this file. ══
        anx_ranked = (await db.execute(text("""
            SELECT run_id, pillar, source_ref src, lang, verdict, item_ref
              FROM (
                SELECT i.*, row_number() OVER (
                         PARTITION BY i.run_id
                         ORDER BY (i.strength='strong') DESC NULLS LAST, i.confidence DESC NULLS LAST
                       ) rn
                  FROM briefing.items i
                 WHERE i.run_id = ANY(:runs) AND i.about_government AND NOT i.unclear
              ) ranked WHERE rn <= 8
        """), {"runs": run_ids})).fetchall()
        a_web = [a.item_ref for a in anx_ranked if a.pillar == "web"]
        a_np = [a.item_ref for a in anx_ranked if a.pillar == "newspaper"]
        a_tv = [a.item_ref for a in anx_ranked if a.pillar == "tv"]
        a_meta: dict = {}
        if a_web:
            for x in (await db.execute(text(
                "SELECT id::text ref, title, url FROM articles WHERE id=ANY(CAST(:i AS uuid[]))"
            ), {"i": a_web})).fetchall():
                a_meta[x.ref] = {"title": x.title, "url": x.url}
        if a_np:
            for x in (await db.execute(text(
                "SELECT id::text ref, headline title FROM clippings WHERE id=ANY(CAST(:i AS uuid[]))"
            ), {"i": a_np})).fetchall():
                a_meta[x.ref] = {"title": x.title, "url": None}
            miss = [x for x in a_np if x not in a_meta]
            if miss:
                for x in (await db.execute(text(
                    "SELECT id::text ref, title, url FROM articles WHERE id=ANY(CAST(:i AS uuid[]))"
                ), {"i": miss})).fetchall():
                    a_meta[x.ref] = {"title": x.title, "url": x.url}
        if a_tv:
            for x in (await db.execute(text(
                "SELECT video_id ref, max(video_title) title FROM youtube_clips_v2 WHERE video_id=ANY(:i) GROUP BY video_id"
            ), {"i": a_tv})).fetchall():
                a_meta[x.ref] = {"title": x.title, "url": "https://youtu.be/" + x.ref}
        annexure = []
        for a in anx_ranked:
            m = a_meta.get(a.item_ref, {})
            annexure.append({"date": day_by_run[a.run_id], "pillar": a.pillar, "source": a.src,
                             "lang": a.lang, "verdict": a.verdict,
                             "title": m.get("title"), "url": m.get("url")})

        report = {
            "org_id": org_id,
            "period": {"start": str(start_date), "end": str(end_date), "days": days},
            "strip": {
                "total": total, "by_pillar": by_pillar, "about_government": gov_total,
                "scanned": scanned, "biggest_subject": {"topic": biggest, "items": biggest_n},
                "sentiment": {"net": net, "favourable": fav, "critical": crit, "neutral": neu},
                "top_outlet_by_medium": top_by_medium, "daily_totals": daily_totals,
            },
            "previous": prev,
            "movers": movers,
            "glance": _glance_box["text"],
            "tv_sov": sov,
            "week_brief": week_brief,
            "big_story": big,
            "topics": topic_rows,
            "topic_cards": topic_cards,
            "schemes": scheme_rows,
            "districts": district_rows,
            "media_compare": media_rows,
            "outlets": outlet_rows,
            "quotes": quotes,
            "figures": figure_rows,
            "annexure": annexure,
        }
        return report
