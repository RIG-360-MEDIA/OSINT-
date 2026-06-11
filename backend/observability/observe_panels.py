"""observe_panels.py — SQL helpers for every /api/observe/* endpoint.

All helpers accept an async SQLAlchemy session and return a dict shaped
exactly to the TypeScript interface in frontend/src/lib/observe-client.ts.

Design rules:
  - Never raise on missing data. Return zeros / empty lists / null where
    the panel-level field can't be computed (judge / regression / etc).
  - Use parameter binding for any user input (limit, level, after, actor).
  - Keep each helper independently testable; the router is just glue.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)


# ── Top counters (corpus_overview) ──────────────────────────────────────────


async def corpus_overview(db) -> dict[str, Any]:
    """Top-bar counters across the entire corpus.

    Returns CorpusOverview shape:
      total_articles, v3_articles, total_sources, languages, articles_24h,
      active_stories, total_claims, total_quotes, total_events, total_locations
    """
    row = (
        await db.execute(
            text(
                """
                SELECT
                  (SELECT COUNT(*) FROM articles)                            AS total_articles,
                  (SELECT COUNT(*) FROM articles WHERE extraction_version=3) AS v3_articles,
                  (SELECT COUNT(*) FROM sources)                             AS total_sources,
                  (SELECT COUNT(DISTINCT language_detected) FROM articles
                    WHERE language_detected IS NOT NULL)                     AS languages,
                  (SELECT COUNT(*) FROM articles
                    WHERE collected_at >= NOW() - INTERVAL '24 hours')       AS articles_24h,
                  (SELECT COUNT(*) FROM event_clusters
                    WHERE is_active AND source_count >= 2)                   AS active_stories,
                  (SELECT COUNT(*) FROM article_claims)                      AS total_claims,
                  (SELECT COUNT(*) FROM article_quotes)                      AS total_quotes,
                  (SELECT COUNT(*) FROM article_events)                      AS total_events,
                  (SELECT COUNT(*) FROM article_locations)                   AS total_locations
                """
            )
        )
    ).fetchone()
    return {
        "total_articles":   int(row.total_articles or 0),
        "v3_articles":      int(row.v3_articles or 0),
        "total_sources":    int(row.total_sources or 0),
        "languages":        int(row.languages or 0),
        "articles_24h":     int(row.articles_24h or 0),
        "active_stories":   int(row.active_stories or 0),
        "total_claims":     int(row.total_claims or 0),
        "total_quotes":     int(row.total_quotes or 0),
        "total_events":     int(row.total_events or 0),
        "total_locations":  int(row.total_locations or 0),
    }


# ── IngestPulse ─────────────────────────────────────────────────────────────


async def ingest_pulse(db) -> dict[str, Any]:
    by_hour_rows = (
        await db.execute(
            text(
                """
                SELECT date_trunc('hour', collected_at) AS h, COUNT(*) AS n
                  FROM articles
                 WHERE collected_at >= NOW() - INTERVAL '24 hours'
                 GROUP BY 1 ORDER BY 1
                """
            )
        )
    ).fetchall()

    per_source_rows = (
        await db.execute(
            text(
                """
                SELECT s.name AS source,
                       MAX(a.collected_at) AS last_seen,
                       COUNT(*) FILTER (WHERE a.collected_at >= NOW() - INTERVAL '24 hours') AS n_24h
                  FROM sources s
                  LEFT JOIN articles a ON a.source_id = s.id
                 GROUP BY s.name
                 ORDER BY n_24h DESC NULLS LAST
                 LIMIT 50
                """
            )
        )
    ).fetchall()

    now = datetime.now(timezone.utc)

    def _hours_since(ts) -> float:
        if ts is None:
            return 999.0
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return round((now - ts).total_seconds() / 3600.0, 1)

    per_source = [
        {
            "source": r.source,
            "last_seen": r.last_seen.isoformat() if r.last_seen else None,
            "n_24h": int(r.n_24h or 0),
            "hours_since": _hours_since(r.last_seen),
        }
        for r in per_source_rows
    ]

    stalled = [
        {"source": p["source"], "last_seen": p["last_seen"], "hours_since": p["hours_since"]}
        for p in per_source
        if p["hours_since"] >= 24.0
    ][:20]

    return {
        "by_hour": [
            {"hour": r.h.isoformat(), "n": int(r.n)} for r in by_hour_rows
        ],
        "per_source": per_source,
        "stalled_sources": stalled,
        "total_24h": sum(int(r.n) for r in by_hour_rows),
    }


# ── SourceScorecard ─────────────────────────────────────────────────────────


async def source_scorecard(db) -> dict[str, Any]:
    rows = (
        await db.execute(
            text(
                """
                SELECT s.name AS source,
                       COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE a.extraction_version=3 AND a.substrate_status='ok') AS v3_ok,
                       COUNT(*) FILTER (WHERE a.summary_executive IS NOT NULL
                                          AND length(a.summary_executive) >= 80) AS with_summary,
                       COUNT(*) FILTER (WHERE a.title_embedding IS NOT NULL)     AS with_embedding,
                       COUNT(DISTINCT a.language_detected) AS languages,
                       MAX(a.collected_at) AS last_seen
                  FROM sources s
                  JOIN articles a ON a.source_id = s.id
                 GROUP BY s.name
                HAVING COUNT(*) >= 5
                 ORDER BY total DESC
                 LIMIT 80
                """
            )
        )
    ).fetchall()

    return {
        "sources": [
            {
                "source": r.source,
                "total": int(r.total or 0),
                "v3_ok": int(r.v3_ok or 0),
                "has_summary_pct": round(100.0 * (r.with_summary or 0) / max(int(r.total or 1), 1), 1),
                "has_embedding_pct": round(100.0 * (r.with_embedding or 0) / max(int(r.total or 1), 1), 1),
                "languages": int(r.languages or 0),
                "last_seen": r.last_seen.isoformat() if r.last_seen else None,
            }
            for r in rows
        ]
    }


# ── QualityMonitor ──────────────────────────────────────────────────────────

_QA_DIR = Path("/app/qa")


def _load_latest_judge() -> dict[str, Any] | None:
    """Read the most recent qa_result_*.json with a 'judge' block."""
    if not _QA_DIR.exists():
        return None
    candidates = sorted(_QA_DIR.glob("qa_result*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in candidates[:10]:
        try:
            data = json.loads(p.read_text())
            judge = data.get("judge") or data
            if isinstance(judge, dict) and ("median_scores" in judge or "successes" in judge):
                judge.setdefault("source_file", p.name)
                return judge
        except Exception:
            continue
    return None


def _load_latest_regression() -> dict[str, Any] | None:
    if not _QA_DIR.exists():
        return None
    candidates = sorted(_QA_DIR.glob("qa_*regression*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        candidates = sorted(_QA_DIR.glob("qa_result*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in candidates[:5]:
        try:
            data = json.loads(p.read_text())
            reg = data.get("regression") or data
            if isinstance(reg, dict) and "gold_size" in reg:
                reg.setdefault("source_file", p.name)
                return reg
        except Exception:
            continue
    return None


async def quality_monitor(db) -> dict[str, Any]:
    live = (
        await db.execute(
            text(
                """
                SELECT
                  COUNT(*) FILTER (WHERE extraction_version=3 AND substrate_status='ok') AS v3_ok_total,
                  COUNT(*) FILTER (WHERE summary_executive IS NOT NULL
                                     AND length(summary_executive) BETWEEN 480 AND 520) AS cliff_500,
                  COUNT(*) FILTER (WHERE summary_executive IS NOT NULL
                                     AND length(summary_executive) BETWEEN 980 AND 1020) AS cliff_1000,
                  COUNT(*) FILTER (WHERE extraction_version=3
                                     AND substrate_status='ok'
                                     AND primary_subject IS NULL) AS null_subject,
                  COUNT(*) FILTER (WHERE extraction_version=3
                                     AND substrate_status='ok'
                                     AND (summary_executive IS NULL OR length(summary_executive) < 80)) AS thin_summary,
                  COUNT(*) FILTER (WHERE extraction_version=3
                                     AND substrate_status='ok'
                                     AND title_embedding IS NULL) AS null_embedding
                  FROM articles
                """
            )
        )
    ).fetchone()

    claim_row = (
        await db.execute(
            text(
                """
                SELECT
                  COUNT(*) AS claims_total,
                  COUNT(*) FILTER (WHERE claim_text ILIKE '%placeholder%'
                                    OR claim_text ILIKE '%lorem%'
                                    OR length(claim_text) < 20) AS claims_placeholder
                  FROM article_claims
                """
            )
        )
    ).fetchone()

    v3_ok_total = int(live.v3_ok_total or 0)
    thin = int(live.thin_summary or 0)
    claims_total = int(claim_row.claims_total or 0)
    claims_ph = int(claim_row.claims_placeholder or 0)

    return {
        "judge": _load_latest_judge(),
        "regression": _load_latest_regression(),
        "live": {
            "v3_ok_total": v3_ok_total,
            "cliff_500": int(live.cliff_500 or 0),
            "cliff_1000": int(live.cliff_1000 or 0),
            "null_subject": int(live.null_subject or 0),
            "thin_summary": thin,
            "thin_summary_pct": round(100.0 * thin / max(v3_ok_total, 1), 1),
            "null_embedding": int(live.null_embedding or 0),
            "claims_placeholder": claims_ph,
            "claims_placeholder_pct": round(100.0 * claims_ph / max(claims_total, 1), 1),
            "claims_total": claims_total,
        },
    }


# ── GeoHeatmap ──────────────────────────────────────────────────────────────


async def geo_heatmap(db, level: str = "country") -> dict[str, Any]:
    if level not in ("country", "state", "district"):
        level = "country"

    if level == "country":
        rows = (
            await db.execute(
                text(
                    """
                    SELECT COALESCE(country_iso2, 'UNK') AS region, COUNT(*) AS n
                      FROM article_locations
                     WHERE country_iso2 IS NOT NULL
                     GROUP BY 1 ORDER BY 2 DESC LIMIT 60
                    """
                )
            )
        ).fetchall()
    elif level == "state":
        rows = (
            await db.execute(
                text(
                    """
                    SELECT COALESCE(state_name, 'Unknown') AS region, COUNT(*) AS n
                      FROM article_locations
                     WHERE state_name IS NOT NULL
                     GROUP BY 1 ORDER BY 2 DESC LIMIT 60
                    """
                )
            )
        ).fetchall()
    else:  # district
        rows = (
            await db.execute(
                text(
                    """
                    SELECT COALESCE(d.name, 'Unknown') AS region, COUNT(*) AS n
                      FROM article_districts ad
                      LEFT JOIN districts d ON d.id = ad.district_id
                     GROUP BY 1 ORDER BY 2 DESC LIMIT 100
                    """
                )
            )
        ).fetchall()

    return {
        "level": level,
        "regions": [{"region": r.region, "n": int(r.n or 0)} for r in rows],
    }


# ── StoryPulse ──────────────────────────────────────────────────────────────


async def story_pulse(db, limit: int = 30) -> dict[str, Any]:
    rows = (
        await db.execute(
            text(
                """
                SELECT ec.id::text AS cluster_id,
                       COALESCE(ec.canonical_description, '(no headline)') AS headline,
                       ec.canonical_event_type AS event_type,
                       ec.article_count, ec.source_count,
                       (SELECT COUNT(*) FROM article_events ae
                          JOIN articles a ON a.id = ae.article_id
                         WHERE ae.event_cluster_id = ec.id
                           AND a.collected_at >= NOW() - INTERVAL '24 hours') AS new_24h,
                       ec.importance_score AS importance,
                       ec.last_updated_at AS last_updated
                  FROM event_clusters ec
                 WHERE ec.is_active AND ec.source_count >= 2
                 ORDER BY COALESCE(ec.importance_score, 0) DESC,
                          ec.last_updated_at DESC NULLS LAST
                 LIMIT :lim
                """
            ),
            {"lim": int(limit)},
        )
    ).fetchall()
    return {
        "clusters": [
            {
                "cluster_id": r.cluster_id,
                "headline": (r.headline or "")[:240],
                "event_type": r.event_type,
                "article_count": int(r.article_count or 0),
                "source_count": int(r.source_count or 0),
                "new_24h": int(r.new_24h or 0),
                "importance": float(r.importance) if r.importance is not None else None,
                "last_updated": r.last_updated.isoformat() if r.last_updated else None,
            }
            for r in rows
        ]
    }


# ── BreakingNow ─────────────────────────────────────────────────────────────


async def breaking_now(db, limit: int = 12) -> dict[str, Any]:
    rows = (
        await db.execute(
            text(
                """
                SELECT a.id::text AS aid,
                       a.title,
                       COALESCE(a.primary_subject, '') AS subject,
                       COALESCE(s.name, '') AS source,
                       a.language_detected AS lang,
                       a.collected_at
                  FROM articles a
                  LEFT JOIN sources s ON s.id = a.source_id
                 WHERE a.register_is_breaking = TRUE
                   AND a.collected_at >= NOW() - INTERVAL '24 hours'
                 ORDER BY a.collected_at DESC
                 LIMIT :lim
                """
            ),
            {"lim": int(limit)},
        )
    ).fetchall()
    return {
        "items": [
            {
                "aid": r.aid,
                "title": (r.title or "")[:220],
                "subject": r.subject or "",
                "source": r.source or "",
                "lang": r.lang,
                "collected_at": r.collected_at.isoformat() if r.collected_at else None,
            }
            for r in rows
        ]
    }


# ── TopSpeakers ─────────────────────────────────────────────────────────────


async def top_speakers(db, limit: int = 15) -> dict[str, Any]:
    rows = (
        await db.execute(
            text(
                """
                SELECT COALESCE(speaker_name_en, speaker_name) AS speaker,
                       COUNT(*) AS n_quotes,
                       COUNT(DISTINCT a.source_id) AS n_sources,
                       (SELECT LEFT(q2.quote_text, 180)
                          FROM article_quotes q2
                          JOIN articles a2 ON a2.id = q2.article_id
                         WHERE COALESCE(q2.speaker_name_en, q2.speaker_name) =
                               COALESCE(q.speaker_name_en, q.speaker_name)
                           AND a2.collected_at >= NOW() - INTERVAL '24 hours'
                           AND length(q2.quote_text) >= 30
                         ORDER BY length(q2.quote_text) DESC LIMIT 1) AS sample_quote
                  FROM article_quotes q
                  JOIN articles a ON a.id = q.article_id
                 WHERE a.collected_at >= NOW() - INTERVAL '24 hours'
                   AND COALESCE(q.speaker_name_en, q.speaker_name) IS NOT NULL
                   AND length(COALESCE(q.speaker_name_en, q.speaker_name)) BETWEEN 3 AND 80
                 GROUP BY 1
                 ORDER BY n_quotes DESC
                 LIMIT :lim
                """
            ),
            {"lim": int(limit)},
        )
    ).fetchall()
    return {
        "speakers": [
            {
                "speaker": r.speaker,
                "n_quotes": int(r.n_quotes or 0),
                "n_sources": int(r.n_sources or 0),
                "sample_quote": r.sample_quote,
            }
            for r in rows
        ]
    }


# ── PipelineHealth ──────────────────────────────────────────────────────────


async def pipeline_health(db) -> dict[str, Any]:
    t4 = (
        await db.execute(
            text(
                """
                SELECT COUNT(*) FILTER (WHERE claims_extracted = TRUE) AS completed,
                       COUNT(*) FILTER (WHERE substrate_status = 'ok') AS target
                  FROM articles
                """
            )
        )
    ).fetchone()

    v3 = (
        await db.execute(
            text(
                """
                SELECT
                  COUNT(*) FILTER (WHERE extraction_version=3 AND substrate_status='ok') AS v3,
                  COUNT(*) FILTER (WHERE extraction_version=2 AND substrate_status='ok') AS v2
                  FROM articles
                """
            )
        )
    ).fetchone()

    t4_completed = int(t4.completed or 0)
    t4_target = int(t4.target or 0)
    v3_n = int(v3.v3 or 0)
    v2_n = int(v3.v2 or 0)
    total = v3_n + v2_n

    return {
        "t4_backfill": {
            "completed": t4_completed,
            "target": t4_target,
            "pct": round(100.0 * t4_completed / max(t4_target, 1), 1),
            "running": (t4_target - t4_completed) > 0,
        },
        "v3_upgrade": {
            "v3": v3_n,
            "v2": v2_n,
            "pct_v3": round(100.0 * v3_n / max(total, 1), 1),
        },
        "latest_regression": _load_latest_regression(),
    }


# ── Trending ────────────────────────────────────────────────────────────────


async def trending(db, limit: int = 25) -> dict[str, Any]:
    rows = (
        await db.execute(
            text(
                """
                WITH today AS (
                  SELECT entity_text,
                         SUM(n_mentions_total) AS n_today,
                         COUNT(DISTINCT source_id) AS sources_today
                    FROM entity_mention_daily
                   WHERE date = CURRENT_DATE
                   GROUP BY entity_text
                ),
                baseline AS (
                  SELECT entity_text, AVG(daily_n) AS baseline_avg
                    FROM (
                      SELECT entity_text, date, SUM(n_mentions_total) AS daily_n
                        FROM entity_mention_daily
                       WHERE date BETWEEN CURRENT_DATE - INTERVAL '7 days' AND CURRENT_DATE - INTERVAL '1 day'
                       GROUP BY entity_text, date
                    ) d
                   GROUP BY entity_text
                )
                SELECT t.entity_text AS entity,
                       t.n_today      AS mentions_today,
                       t.sources_today,
                       COALESCE(b.baseline_avg, 0) AS baseline_avg,
                       CASE WHEN COALESCE(b.baseline_avg, 0) > 0
                            THEN ROUND((t.n_today::numeric / b.baseline_avg::numeric), 2)
                            ELSE NULL END AS surge_ratio,
                       (b.baseline_avg IS NULL OR b.baseline_avg = 0) AS is_new
                  FROM today t
                  LEFT JOIN baseline b USING (entity_text)
                 WHERE LENGTH(t.entity_text) BETWEEN 3 AND 60
                   AND t.n_today >= 3
                 ORDER BY (CASE WHEN COALESCE(b.baseline_avg, 0) > 0
                                THEN t.n_today::numeric / b.baseline_avg::numeric
                                ELSE 999 END) DESC,
                          t.n_today DESC
                 LIMIT :lim
                """
            ),
            {"lim": int(limit)},
        )
    ).fetchall()
    out = []
    for r in rows:
        surge = float(r.surge_ratio) if r.surge_ratio is not None else None
        out.append(
            {
                "entity": r.entity,
                "mentions_today": int(r.mentions_today or 0),
                "sources_today": int(r.sources_today or 0),
                "baseline_avg": float(r.baseline_avg or 0),
                "surge_ratio": surge,
                "is_new": bool(r.is_new),
                "is_surging": bool(surge is not None and surge >= 2.0),
            }
        )
    return {"entities": out}


# ── ArticleTypes ────────────────────────────────────────────────────────────


async def article_types(db) -> dict[str, Any]:
    types_rows = (
        await db.execute(
            text(
                """
                SELECT COALESCE(article_type, 'unknown') AS type, COUNT(*) AS n
                  FROM articles
                 WHERE collected_at >= NOW() - INTERVAL '7 days'
                 GROUP BY 1 ORDER BY 2 DESC LIMIT 25
                """
            )
        )
    ).fetchall()

    lang_rows = (
        await db.execute(
            text(
                """
                SELECT UPPER(COALESCE(language_detected, '??')) AS lang, COUNT(*) AS n
                  FROM articles
                 WHERE collected_at >= NOW() - INTERVAL '24 hours'
                 GROUP BY 1 ORDER BY 2 DESC LIMIT 12
                """
            )
        )
    ).fetchall()

    stance_rows = (
        await db.execute(
            text(
                """
                SELECT
                  CASE
                    WHEN intensity >= 0.15  THEN 'supportive'
                    WHEN intensity <= -0.15 THEN 'critical'
                    ELSE 'neutral'
                  END AS stance,
                  COUNT(*) AS n
                  FROM article_stances
                 WHERE intensity IS NOT NULL
                 GROUP BY 1 ORDER BY 2 DESC
                """
            )
        )
    ).fetchall()

    country_rows = (
        await db.execute(
            text(
                """
                SELECT COALESCE(country_iso2, 'UNK') AS country, COUNT(*) AS n
                  FROM article_locations
                 WHERE country_iso2 IS NOT NULL
                 GROUP BY 1 ORDER BY 2 DESC LIMIT 12
                """
            )
        )
    ).fetchall()

    dict_row = (
        await db.execute(
            text(
                """
                SELECT
                  COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE entity_type IN ('person', 'people')) AS people,
                  COUNT(*) FILTER (WHERE entity_type IN ('location','geo','place')) AS locations,
                  COUNT(*) FILTER (WHERE entity_type IN ('org','organization','party')) AS orgs,
                  COUNT(*) FILTER (WHERE entity_type IN ('constituency','ac','pc')) AS constituencies
                  FROM entity_dictionary
                """
            )
        )
    ).fetchone()

    return {
        "article_types": [{"type": r.type, "n": int(r.n or 0)} for r in types_rows],
        "languages_24h": [{"lang": r.lang, "n": int(r.n or 0)} for r in lang_rows],
        "stances":       [{"stance": r.stance, "n": int(r.n or 0)} for r in stance_rows],
        "top_countries": [{"country": r.country, "n": int(r.n or 0)} for r in country_rows],
        "entity_dictionary": {
            "total":          int(dict_row.total or 0),
            "people":         int(dict_row.people or 0),
            "locations":      int(dict_row.locations or 0),
            "orgs":           int(dict_row.orgs or 0),
            "constituencies": int(dict_row.constituencies or 0),
        },
    }


# ── LiveTail ────────────────────────────────────────────────────────────────


async def live_tail(db, after: str | None = None, limit: int = 50) -> dict[str, Any]:
    sql = """
        SELECT a.id::text AS aid,
               COALESCE(s.name, '') AS source,
               COALESCE(a.title, '(untitled)') AS title,
               a.language_detected AS lang,
               a.collected_at,
               a.substrate_status,
               COALESCE(a.extraction_version, 0) AS extraction_version,
               COALESCE(length(a.summary_executive), 0) AS summary_len
          FROM articles a
          LEFT JOIN sources s ON s.id = a.source_id
         {where}
         ORDER BY a.collected_at DESC LIMIT :lim
    """
    params: dict[str, Any] = {"lim": int(limit) + 1}
    where = ""
    if after:
        try:
            after_ts = datetime.fromisoformat(after.replace("Z", "+00:00"))
            params["after"] = after_ts
            where = "WHERE a.collected_at < :after"
        except ValueError:
            pass

    rows = (await db.execute(text(sql.format(where=where)), params)).fetchall()
    items = rows[: int(limit)]
    next_cursor = items[-1].collected_at.isoformat() if len(rows) > int(limit) and items[-1].collected_at else None

    return {
        "next_cursor": next_cursor,
        "articles": [
            {
                "aid": r.aid,
                "source": r.source,
                "title": (r.title or "")[:220],
                "lang": r.lang,
                "collected_at": r.collected_at.isoformat() if r.collected_at else None,
                "substrate_status": r.substrate_status,
                "extraction_version": int(r.extraction_version or 0),
                "summary_len": int(r.summary_len or 0),
            }
            for r in items
        ],
    }


# ── CrossTab ────────────────────────────────────────────────────────────────


async def crosstab(db, actor: str, days: int = 30) -> dict[str, Any]:
    rows = (
        await db.execute(
            text(
                """
                SELECT COALESCE(s.name, '?') AS source,
                       date_trunc('week', a.collected_at)::date::text AS week,
                       COUNT(DISTINCT ae.id) AS n_events,
                       COUNT(DISTINCT a.id) AS n_articles
                  FROM article_events ae
                  JOIN articles a ON a.id = ae.article_id
                  LEFT JOIN sources s ON s.id = a.source_id
                  LEFT JOIN event_clusters ec ON ec.id = ae.event_cluster_id
                 WHERE a.collected_at >= NOW() - make_interval(days => :d)
                   AND (
                        ec.canonical_description ILIKE '%' || :actor || '%'
                     OR ae.event_text ILIKE '%' || :actor || '%'
                     OR a.title ILIKE '%' || :actor || '%'
                   )
                 GROUP BY 1, 2
                 ORDER BY 2 DESC, n_events DESC
                 LIMIT 200
                """
            ),
            {"actor": actor.strip(), "d": int(days)},
        )
    ).fetchall()
    return {
        "actor": actor.strip() or None,
        "rows": [
            {
                "source": r.source,
                "week": r.week,
                "n_events": int(r.n_events or 0),
                "n_articles": int(r.n_articles or 0),
            }
            for r in rows
        ],
    }


# ── AuditQueue + AuditDecision ──────────────────────────────────────────────


async def audit_queue(db, limit: int = 30) -> dict[str, Any]:
    rows = (
        await db.execute(
            text(
                """
                SELECT a.id::text AS aid,
                       'thin_summary' AS flag,
                       'summary < 80 chars on v3-ok article' AS hint,
                       COALESCE(s.name, '') AS source,
                       COALESCE(a.title, '(untitled)') AS title,
                       a.collected_at,
                       (SELECT verdict FROM audit_decisions ad
                         WHERE ad.article_id = a.id AND ad.field_name = 'summary_executive'
                         ORDER BY ad.decided_at DESC LIMIT 1) AS existing_verdict
                  FROM articles a
                  LEFT JOIN sources s ON s.id = a.source_id
                 WHERE a.extraction_version = 3
                   AND a.substrate_status = 'ok'
                   AND (a.summary_executive IS NULL OR length(a.summary_executive) < 80)
                   AND a.collected_at >= NOW() - INTERVAL '7 days'
                 ORDER BY a.collected_at DESC
                 LIMIT :lim
                """
            ),
            {"lim": int(limit)},
        )
    ).fetchall()
    return {
        "queue": [
            {
                "aid": r.aid,
                "flag": r.flag,
                "hint": r.hint,
                "source": r.source,
                "title": (r.title or "")[:220],
                "collected_at": r.collected_at.isoformat() if r.collected_at else None,
                "existing_verdict": r.existing_verdict,
            }
            for r in rows
        ]
    }


async def audit_decision(db, body: dict[str, Any]) -> dict[str, Any]:
    """Insert an audit decision row. body must have article_id, field_name,
    extraction_version, verdict, optional note.
    """
    required = ("article_id", "field_name", "extraction_version", "verdict")
    for k in required:
        if k not in body:
            raise ValueError(f"missing field: {k}")
    if body["verdict"] not in ("correct", "wrong", "unsure"):
        raise ValueError("verdict must be one of correct|wrong|unsure")

    row = (
        await db.execute(
            text(
                """
                INSERT INTO audit_decisions
                       (article_id, field_name, extraction_version, verdict, note, decided_at)
                VALUES (CAST(:aid AS uuid), :field, :ver, :verdict, :note, NOW())
                RETURNING id::text AS id, decided_at
                """
            ),
            {
                "aid": body["article_id"],
                "field": body["field_name"],
                "ver": int(body["extraction_version"]),
                "verdict": body["verdict"],
                "note": body.get("note"),
            },
        )
    ).fetchone()
    await db.commit()
    return {
        "ok": True,
        "id": row.id,
        "decided_at": row.decided_at.isoformat() if row.decided_at else "",
    }
