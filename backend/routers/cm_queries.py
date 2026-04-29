"""
SQL helpers for the CM Page router.

Each helper returns plain Python dicts/lists so the router maps them into
Pydantic models without a second translation layer. Helpers are intentionally
defensive: a missing table or empty result returns an empty payload rather
than raising — the CM Page must never blank a section because of an unrun
migration or an empty cm_* table.

State scoping convention:
    - "TG" / "AP" — restricts to articles/posts whose geo_primary contains
      the state name OR cm_* rows tagged with that state.
    - None / "" — no scoping (admin / debug only).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError, InternalError

from backend.database import get_db

logger = logging.getLogger(__name__)


_STATE_GEO_NEEDLE: dict[str, list[str]] = {
    "TG": ["telangana", "hyderabad", "tg"],
    "AP": ["andhra pradesh", "andhra", "vijayawada", "visakhapatnam", "amaravati", "ap"],
}


def _state_like_clause(col: str, state: str | None) -> tuple[str, dict[str, Any]]:
    """Build an OR ... ILIKE clause matching common state geo strings.
    Returns ('TRUE', {}) if state is empty so the caller can compose freely."""
    if not state:
        return "TRUE", {}
    needles = _STATE_GEO_NEEDLE.get(state, [state.lower()])
    parts = []
    params: dict[str, Any] = {}
    for i, n in enumerate(needles):
        params[f"_geo{i}"] = f"%{n}%"
        parts.append(f"LOWER({col}) LIKE :_geo{i}")
    return "(" + " OR ".join(parts) + ")", params


async def _safe_execute(db, sql: str, params: dict[str, Any] | None = None):
    """Execute SQL but treat 'undefined table / column' as empty result —
    this lets the router work before all migrations are applied or before
    any cm_* tasks have run."""
    try:
        return await db.execute(text(sql), params or {})
    except (ProgrammingError, InternalError) as exc:
        msg = str(exc).lower()
        if "does not exist" in msg or "undefined" in msg:
            logger.info("cm query skipped (missing relation): %s", msg.split(":")[0][:120])
            return None
        raise


# ── User profile state lookup ───────────────────────────────────────────

async def resolve_state(user_id: str, override: str | None) -> str | None:
    """Return the state code to scope on. Explicit override wins; else
    user_profiles.geo_primary; else None."""
    if override:
        return override.upper()
    async with get_db() as db:
        row = (
            await db.execute(
                text("SELECT geo_primary FROM user_profiles WHERE user_id = :uid"),
                {"uid": user_id},
            )
        ).first()
    if not row or not row.geo_primary:
        return None
    geo = (row.geo_primary or "").strip().lower()
    if "telangana" in geo or geo == "tg":
        return "TG"
    if "andhra" in geo or geo == "ap":
        return "AP"
    return None


# ── I — Pulse ───────────────────────────────────────────────────────────

async def fetch_pulse(state: str | None, window: str) -> dict[str, Any]:
    """Aggregate sentiment from social_posts + articles. Window = '24h' / '7d' / '30d'."""
    delta_map = {"24h": "24 hours", "7d": "7 days", "30d": "30 days"}
    window_iv = delta_map.get(window, "24 hours")
    # window_iv is from a closed set above — safe to inline as a literal.
    # Bind-parameterising `interval '{window_iv}'` produces `interval $1` which
    # asyncpg cannot type-infer, leading to "syntax error at or near $1".
    geo_sql, geo_params = _state_like_clause("a.geo_primary", state)

    # Sentiment sources:
    #   articles → derived from cm_stance_scores when populated; until then
    #              the article side is empty and only social_posts contributes.
    #   social_posts.sentiment_score is already a [-1,+1] real today.
    overall_sql = f"""
        WITH article_sent AS (
            SELECT
                (CASE s.stance
                    WHEN 'opposition_attack' THEN -1.0
                    WHEN 'ruling_supportive' THEN  1.0
                    ELSE 0.0
                END * COALESCE(s.confidence, 0.0))::float AS s,
                a.published_at AS at
            FROM articles a
            JOIN cm_stance_scores s ON s.source_kind = 'article' AND s.source_id = a.id
            WHERE a.published_at > now() - interval '{window_iv}'
              AND {geo_sql}
        ),
        social_sent AS (
            SELECT
                COALESCE(sp.sentiment_score, 0)::float AS s,
                sp.collected_at AS at
            FROM social_posts sp
            WHERE sp.collected_at > now() - interval '{window_iv}'
              AND sp.sentiment_score IS NOT NULL
        )
        SELECT
            AVG(s) AS score_window,
            COUNT(*) AS n_window
        FROM (SELECT s, at FROM article_sent UNION ALL SELECT s, at FROM social_sent) u
    """
    delta_sql = f"""
        WITH article_sent AS (
            SELECT
                (CASE s.stance
                    WHEN 'opposition_attack' THEN -1.0
                    WHEN 'ruling_supportive' THEN  1.0
                    ELSE 0.0
                END * COALESCE(s.confidence, 0.0))::float AS s,
                a.published_at AS at
            FROM articles a
            JOIN cm_stance_scores s ON s.source_kind = 'article' AND s.source_id = a.id
            WHERE a.published_at > now() - interval '7 days'
              AND {geo_sql}
        ),
        social_sent AS (
            SELECT COALESCE(sp.sentiment_score, 0)::float AS s, sp.collected_at AS at
            FROM social_posts sp
            WHERE sp.collected_at > now() - interval '7 days'
              AND sp.sentiment_score IS NOT NULL
        )
        SELECT AVG(s) AS s7d FROM (SELECT s,at FROM article_sent UNION ALL SELECT s,at FROM social_sent) u
    """

    async with get_db() as db:
        params: dict[str, Any] = dict(geo_params)
        ovr_row = await _safe_execute(db, overall_sql, params)
        if ovr_row is None:
            return _empty_pulse(state, window)
        ovr = ovr_row.first()
        d_row = await _safe_execute(db, delta_sql, geo_params)
        s7d = d_row.first().s7d if d_row else None

        topic_sql = f"""
            SELECT COALESCE(a.topic_category, 'unknown') AS topic,
                   AVG(
                       CASE s.stance
                           WHEN 'opposition_attack' THEN -1.0
                           WHEN 'ruling_supportive' THEN  1.0
                           ELSE 0.0
                       END * COALESCE(s.confidence, 0.0)
                   )::float AS s,
                   COUNT(*) AS n
            FROM articles a
            LEFT JOIN cm_stance_scores s
              ON s.source_kind = 'article' AND s.source_id = a.id
            WHERE a.published_at > now() - interval '{window_iv}'
              AND {geo_sql}
            GROUP BY 1
            ORDER BY n DESC
            LIMIT 10
        """
        topics_row = await _safe_execute(db, topic_sql, params)
        topic_rows = topics_row.all() if topics_row else []

        region_sql = f"""
            SELECT
                CASE
                    WHEN LOWER(COALESCE(a.geo_primary,'')) LIKE '%hyderabad%' THEN 'Hyderabad'
                    WHEN LOWER(COALESCE(a.geo_primary,'')) LIKE '%vishakha%' OR LOWER(COALESCE(a.geo_primary,'')) LIKE '%vizag%' THEN 'Visakhapatnam'
                    WHEN LOWER(COALESCE(a.geo_primary,'')) LIKE '%vijayawada%' THEN 'Vijayawada'
                    WHEN LOWER(COALESCE(a.geo_primary,'')) LIKE '%warangal%' THEN 'Warangal'
                    WHEN LOWER(COALESCE(a.geo_primary,'')) LIKE '%tirupati%' THEN 'Tirupati'
                    ELSE 'Other'
                END AS region,
                AVG(
                    CASE s.stance
                        WHEN 'opposition_attack' THEN -1.0
                        WHEN 'ruling_supportive' THEN  1.0
                        ELSE 0.0
                    END * COALESCE(s.confidence, 0.0)
                )::float AS s,
                COUNT(*) AS n
            FROM articles a
            LEFT JOIN cm_stance_scores s
              ON s.source_kind = 'article' AND s.source_id = a.id
            WHERE a.published_at > now() - interval '{window_iv}'
              AND a.geo_primary IS NOT NULL
            GROUP BY 1
            ORDER BY n DESC
            LIMIT 8
        """
        regions_row = await _safe_execute(db, region_sql, {})
        region_rows = regions_row.all() if regions_row else []

    score_now = float(ovr.score_window or 0.0)
    n_window = int(ovr.n_window or 0)
    delta_7d = float((s7d or 0.0) - score_now) * -1.0  # Δ vs week
    return {
        "state": state,
        "window": window,
        "overall": {
            "topic": "overall",
            "score": score_now,
            "delta_7d": delta_7d,
            "n": n_window,
        },
        "by_topic": [
            {"topic": r.topic or "unknown", "score": float(r.s or 0), "delta_7d": 0.0, "n": int(r.n or 0)}
            for r in topic_rows
        ],
        "by_region": [
            {"region": r.region, "score": float(r.s or 0), "delta_7d": 0.0, "n": int(r.n or 0)}
            for r in region_rows
        ],
        "sample_size": n_window,
        "computed_at": datetime.utcnow(),
    }


def _empty_pulse(state: str | None, window: str) -> dict[str, Any]:
    return {
        "state": state,
        "window": window,
        "overall": {"topic": "overall", "score": 0.0, "delta_7d": 0.0, "n": 0},
        "by_topic": [],
        "by_region": [],
        "sample_size": 0,
        "computed_at": datetime.utcnow(),
    }


# ── II — Issues ─────────────────────────────────────────────────────────

async def fetch_issues(state: str | None, limit: int = 8) -> list[dict[str, Any]]:
    issue_sql = """
        SELECT id, label, slug, intensity, last_seen, ruling_stance_summary,
               opposition_stance_summary, neutral_summary, volume_24h, volume_7d, trajectory
        FROM cm_issues
        WHERE (CAST(:state AS text) IS NULL OR state = :state)
        ORDER BY intensity DESC NULLS LAST, last_seen DESC
        LIMIT :limit
    """
    async with get_db() as db:
        rows_res = await _safe_execute(db, issue_sql, {"state": state, "limit": limit})
        if rows_res is None:
            return []
        rows = rows_res.all()
        if not rows:
            return []
        ids = [r.id for r in rows]
        triad_sql = """
            SELECT cie.issue_id,
                   cie.side,
                   COUNT(*) AS n,
                   AVG(CASE s.stance
                       WHEN 'opposition_attack' THEN -1.0
                       WHEN 'ruling_supportive' THEN  1.0
                       WHEN 'neutral_factual'   THEN  0.0
                       ELSE 0.0
                   END * COALESCE(s.confidence, 0.0))::float AS stance_score
            FROM cm_issue_evidence cie
            LEFT JOIN cm_stance_scores s
              ON s.source_id = cie.source_id
             AND s.source_kind = cie.source_kind
            WHERE cie.issue_id = ANY(:ids)
            GROUP BY cie.issue_id, cie.side
        """
        triad_res = await _safe_execute(db, triad_sql, {"ids": ids})
        triad_rows = triad_res.all() if triad_res else []
        triad_by_issue: dict[int, dict[str, dict[str, float]]] = {}
        for tr in triad_rows:
            triad_by_issue.setdefault(tr.issue_id, {})[(tr.side or "neutral")] = {
                "n": int(tr.n or 0),
                "score": float(tr.stance_score or 0.0),
            }

        quotes_sql = """
            SELECT q.issue_id, q.speaker, q.party, q.role, q.quote, q.source_url,
                   q.source_kind, q.extracted_at
            FROM cm_spokesperson_quotes q
            WHERE q.issue_id = ANY(:ids)
            ORDER BY q.extracted_at DESC
            LIMIT 200
        """
        quotes_res = await _safe_execute(db, quotes_sql, {"ids": ids})
        quotes_rows = quotes_res.all() if quotes_res else []
        quotes_by_issue: dict[int, list[dict]] = {}
        for q in quotes_rows:
            quotes_by_issue.setdefault(q.issue_id, []).append(
                {
                    "speaker": q.speaker,
                    "party": q.party,
                    "role": q.role,
                    "quote": q.quote,
                    "source_url": q.source_url,
                    "source_kind": q.source_kind,
                    "captured_at": q.extracted_at,
                }
            )

    out: list[dict[str, Any]] = []
    for r in rows:
        triads = triad_by_issue.get(r.id, {})
        ruling = triads.get("ruling", {"n": 0, "score": 0.0})
        opp = triads.get("opposition", {"n": 0, "score": 0.0})
        neu = triads.get("neutral", {"n": 0, "score": 0.0})
        out.append(
            {
                "id": r.id,
                "label": r.label,
                "slug": r.slug,
                "intensity": float(r.intensity or 0.0),
                "intensity_delta_24h": 0.0,
                "last_mention_at": r.last_seen,
                "ruling_summary": r.ruling_stance_summary,
                "opposition_summary": r.opposition_stance_summary,
                "neutral_summary": r.neutral_summary,
                "stances": {
                    "ruling": ruling["score"],
                    "opposition": opp["score"],
                    "neutral": neu["score"],
                    "n_ruling": ruling["n"],
                    "n_opposition": opp["n"],
                    "n_neutral": neu["n"],
                },
                "party_stances": [],
                "top_quotes": (quotes_by_issue.get(r.id) or [])[:3],
                "evidence_count": ruling["n"] + opp["n"] + neu["n"],
                "trajectory": r.trajectory or "unknown",
            }
        )
    return out


# ── III — Silence ───────────────────────────────────────────────────────

async def fetch_silence(state: str | None, limit: int = 5) -> list[dict[str, Any]]:
    """Issues with high opposition/public volume in the last 7 days but
    zero ruling-tagged statements in the last 6 hours. Falls back to
    existing social_events.SILENCE rows when cm_stance_scores is empty."""
    primary_sql = """
        WITH active AS (
            SELECT i.id, i.label, i.last_seen,
                   COUNT(DISTINCT cie.source_id) FILTER (WHERE cie.side = 'opposition') AS opp_vol,
                   COUNT(DISTINCT cie.source_id) AS public_vol_7d
            FROM cm_issues i
            LEFT JOIN cm_issue_evidence cie ON cie.issue_id = i.id
            WHERE (CAST(:state AS text) IS NULL OR i.state = :state)
              AND i.last_seen > now() - interval '7 days'
            GROUP BY i.id, i.label, i.last_seen
        ),
        ruling_hits AS (
            SELECT cie.issue_id,
                   MAX(s.scored_at) AS last_ruling_at,
                   COUNT(*) AS n
            FROM cm_issue_evidence cie
            JOIN cm_stance_scores s
              ON s.source_id = cie.source_id AND s.source_kind = cie.source_kind
            WHERE s.party_kind = 'ruling'
              AND s.scored_at > now() - interval '7 days'
            GROUP BY cie.issue_id
        )
        SELECT a.id, a.label, a.opp_vol, a.public_vol_7d, COALESCE(rh.n, 0) AS govt_vol,
               rh.last_ruling_at,
               EXTRACT(EPOCH FROM (now() - COALESCE(rh.last_ruling_at, now() - interval '7 days')))/3600.0 AS age_hours
        FROM active a
        LEFT JOIN ruling_hits rh ON rh.issue_id = a.id
        WHERE COALESCE(rh.n, 0) = 0 AND a.opp_vol >= 10
        ORDER BY a.opp_vol DESC
        LIMIT :limit
    """
    fallback_sql = """
        SELECT subject AS label, detected_at, body, sources
        FROM social_events
        WHERE event_type = 'SILENCE'
          AND detected_at > now() - interval '7 days'
        ORDER BY detected_at DESC
        LIMIT :limit
    """
    async with get_db() as db:
        primary = await _safe_execute(db, primary_sql, {"state": state, "limit": limit})
        rows = primary.all() if primary else []
        if rows:
            out: list[dict[str, Any]] = []
            for r in rows:
                age_h = float(r.age_hours or 0.0)
                severity = "watch" if age_h < 12 else "warn" if age_h < 24 else "critical"
                out.append(
                    {
                        "issue_id": r.id,
                        "label": r.label,
                        "started_at": r.last_ruling_at,
                        "age_hours": age_h,
                        "public_volume_7d": int(r.public_vol_7d or 0),
                        "govt_mentions_7d": int(r.govt_vol or 0),
                        "days_since_govt_statement": age_h / 24.0,
                        "ministers_named": [],
                        "severity": severity,
                        "sample_evidence": [],
                    }
                )
            return out

        fb = await _safe_execute(db, fallback_sql, {"limit": limit})
        fb_rows = fb.all() if fb else []
        return [
            {
                "issue_id": None,
                "label": r.label,
                "started_at": r.detected_at,
                "age_hours": 0.0,
                "public_volume_7d": 0,
                "govt_mentions_7d": 0,
                "days_since_govt_statement": None,
                "ministers_named": [],
                "severity": "watch",
                "sample_evidence": [],
            }
            for r in fb_rows
        ]


# ── IV — Spokespersons ──────────────────────────────────────────────────

async def fetch_spokespersons(
    state: str | None,
    mode: str,
    limit: int = 8,
) -> list[dict[str, Any]]:
    sign = -1.0 if mode == "attackers" else 1.0
    sql = """
        SELECT speaker, party, mentions_24h, mentions_7d,
               avg_sentiment_24h, avg_sentiment_7d
        FROM mv_cm_voice_share
        WHERE (CAST(:state AS text) IS NULL OR state = :state)
          AND mentions_24h IS NOT NULL
          AND mentions_24h > 0
        ORDER BY (mentions_24h * (1 + :sign * COALESCE(avg_sentiment_24h, 0))) DESC
        LIMIT :limit
    """
    async with get_db() as db:
        res = await _safe_execute(db, sql, {"state": state, "sign": sign, "limit": limit})
        if res is None:
            return []
        rows = res.all()

    out: list[dict[str, Any]] = []
    for r in rows:
        n24 = int(r.mentions_24h or 0)
        n7 = max(int(r.mentions_7d or 0), 1)
        delta = (n24 * 7.0 - n7) / float(n7) * 100.0
        sent = float(r.avg_sentiment_24h or 0.0)
        score = min(100.0, n24 * (1 + sign * sent) * 5.0)
        out.append(
            {
                "speaker": r.speaker,
                "party": r.party,
                "role": None,
                "score": score,
                "mentions_24h": n24,
                "mentions_7d": int(r.mentions_7d or 0),
                "delta_pct": delta,
                "avg_sentiment": sent,
                "on_message_rate": None if mode == "attackers" else max(0.0, sent + 1.0) * 50.0,
                "top_topics": [],
                "latest_quote": None,
            }
        )
    return out


# ── V — Dissent ────────────────────────────────────────────────────────

async def fetch_dissent(state: str | None, confidence_floor: float = 0.7) -> dict[str, list[dict[str, Any]]]:
    sql = """
        SELECT id, coalition, party, speakers, summary, severity, confidence,
               evidence_urls, issue_id, detected_at
        FROM cm_dissent_signals
        WHERE (CAST(:state AS text) IS NULL OR state = :state)
          AND confidence >= :floor
          AND detected_at > now() - interval '14 days'
        ORDER BY detected_at DESC
        LIMIT 16
    """
    async with get_db() as db:
        res = await _safe_execute(db, sql, {"state": state, "floor": confidence_floor})
        if res is None:
            return {"ruling": [], "opposition": []}
        rows = res.all()
    by_coalition: dict[str, list[dict[str, Any]]] = {"ruling": [], "opposition": []}
    for r in rows:
        rec = {
            "id": r.id,
            "coalition": r.coalition,
            "party": r.party,
            "faction": None,
            "headline": r.summary,
            "severity": r.severity,
            "confidence": float(r.confidence or 0.0),
            "members": [
                {"speaker": s, "party": r.party, "quote": {"speaker": s, "quote": ""}}
                for s in (r.speakers or [])[:4]
            ],
            "issue_id": r.issue_id,
            "evidence_urls": list(r.evidence_urls or []),
            "detected_at": r.detected_at,
        }
        by_coalition[r.coalition].append(rec)
    return by_coalition


# ── VI — Trajectory ─────────────────────────────────────────────────────

async def fetch_trajectory(state: str | None, days: int = 7) -> list[dict[str, Any]]:
    # `days` is integer-coerced and inlined as a literal — bind parameters
    # with the colon-name syntax (`:days`) collide with SQLAlchemy's bind
    # token when the placeholder appears inside a string literal like
    # `interval ':days days'`. Inlining is safe because we cast through int().
    days_int = max(3, min(int(days), 30))
    sql = f"""
        WITH issues AS (
            SELECT id, label
            FROM cm_issues
            WHERE (CAST(:state AS text) IS NULL OR state = :state)
              AND last_seen > now() - interval '{days_int} days'
            ORDER BY intensity DESC NULLS LAST
            LIMIT 12
        ),
        hourly AS (
            SELECT issue_id,
                   date_trunc('day', hour) AS d,
                   SUM(volume) AS vol,
                   AVG(avg_stance) AS sent
            FROM mv_cm_issue_hourly
            WHERE issue_id IN (SELECT id FROM issues)
            GROUP BY issue_id, date_trunc('day', hour)
        )
        SELECT i.id, i.label,
               array_agg(COALESCE(h.vol, 0)::int ORDER BY h.d ASC) AS series_v,
               array_agg(COALESCE(h.sent, 0)::float ORDER BY h.d ASC) AS series_s
        FROM issues i
        LEFT JOIN hourly h ON h.issue_id = i.id
        GROUP BY i.id, i.label
    """
    async with get_db() as db:
        res = await _safe_execute(db, sql, {"state": state})
        if res is None:
            return []
        rows = res.all()

    out: list[dict[str, Any]] = []
    for r in rows:
        series_v = list(r.series_v or [])
        series_s = list(r.series_s or [])
        if len(series_v) >= 2:
            slope = (series_v[-1] - series_v[0]) / max(len(series_v) - 1, 1)
            delta_24h = float(series_v[-1] - (series_v[-2] if len(series_v) >= 2 else 0))
        else:
            slope = 0.0
            delta_24h = 0.0
        if slope > 1.5:
            classification = "intensifying"
        elif slope < -1.5:
            classification = "fading"
        else:
            classification = "steady"
        out.append(
            {
                "issue_id": r.id,
                "label": r.label,
                "series_volume": [int(v) for v in series_v],
                "series_sentiment": [float(s) for s in series_s],
                "classification": classification,
                "slope": float(slope),
                "delta_24h": delta_24h,
            }
        )
    return out


# ── VII — Heatmap ───────────────────────────────────────────────────────

async def fetch_heatmap(state: str | None) -> list[dict[str, Any]]:
    sql = """
        SELECT constituency_code, name, state, volume, mood_proxy
        FROM mv_cm_constituency_daily
        WHERE (CAST(:state AS text) IS NULL OR state = :state)
        ORDER BY constituency_code
    """
    async with get_db() as db:
        res = await _safe_execute(db, sql, {"state": state})
        if res is None:
            return []
        rows = res.all()
    return [
        {
            "constituency_code": r.constituency_code,
            "constituency_name": r.name,
            "state": r.state,
            "score": float(r.mood_proxy or 0.0),
            "volume": int(r.volume or 0),
            "top_issue_ids": [],
        }
        for r in rows
    ]


# ── VIII — Promises ─────────────────────────────────────────────────────

async def fetch_promises(state: str | None, limit: int = 12) -> list[dict[str, Any]]:
    sql = """
        SELECT id, pledge_text, pledge_short, owner_party, deadline, status,
               status_confidence, last_status_change, exploitation_index,
               source_url, last_evidence_url
        FROM cm_promises
        WHERE (CAST(:state AS text) IS NULL OR state = :state)
        ORDER BY exploitation_index DESC, last_status_change DESC
        LIMIT :limit
    """
    async with get_db() as db:
        res = await _safe_execute(db, sql, {"state": state, "limit": limit})
        if res is None:
            return []
        rows = res.all()
    return [
        {
            "id": r.id,
            "pledge_text": r.pledge_text,
            "pledge_short": r.pledge_short,
            "owner_party": r.owner_party,
            "deadline": r.deadline,
            "status": r.status,
            "status_confidence": (
                float(r.status_confidence) if r.status_confidence is not None else None
            ),
            "last_status_change": r.last_status_change,
            "exploitation_index": float(r.exploitation_index or 0.0),
            "source_url": r.source_url,
            "last_evidence_url": r.last_evidence_url,
        }
        for r in rows
    ]


# ── IX — Counter-narratives ─────────────────────────────────────────────

async def fetch_counter_narratives(state: str | None, limit: int = 3) -> list[dict[str, Any]]:
    sql = """
        SELECT cn.id, cn.issue_id, i.label, cn.talking_points,
               cn.grounding_doc_ids, cn.grounding_kinds, cn.model, cn.generated_at
        FROM cm_counter_narratives cn
        JOIN cm_issues i ON i.id = cn.issue_id
        WHERE (CAST(:state AS text) IS NULL OR cn.state = :state)
          AND cn.rejected = FALSE
          AND cn.generated_at > now() - interval '36 hours'
        ORDER BY cn.generated_at DESC
        LIMIT :limit
    """
    async with get_db() as db:
        res = await _safe_execute(db, sql, {"state": state, "limit": limit})
        if res is None:
            return []
        rows = res.all()
    out: list[dict[str, Any]] = []
    for r in rows:
        tp_raw = r.talking_points or []
        if isinstance(tp_raw, str):
            import json as _json

            try:
                tp_raw = _json.loads(tp_raw)
            except Exception:
                tp_raw = []
        out.append(
            {
                "issue_id": r.issue_id,
                "issue_label": r.label,
                "talking_points": [
                    {"text": tp.get("text", ""), "cites": list(tp.get("cites", []))}
                    for tp in (tp_raw or [])
                    if isinstance(tp, dict)
                ],
                "grounding_doc_ids": list(r.grounding_doc_ids or []),
                "grounding_kinds": list(r.grounding_kinds or []),
                "generated_at": r.generated_at,
                "model": r.model,
                "is_draft": True,
            }
        )
    return out


# ── X — Risk window ─────────────────────────────────────────────────────

async def fetch_risk_window(state: str | None, days: int = 7) -> list[dict[str, Any]]:
    sql = """
        SELECT id, event_date, state, kind, title, description, risk_summary,
               risk_level, source_url
        FROM cm_risk_calendar
        WHERE event_date >= CURRENT_DATE
          AND event_date < CURRENT_DATE + (:days || ' days')::interval
          AND (CAST(:state AS text) IS NULL OR state IS NULL OR state = :state)
        ORDER BY event_date ASC, risk_level DESC
        LIMIT 100
    """
    async with get_db() as db:
        res = await _safe_execute(db, sql, {"state": state, "days": str(int(days))})
        if res is None:
            return []
        rows = res.all()
    return [
        {
            "id": r.id,
            "event_date": r.event_date,
            "state": r.state,
            "kind": r.kind,
            "title": r.title,
            "description": r.description,
            "risk_summary": r.risk_summary,
            "risk_level": r.risk_level,
            "source_url": r.source_url,
        }
        for r in rows
    ]


# ── XI — Quotes (Verbatim) ──────────────────────────────────────────────

async def fetch_quotes(state: str | None, limit: int = 9) -> list[dict[str, Any]]:
    sql = """
        SELECT id, speaker, party, role, quote, quote_lang, issue_id,
               sentiment, stance, source_url, source_kind, extracted_at
        FROM cm_spokesperson_quotes
        WHERE (CAST(:state AS text) IS NULL OR state = :state)
          AND extracted_at > now() - interval '36 hours'
        ORDER BY ABS(COALESCE(sentiment, 0)) DESC NULLS LAST, extracted_at DESC
        LIMIT :limit
    """
    async with get_db() as db:
        res = await _safe_execute(db, sql, {"state": state, "limit": limit})
        if res is None:
            return []
        rows = res.all()
    return [
        {
            "id": r.id,
            "speaker": r.speaker,
            "party": r.party,
            "role": r.role,
            "quote": r.quote,
            "quote_lang": r.quote_lang,
            "issue_id": r.issue_id,
            "sentiment": (float(r.sentiment) if r.sentiment is not None else None),
            "stance": r.stance,
            "source_url": r.source_url,
            "source_kind": r.source_kind,
            "captured_at": r.extracted_at,
        }
        for r in rows
    ]


# ── XII — Voice share ──────────────────────────────────────────────────

async def fetch_voice_share(state: str | None, limit: int = 8) -> list[dict[str, Any]]:
    sql = """
        WITH base AS (
            SELECT speaker, party, mentions_24h, mentions_7d
            FROM mv_cm_voice_share
            WHERE (CAST(:state AS text) IS NULL OR state = :state)
        ),
        totals AS (
            SELECT NULLIF(SUM(mentions_24h), 0)::float AS t24,
                   NULLIF(SUM(mentions_7d), 0)::float AS t7
            FROM base
        )
        SELECT b.speaker, b.party,
               (b.mentions_24h::float / t.t24) * 100 AS share_24h,
               (b.mentions_7d::float / t.t7)   * 100 AS share_7d,
               b.mentions_24h, b.mentions_7d
        FROM base b CROSS JOIN totals t
        WHERE b.mentions_24h > 0 OR b.mentions_7d > 0
        ORDER BY ABS((b.mentions_24h::float / NULLIF(t.t24,0)) - (b.mentions_7d::float / NULLIF(t.t7,0))) DESC
        LIMIT :limit
    """
    async with get_db() as db:
        res = await _safe_execute(db, sql, {"state": state, "limit": limit})
        if res is None:
            return []
        rows = res.all()
    out: list[dict[str, Any]] = []
    for r in rows:
        s24 = float(r.share_24h or 0.0)
        s7 = float(r.share_7d or 0.0)
        out.append(
            {
                "speaker": r.speaker,
                "party": r.party,
                "share_24h_pct": s24,
                "share_7d_pct": s7,
                "delta_pct": s24 - s7,
                "mentions_24h": int(r.mentions_24h or 0),
                "mentions_7d": int(r.mentions_7d or 0),
            }
        )
    return out


# ── XIII / XIV — Divergence ────────────────────────────────────────────

async def fetch_language_divergence(state: str | None) -> list[dict[str, Any]]:
    """Per topic, compare sentiment in English vs Telugu (and Hindi when present)."""
    geo_sql, geo_params = _state_like_clause("a.geo_primary", state)
    sql = f"""
        SELECT COALESCE(a.topic_category, 'general') AS topic,
               COALESCE(a.language_detected, 'en')   AS lang,
               AVG(
                   CASE s.stance
                       WHEN 'opposition_attack' THEN -1.0
                       WHEN 'ruling_supportive' THEN  1.0
                       ELSE 0.0
                   END * COALESCE(s.confidence, 0.0)
               )::float AS score,
               COUNT(*) AS n
        FROM articles a
        LEFT JOIN cm_stance_scores s
          ON s.source_kind = 'article' AND s.source_id = a.id
        WHERE a.published_at > now() - interval '7 days'
          AND {geo_sql}
        GROUP BY 1, 2
        HAVING COUNT(*) >= 4
    """
    async with get_db() as db:
        res = await _safe_execute(db, sql, geo_params)
        if res is None:
            return []
        rows = res.all()
    by_topic: dict[str, dict[str, dict[str, float]]] = {}
    for r in rows:
        by_topic.setdefault(r.topic, {})[r.lang] = {"score": float(r.score), "n": int(r.n)}
    out: list[dict[str, Any]] = []
    for topic, langs in by_topic.items():
        if "en" not in langs or len(langs) < 2:
            continue
        en_score = langs["en"]["score"]
        for other_lang, data in langs.items():
            if other_lang == "en":
                continue
            delta = abs(en_score - data["score"])
            out.append(
                {
                    "topic": topic,
                    "side_a_label": f"english_{topic}",
                    "side_b_label": f"{other_lang}_{topic}",
                    "score_a": en_score,
                    "score_b": data["score"],
                    "delta": delta,
                    "flagged": delta > 0.4,
                    "sample_a": [],
                    "sample_b": [],
                }
            )
    out.sort(key=lambda x: x["delta"], reverse=True)
    return out[:6]


async def fetch_medium_divergence(state: str | None) -> list[dict[str, Any]]:
    """Newspaper editorial sentiment vs social discourse sentiment per topic."""
    geo_sql_n, gp_n = _state_like_clause("nc.geo_primary", state)
    # newspaper_clippings.sentiment is TEXT ('positive' / 'negative' /
    # 'neutral' / NULL). We map to [-1, +1] in SQL so the divergence row
    # is comparable to social_posts.sentiment_score (already a real).
    np_sql = f"""
        SELECT COALESCE(nc.topic_category, 'general') AS topic,
               AVG(
                   CASE LOWER(COALESCE(nc.sentiment, ''))
                       WHEN 'positive' THEN  1.0
                       WHEN 'negative' THEN -1.0
                       WHEN 'neutral'  THEN  0.0
                       ELSE 0.0
                   END
               )::float AS score,
               COUNT(*) AS n
        FROM newspaper_clippings nc
        WHERE nc.edition_date > CURRENT_DATE - 7
          AND {geo_sql_n}
        GROUP BY 1
        HAVING COUNT(*) >= 3
    """
    sp_sql = """
        SELECT COALESCE(sp.topic_category, 'general') AS topic,
               AVG(COALESCE(sp.sentiment_score, 0))::float AS score,
               COUNT(*) AS n
        FROM social_posts sp
        WHERE sp.collected_at > now() - interval '7 days'
        GROUP BY 1
        HAVING COUNT(*) >= 3
    """
    # Use a fresh DB session per query so that an error in one (e.g. a
    # missing optional column) doesn't poison the second query's
    # transaction with InFailedSQLTransactionError.
    async with get_db() as db:
        np_res = await _safe_execute(db, np_sql, gp_n)
        np_rows = np_res.all() if np_res else []
    async with get_db() as db:
        sp_res = await _safe_execute(db, sp_sql, {})
        sp_rows = sp_res.all() if sp_res else []
    by_topic_np = {r.topic: float(r.score) for r in np_rows}
    by_topic_sp = {r.topic: float(r.score) for r in sp_rows}
    out: list[dict[str, Any]] = []
    for topic in set(by_topic_np) & set(by_topic_sp):
        delta = abs(by_topic_np[topic] - by_topic_sp[topic])
        out.append(
            {
                "topic": topic,
                "side_a_label": "newspaper_editorial",
                "side_b_label": "social_discourse",
                "score_a": by_topic_np[topic],
                "score_b": by_topic_sp[topic],
                "delta": delta,
                "flagged": delta > 0.4,
                "sample_a": [],
                "sample_b": [],
            }
        )
    out.sort(key=lambda x: x["delta"], reverse=True)
    return out[:6]
