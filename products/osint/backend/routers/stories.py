"""GET /api/brief/stories — Defining Stories panel.

Phase 4.1 enhancements (2026-05-29) — adds the 6 fields the brief design needs
that were previously stubbed: principalQuote, coverage (crit/neu/sup %),
citeBlocks (top-3 outlets with article counts), thumbnail (og_image),
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

from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import text

from db import get_db

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

    # ─── Thumbnail — most-recent og_image (PHASE 4.1) ───────────────────────
    thumb_row = (await db.execute(text(f"""
        SELECT a.og_image
          FROM article_events ae JOIN articles a ON a.id = ae.article_id
         WHERE ae.event_cluster_id = CAST(:cid AS uuid)
           AND a.og_image IS NOT NULL AND a.og_image != ''
           AND a.collected_at >= analytics.now_sim() - {week_window}
           AND a.collected_at <= analytics.now_sim()
           {country_clause}
         ORDER BY a.collected_at DESC LIMIT 1
    """), params)).fetchone()
    thumbnail = thumb_row.og_image if thumb_row else None

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


@router.get("/stories")
async def get_stories(
    limit: int = Query(default=5, ge=1, le=20),
    since_hours: int = Query(default=24, ge=1, le=168),
    country: str | None = Query(default=None, pattern=r"^[A-Z]{2}$"),
) -> dict[str, Any]:
    """List the top defining stories ranked by importance.

    Phase 4 filter params (default to the boss template when omitted):
      since_hours — width of the "today" window in the response metrics.
      country — ISO 3166-1 alpha-2 (e.g., IN) to restrict articles by source country.
    """
    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT ec.id::text AS cluster_id, ec.canonical_description,
                   ec.canonical_event_type, ec.source_count, ec.article_count,
                   ec.importance_score
              FROM event_clusters ec
             WHERE ec.is_active
               AND ec.source_count >= 2
               AND ec.importance_score IS NOT NULL
               AND EXISTS (
                 SELECT 1 FROM article_events ae JOIN articles a ON a.id = ae.article_id
                  WHERE ae.event_cluster_id = ec.id
                    AND a.collected_at >= analytics.now_sim() - INTERVAL '7 days'
                    AND a.collected_at <= analytics.now_sim()
               )
             ORDER BY ec.importance_score DESC, ec.last_updated_at DESC NULLS LAST
             LIMIT :lim
        """), {"lim": int(limit)})).fetchall()

        stories = [
            await _one_cluster(db, r, i, since_hours, country)
            for i, r in enumerate(rows)
        ]
    return {
        "stories": stories,
        "filters": {"since_hours": since_hours, "country": country, "limit": limit},
    }
