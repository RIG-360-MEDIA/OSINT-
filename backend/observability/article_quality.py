"""Query helpers for the /observe admin page panels.

Pure async helpers; each takes the open `db` session and returns a JSON-able
dict. Routes in `backend/routers/observe_router.py` call these.

Owned by: backend/observability/article_quality.py.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text


# ── Panel 1: Ingest pulse ─────────────────────────────────────────────────────

async def ingest_pulse(db) -> dict[str, Any]:
    """Articles/min last 24h, latest per source, stalled sources."""
    by_hour = (await db.execute(text("""
        SELECT date_trunc('hour', collected_at) AS hour,
               COUNT(*) AS n
          FROM articles
         WHERE collected_at >= NOW() - INTERVAL '24 hours'
         GROUP BY 1 ORDER BY 1
    """))).fetchall()

    per_source = (await db.execute(text("""
        SELECT s.name AS source,
               MAX(a.collected_at) AS last_seen,
               COUNT(*) FILTER (WHERE a.collected_at >= NOW() - INTERVAL '24 hours') AS n_24h,
               EXTRACT(EPOCH FROM (NOW() - MAX(a.collected_at)))/3600.0 AS hours_since
          FROM sources s
          JOIN articles a ON a.source_id = s.id
         GROUP BY s.name
         ORDER BY MAX(a.collected_at) DESC NULLS LAST
    """))).fetchall()

    stalled = [
        {"source": r.source,
         "last_seen": r.last_seen.isoformat() if r.last_seen else None,
         "hours_since": round(float(r.hours_since or 0), 1)}
        for r in per_source
        if r.hours_since and r.hours_since > 24
    ]

    return {
        "by_hour": [{"hour": r.hour.isoformat(), "n": int(r.n)} for r in by_hour],
        "per_source": [
            {"source": r.source,
             "last_seen": r.last_seen.isoformat() if r.last_seen else None,
             "n_24h": int(r.n_24h or 0),
             "hours_since": round(float(r.hours_since or 0), 1)}
            for r in per_source
        ],
        "stalled_sources": stalled,
        "total_24h": sum(int(r.n) for r in by_hour),
    }


# ── Panel 2: Source scorecard ─────────────────────────────────────────────────

async def source_scorecard(db) -> dict[str, Any]:
    """Per-source quality × volume × language × last-seen."""
    rows = (await db.execute(text("""
        SELECT s.name AS source,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE a.substrate_status='ok'
                                  AND a.extraction_version >= 3) AS v3_ok,
               COUNT(*) FILTER (WHERE a.summary_executive IS NOT NULL
                                  AND LENGTH(a.summary_executive) >= 50) AS has_summary,
               COUNT(*) FILTER (WHERE a.labse_embedding IS NOT NULL) AS has_embedding,
               COUNT(DISTINCT a.language_detected) AS languages,
               MAX(a.collected_at) AS last_seen
          FROM sources s
          LEFT JOIN articles a ON a.source_id = s.id
         GROUP BY s.name
         HAVING COUNT(*) > 0
         ORDER BY COUNT(*) DESC
    """))).fetchall()

    return {
        "sources": [
            {"source": r.source,
             "total": int(r.total),
             "v3_ok": int(r.v3_ok),
             "has_summary_pct": round(100.0 * (r.has_summary or 0) / max(r.total, 1), 1),
             "has_embedding_pct": round(100.0 * (r.has_embedding or 0) / max(r.total, 1), 1),
             "languages": int(r.languages or 0),
             "last_seen": r.last_seen.isoformat() if r.last_seen else None}
            for r in rows
        ]
    }


# ── Panel 3: Quality monitor (LLM-judge medians) ──────────────────────────────

async def quality_monitor(db) -> dict[str, Any]:
    """Per-field quality gauges.

    Combines:
    - Latest LLM-judge medians from disk (if available)
    - Live placeholder-subject count from article_claims
    - Live grounding cliffs (truncation + null-rate snapshots)
    """
    import json
    from pathlib import Path

    out: dict[str, Any] = {"judge": None, "regression": None, "live": {}}

    # Latest judge summary
    q_dir = Path("/docs/quality")
    if not q_dir.exists():
        q_dir = Path("docs/quality")
    summaries = sorted(q_dir.glob("judge_summary_*.json")) if q_dir.exists() else []
    if summaries:
        try:
            out["judge"] = json.loads(summaries[-1].read_text(encoding="utf-8"))
            out["judge"]["source_file"] = summaries[-1].name
        except Exception:
            pass

    # Latest gold-set regression
    regs = sorted(q_dir.glob("regression_*.json")) if q_dir.exists() else []
    if regs:
        try:
            reg = json.loads(regs[-1].read_text(encoding="utf-8"))
            reg["source_file"] = regs[-1].name
            out["regression"] = reg
        except Exception:
            pass

    # Latest new-vs-baseline comparison (T14)
    cmps = sorted(q_dir.glob("new-vs-baseline-*.json")) if q_dir.exists() else []
    if cmps:
        try:
            cmp_data = json.loads(cmps[-1].read_text(encoding="utf-8"))
            cmp_data["source_file"] = cmps[-1].name
            out["new_article_compare"] = cmp_data
        except Exception:
            pass

    # Live cliffs
    cliffs = (await db.execute(text("""
        SELECT
          COUNT(*) FILTER (WHERE LENGTH(summary_executive) = 500) AS cliff_500,
          COUNT(*) FILTER (WHERE LENGTH(summary_executive) = 1000) AS cliff_1000,
          COUNT(*) FILTER (WHERE primary_subject IS NULL) AS null_subject,
          COUNT(*) FILTER (WHERE summary_executive IS NULL OR LENGTH(summary_executive) < 50) AS thin_summary,
          COUNT(*) FILTER (WHERE labse_embedding IS NULL) AS null_embedding,
          COUNT(*) AS total
          FROM articles
         WHERE substrate_status='ok' AND extraction_version >= 3
    """))).fetchone()

    placeholder = (await db.execute(text("""
        SELECT
          COUNT(*) FILTER (WHERE LOWER(subject_text) IN ('article','story','report','piece','news')) AS placeholder,
          COUNT(*) AS total
          FROM article_claims
    """))).fetchone()

    total = int(cliffs.total or 1)
    out["live"] = {
        "v3_ok_total": total,
        "cliff_500": int(cliffs.cliff_500 or 0),
        "cliff_1000": int(cliffs.cliff_1000 or 0),
        "null_subject": int(cliffs.null_subject or 0),
        "thin_summary": int(cliffs.thin_summary or 0),
        "thin_summary_pct": round(100.0 * (cliffs.thin_summary or 0) / total, 2),
        "null_embedding": int(cliffs.null_embedding or 0),
        "claims_placeholder": int(placeholder.placeholder or 0),
        "claims_placeholder_pct": round(
            100.0 * (placeholder.placeholder or 0) / max(int(placeholder.total or 1), 1), 1
        ),
        "claims_total": int(placeholder.total or 0),
    }
    return out


# ── Panel 4: Geo heatmap ──────────────────────────────────────────────────────

async def geo_heatmap(db, level: str = "country") -> dict[str, Any]:
    """Counts by region from article_locations.

    level ∈ {country, state, district}. Falls back to country if unknown.
    """
    level = level if level in ("country", "state", "district") else "country"
    col = {"country": "country", "state": "region", "district": "city"}[level]
    rows = (await db.execute(text(f"""
        SELECT COALESCE({col}, 'unknown') AS region, COUNT(*) AS n
          FROM article_locations
         WHERE {col} IS NOT NULL
         GROUP BY 1 ORDER BY 2 DESC LIMIT 200
    """))).fetchall()
    return {
        "level": level,
        "regions": [{"region": r.region, "n": int(r.n)} for r in rows],
    }


# ── Panel 5: Story pulse (active multi-source clusters) ───────────────────────

async def story_pulse(db, limit: int = 30) -> dict[str, Any]:
    rows = (await db.execute(text("""
        SELECT ec.id::text AS cluster_id,
               ec.canonical_description,
               ec.canonical_event_type,
               ec.article_count, ec.source_count,
               ec.last_updated_at,
               ec.importance_score,
               (SELECT COUNT(*) FROM article_events ae
                 JOIN articles a ON a.id = ae.article_id
                 WHERE ae.event_cluster_id = ec.id
                   AND a.collected_at >= NOW() - INTERVAL '24 hours') AS new_24h
          FROM event_clusters ec
         WHERE ec.is_active
           AND ec.source_count >= 2
         ORDER BY ec.importance_score DESC NULLS LAST,
                  ec.last_updated_at DESC NULLS LAST
         LIMIT :lim
    """), {"lim": int(limit)})).fetchall()
    return {
        "clusters": [
            {"cluster_id": r.cluster_id,
             "headline": r.canonical_description,
             "event_type": r.canonical_event_type,
             "article_count": int(r.article_count or 0),
             "source_count": int(r.source_count or 0),
             "new_24h": int(r.new_24h or 0),
             "importance": round(float(r.importance_score), 1) if r.importance_score is not None else None,
             "last_updated": r.last_updated_at.isoformat() if r.last_updated_at else None}
            for r in rows
        ]
    }


# ── Panel 6: Crosstab (flexible) ──────────────────────────────────────────────

async def crosstab(db, actor: str | None = None, time_window_days: int = 30) -> dict[str, Any]:
    """Loose crosstab — counts of articles+events grouped by source × week
    for a given actor (substring match on article_events.actors[])."""
    if not actor:
        return {"actor": None, "rows": []}
    rows = (await db.execute(text("""
        SELECT s.name AS source,
               date_trunc('week', ae.effective_event_date) AS week,
               COUNT(*) AS n_events,
               COUNT(DISTINCT a.id) AS n_articles
          FROM article_events ae
          JOIN articles a ON a.id = ae.article_id
          JOIN sources s ON s.id = a.source_id
         WHERE ae.actors IS NOT NULL
           AND LOWER(array_to_string(ae.actors, ',')) LIKE '%' || LOWER(:needle) || '%'
           AND ae.effective_event_date >= CURRENT_DATE - make_interval(days => :days)
         GROUP BY s.name, date_trunc('week', ae.effective_event_date)
         ORDER BY 2 DESC, 3 DESC
         LIMIT 200
    """), {"needle": actor, "days": int(time_window_days)})).fetchall()
    return {
        "actor": actor,
        "rows": [
            {"source": r.source,
             "week": r.week.date().isoformat() if r.week else None,
             "n_events": int(r.n_events or 0),
             "n_articles": int(r.n_articles or 0)}
            for r in rows
        ]
    }


# ── Panel 7: Live article tail ────────────────────────────────────────────────

async def live_tail(db, after: str | None = None, limit: int = 50) -> dict[str, Any]:
    """Recent articles + extraction status. `after` is an ISO8601 timestamp cursor."""
    params: dict[str, Any] = {"lim": int(limit)}
    where = ""
    if after:
        where = "WHERE a.collected_at > CAST(:after AS timestamptz)"
        params["after"] = after
    rows = (await db.execute(text(f"""
        SELECT a.id::text AS aid,
               s.name AS source,
               a.title,
               a.language_detected AS lang,
               a.collected_at,
               a.substrate_status,
               a.extraction_version,
               LENGTH(COALESCE(a.summary_executive, '')) AS sum_len
          FROM articles a
          JOIN sources s ON s.id = a.source_id
          {where}
         ORDER BY a.collected_at DESC
         LIMIT :lim
    """), params)).fetchall()
    next_cursor = rows[0].collected_at.isoformat() if rows else after
    return {
        "next_cursor": next_cursor,
        "articles": [
            {"aid": r.aid, "source": r.source,
             "title": (r.title or "")[:200],
             "lang": r.lang,
             "collected_at": r.collected_at.isoformat() if r.collected_at else None,
             "substrate_status": r.substrate_status,
             "extraction_version": int(r.extraction_version or 0),
             "summary_len": int(r.sum_len or 0)}
            for r in rows
        ]
    }
