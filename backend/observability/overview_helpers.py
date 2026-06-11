"""overview_helpers.py — helpers for the /observe v2 top banner + new panels.

Three additions on top of article_quality.py + audit_queue.py:
  * corpus_overview()    — single-line TLDR of the entire corpus
  * pipeline_health()    — what's running right now (T4, v3 upgrade, last task runs)
  * trending_entities()  — uses T6 entity_mention_daily for the "trending now" panel
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import text


# ── 1. Corpus overview — single-line TLDR for the banner ────────────────────

async def corpus_overview(db) -> dict[str, Any]:
    row = (await db.execute(text("""
        SELECT
          (SELECT COUNT(*) FROM articles WHERE substrate_status='ok') AS total_articles,
          (SELECT COUNT(*) FROM articles
            WHERE substrate_status='ok' AND extraction_version >= 3) AS v3_articles,
          (SELECT COUNT(DISTINCT id) FROM sources) AS total_sources,
          (SELECT COUNT(DISTINCT language_detected) FROM articles
            WHERE language_detected IS NOT NULL) AS languages,
          (SELECT COUNT(*) FROM articles
            WHERE collected_at >= NOW() - INTERVAL '24 hours') AS articles_24h,
          (SELECT COUNT(*) FROM event_clusters
            WHERE is_active AND source_count >= 2) AS active_stories,
          (SELECT COUNT(*) FROM article_claims) AS total_claims,
          (SELECT COUNT(*) FROM article_quotes) AS total_quotes,
          (SELECT COUNT(*) FROM article_events) AS total_events,
          (SELECT COUNT(*) FROM article_locations) AS total_locations
    """))).fetchone()
    return {
        "total_articles": int(row.total_articles or 0),
        "v3_articles": int(row.v3_articles or 0),
        "total_sources": int(row.total_sources or 0),
        "languages": int(row.languages or 0),
        "articles_24h": int(row.articles_24h or 0),
        "active_stories": int(row.active_stories or 0),
        "total_claims": int(row.total_claims or 0),
        "total_quotes": int(row.total_quotes or 0),
        "total_events": int(row.total_events or 0),
        "total_locations": int(row.total_locations or 0),
    }


# ── 2. Pipeline health — what's running right now ───────────────────────────

QUALITY_DIR = (
    Path("/docs/quality") if Path("/docs/quality").exists()
    else Path("docs/quality")
)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


async def pipeline_health(db) -> dict[str, Any]:
    """Reports state of background workers + recent task results."""
    # T4 placeholder backfill — state file
    t4_state = _read_json(QUALITY_DIR / "backfill_state.json") or {}
    t4_done = len(t4_state.get("completed", []))
    t4_total = 64755  # measured at T4 start
    t4_pct = round(100.0 * t4_done / max(t4_total, 1), 1)

    # v3 upgrade backlog
    row = (await db.execute(text("""
        SELECT
          COUNT(*) FILTER (WHERE extraction_version=3) AS v3_count,
          COUNT(*) FILTER (WHERE extraction_version<3) AS v2_count,
          COUNT(*) FILTER (WHERE substrate_status='ok') AS ok_count
        FROM articles
    """))).fetchone()

    # Latest regression / new-vs-baseline runs
    latest_regression = None
    regs = sorted(QUALITY_DIR.glob("regression_*.json")) if QUALITY_DIR.exists() else []
    if regs:
        latest_regression = _read_json(regs[-1])
        if latest_regression:
            latest_regression["source_file"] = regs[-1].name

    return {
        "t4_backfill": {
            "completed": t4_done,
            "target": t4_total,
            "pct": t4_pct,
            "running": t4_done < t4_total,
        },
        "v3_upgrade": {
            "v3": int(row.v3_count or 0),
            "v2": int(row.v2_count or 0),
            "pct_v3": round(100.0 * (row.v3_count or 0)
                            / max(row.ok_count, 1), 1),
        },
        "latest_regression": latest_regression,
    }


# ── 3. Trending entities — uses T6's entity_mention_daily ───────────────────

# ── 4. Breaking news — register_is_breaking from v3 articles ────────────────

async def breaking_now(db, limit: int = 12) -> dict[str, Any]:
    rows = (await db.execute(text("""
        SELECT a.id::text AS aid,
               LEFT(a.title, 180) AS title,
               LEFT(a.primary_subject, 220) AS subject,
               s.name AS source,
               a.language_detected AS lang,
               a.collected_at
          FROM articles a
          JOIN sources s ON s.id = a.source_id
         WHERE a.register_is_breaking = TRUE
           AND a.substrate_status = 'ok'
           AND a.collected_at >= NOW() - INTERVAL '24 hours'
         ORDER BY a.collected_at DESC
         LIMIT :lim
    """), {"lim": int(limit)})).fetchall()
    return {
        "items": [
            {"aid": r.aid, "title": r.title, "subject": r.subject,
             "source": r.source, "lang": r.lang,
             "collected_at": r.collected_at.isoformat() if r.collected_at else None}
            for r in rows
        ]
    }


# ── 5. Top speakers being quoted today ──────────────────────────────────────

async def top_speakers(db, limit: int = 15) -> dict[str, Any]:
    """Most-quoted speakers in last 24h, with sample quote."""
    rows = (await db.execute(text("""
        WITH recent_quotes AS (
          SELECT LOWER(TRIM(aq.speaker_name)) AS speaker,
                 aq.quote_text, aq.article_id, a.source_id
            FROM article_quotes aq
            JOIN articles a ON a.id = aq.article_id
           WHERE a.collected_at >= NOW() - INTERVAL '24 hours'
             AND aq.speaker_name IS NOT NULL
             AND LENGTH(TRIM(aq.speaker_name)) BETWEEN 3 AND 60
             AND LOWER(TRIM(aq.speaker_name)) NOT IN
                 ('author','article','reporter','correspondent','editor','spokesperson')
        )
        SELECT speaker, COUNT(*) AS n_quotes,
               COUNT(DISTINCT source_id) AS n_sources,
               (array_agg(LEFT(quote_text,160) ORDER BY length(quote_text) DESC))[1] AS sample_quote
          FROM recent_quotes
         GROUP BY speaker
        HAVING COUNT(*) >= 2
         ORDER BY n_quotes DESC
         LIMIT :lim
    """), {"lim": int(limit)})).fetchall()
    return {
        "speakers": [
            {"speaker": r.speaker, "n_quotes": int(r.n_quotes),
             "n_sources": int(r.n_sources or 0),
             "sample_quote": r.sample_quote}
            for r in rows
        ]
    }


# ── 6. Article-type breakdown (for donut viz) ───────────────────────────────

async def article_types(db) -> dict[str, Any]:
    rows = (await db.execute(text("""
        SELECT article_type AS type, COUNT(*) AS n
          FROM articles
         WHERE substrate_status='ok' AND article_type IS NOT NULL
         GROUP BY 1 ORDER BY 2 DESC
    """))).fetchall()
    rows_lang = (await db.execute(text("""
        SELECT language_detected AS lang, COUNT(*) AS n
          FROM articles
         WHERE collected_at >= NOW() - INTERVAL '24 hours'
           AND language_detected IS NOT NULL
         GROUP BY 1 ORDER BY 2 DESC LIMIT 15
    """))).fetchall()
    rows_stance = (await db.execute(text("""
        SELECT stance, COUNT(*) AS n
          FROM article_stances WHERE stance IS NOT NULL
         GROUP BY 1 ORDER BY 2 DESC LIMIT 8
    """))).fetchall()
    rows_country = (await db.execute(text("""
        SELECT country, COUNT(*) AS n FROM article_locations
         WHERE country IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 10
    """))).fetchall()
    # Entity-dictionary breakdown
    entities = (await db.execute(text("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE entity_type='person') AS people,
               COUNT(*) FILTER (WHERE entity_type='location') AS locations,
               COUNT(*) FILTER (WHERE entity_type IN ('organization','org','organisation')) AS orgs,
               COUNT(*) FILTER (WHERE entity_type='constituency') AS constituencies
          FROM entity_dictionary
    """))).fetchone()
    return {
        "article_types": [
            {"type": r.type, "n": int(r.n)} for r in rows
        ],
        "languages_24h": [{"lang": r.lang, "n": int(r.n)} for r in rows_lang],
        "stances": [{"stance": r.stance, "n": int(r.n)} for r in rows_stance],
        "top_countries": [{"country": r.country, "n": int(r.n)} for r in rows_country],
        "entity_dictionary": {
            "total": int(entities.total or 0),
            "people": int(entities.people or 0),
            "locations": int(entities.locations or 0),
            "orgs": int(entities.orgs or 0),
            "constituencies": int(entities.constituencies or 0),
        },
    }


async def trending_entities(db, limit: int = 25) -> dict[str, Any]:
    """Top entities mentioned in last 24h, with 7-day baseline comparison."""
    rows = (await db.execute(text("""
        WITH today AS (
          SELECT entity_text, SUM(n_mentions_total) AS today_n,
                 MAX(n_sources) AS today_srcs
            FROM entity_mention_daily
           WHERE date >= CURRENT_DATE - 1
           GROUP BY entity_text
        ),
        baseline AS (
          SELECT entity_text, AVG(n_mentions_total)::numeric AS avg_n
            FROM entity_mention_daily
           WHERE date BETWEEN CURRENT_DATE - 8 AND CURRENT_DATE - 2
           GROUP BY entity_text
        )
        SELECT t.entity_text, t.today_n, t.today_srcs,
               COALESCE(b.avg_n, 0) AS baseline_n,
               CASE WHEN COALESCE(b.avg_n, 0) > 0
                    THEN ROUND((t.today_n / b.avg_n)::numeric, 2)
                    ELSE NULL END AS surge_ratio
          FROM today t
          LEFT JOIN baseline b USING (entity_text)
         ORDER BY t.today_n DESC
         LIMIT :lim
    """), {"lim": int(limit)})).fetchall()
    return {
        "entities": [
            {"entity": r.entity_text,
             "mentions_today": int(r.today_n),
             "sources_today": int(r.today_srcs or 0),
             "baseline_avg": float(r.baseline_n or 0),
             "surge_ratio": float(r.surge_ratio) if r.surge_ratio else None,
             "is_new": r.baseline_n == 0,
             "is_surging": (r.surge_ratio or 0) >= 3.0}
            for r in rows
        ]
    }
