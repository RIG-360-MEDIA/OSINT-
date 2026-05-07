"""
SQL helpers for CM Page v2 endpoints.

Mirrors the pattern in ``cm_queries.py``: each function takes a state
code (and any other narrow params) and returns a list of dicts ready
to spread into the v2 Pydantic models. No business logic here — just
queries.

All helpers use the ``_safe_execute`` wrapper from ``cm_queries`` so
broken SQL doesn't take down the dashboard aggregator.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.routers.cm_queries import _safe_execute

logger = logging.getLogger(__name__)


# ── 1. Lead headlines ────────────────────────────────────────────────────


async def fetch_lead_headlines(state: str | None) -> list[dict[str, Any]]:
    sql = """
        SELECT
            rank, eyebrow, headline, cite_ids,
            generated_at, model
        FROM cm_lead_headlines
        WHERE state_code = COALESCE(:state, state_code)
          AND validated = TRUE
          AND rejected  = FALSE
          AND generated_at = (
              SELECT MAX(generated_at) FROM cm_lead_headlines
              WHERE state_code = COALESCE(:state, state_code)
                AND validated = TRUE AND rejected = FALSE
          )
        ORDER BY rank ASC
        LIMIT 20
    """
    async with get_db() as db:
        rows = await _safe_execute(db, sql, {"state": state})
    return [
        {
            "rank": r.rank,
            "eyebrow": r.eyebrow,
            "headline": r.headline,
            "cite_ids": [str(u) for u in (r.cite_ids or [])],
            "generated_at": r.generated_at,
            "model": r.model,
        }
        for r in (rows or [])
    ]


# ── 2. News on Chair ─────────────────────────────────────────────────────


async def fetch_news_on_chair(state: str | None, *, limit: int = 4) -> list[dict[str, Any]]:
    """Top recent articles tagged to this state where the CM (or a key
    minister) appears in entities_extracted. Joined to article_districts
    for the per-district badge list."""
    sql = """
        WITH cm_articles AS (
            SELECT DISTINCT a.id, a.title, a.url, a.published_at,
                   a.lead_text_translated, a.lead_text_original,
                   s.name AS source_name,
                   a.entities_extracted,
                   a.geo_primary
            FROM articles a
            LEFT JOIN sources s ON s.id = a.source_id
            JOIN article_districts ad ON ad.article_id = a.id
            JOIN districts d ON d.id = ad.district_id
            WHERE a.nlp_processed = TRUE
              AND a.collected_at > NOW() - INTERVAL '24 hours'
              AND d.state_code = COALESCE(:state, d.state_code)
              AND (
                a.entities_extracted::text ILIKE '%revanth%' OR
                a.title ILIKE '%revanth%' OR
                a.title ILIKE '%chief minister%' OR
                a.title ~* '\mCM\M' OR
                a.lead_text_translated ILIKE '%revanth reddy%' OR
                a.lead_text_original   ILIKE '%revanth reddy%'
              )
            ORDER BY a.published_at DESC NULLS LAST
            LIMIT 20
        )
        SELECT a.*,
               COALESCE(ARRAY_AGG(ad.district_id) FILTER (WHERE ad.district_id IS NOT NULL), '{}') AS districts
        FROM cm_articles a
        LEFT JOIN article_districts ad ON ad.article_id = a.id
        GROUP BY a.id, a.title, a.url, a.published_at, a.lead_text_translated,
                 a.lead_text_original, a.source_name, a.entities_extracted, a.geo_primary
        ORDER BY a.published_at DESC NULLS LAST
        LIMIT :lim
    """
    async with get_db() as db:
        rows = await _safe_execute(db, sql, {"state": state, "lim": limit})
    return [
        {
            "id": str(r.id),
            "title": r.title or "",
            "source": r.source_name or "Unknown",
            "age_label": _age_label(r.published_at),
            "sentiment": None,                # filled in by callers if needed
            "reach": None,
            "url": r.url,
            "districts": list(r.districts or []),
            "published_at": r.published_at,
        }
        for r in (rows or [])
    ]


# ── 3. Opposition Watch ──────────────────────────────────────────────────


async def fetch_opposition_watch(state: str | None, *, limit: int = 4) -> list[dict[str, Any]]:
    sql = """
        SELECT sp.id, sp.author_display_name, sp.author_username,
               sp.platform, sp.post_text, sp.post_url, sp.posted_at,
               sp.sentiment_score, sp.upvotes, sp.author_follower_count,
               h.party, h.person_name, h.person_role
        FROM social_posts sp
        JOIN cm_political_handles h
          ON LOWER(h.handle) = LOWER(sp.author_username)
         AND h.platform = sp.platform
         AND h.active = TRUE
        JOIN cm_coalitions c
          ON c.state = h.state AND c.party = h.party
         AND c.coalition = 'opposition'
        WHERE c.state = COALESCE(:state, c.state)
          AND sp.posted_at > NOW() - INTERVAL '24 hours'
        ORDER BY sp.posted_at DESC
        LIMIT :lim
    """
    async with get_db() as db:
        rows = await _safe_execute(db, sql, {"state": state, "lim": limit})
    return [
        {
            "id": str(r.id),
            "actor": r.person_name or r.author_display_name or r.author_username or "",
            "party": r.party or "",
            "channel": r.platform,
            "age_label": _age_label(r.posted_at),
            "text": (r.post_text or "")[:280],
            "reach": _format_reach(r.upvotes, r.author_follower_count),
            "sentiment": float(r.sentiment_score) if r.sentiment_score is not None else None,
            "url": r.post_url,
        }
        for r in (rows or [])
    ]


# ── 4. Threats ───────────────────────────────────────────────────────────


async def fetch_threats(state: str | None, *, limit: int = 4) -> list[dict[str, Any]]:
    """Composite: dissent + counter-narratives + risk-calendar. Severity
    is mapped to LOW / LOW-MED / MED / HIGH."""
    sql = """
        (
            SELECT 'dissent' AS source, ds.id::text, ds.summary AS text,
                   CASE
                     WHEN ds.severity >= 0.8 THEN 'HIGH'
                     WHEN ds.severity >= 0.6 THEN 'MED'
                     WHEN ds.severity >= 0.4 THEN 'LOW-MED'
                     ELSE 'LOW'
                   END AS level,
                   COALESCE('contradiction · '||ds.party, 'intra-coalition') AS posture,
                   ds.detected_at AS sort_at,
                   ds.evidence_urls AS cite_urls
            FROM cm_dissent_signals ds
            WHERE ds.state = COALESCE(:state, ds.state)
              AND ds.detected_at > NOW() - INTERVAL '7 days'
        )
        UNION ALL
        (
            SELECT 'counter_narrative' AS source, cn.id::text,
                   COALESCE(i.label, 'narrative pressure') AS text,
                   CASE WHEN cn.rejected THEN 'LOW' ELSE 'MED' END AS level,
                   'counter-window opening' AS posture,
                   cn.generated_at AS sort_at,
                   '{}'::text[] AS cite_urls
            FROM cm_counter_narratives cn
            LEFT JOIN cm_issues i ON i.id = cn.issue_id
            WHERE cn.state = COALESCE(:state, cn.state)
              AND cn.generated_at > NOW() - INTERVAL '36 hours'
        )
        UNION ALL
        (
            SELECT 'risk_calendar' AS source, rc.id::text, rc.title AS text,
                   COALESCE(UPPER(rc.risk_level), 'LOW') AS level,
                   COALESCE(rc.risk_summary, rc.kind) AS posture,
                   (rc.event_date AT TIME ZONE 'UTC')::timestamptz AS sort_at,
                   ARRAY[rc.source_url]::text[] AS cite_urls
            FROM cm_risk_calendar rc
            WHERE rc.state = COALESCE(:state, rc.state)
              AND rc.event_date >= CURRENT_DATE - INTERVAL '1 day'
        )
        ORDER BY sort_at DESC NULLS LAST
        LIMIT :lim
    """
    async with get_db() as db:
        rows = await _safe_execute(db, sql, {"state": state, "lim": limit})
    out: list[dict[str, Any]] = []
    for r in (rows or []):
        level = r.level if r.level in {"LOW", "LOW-MED", "MED", "HIGH"} else "LOW"
        out.append({
            "id": str(r.id),
            "text": r.text or "",
            "level": level,
            "posture": r.posture or "",
            "source": r.source,
            "cite_ids": [],   # cite-IDs map to article UUIDs; risk_calendar URLs aren't UUIDs
        })
    return out


# ── 5. Outlook ───────────────────────────────────────────────────────────


async def fetch_outlook(state: str | None, *, limit: int = 4) -> list[dict[str, Any]]:
    sql = """
        SELECT id, event_date, kind, title, description,
               source_url, risk_summary, risk_level
        FROM cm_risk_calendar
        WHERE state = COALESCE(:state, state)
          AND event_date >= CURRENT_DATE
        ORDER BY event_date ASC
        LIMIT :lim
    """
    async with get_db() as db:
        rows = await _safe_execute(db, sql, {"state": state, "lim": limit})
    out: list[dict[str, Any]] = []
    for r in (rows or []):
        when = r.event_date.strftime("%-d %b") if r.event_date else ""
        text_blob = r.description or r.risk_summary or r.title or ""
        out.append({
            "when": when,
            "event_date": _to_dt(r.event_date),
            "text": text_blob,
            "risk_level": r.risk_level,
            "source_url": r.source_url,
        })
    return out


# ── 6. Monitor (watched-entity volume vs baseline) ───────────────────────


async def fetch_monitor(state: str | None, *, limit: int = 6) -> list[dict[str, Any]]:
    """Volume of mentions per watched entity in last 24h vs 7-day baseline.
    Watched entities come from cm_political_handles (active opposition
    handles) plus a curated keyword list (Musi, Hydra, Group-1, etc.)."""
    sql = """
        WITH watched AS (
            SELECT DISTINCT
                LOWER(handle) AS label,
                'handle'::text AS kind
            FROM cm_political_handles
            WHERE state = COALESCE(:state, state)
              AND active = TRUE
            UNION ALL
            SELECT 'musi', 'topic'
            UNION ALL SELECT 'hydra', 'topic'
            UNION ALL SELECT 'group-1', 'topic'
            UNION ALL SELECT 'caste survey', 'topic'
            UNION ALL SELECT 'rythu bandhu', 'topic'
        ),
        recent AS (
            SELECT w.label,
                   COUNT(*) FILTER (WHERE a.collected_at > NOW() - INTERVAL '24 hours')                  AS now_n,
                   COUNT(*) FILTER (WHERE a.collected_at > NOW() - INTERVAL '8 days'
                                       AND a.collected_at <= NOW() - INTERVAL '1 day')                    AS base_n
            FROM watched w
            LEFT JOIN articles a
                   ON a.entities_extracted::text ILIKE '%' || w.label || '%'
                  AND a.collected_at > NOW() - INTERVAL '8 days'
            GROUP BY w.label
        )
        SELECT label, now_n, base_n
        FROM recent
        ORDER BY now_n DESC
        LIMIT :lim
    """
    async with get_db() as db:
        rows = await _safe_execute(db, sql, {"state": state, "lim": limit})
    out: list[dict[str, Any]] = []
    for r in (rows or []):
        now_n, base_n = (r.now_n or 0), (r.base_n or 0)
        baseline = (base_n / 7.0) if base_n else 0
        delta_pct = ((now_n - baseline) / baseline * 100) if baseline > 0 else (100.0 if now_n > 0 else 0.0)
        if delta_pct > 5:
            trend = "up"
        elif delta_pct < -5:
            trend = "down"
        else:
            trend = "flat"
        arrow = {"up": "↑", "down": "↓", "flat": "→"}[trend]
        status = f"{arrow} {'+' if delta_pct >= 0 else ''}{delta_pct:.0f}%" if baseline else f"new · {now_n}"
        out.append({
            "label": r.label,
            "status": status,
            "delta_pct": round(delta_pct, 1),
            "trend": trend,
        })
    return out


# ── 7. Live Pulse ────────────────────────────────────────────────────────


async def fetch_live_pulse(state: str | None) -> list[dict[str, Any]]:
    """Five live counters. Returned in display order."""
    sql_24h = """
        SELECT
            (SELECT COUNT(*) FROM articles a
             JOIN article_districts ad ON ad.article_id = a.id
             JOIN districts d ON d.id = ad.district_id
             WHERE a.collected_at > NOW() - INTERVAL '24 hours'
               AND d.state_code = COALESCE(:state, d.state_code))           AS mentions_24h,
            (SELECT AVG(value) FROM mv_district_sentiment_24h ms
             JOIN districts d ON d.id = ms.district_id
             WHERE d.state_code = COALESCE(:state, d.state_code))           AS sent_now,
            (SELECT COUNT(*) FROM cm_action_queue
             WHERE state_code = COALESCE(:state, state_code) AND status = 'active') AS alerts_active,
            (SELECT MAX(scored_at) FROM cm_stance_scores
             WHERE state = COALESCE(:state, state))                         AS last_stance_at
    """
    async with get_db() as db:
        row = (await db.execute(text(sql_24h), {"state": state})).first()

    mentions = int(row.mentions_24h or 0) if row else 0
    sent = float(row.sent_now or 0.0) if row else 0.0
    alerts = int(row.alerts_active or 0) if row else 0
    last = row.last_stance_at if row else None

    return [
        {
            "label": "TOTAL MENTIONS · 24H",
            "value": f"{mentions:,}",
            "delta": None,
            "trend": "flat",
        },
        {
            "label": "STATEWIDE SENTIMENT",
            "value": f"{sent:+.2f}",
            "delta": None,
            "trend": "down" if sent < -0.1 else ("up" if sent > 0.1 else "flat"),
        },
        {
            "label": "ACTIVE ALERTS",
            "value": str(alerts),
            "delta": None,
            "trend": "flat",
        },
        {
            "label": "LAST REFRESH",
            "value": _hhmm(last) if last else "—",
            "delta": "stance pipeline",
            "trend": "flat",
        },
    ]


# ── 8. Actions ───────────────────────────────────────────────────────────


async def fetch_actions(state: str | None, *, limit: int = 5) -> list[dict[str, Any]]:
    sql = """
        SELECT id, priority, text, deadline, source_type, cite_ids, expires_at
        FROM cm_action_queue
        WHERE state_code = COALESCE(:state, state_code)
          AND status = 'active'
          AND expires_at > NOW()
        ORDER BY
          CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 ELSE 2 END,
          generated_at DESC
        LIMIT :lim
    """
    async with get_db() as db:
        rows = await _safe_execute(db, sql, {"state": state, "lim": limit})
    return [
        {
            "id": str(r.id),
            "priority": r.priority,
            "text": r.text,
            "deadline": r.deadline,
            "source_type": r.source_type,
            "cite_ids": [str(u) for u in (r.cite_ids or [])],
            "expires_at": r.expires_at,
        }
        for r in (rows or [])
    ]


# ── 9. Analysis ──────────────────────────────────────────────────────────


async def fetch_analysis(state: str | None) -> dict[str, Any] | None:
    sql = """
        SELECT eyebrow, byline, headline, deck, paragraphs, pull_quote,
               endnote, cite_ids, published_at, model
        FROM cm_analysis_drafts
        WHERE state_code = COALESCE(:state, state_code)
          AND status = 'published'
        ORDER BY published_at DESC
        LIMIT 1
    """
    async with get_db() as db:
        rows = await _safe_execute(db, sql, {"state": state})
    rows_list = list(rows) if rows else []
    if not rows_list:
        return None
    r = rows_list[0]
    return {
        "eyebrow": r.eyebrow or "ANALYSIS",
        "byline": r.byline or "By the Strategy Desk",
        "headline": r.headline,
        "deck": r.deck,
        "paragraphs": list(r.paragraphs or []),
        "pull_quote": r.pull_quote,
        "endnote": r.endnote,
        "cite_ids": [str(u) for u in (r.cite_ids or [])],
        "published_at": r.published_at,
        "model": r.model,
    }


# ── 10. Atlas Layer ──────────────────────────────────────────────────────


_LAYER_MV: dict[str, str] = {
    "news-hotspot": "mv_district_news_volume_24h",
    "sentiment":    "mv_district_sentiment_24h",
    "acled":        "mv_district_acled_7d",
    "mandi":        "mv_district_mandi_volatility_30d",
    "welfare":      "mv_district_welfare_coverage",
    "power":        "mv_district_power_stress",
    "stability":    "mv_district_stability_composite",
}

_LAYER_SOURCE_HEALTH: dict[str, str] = {
    "mandi":   "mandi_agmarknet",
    "welfare": "welfare_coverage",
    "power":   "tgspdcl_power",
    "acled":   "acled_sink",
}


async def fetch_atlas_layer(state: str | None, layer_id: str) -> dict[str, Any]:
    mv = _LAYER_MV.get(layer_id)
    if mv is None:
        return {"layer_id": layer_id, "rows": [], "stale": True, "last_source_run_at": None}

    sql = f"""
        SELECT m.district_id, m.value, d.state_code
        FROM {mv} m
        JOIN districts d ON d.id = m.district_id
        WHERE d.state_code = COALESCE(:state, d.state_code)
        ORDER BY m.value DESC NULLS LAST
    """
    async with get_db() as db:
        rows = await _safe_execute(db, sql, {"state": state})
        last_run_at: datetime | None = None
        stale = False
        if (sh := _LAYER_SOURCE_HEALTH.get(layer_id)) is not None:
            health_row = (await db.execute(
                text("SELECT last_success_at FROM source_run_health WHERE source_id = :sid"),
                {"sid": sh},
            )).first()
            if health_row and health_row.last_success_at:
                last_run_at = health_row.last_success_at
                age = (datetime.now(timezone.utc) - last_run_at).total_seconds()
                stale = age > 24 * 3600   # any source quiet >24h is "stale"

    return {
        "layer_id": layer_id,
        "rows": [
            {"district_id": r.district_id, "value": float(r.value or 0.0)}
            for r in (rows or [])
        ],
        "stale": stale,
        "last_source_run_at": last_run_at,
    }


# ── 11. Ticker ───────────────────────────────────────────────────────────


async def fetch_ticker(state: str | None, *, limit: int = 7) -> list[dict[str, Any]]:
    sql = """
        (
            SELECT 'risk' AS source_kind,
                   rc.title AS text,
                   rc.source_url AS url,
                   (rc.event_date AT TIME ZONE 'UTC')::timestamptz AS at_utc
            FROM cm_risk_calendar rc
            WHERE rc.state = COALESCE(:state, rc.state)
              AND rc.event_date >= CURRENT_DATE - INTERVAL '1 day'
        )
        UNION ALL
        (
            SELECT 'acled' AS source_kind,
                   COALESCE(ae.notes, ae.event_type) AS text,
                   NULL::text AS url,
                   ae.event_date::timestamptz AS at_utc
            FROM acled_events ae
            WHERE ae.state_code = COALESCE(:state, ae.state_code)
              AND ae.event_date > CURRENT_DATE - INTERVAL '3 days'
        )
        UNION ALL
        (
            SELECT 'news' AS source_kind,
                   a.title AS text,
                   a.url,
                   a.published_at AS at_utc
            FROM articles a
            JOIN article_districts ad ON ad.article_id = a.id
            JOIN districts d ON d.id = ad.district_id
            WHERE d.state_code = COALESCE(:state, d.state_code)
              AND a.collected_at > NOW() - INTERVAL '6 hours'
              AND ad.is_primary = TRUE
        )
        ORDER BY at_utc DESC NULLS LAST
        LIMIT :lim
    """
    async with get_db() as db:
        rows = await _safe_execute(db, sql, {"state": state, "lim": limit})
    return [
        {
            "time": _hhmm(r.at_utc) if r.at_utc else "—",
            "text": r.text or "",
            "source_kind": r.source_kind,
            "url": r.url,
        }
        for r in (rows or [])
    ]


# ── 12. District Brief ───────────────────────────────────────────────────


async def fetch_district_brief(district_id: str) -> dict[str, Any] | None:
    """Aggregator endpoint for the modal. Joins district facts + recent
    news/ACLED counts. Returns None if the district doesn't exist."""
    async with get_db() as db:
        d = (await db.execute(
            text(
                "SELECT id, name, hq_city, state_code, centroid_lat, centroid_lon "
                "FROM districts WHERE id = :id"
            ),
            {"id": district_id},
        )).first()
        if not d:
            return None

        news_rows = await _safe_execute(db, """
            SELECT a.id, a.title, a.url, a.published_at, s.name AS source_name
            FROM article_districts ad
            JOIN articles a ON a.id = ad.article_id
            LEFT JOIN sources s ON s.id = a.source_id
            WHERE ad.district_id = :id
              AND a.collected_at > NOW() - INTERVAL '24 hours'
            ORDER BY a.published_at DESC NULLS LAST
            LIMIT 5
        """, {"id": district_id})

        acled_count_row = (await db.execute(
            text("SELECT COUNT(*) AS n FROM acled_events WHERE district_id = :id AND event_date > CURRENT_DATE - INTERVAL '7 days'"),
            {"id": district_id},
        )).first()

        stability_row = (await db.execute(
            text("SELECT value FROM mv_district_stability_composite WHERE district_id = :id"),
            {"id": district_id},
        )).first()

        mandi_rows = await _safe_execute(db, """
            SELECT market, commodity, modal_price, recorded_at
            FROM mandi_prices
            WHERE district_id = :id
              AND recorded_at > CURRENT_DATE - INTERVAL '14 days'
              AND modal_price IS NOT NULL
            ORDER BY recorded_at DESC
            LIMIT 5
        """, {"id": district_id})

        welfare_rows = await _safe_execute(db, """
            SELECT DISTINCT ON (scheme) scheme, coverage_pct, detail
            FROM welfare_coverage
            WHERE district_id = :id
            ORDER BY scheme, recorded_at DESC
            LIMIT 4
        """, {"id": district_id})

        power_row = (await db.execute(
            text("""
                SELECT demand_mw, supply_mw, deficit_mw, feeder_status
                FROM power_grid_status
                WHERE district_id = :id
                ORDER BY recorded_at DESC
                LIMIT 1
            """),
            {"id": district_id},
        )).first()

    return {
        "district_id": d.id,
        "name": d.name,
        "facts": {
            "hq_city": d.hq_city,
            "population": None,
            "area": None,
            "notable": None,
        },
        "stability_score": int(round(stability_row.value)) if stability_row and stability_row.value is not None else None,
        "one_liner": None,
        "news": [
            {
                "id": str(r.id),
                "title": r.title or "",
                "source": r.source_name or "Unknown",
                "age_label": _age_label(r.published_at),
                "url": r.url,
                "districts": [district_id],
                "published_at": r.published_at,
            }
            for r in (news_rows or [])
        ],
        "acled_count_7d": int(acled_count_row.n or 0) if acled_count_row else 0,
        "mandi_top_movers": [
            {
                "market": r.market,
                "commodity": r.commodity,
                "price": r.modal_price,
                "recorded_at": r.recorded_at,
            }
            for r in (mandi_rows or [])
        ],
        "welfare_summary": [
            {"scheme": r.scheme, "coverage_pct": float(r.coverage_pct or 0), "detail": r.detail}
            for r in (welfare_rows or [])
        ],
        "power_status": (
            {
                "demand_mw": power_row.demand_mw,
                "supply_mw": power_row.supply_mw,
                "deficit_mw": power_row.deficit_mw,
                "feeder_status": power_row.feeder_status,
            }
            if power_row else None
        ),
        "counter_narrative": None,        # filled in Phase 4 from cm_counter_narratives
    }


# ── helpers ──────────────────────────────────────────────────────────────


def _age_label(at: datetime | None) -> str:
    if not at:
        return ""
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    delta_s = (datetime.now(timezone.utc) - at).total_seconds()
    if delta_s < 60:
        return f"{int(delta_s)}s"
    if delta_s < 3600:
        return f"{int(delta_s // 60)}m"
    if delta_s < 86400:
        return f"{int(delta_s // 3600)}h"
    return f"{int(delta_s // 86400)}d"


def _hhmm(at: datetime | None) -> str:
    if not at:
        return "—"
    return at.strftime("%H:%M")


def _to_dt(d) -> datetime | None:
    if d is None:
        return None
    if isinstance(d, datetime):
        return d
    return datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc)


def _format_reach(upvotes: int | None, followers: int | None) -> str | None:
    if not upvotes and not followers:
        return None
    parts: list[str] = []
    if upvotes:
        parts.append(f"{upvotes} eng")
    if followers:
        parts.append(f"{followers // 1000}k followers" if followers >= 1000 else f"{followers} followers")
    return " · ".join(parts)


__all__ = [
    "fetch_actions",
    "fetch_analysis",
    "fetch_atlas_layer",
    "fetch_district_brief",
    "fetch_lead_headlines",
    "fetch_live_pulse",
    "fetch_monitor",
    "fetch_news_on_chair",
    "fetch_opposition_watch",
    "fetch_outlook",
    "fetch_threats",
    "fetch_ticker",
]
