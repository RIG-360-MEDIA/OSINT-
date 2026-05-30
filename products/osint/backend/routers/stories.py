"""GET /api/brief/stories — Defining Stories panel.

Phase 4.1 enhancements (2026-05-29) — adds the 6 fields the brief design needs
that were previously stubbed: principalQuote, coverage (crit/neu/sup %),
citeBlocks (top-3 outlets with article counts), thumbnail (thumbnail_url),
vs% (today vs 7-day baseline), peakTime (hour of peak in last sim-24h).

Filter params added day-1 so personalization can plug in later without
touching this code:
  ?since_hours=24    — width of the "today" window (default 24)
  ?country=IN        — restrict to articles where source_country = X
  ?limit=5

All datetime gates use analytics.now_sim() — the replay clock — so the
endpoint behaves correctly whether scrapers are flowing or paused.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from auth.middleware import get_optional_user
from brief_prefs import load_prefs
from db import get_db
from llm_synth import synthesize_paragraph
from relevance import score_relevant

router = APIRouter(prefix="/api/brief", tags=["brief"])


TONE_BY_RANK = ["amber", "cyan", "rose", "violet", "green"]


def _impact_label(score: float) -> str:
    if score >= 80: return "Very High"
    if score >= 60: return "High"
    if score >= 40: return "Medium"
    return "Low"


def _sentiment_label(value: float) -> str:
    if value >= 0.10: return "Positive"
    if value <= -0.10: return "Negative"
    return "Neutral"


def _vs_str(today: int, baseline: float | None) -> str:
    """Format the vs-baseline % as '+340%' / '−12%' / '' if baseline empty."""
    if not baseline or baseline <= 0:
        # No baseline → treat fresh activity as 'new'.
        return "+NEW" if today > 0 else ""
    pct = (today - baseline) / baseline * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{int(pct)}%"


async def _one_cluster(
    db,
    ec_row: Any,
    rank_idx: int,
    since_hours: int,
    country: str | None,
) -> dict[str, Any]:
    cluster_id = ec_row.cluster_id
    today_window = f"INTERVAL '{since_hours} hours'"
    week_window = "INTERVAL '7 days'"
    country_clause = "AND a.source_country = :country" if country else ""
    params = {"cid": cluster_id}
    if country:
        params["country"] = country

    # ─── Fresh headline ─────────────────────────────────────────────────────
    fresh_headline = (await db.execute(text(f"""
        SELECT a.title
          FROM article_events ae
          JOIN articles a ON a.id = ae.article_id
         WHERE ae.event_cluster_id = CAST(:cid AS uuid)
           AND a.title IS NOT NULL AND LENGTH(a.title) >= 20
           AND a.collected_at >= analytics.now_sim() - {week_window}
           AND a.collected_at <= analytics.now_sim()
           {country_clause}
         ORDER BY a.collected_at DESC LIMIT 1
    """), params)).fetchone()
    headline = (fresh_headline.title[:160] if fresh_headline
                else (ec_row.canonical_description or "")[:160])

    # ─── Article + source counts (7d) ───────────────────────────────────────
    agg = (await db.execute(text(f"""
        SELECT COUNT(*) AS n_articles, COUNT(DISTINCT a.source_id) AS n_sources
          FROM article_events ae JOIN articles a ON a.id = ae.article_id
         WHERE ae.event_cluster_id = CAST(:cid AS uuid)
           AND a.collected_at >= analytics.now_sim() - {week_window}
           AND a.collected_at <= analytics.now_sim()
           {country_clause}
    """), params)).fetchone()
    n_art = int(agg.n_articles or 0)
    n_src = int(agg.n_sources or 0)

    # ─── Sentiment (avg across cluster) ─────────────────────────────────────
    sent = (await db.execute(text(f"""
        SELECT AVG(s.intensity) AS s
          FROM article_events ae
          JOIN article_stances s ON s.article_id = ae.article_id
          JOIN articles a ON a.id = ae.article_id
         WHERE ae.event_cluster_id = CAST(:cid AS uuid)
           AND s.intensity IS NOT NULL
           AND a.collected_at >= analytics.now_sim() - {week_window}
           AND a.collected_at <= analytics.now_sim()
           {country_clause}
    """), params)).fetchone()
    sent_val = float(sent.s) if sent and sent.s is not None else 0.0

    # ─── Coverage breakdown — % supportive / critical / neutral (PHASE 4.1) ─
    cov = (await db.execute(text(f"""
        SELECT
          COUNT(*) AS n,
          SUM(CASE WHEN s.intensity >=  0.10 THEN 1 ELSE 0 END) AS sup_n,
          SUM(CASE WHEN s.intensity <= -0.10 THEN 1 ELSE 0 END) AS crit_n,
          SUM(CASE WHEN s.intensity >  -0.10 AND s.intensity <  0.10 THEN 1 ELSE 0 END) AS neu_n
          FROM article_events ae
          JOIN article_stances s ON s.article_id = ae.article_id
          JOIN articles a ON a.id = ae.article_id
         WHERE ae.event_cluster_id = CAST(:cid AS uuid)
           AND s.intensity IS NOT NULL
           AND a.collected_at >= analytics.now_sim() - {week_window}
           AND a.collected_at <= analytics.now_sim()
           {country_clause}
    """), params)).fetchone()
    stance_n = int(cov.n or 0) if cov else 0
    if stance_n > 0:
        sup_pct = round(100 * int(cov.sup_n or 0) / stance_n)
        crit_pct = round(100 * int(cov.crit_n or 0) / stance_n)
        neu_pct = max(0, 100 - sup_pct - crit_pct)
        coverage = {"crit": crit_pct, "neu": neu_pct, "sup": sup_pct}
    else:
        # Backward-compat default — totals 100% so the bar still renders.
        coverage = {"crit": 0, "neu": 100, "sup": 0}

    # ─── Cite blocks — top-3 outlets with article counts (PHASE 4.1) ────────
    cite_rows = (await db.execute(text(f"""
        SELECT s.name, COUNT(*) AS n
          FROM article_events ae JOIN articles a ON a.id = ae.article_id JOIN sources s ON s.id = a.source_id
         WHERE ae.event_cluster_id = CAST(:cid AS uuid)
           AND a.collected_at >= analytics.now_sim() - {week_window}
           AND a.collected_at <= analytics.now_sim()
           {country_clause}
         GROUP BY s.name ORDER BY n DESC LIMIT 12
    """), params)).fetchall()
    cite_blocks = [{"outlet": r.name, "n": int(r.n)} for r in cite_rows[:3]]
    more_outlets = max(0, len(cite_rows) - 3)
    outlets_str = (
        ", ".join(c["outlet"] for c in cite_blocks)
        + (f" + {more_outlets} more" if more_outlets else "")
    )

    # ─── Momentum bars (last 12 hours, hourly) ──────────────────────────────
    mom_rows = (await db.execute(text(f"""
        SELECT date_trunc('hour', a.collected_at) AS h, COUNT(*) AS n
          FROM article_events ae JOIN articles a ON a.id = ae.article_id
         WHERE ae.event_cluster_id = CAST(:cid AS uuid)
           AND a.collected_at >= analytics.now_sim() - INTERVAL '12 hours'
           AND a.collected_at <= analytics.now_sim()
           {country_clause}
         GROUP BY 1 ORDER BY 1
    """), params)).fetchall()
    bars = [int(r.n) for r in mom_rows]
    while len(bars) < 12: bars.insert(0, 0)
    bars = bars[-12:]

    # ─── Peak time in the sim-24h window (PHASE 4.1) ────────────────────────
    peak = (await db.execute(text(f"""
        SELECT date_trunc('hour', a.collected_at) AS h, COUNT(*) AS n
          FROM article_events ae JOIN articles a ON a.id = ae.article_id
         WHERE ae.event_cluster_id = CAST(:cid AS uuid)
           AND a.collected_at >= analytics.now_sim() - {today_window}
           AND a.collected_at <= analytics.now_sim()
           {country_clause}
         GROUP BY 1 ORDER BY 2 DESC LIMIT 1
    """), params)).fetchone()
    peak_time = peak.h.strftime("%H:%M UTC") if peak and peak.h else "—"

    # ─── Summary (executive line from most-recent rich article) ─────────────
    summary_row = (await db.execute(text(f"""
        SELECT a.summary_executive
          FROM article_events ae JOIN articles a ON a.id = ae.article_id
         WHERE ae.event_cluster_id = CAST(:cid AS uuid)
           AND a.summary_executive IS NOT NULL AND LENGTH(a.summary_executive) >= 80
           AND a.collected_at >= analytics.now_sim() - {week_window}
           AND a.collected_at <= analytics.now_sim()
           {country_clause}
         ORDER BY a.collected_at DESC LIMIT 1
    """), params)).fetchone()
    summary = (summary_row.summary_executive[:240] if summary_row else
               (ec_row.canonical_description or ""))

    # ─── Principal quote (PHASE 4.1) ────────────────────────────────────────
    pq = (await db.execute(text(f"""
        SELECT aq.quote_text, aq.speaker_name, s.name AS source, a.collected_at
          FROM article_quotes aq
          JOIN articles a ON a.id = aq.article_id
          JOIN article_events ae ON ae.article_id = a.id
          JOIN sources s ON s.id = a.source_id
         WHERE ae.event_cluster_id = CAST(:cid AS uuid)
           AND LENGTH(aq.quote_text) BETWEEN 40 AND 280
           AND aq.quote_text !~ '^[A-Z][a-z]+,\\s+[A-Z][a-z]+\\s*$'
           AND a.collected_at >= analytics.now_sim() - {week_window}
           AND a.collected_at <= analytics.now_sim()
           {country_clause}
         ORDER BY LENGTH(aq.quote_text) DESC, a.collected_at DESC
         LIMIT 1
    """), params)).fetchone()
    principal_quote = None
    if pq and pq.quote_text:
        principal_quote = {
            "text": pq.quote_text[:280],
            "attribution": pq.speaker_name or "—",
            "role": "",  # later: join entity_dictionary for role/party
            "source": pq.source or "—",
            "timestamp": pq.collected_at.strftime("%d %b · %H:%M IST") if pq.collected_at else "—",
        }

    # ─── Thumbnail — most-recent thumbnail_url (PHASE 4.1) ───────────────────────
    thumb_row = (await db.execute(text(f"""
        SELECT a.thumbnail_url
          FROM article_events ae JOIN articles a ON a.id = ae.article_id
         WHERE ae.event_cluster_id = CAST(:cid AS uuid)
           AND a.thumbnail_url IS NOT NULL AND a.thumbnail_url != ''
           AND a.collected_at >= analytics.now_sim() - {week_window}
           AND a.collected_at <= analytics.now_sim()
           {country_clause}
         ORDER BY a.collected_at DESC LIMIT 1
    """), params)).fetchone()
    thumbnail = thumb_row.thumbnail_url if thumb_row else None

    # ─── Lens cards (1 quote per outlet up to 5) ────────────────────────────
    lens_rows = (await db.execute(text(f"""
        SELECT DISTINCT ON (s.name) s.name AS outlet, a.language_iso AS lang,
               LEFT(aq.quote_text, 180) AS quote
          FROM article_events ae
          JOIN articles a ON a.id = ae.article_id
          JOIN sources s ON s.id = a.source_id
          LEFT JOIN article_quotes aq ON aq.article_id = a.id AND LENGTH(aq.quote_text) >= 30
         WHERE ae.event_cluster_id = CAST(:cid AS uuid)
           AND a.collected_at >= analytics.now_sim() - {week_window}
           AND a.collected_at <= analytics.now_sim()
           {country_clause}
         ORDER BY s.name, LENGTH(aq.quote_text) DESC NULLS LAST
         LIMIT 5
    """), params)).fetchall()
    lens = []
    for lr in lens_rows:
        st_row = (await db.execute(text("""
            SELECT AVG(s.intensity) AS i
              FROM article_events ae
              JOIN articles a ON a.id = ae.article_id
              JOIN sources sr ON sr.id = a.source_id
              LEFT JOIN article_stances s ON s.article_id = a.id
             WHERE ae.event_cluster_id = CAST(:cid AS uuid) AND sr.name = :sn
        """), {"cid": cluster_id, "sn": lr.outlet})).fetchone()
        stance = "neutral"
        if st_row and st_row.i is not None:
            if st_row.i >= 0.15: stance = "supportive"
            elif st_row.i <= -0.15: stance = "critical"
        lens.append({
            "outlet": lr.outlet,
            "lang": (lr.lang or "english"),
            "stance": stance,
            "quote": lr.quote or "(no quote captured)",
        })

    # ─── vs% — today vs 7-day baseline (PHASE 4.1) ──────────────────────────
    vs_data = (await db.execute(text(f"""
        SELECT
          (SELECT COUNT(*) FROM article_events ae JOIN articles a ON a.id = ae.article_id
            WHERE ae.event_cluster_id = CAST(:cid AS uuid)
              AND a.collected_at >= analytics.now_sim() - {today_window}
              AND a.collected_at <= analytics.now_sim()
              {country_clause}) AS today_n,
          (SELECT COUNT(*)/7.0 FROM article_events ae JOIN articles a ON a.id = ae.article_id
            WHERE ae.event_cluster_id = CAST(:cid AS uuid)
              AND a.collected_at >= analytics.now_sim() - INTERVAL '8 days'
              AND a.collected_at <  analytics.now_sim() - INTERVAL '1 day'
              {country_clause}) AS baseline
    """), params)).fetchone()
    today_n = int(vs_data.today_n) if vs_data and vs_data.today_n is not None else 0
    baseline_v = float(vs_data.baseline) if vs_data and vs_data.baseline is not None else None
    vs_str = _vs_str(today_n, baseline_v)

    impact_score = min(100, int((ec_row.importance_score or 0) * 10))

    return {
        "rank": f"{rank_idx + 1:02d}",
        "tone": TONE_BY_RANK[rank_idx % len(TONE_BY_RANK)],
        "image": thumbnail,
        "thumbnail": thumbnail,  # alias for whichever name boss's component uses
        "categories": [ec_row.canonical_event_type] if ec_row.canonical_event_type else [],
        "headline": headline,
        "summary": summary,
        "outlets": outlets_str,
        "citeBlocks": cite_blocks,
        "impact": impact_score,
        "impactLabel": _impact_label(impact_score),
        "sentiment": f"{'+' if sent_val >= 0 else ''}{int(sent_val * 100)}%",
        "sentimentLabel": _sentiment_label(sent_val),
        "sentimentSpark": "sentiment",
        "coverage": coverage,
        "momentumBars": bars,
        "momentumLabel": _impact_label(max(bars) * 10) if bars else "Low",
        "peakTime": peak_time,
        "thumbHue": TONE_BY_RANK[rank_idx % len(TONE_BY_RANK)],
        "principalQuote": principal_quote,
        "lens": lens,
        "metrics": {"articles": n_art, "outlets": n_src, "vs": vs_str},
    }


async def _synthesize_story_summaries(
    stories: list[dict[str, Any]], limit_synth: int = 5,
) -> list[dict[str, Any]]:
    """Replace each shown story's single-article summary with an LLM synthesis
    over the cluster's real, multi-outlet signals (headline, coverage split,
    lead outlets, a representative quote). Grounded + faithfulness-gated inside
    synthesize_paragraph; on any failure the original summary is kept. Runs
    concurrently across the top stories so latency stays bounded.
    """
    def _facts(s: dict[str, Any]) -> str:
        cov = s.get("coverage") or {}
        metrics = s.get("metrics") or {}
        lines = [
            f"HEADLINE: {s.get('headline', '')}",
            f"COVERAGE: {metrics.get('outlets', 0)} outlets — "
            f"{cov.get('sup', 0)}% supportive, {cov.get('crit', 0)}% critical, "
            f"{cov.get('neu', 0)}% neutral",
        ]
        if s.get("outlets"):
            lines.append(f"LEAD OUTLETS: {s['outlets']}")
        if s.get("summary"):
            lines.append(f"DETAIL: {s['summary']}")
        for lc in (s.get("lens") or []):
            q = (lc.get("quote") or "").strip()
            if q and "no quote" not in q.lower():
                lines.append(f'QUOTE ({lc.get("outlet", "outlet")}): "{q}"')
                break
        return "\n".join(lines)

    system = (
        "/no_think\n"
        "You are an intelligence editor. In TWO sentences, summarise this news "
        "story for a busy principal: first what happened, then where coverage "
        "stands. Use ONLY the facts given; attribute any claim to its outlet or "
        "speaker; do NOT assert contested claims as fact; do NOT invent numbers, "
        "names, or outcomes. No preamble, no label — output only the two sentences."
    )

    async def _one(s: dict[str, Any]) -> dict[str, Any]:
        facts = _facts(s)
        llm = await synthesize_paragraph(
            system=system, facts=facts, source_check=facts,
            min_words=14, min_chars=60,
        )
        if llm:
            return {**s, "summary": llm, "summary_source": "llm"}
        return {**s, "summary_source": "template"}

    head = await asyncio.gather(*[_one(s) for s in stories[:limit_synth]])
    return list(head) + stories[limit_synth:]


def _story_key(title: str | None) -> str:
    """Unicode-safe story key for de-duping syndicated re-scrapes.

    Drops a leading 'Outlet | ' prefix, collapses whitespace, lowercases —
    and KEEPS non-Latin scripts. An ascii-only normaliser would blank Telugu /
    Devanagari headlines and merge every regional article into one junk group.
    """
    t = (title or "").split("|")[0]
    return re.sub(r"\s+", " ", t).strip().lower()[:80]


def _group_relevant(scored: list[dict[str, Any]], limit: int) -> list[list[dict[str, Any]]]:
    """Group the user's relevant articles into stories by normalised headline,
    ranked by best member score; return the top `limit` groups (members sorted)."""
    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for r in scored:
        k = _story_key(r["title"])
        if not k:
            continue
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(r)
    order.sort(key=lambda k: -max(m["score"] for m in groups[k]))
    return [sorted(groups[k], key=lambda m: -m["score"]) for k in order[:limit]]


async def _enrich_batch(db, ids: list[str]) -> tuple[dict, dict, dict, Any]:
    """One batched pull of the per-article signals the story cards need."""
    meta = {r.id: r for r in (await db.execute(text("""
        SELECT a.id::text AS id, a.collected_at, a.thumbnail_url, a.language_iso
          FROM articles a WHERE a.id = ANY(CAST(:ids AS uuid[]))
    """), {"ids": ids})).fetchall()}
    stances: dict[str, list[float]] = {}
    for row in (await db.execute(text("""
        SELECT article_id::text AS id, intensity FROM article_stances
         WHERE article_id = ANY(CAST(:ids AS uuid[])) AND intensity IS NOT NULL
    """), {"ids": ids})).fetchall():
        stances.setdefault(row.id, []).append(float(row.intensity))
    quotes: dict[str, list[tuple[str, str | None]]] = {}
    for row in (await db.execute(text("""
        SELECT article_id::text AS id, quote_text, speaker_name FROM article_quotes
         WHERE article_id = ANY(CAST(:ids AS uuid[])) AND LENGTH(quote_text) BETWEEN 40 AND 280
    """), {"ids": ids})).fetchall():
        quotes.setdefault(row.id, []).append((row.quote_text, row.speaker_name))
    now_sim = (await db.execute(text("SELECT analytics.now_sim()"))).scalar()
    return meta, stances, quotes, now_sim


def _build_story(idx: int, members: list[dict[str, Any]], meta: dict,
                 stances: dict, quotes: dict, now_sim: Any) -> dict[str, Any]:
    """Assemble one story card (same shape as _one_cluster) from a group of the
    user's relevant articles + their batched signals."""
    lead = members[0]
    ids = [m["id"] for m in members]
    outlets: list[str] = []
    for m in members:
        if m["source"] and m["source"] not in outlets:
            outlets.append(m["source"])
    ints = [v for i in ids for v in stances.get(i, [])]
    sent = sum(ints) / len(ints) if ints else 0.0
    if ints:
        sup = round(100 * sum(1 for v in ints if v >= 0.10) / len(ints))
        crit = round(100 * sum(1 for v in ints if v <= -0.10) / len(ints))
        coverage = {"crit": crit, "neu": max(0, 100 - sup - crit), "sup": sup}
    else:
        coverage = {"crit": 0, "neu": 100, "sup": 0}
    cand_q = [q for i in ids for q in quotes.get(i, [])]
    pq = None
    if cand_q:
        qt, sp = max(cand_q, key=lambda x: len(x[0]))
        pq = {"text": qt[:280], "attribution": sp or "—", "role": "",
              "source": lead["source"] or "—", "timestamp": ""}
    bars = [0] * 12
    for i in ids:
        mt = meta.get(i)
        if mt and mt.collected_at:
            h = (now_sim - mt.collected_at).total_seconds() / 3600.0
            if 0 <= h < 12:
                bars[11 - int(h)] += 1
    lens: list[dict[str, Any]] = []
    for m in members:
        if any(lc["outlet"] == m["source"] for lc in lens):
            continue
        mq = quotes.get(m["id"], [])
        lang = (meta.get(m["id"]).language_iso if meta.get(m["id"]) else None) or "english"
        lens.append({"outlet": m["source"], "lang": lang, "stance": "neutral",
                     "quote": (mq[0][0][:180] if mq else (m["summary"] or "")[:140]) or "(no quote captured)"})
        if len(lens) >= 5:
            break
    thumb = next((meta[i].thumbnail_url for i in ids if meta.get(i) and meta[i].thumbnail_url), None)
    impact = min(100, int((lead["score"] or 0) * 10))
    tone = TONE_BY_RANK[idx % len(TONE_BY_RANK)]
    return {
        "rank": f"{idx + 1:02d}", "tone": tone, "image": thumb, "thumbnail": thumb,
        "categories": [lead["topic"]] if lead.get("topic") else [],
        "headline": (lead["title"] or "").strip(),
        "summary": (lead["summary"] or "").strip()[:240],
        "outlets": ", ".join(outlets[:3]) + (f" + {len(outlets) - 3} more" if len(outlets) > 3 else ""),
        "citeBlocks": [{"outlet": o, "n": sum(1 for m in members if m["source"] == o)} for o in outlets[:3]],
        "impact": impact, "impactLabel": _impact_label(impact),
        "sentiment": f"{'+' if sent >= 0 else ''}{int(sent * 100)}%",
        "sentimentLabel": _sentiment_label(sent), "sentimentSpark": "sentiment",
        "coverage": coverage, "momentumBars": bars,
        "momentumLabel": _impact_label(max(bars) * 10) if any(bars) else "Low",
        "peakTime": "—", "thumbHue": tone, "principalQuote": pq, "lens": lens,
        "metrics": {"articles": len(members), "outlets": len(outlets), "vs": "",
                    "stance_n": len(ints)},
        "matched": lead.get("matched"),
    }


async def _personal_stories(db, prefs: dict[str, Any], window_hours: int,
                            limit: int) -> list[dict[str, Any]]:
    """Defining Stories built directly from the user's relevance stream — no
    dependency on the (WIP) story_threads engine. Dedup syndicated re-scrapes
    into stories, rank by relevance, enrich with real coverage signals."""
    scored = await score_relevant(db, prefs, window_hours=window_hours, limit=180)
    if not scored:
        return []
    groups = _group_relevant(scored, limit)
    all_ids = [m["id"] for g in groups for m in g]
    if not all_ids:
        return []
    meta, stances, quotes, now_sim = await _enrich_batch(db, all_ids)
    return [_build_story(i, g, meta, stances, quotes, now_sim) for i, g in enumerate(groups)]


@router.get("/stories")
async def get_stories(
    limit: int = Query(default=5, ge=1, le=20),
    since_hours: int = Query(default=24, ge=1, le=168),
    window_hours: int = Query(default=72, ge=6, le=168),
    country: str | None = Query(default=None, pattern=r"^[A-Z]{2}$"),
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    """List the defining stories for THIS user, ranked by their own relevance.

    Personalised directly from the relevance core: the user's relevant article
    stream is de-duplicated into distinct stories (syndicated re-scrapes merged
    by headline) and ranked by relevance — so a Telangana CM sees Telangana, a
    Delhi user sees Delhi. This deliberately does NOT use the story_threads
    clustering engine (a WIP prototype: unrun v1→v2 cutover, single-source
    runaway threads, no live threading). Signed-out / no-prefs requests fall
    back to the global event_clusters importance ranking.

    Filter params (default to the boss template when omitted):
      since_hours — width of the "today" window in the response metrics.
      window_hours — look-back for the personal relevance scan.
      country — ISO 3166-1 alpha-2 (e.g., IN); only applied to the global fallback.
    """
    # Global fallback ranks importance_score * EXP(-hours_since_activity / 12h)
    # so a 2-hour breaking story can outrank a 5-day-old high-salience cluster.
    HALF_LIFE_H = 12.0
    personalized = False
    async with get_db() as db:
        prefs = await load_prefs(db, user["id"]) if user else None
        stories: list[dict[str, Any]] = []
        if prefs:
            stories = await _personal_stories(db, prefs, window_hours, limit)
            personalized = bool(stories)

        if not stories:
            # Global fallback (signed-out, no prefs, or no personal matches) —
            # the event_clusters importance ranking, enriched per cluster.
            rows = (await db.execute(text(f"""
                WITH active AS (
                    SELECT ec.id::text AS cluster_id, ec.canonical_description,
                           ec.canonical_event_type, ec.source_count, ec.article_count,
                           ec.importance_score,
                           MAX(a.collected_at) AS last_activity
                      FROM event_clusters ec
                      JOIN article_events ae ON ae.event_cluster_id = ec.id
                      JOIN articles a ON a.id = ae.article_id
                     WHERE ec.is_active
                       AND ec.source_count >= 2
                       AND ec.importance_score IS NOT NULL
                       AND a.collected_at >= analytics.now_sim() - INTERVAL '7 days'
                       AND a.collected_at <= analytics.now_sim()
                     GROUP BY ec.id, ec.canonical_description, ec.canonical_event_type,
                              ec.source_count, ec.article_count, ec.importance_score
                )
                SELECT cluster_id, canonical_description, canonical_event_type,
                       source_count, article_count, importance_score,
                       importance_score * EXP(
                           - EXTRACT(EPOCH FROM (analytics.now_sim() - last_activity))
                           / 3600.0 / {HALF_LIFE_H}
                       ) AS effective_rank
                  FROM active
                 ORDER BY effective_rank DESC NULLS LAST
                 LIMIT :lim
            """), {"lim": int(limit)})).fetchall()
            stories = [
                await _one_cluster(db, r, i, since_hours, country)
                for i, r in enumerate(rows)
            ]

    # LLM synthesis pass — OUTSIDE the DB context so no connection is held during
    # the model calls. Concurrent across the shown stories; falls back per-story
    # to the single-article summary on any failure.
    stories = await _synthesize_story_summaries(stories, limit_synth=min(limit, 6))
    return {
        "stories": stories,
        "personalized": personalized,
        "filters": {"since_hours": since_hours, "country": country, "limit": limit},
    }
