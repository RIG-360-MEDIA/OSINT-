"""brief_stories.py — Defining Stories panel data.

For each of the top-N event_clusters (by importance_score T5):
  - headline:   ec.canonical_description (cleaned, ≤ 120 chars)
  - summary:    most-recent article's summary_executive (first sentence, ≤ 200)
  - outlets:    distinct source names, comma-joined + "+ N more"
  - impact:     ec.importance_score × 10 → 0-100 scale
  - sentiment:  AVG(article_stances.intensity) over articles in cluster, % string
  - momentum:   12-bar hourly count of articles joining cluster last 24h
  - lens:       up to 5 outlets covering the story, with stance + first quote

Returns a list shaped like the boss's DEFINING_STORIES + SOURCE_LENS_DATA combined.
"""
from __future__ import annotations

from typing import Any
from sqlalchemy import text


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


async def _one_cluster(db, ec_row: Any, rank_idx: int) -> dict[str, Any]:
    cluster_id = ec_row.cluster_id

    # B: Most-recent article's title beats stale canonical_description
    fresh_headline = (await db.execute(text("""
        SELECT a.title, a.collected_at
          FROM article_events ae
          JOIN articles a ON a.id = ae.article_id
         WHERE ae.event_cluster_id = CAST(:cid AS uuid)
           AND a.title IS NOT NULL
           AND LENGTH(a.title) >= 20
           AND a.collected_at >= NOW() - INTERVAL '7 days'
         ORDER BY a.collected_at DESC LIMIT 1
    """), {"cid": cluster_id})).fetchone()
    headline = (fresh_headline.title[:160] if fresh_headline
                else (ec_row.canonical_description or "")[:160])

    # Aggregate per-cluster metrics (only count last-7d articles to match recency)
    agg = (await db.execute(text("""
        SELECT COUNT(*) AS n_articles,
               COUNT(DISTINCT a.source_id) AS n_sources
          FROM article_events ae
          JOIN articles a ON a.id = ae.article_id
         WHERE ae.event_cluster_id = CAST(:cid AS uuid)
           AND a.collected_at >= NOW() - INTERVAL '7 days'
    """), {"cid": cluster_id})).fetchone()

    # Sentiment across articles in this cluster
    sent = (await db.execute(text("""
        SELECT AVG(s.intensity) AS s
          FROM article_events ae
          JOIN article_stances s ON s.article_id = ae.article_id
         WHERE ae.event_cluster_id = CAST(:cid AS uuid)
           AND s.intensity IS NOT NULL
    """), {"cid": cluster_id})).fetchone()
    sent_val = float(sent.s) if sent.s is not None else 0.0

    # Outlet list (top 3 by article count, "+ N more")
    outlets_rows = (await db.execute(text("""
        SELECT s.name, COUNT(*) AS n
          FROM article_events ae
          JOIN articles a ON a.id = ae.article_id
          JOIN sources s ON s.id = a.source_id
         WHERE ae.event_cluster_id = CAST(:cid AS uuid)
         GROUP BY s.name ORDER BY n DESC LIMIT 12
    """), {"cid": cluster_id})).fetchall()
    top3 = [r.name for r in outlets_rows[:3]]
    more = max(0, len(outlets_rows) - 3)
    outlets_str = ", ".join(top3) + (f" + {more} more" if more else "")

    # Momentum: hourly count last 12 hours
    mom_rows = (await db.execute(text("""
        SELECT date_trunc('hour', a.collected_at) AS h, COUNT(*) AS n
          FROM article_events ae
          JOIN articles a ON a.id = ae.article_id
         WHERE ae.event_cluster_id = CAST(:cid AS uuid)
           AND a.collected_at >= NOW() - INTERVAL '12 hours'
         GROUP BY 1 ORDER BY 1
    """), {"cid": cluster_id})).fetchall()
    bars = [int(r.n) for r in mom_rows]
    while len(bars) < 12: bars.insert(0, 0)
    bars = bars[-12:]

    # Summary from the most-recent article's summary_executive
    summary_row = (await db.execute(text("""
        SELECT a.summary_executive
          FROM article_events ae
          JOIN articles a ON a.id = ae.article_id
         WHERE ae.event_cluster_id = CAST(:cid AS uuid)
           AND a.summary_executive IS NOT NULL
           AND LENGTH(a.summary_executive) >= 80
         ORDER BY a.collected_at DESC LIMIT 1
    """), {"cid": cluster_id})).fetchone()
    summary = (summary_row.summary_executive[:240] if summary_row else
               ec_row.canonical_description or "")

    # Lens: up to 5 outlets covering — one quote per outlet
    lens_rows = (await db.execute(text("""
        SELECT DISTINCT ON (s.name) s.name AS outlet, a.language_detected AS lang,
               LEFT(aq.quote_text, 180) AS quote
          FROM article_events ae
          JOIN articles a ON a.id = ae.article_id
          JOIN sources s ON s.id = a.source_id
          LEFT JOIN article_quotes aq ON aq.article_id = a.id
                AND LENGTH(aq.quote_text) >= 30
         WHERE ae.event_cluster_id = CAST(:cid AS uuid)
         ORDER BY s.name, LENGTH(aq.quote_text) DESC NULLS LAST
         LIMIT 5
    """), {"cid": cluster_id})).fetchall()

    # Stance heuristic per outlet for lens entries (avg over its articles in this cluster)
    lens = []
    for lr in lens_rows:
        st_row = (await db.execute(text("""
            SELECT AVG(s.intensity) AS i
              FROM article_events ae
              JOIN articles a ON a.id = ae.article_id
              JOIN sources sr ON sr.id = a.source_id
              LEFT JOIN article_stances s ON s.article_id = a.id
             WHERE ae.event_cluster_id = CAST(:cid AS uuid)
               AND sr.name = :sn
        """), {"cid": cluster_id, "sn": lr.outlet})).fetchone()
        stance = "neutral"
        if st_row.i is not None:
            if st_row.i >= 0.15: stance = "supportive"
            elif st_row.i <= -0.15: stance = "critical"
        lens.append({
            "outlet": lr.outlet,
            "lang": (lr.lang or "english"),
            "stance": stance,
            "quote": lr.quote or "(no quote captured)",
        })

    n_art = int(agg.n_articles or 0)
    n_src = int(agg.n_sources or 0)
    impact_score = min(100, int((ec_row.importance_score or 0) * 10))

    return {
        "rank": f"{rank_idx + 1:02d}",
        "tone": TONE_BY_RANK[rank_idx % len(TONE_BY_RANK)],
        "image": None,
        "categories": [ec_row.canonical_event_type] if ec_row.canonical_event_type else [],
        "headline": headline,
        "summary": summary,
        "outlets": outlets_str,
        "impact": impact_score,
        "impactLabel": _impact_label(impact_score),
        "sentiment": f"{'+' if sent_val >= 0 else ''}{int(sent_val * 100)}%",
        "sentimentLabel": _sentiment_label(sent_val),
        "sentimentSpark": "sentiment",
        "momentumBars": bars,
        "momentumLabel": _impact_label(max(bars) * 10) if bars else "Low",
        "peakTime": "—",
        "thumbHue": TONE_BY_RANK[rank_idx % len(TONE_BY_RANK)],
        "lens": lens,
        "metrics": {"articles": n_art, "outlets": n_src, "vs": ""},
    }


async def get_defining_stories(db, limit: int = 5) -> dict[str, Any]:
    # A: filter to clusters that received NEW articles in the last 7 days
    # (drops stale "Russia invasion begins" type stories from months ago)
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
                AND a.collected_at >= NOW() - INTERVAL '7 days'
           )
         ORDER BY ec.importance_score DESC, ec.last_updated_at DESC NULLS LAST
         LIMIT :lim
    """), {"lim": int(limit)})).fetchall()

    stories = []
    for i, r in enumerate(rows):
        stories.append(await _one_cluster(db, r, i))
    return {"stories": stories}
