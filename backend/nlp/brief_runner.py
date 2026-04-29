"""
Per-user brief generation runner.

Single entry point reused by:

* :mod:`backend.routers.brief_router` for ``POST /api/brief/generate``
* :mod:`backend.tasks.brief_task.generate_brief_for_user` (the daily
  Beat fan-out implemented as part of fix/brief-prod-readiness P1.5)

The router previously inlined the entire 200-line flow, which made
implementing a daily auto-generation impossible without copying it.
This module owns:

* User profile + entities lookup
* Tier-1/2 article SELECT with **recency window** + **dedup filter**
  (D-BRIEF-5 / D-BRIEF-6 from the audit)
* Multi-pillar evidence retrieval
* Idempotent upsert (briefs table)
* Timezone-correct ``brief_date`` from ``user_profiles.brief_timezone``

Returned shape mirrors the router response so the router becomes a thin
wrapper that just adds HTTP-shaped errors.
"""
from __future__ import annotations

import ast
import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import date as date_type
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.nlp.brief_generator import generate_brief

logger = logging.getLogger(__name__)


class BriefError(Exception):
    """Generic brief-runner error with a user-facing detail string."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class BriefResult:
    """Return shape for ``run_for_user``. Frozen — immutable by design."""

    content: str
    brief_date: date_type
    articles_used: int
    sections: dict[str, str]
    source_counts: dict[str, int]
    evidence: dict[str, Any]
    section_failures: tuple[str, ...]
    validation_summary: tuple[dict[str, Any], ...]
    cached: bool


# ── Internal helpers ─────────────────────────────────────────────────────────


def _parse_geo(profile: dict) -> list[str]:
    """Build the geo filter list from user_profiles columns."""
    geo_filter: list[str] = []
    if profile.get("geo_primary"):
        geo_filter.append(str(profile["geo_primary"]).strip())
    raw_geo = profile.get("geo_secondary")
    if raw_geo:
        try:
            parsed = (
                ast.literal_eval(str(raw_geo))
                if isinstance(raw_geo, str)
                else raw_geo
            )
            if isinstance(parsed, list):
                geo_filter.extend([str(g).strip() for g in parsed if g])
            else:
                geo_filter.append(str(raw_geo).strip())
        except (ValueError, SyntaxError):
            geo_filter.append(str(raw_geo).strip())
    return geo_filter


async def _fetch_profile(db: AsyncSession, user_id: str) -> dict | None:
    """Look up one user's profile + entities."""
    result = await db.execute(
        text(
            """
            SELECT
                up.user_id,
                up.role_type,
                up.geo_primary,
                up.geo_secondary,
                up.signal_priorities,
                up.role_context,
                up.raw_description,
                up.language_preferences,
                up.brief_time,
                up.brief_timezone,
                up.organisation,
                up.created_at,
                up.updated_at,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'canonical_name', ue.canonical_name,
                            'priority', ue.priority
                        )
                    ) FILTER (WHERE ue.id IS NOT NULL),
                    '[]'::json
                ) AS entities
            FROM user_profiles up
            LEFT JOIN user_entities ue ON ue.user_id = up.user_id
            WHERE up.user_id = :user_id
            GROUP BY
                up.user_id, up.role_type, up.geo_primary,
                up.geo_secondary, up.signal_priorities, up.role_context,
                up.raw_description, up.language_preferences,
                up.brief_time, up.brief_timezone, up.organisation,
                up.created_at, up.updated_at
            """
        ),
        {"user_id": user_id},
    )
    row = result.fetchone()
    return dict(row._mapping) if row else None


_ARTICLE_SELECT = """
SELECT
    a.id,
    a.title,
    a.lead_text_translated,
    a.lead_text_original,
    a.topic_category,
    a.geo_primary,
    a.published_at,
    a.thumbnail_url,
    a.author_name,
    s.name AS source_name,
    s.domain,
    uar.score_final,
    uar.relevance_tier,
    uar.relevance_explanation,
    uar.matched_entity_names
FROM user_article_relevance uar
JOIN articles a ON a.id = uar.article_id
JOIN sources s ON a.source_id = s.id
WHERE uar.user_id = :user_id
  AND uar.relevance_tier IN (1, 2)
  AND a.nlp_confidence != 'error'
  AND COALESCE(a.is_duplicate, FALSE) = FALSE
  AND a.published_at >= NOW() - make_interval(hours => :recency_hours)
ORDER BY uar.relevance_tier ASC, uar.score_final DESC
LIMIT :article_limit
"""


async def _fetch_articles(
    db: AsyncSession,
    user_id: str,
    *,
    recency_hours: int,
    article_limit: int,
) -> list[dict]:
    """Top tier-1/2 articles with recency + dedup filter (D-BRIEF-5/6)."""
    result = await db.execute(
        text(_ARTICLE_SELECT),
        {
            "user_id": user_id,
            "recency_hours": recency_hours,
            "article_limit": article_limit,
        },
    )
    return [dict(r._mapping) for r in result.fetchall()]


async def _compute_brief_date(db: AsyncSession, profile: dict) -> date_type:
    """Resolve today's date in the user's local timezone (D-BRIEF/F8 fix).

    Uses ``user_profiles.brief_timezone`` (e.g. ``Asia/Kolkata``) so that
    a brief filed at 23:00 UTC for an IST user lands on the correct
    local date instead of yesterday.
    """
    tz = (profile.get("brief_timezone") or "UTC").strip() or "UTC"
    try:
        result = await db.execute(
            text("SELECT (NOW() AT TIME ZONE :tz)::date AS d"),
            {"tz": tz},
        )
        row = result.fetchone()
        if row and row._mapping.get("d"):
            return row._mapping["d"]
    except Exception as exc:  # noqa: BLE001 — fall back to UTC date
        logger.warning(
            "Brief date timezone lookup failed for tz=%r: %s; using UTC",
            tz, exc,
        )
    return date_type.today()


# ── Public entry point ───────────────────────────────────────────────────────


async def run_for_user(
    db: AsyncSession,
    *,
    user_id: str,
    user_email: str,
) -> BriefResult:
    """Generate (or return-cached) today's brief for ``user_id``.

    Raises :class:`BriefError` with a status code that the caller should
    map to HTTP. Beat task callers can log and continue; the router
    turns it into ``HTTPException``.
    """
    # Ghost-row insert so the FK on briefs.user_id is satisfied even if
    # this is the user's very first brief.
    await db.execute(
        text(
            "INSERT INTO users (id, email) VALUES (:id, :email) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"id": user_id, "email": user_email},
    )

    profile = await _fetch_profile(db, user_id)
    if not profile:
        raise BriefError(
            404, "User profile not found. Complete onboarding first."
        )

    today = await _compute_brief_date(db, profile)

    # ── Idempotency window (P1.4) ───────────────────────────────────────
    # If a fresh brief exists within BRIEF_IDEMPOTENCY_WINDOW_S, return
    # it instead of fanning out to Groq again. Prevents the rapid
    # double-click double-spend.
    cached_row = (
        await db.execute(
            text(
                """
                SELECT content, brief_date, articles_used, generated_at,
                       source_counts, evidence, model_used,
                       EXTRACT(EPOCH FROM (NOW() - generated_at)) AS age_s
                FROM briefs
                WHERE user_id = :uid AND brief_date = :d
                LIMIT 1
                """
            ),
            {"uid": user_id, "d": today},
        )
    ).fetchone()
    if cached_row and (
        (cached_row._mapping.get("age_s") or 0)
        < settings.BRIEF_IDEMPOTENCY_WINDOW_S
    ):
        m = cached_row._mapping
        logger.info(
            "Brief idempotent return for user %s — last generated %.0fs ago",
            user_id, m["age_s"] or 0,
        )
        return BriefResult(
            content=m["content"],
            brief_date=m["brief_date"],
            articles_used=m["articles_used"] or 0,
            sections={},
            source_counts=m["source_counts"] or {},
            evidence=m["evidence"] or {
                "govt_docs": [], "social_posts": [],
                "newspaper_clippings": [], "video_clips": [],
            },
            section_failures=(),
            validation_summary=(),
            cached=True,
        )

    # ── Advisory lock — second click waits for the first to commit ──────
    # hashtext fits inside the 32-bit int the lock function expects.
    lock_key = f"brief:{user_id}:{today.isoformat()}"
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
        {"k": lock_key},
    )

    # Re-check after acquiring lock — another in-flight call may have just
    # finished.
    cached_row = (
        await db.execute(
            text(
                """
                SELECT content, brief_date, articles_used, generated_at,
                       source_counts, evidence, model_used,
                       EXTRACT(EPOCH FROM (NOW() - generated_at)) AS age_s
                FROM briefs
                WHERE user_id = :uid AND brief_date = :d
                LIMIT 1
                """
            ),
            {"uid": user_id, "d": today},
        )
    ).fetchone()
    if cached_row and (
        (cached_row._mapping.get("age_s") or 0)
        < settings.BRIEF_IDEMPOTENCY_WINDOW_S
    ):
        m = cached_row._mapping
        return BriefResult(
            content=m["content"],
            brief_date=m["brief_date"],
            articles_used=m["articles_used"] or 0,
            sections={},
            source_counts=m["source_counts"] or {},
            evidence=m["evidence"] or {
                "govt_docs": [], "social_posts": [],
                "newspaper_clippings": [], "video_clips": [],
            },
            section_failures=(),
            validation_summary=(),
            cached=True,
        )

    entities_raw = profile.get("entities", [])
    entities: list[dict] = (
        json.loads(entities_raw) if isinstance(entities_raw, str)
        else (entities_raw or [])
    )

    # Recency-filtered article fetch with one fallback widening.
    articles = await _fetch_articles(
        db, user_id,
        recency_hours=settings.BRIEF_ARTICLE_RECENCY_HOURS,
        article_limit=settings.BRIEF_ARTICLE_LIMIT,
    )
    if len(articles) < 10:
        logger.warning(
            "Brief: only %d fresh tier-1/2 articles in %dh window for %s; "
            "widening to %dh fallback",
            len(articles),
            settings.BRIEF_ARTICLE_RECENCY_HOURS,
            user_id,
            settings.BRIEF_ARTICLE_RECENCY_FALLBACK_HOURS,
        )
        articles = await _fetch_articles(
            db, user_id,
            recency_hours=settings.BRIEF_ARTICLE_RECENCY_FALLBACK_HOURS,
            article_limit=settings.BRIEF_ARTICLE_LIMIT,
        )

    if not articles:
        raise BriefError(404, "No relevant articles found.")
    if len(articles) < 10:
        raise BriefError(
            425,
            f"Only {len(articles)} relevant articles found in the last "
            f"{settings.BRIEF_ARTICLE_RECENCY_FALLBACK_HOURS}h. Your feed "
            "is still being prepared — check back in a few minutes."
        )

    geo_filter = _parse_geo(profile)

    # Multi-pillar evidence retrieval — best-effort, gather with exceptions.
    from backend.nlp.rag_engine import (
        retrieve_relevant_clips,
        retrieve_relevant_govt_docs,
        retrieve_relevant_newspaper_clippings,
        retrieve_relevant_social,
    )

    seed_query = (
        (articles[0].get("title") or "")
        + " "
        + (profile.get("role_context") or "Telangana")
    )[:300]

    govt_res, social_res, paper_res, clips_res = await asyncio.gather(
        retrieve_relevant_govt_docs(
            query=seed_query, user_id=user_id, db=db,
            geo_filter=geo_filter or None, mode="BRIEF", k=8,
        ),
        retrieve_relevant_social(
            query=seed_query, user_id=user_id, top_k=10,
        ),
        retrieve_relevant_newspaper_clippings(
            query=seed_query, user_id=user_id,
            geo_filter=geo_filter or None, top_k=8,
        ),
        retrieve_relevant_clips(
            query=seed_query, user_id=user_id, top_k=4,
        ),
        return_exceptions=True,
    )
    govt_docs = govt_res if not isinstance(govt_res, Exception) else []
    if isinstance(govt_res, Exception):
        logger.warning("Brief: govt-doc retrieval failed: %s", govt_res)
    social_posts = social_res if not isinstance(social_res, Exception) else []
    if isinstance(social_res, Exception):
        logger.warning("Brief: social retrieval failed: %s", social_res)
    newspaper_clippings = (
        paper_res if not isinstance(paper_res, Exception) else []
    )
    if isinstance(paper_res, Exception):
        logger.warning("Brief: newspaper retrieval failed: %s", paper_res)
    video_clips = clips_res if not isinstance(clips_res, Exception) else []
    if isinstance(clips_res, Exception):
        logger.warning("Brief: clip retrieval failed: %s", clips_res)

    # Per-pillar freshness gate (P2.8) — if newspaper has 24h-fresh
    # rows, prefer them; same for govt docs.
    newspaper_clippings = _prefer_recent(
        newspaper_clippings, key="edition_date", target_min=3,
    )

    logger.info(
        "Generating brief for user %s — articles=%d govt=%d social=%d "
        "paper=%d clips=%d",
        user_id, len(articles), len(govt_docs), len(social_posts),
        len(newspaper_clippings), len(video_clips),
    )

    result = await generate_brief(
        user_id=user_id,
        user_profile=profile,
        user_entities=entities,
        articles=articles,
        govt_docs=govt_docs,
        social_posts=social_posts,
        newspaper_clippings=newspaper_clippings,
        video_clips=video_clips,
    )

    if not result.get("content"):
        raise BriefError(
            500, result.get("error", "Brief generation failed"),
        )

    source_counts_payload: dict[str, int] = {
        "articles": len(articles),
        "govt_docs": len(govt_docs),
        "social_posts": len(social_posts),
        "newspaper_clippings": len(newspaper_clippings),
        "video_clips": len(video_clips),
    }
    evidence_payload: dict[str, Any] = {
        "govt_docs": govt_docs,
        "social_posts": social_posts,
        "newspaper_clippings": newspaper_clippings,
        "video_clips": video_clips,
    }

    await db.execute(
        text(
            """
            INSERT INTO briefs (
                user_id, content, brief_date, articles_used, model_used,
                source_counts, evidence
            ) VALUES (
                :user_id, :content, :brief_date, :articles_used, :model_used,
                CAST(:source_counts AS jsonb), CAST(:evidence AS jsonb)
            )
            ON CONFLICT (user_id, brief_date) DO UPDATE SET
                content       = EXCLUDED.content,
                articles_used = EXCLUDED.articles_used,
                model_used    = EXCLUDED.model_used,
                source_counts = EXCLUDED.source_counts,
                evidence      = EXCLUDED.evidence,
                generated_at  = NOW()
            """
        ),
        {
            "user_id": user_id,
            "content": result["content"],
            "brief_date": today,
            "articles_used": result["articles_used"],
            "model_used": "llama-3.3-70b-versatile",
            "source_counts": json.dumps(source_counts_payload),
            "evidence": json.dumps(evidence_payload, default=str),
        },
    )
    await db.commit()

    return BriefResult(
        content=result["content"],
        brief_date=today,
        articles_used=result["articles_used"],
        sections=result.get("sections", {}),
        source_counts=source_counts_payload,
        evidence=evidence_payload,
        section_failures=tuple(result.get("section_failures") or ()),
        validation_summary=tuple(result.get("validation_summary") or ()),
        cached=False,
    )


# ── Per-pillar freshness gate (P2.8) ─────────────────────────────────────────


def _prefer_recent(
    items: list[dict],
    *,
    key: str,
    target_min: int,
    days_window: int = 1,
) -> list[dict]:
    """Bias the retrieved-evidence list toward today/yesterday.

    The audit found newspaper retrieval picked 3-day-old editions even
    though today's pool was fresh. Apply a soft sort: items with a
    ``key`` (e.g. ``edition_date``) within ``days_window`` days bubble
    to the top, but the tail is preserved if there aren't enough fresh
    items to meet ``target_min``. No items are removed — this is a
    re-rank, not a filter, so callers still receive the same number
    of items they would have without the gate.
    """
    if not items or len(items) <= target_min:
        return items

    today = date_type.today()
    fresh: list[dict] = []
    stale: list[dict] = []
    for item in items:
        raw = item.get(key)
        is_fresh = False
        if raw:
            try:
                parsed = (
                    date_type.fromisoformat(str(raw)[:10])
                    if not hasattr(raw, "year")
                    else raw
                )
                is_fresh = (today - parsed).days <= days_window
            except (ValueError, TypeError):
                pass
        (fresh if is_fresh else stale).append(item)

    if len(fresh) >= target_min:
        return fresh + stale
    # Not enough fresh items — leave order alone so we don't replace
    # ranked-by-similarity with arbitrary date order.
    return items


__all__ = ["BriefError", "BriefResult", "run_for_user"]
