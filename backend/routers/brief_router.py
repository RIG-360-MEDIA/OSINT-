"""
Brief router — generate, retrieve, and list daily intelligence briefs.

Hardened by ``fix/brief-prod-readiness``:

* All five endpoints gate on ``require_page("brief")`` instead of just
  ``get_current_user`` (D-BRIEF-AUDIT-1).
* Generation flow extracted into :mod:`backend.nlp.brief_runner` so the
  Beat task and the router share the same code path.
* ``GET /{brief_date}`` is constrained by a regex and rejects future
  dates (D-BRIEF-16).
* ``GET /history/list`` accepts ``limit`` and ``offset`` (capped) so
  the UI can lazy-load past briefs.
"""
from __future__ import annotations

import datetime as _dt
import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import text

from backend.auth.auth_middleware import require_page
from backend.database import get_db
from backend.nlp.brief_runner import BriefError, run_for_user

logger = logging.getLogger(__name__)

brief_router = APIRouter(prefix="/api/brief", tags=["brief"])


# Constrain ``brief_date`` path arg to ISO YYYY-MM-DD. Falls through with
# 422 (FastAPI's automatic validation response) for anything else; previously
# the route would 200/400 depending on parse outcome (D-BRIEF-16).
_BRIEF_DATE_REGEX = r"^\d{4}-\d{2}-\d{2}$"
_HISTORY_DEFAULT_LIMIT = 30
_HISTORY_MAX_LIMIT = 100


# ── Generate today's brief ────────────────────────────────────────────────────

@brief_router.post("/generate")
async def generate_today_brief(
    user: dict = Depends(require_page("brief")),
) -> dict:
    """Generate today's brief on demand. Idempotent within ~5 minutes."""
    async with get_db() as db:
        try:
            result = await run_for_user(
                db,
                user_id=user["id"],
                user_email=user.get("email", ""),
            )
        except BriefError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail)

    return {
        "content": result.content,
        "brief_date": result.brief_date.isoformat(),
        "articles_used": result.articles_used,
        "sections": result.sections,
        "source_counts": result.source_counts,
        "evidence": result.evidence,
        "cached": result.cached,
        "section_failures": list(result.section_failures),
    }


# ── Get today's brief ─────────────────────────────────────────────────────────

@brief_router.get("/today")
async def get_today_brief(
    user: dict = Depends(require_page("brief")),
) -> dict:
    """Get today's brief if it exists. Returns 404 if not yet generated."""
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT content, brief_date, articles_used, generated_at,
                       model_used, source_counts, evidence
                FROM briefs
                WHERE user_id = :user_id
                  AND generated_at > NOW() - INTERVAL '36 hours'
                ORDER BY brief_date DESC, generated_at DESC
                LIMIT 1
                """
            ),
            {"user_id": user["id"]},
        )
        row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="No brief for today")

    r = row._mapping
    return {
        "content": r["content"],
        "brief_date": r["brief_date"].isoformat(),
        "articles_used": r["articles_used"],
        "generated_at": r["generated_at"].isoformat(),
        "source_counts": r["source_counts"] or {
            "articles": r["articles_used"] or 0,
            "govt_docs": 0, "social_posts": 0,
            "newspaper_clippings": 0, "video_clips": 0,
        },
        "evidence": r["evidence"] or {
            "govt_docs": [], "social_posts": [],
            "newspaper_clippings": [], "video_clips": [],
        },
    }


# ── Get brief by date ─────────────────────────────────────────────────────────

@brief_router.get("/{brief_date}")
async def get_brief_by_date(
    brief_date: str = Path(..., regex=_BRIEF_DATE_REGEX),
    user: dict = Depends(require_page("brief")),
) -> dict:
    """Fetch a specific date's brief by ISO date string (YYYY-MM-DD)."""
    try:
        parsed_date = _dt.date.fromisoformat(brief_date)
    except ValueError:
        # Regex should already exclude this, but defend in depth.
        raise HTTPException(
            status_code=422, detail="Invalid date format — use YYYY-MM-DD"
        )
    if parsed_date > _dt.date.today():
        raise HTTPException(
            status_code=422,
            detail="Future dates are not supported.",
        )

    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT content, brief_date, articles_used, generated_at,
                       source_counts, evidence
                FROM briefs
                WHERE user_id = :user_id
                  AND brief_date = :brief_date
                LIMIT 1
                """
            ),
            {"user_id": user["id"], "brief_date": parsed_date},
        )
        row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"No brief for {brief_date}")

    r = row._mapping
    return {
        "content": r["content"],
        "source_counts": r["source_counts"] or {
            "articles": r["articles_used"] or 0,
            "govt_docs": 0, "social_posts": 0,
            "newspaper_clippings": 0, "video_clips": 0,
        },
        "evidence": r["evidence"] or {
            "govt_docs": [], "social_posts": [],
            "newspaper_clippings": [], "video_clips": [],
        },
        "brief_date": r["brief_date"].isoformat(),
        "articles_used": r["articles_used"],
        "generated_at": r["generated_at"].isoformat(),
    }


# ── Monitoring highlights ─────────────────────────────────────────────────────

@brief_router.get("/monitor/highlights")
async def get_monitoring_highlights(
    user: dict = Depends(require_page("brief")),
) -> dict:
    """Top cross-pillar items for the Brief → Monitoring view's hero band.

    Returns one best item per pillar (articles, newspaper, social, clips,
    govt docs) — ordered to give a guaranteed-mixed top-of-page layout.
    Each item carries a uniform ``pillar`` tag so the frontend can render
    one card type for all five.

    Filters mirror the per-stripe rules:
      - articles: tier 1 + 2 only, by score_final
      - newspaper: relevance_score >= 0.3, by score
      - social: monitored sources (Reddit + Telegram), by engagement
      - clips: tracked entities, by relevance_score
      - govt docs: by relevance_score
    """
    user_id = user["id"]

    async with get_db() as db:
        article_row = (
            await db.execute(
                text(
                    """
                    SELECT
                        a.id::text AS id,
                        a.title AS headline,
                        s.name AS source,
                        a.published_at AS ts,
                        uar.relevance_tier,
                        uar.score_final
                    FROM user_article_relevance uar
                    JOIN articles a ON a.id = uar.article_id
                    JOIN sources  s ON s.id = a.source_id
                    WHERE uar.user_id = :uid
                      AND uar.relevance_tier IN (1, 2)
                      AND a.nlp_confidence != 'error'
                    ORDER BY uar.relevance_tier ASC,
                             uar.score_final DESC,
                             a.published_at DESC NULLS LAST
                    LIMIT 1
                    """
                ),
                {"uid": user_id},
            )
        ).fetchone()

        paper_row = (
            await db.execute(
                text(
                    """
                    SELECT
                        nc.id::text AS id,
                        COALESCE(nc.headline_translated, nc.headline) AS headline,
                        nc.newspaper_name AS source,
                        nc.edition_date AS ts
                    FROM newspaper_clippings nc
                    WHERE nc.collected_at > NOW() - INTERVAL '24 hours'
                      AND nc.relevance_score >= 0.3
                    ORDER BY nc.relevance_score DESC, nc.collected_at DESC
                    LIMIT 1
                    """
                )
            )
        ).fetchone()

        social_row = (
            await db.execute(
                text(
                    """
                    SELECT
                        sp.id::text AS id,
                        COALESCE(
                            NULLIF(LEFT(sp.post_text_translated, 140), ''),
                            LEFT(sp.post_text, 140)
                        ) AS headline,
                        COALESCE(sm.display_name, sp.author_username) AS source,
                        sp.posted_at AS ts,
                        sp.sentiment_score
                    FROM social_posts sp
                    LEFT JOIN social_monitors sm ON sm.id = sp.monitor_id
                    WHERE sp.collected_at > NOW() - INTERVAL '24 hours'
                      AND sp.platform IN ('reddit', 'telegram')
                      AND sp.monitor_id IS NOT NULL
                    ORDER BY (
                        COALESCE(sp.upvotes, 0)
                        + 2 * COALESCE(sp.comment_count, 0)
                        + COALESCE(sp.forward_count, 0)
                    ) DESC, sp.collected_at DESC
                    LIMIT 1
                    """
                )
            )
        ).fetchone()

        clip_row = (
            await db.execute(
                text(
                    """
                    SELECT
                        yc.id::text AS id,
                        yc.video_title AS headline,
                        yc.channel_name AS source,
                        yc.video_published_at AS ts
                    FROM youtube_clips yc
                    JOIN user_entities ue ON ue.canonical_name = yc.matched_entity
                    WHERE ue.user_id = :uid
                      AND yc.processed = TRUE
                      AND yc.collected_at > NOW() - INTERVAL '24 hours'
                    ORDER BY COALESCE(yc.relevance_score, 0) DESC,
                             yc.collected_at DESC
                    LIMIT 1
                    """
                ),
                {"uid": user_id},
            )
        ).fetchone()

        doc_row = (
            await db.execute(
                text(
                    """
                    SELECT
                        d.id::text AS id,
                        d.title AS headline,
                        d.source_geography AS source,
                        d.published_at AS ts,
                        d.relevance_score
                    FROM documents d
                    WHERE d.collected_at > NOW() - INTERVAL '24 hours'
                    ORDER BY COALESCE(d.relevance_score, 0) DESC,
                             d.published_at DESC NULLS LAST
                    LIMIT 1
                    """
                )
            )
        ).fetchone()

    def _iso(value: object) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        try:
            return value.isoformat()  # type: ignore[attr-defined]
        except AttributeError:
            return str(value)

    highlights: list[dict] = []
    if article_row:
        highlights.append({
            "pillar": "articles",
            "id": article_row.id,
            "headline": article_row.headline,
            "source": article_row.source,
            "timestamp": _iso(article_row.ts),
            "score": float(article_row.score_final or 0),
            "extra": {"tier": int(article_row.relevance_tier or 0)},
        })
    if paper_row:
        highlights.append({
            "pillar": "newspaper",
            "id": paper_row.id,
            "headline": paper_row.headline,
            "source": paper_row.source,
            "timestamp": _iso(paper_row.ts),
            "score": None,
            "extra": {},
        })
    if social_row:
        highlights.append({
            "pillar": "social",
            "id": social_row.id,
            "headline": social_row.headline,
            "source": social_row.source,
            "timestamp": _iso(social_row.ts),
            "score": None,
            "extra": {
                "sentiment": (
                    float(social_row.sentiment_score)
                    if social_row.sentiment_score is not None
                    else None
                )
            },
        })
    if clip_row:
        highlights.append({
            "pillar": "clips",
            "id": clip_row.id,
            "headline": clip_row.headline,
            "source": clip_row.source,
            "timestamp": _iso(clip_row.ts),
            "score": None,
            "extra": {},
        })
    if doc_row:
        highlights.append({
            "pillar": "documents",
            "id": doc_row.id,
            "headline": doc_row.headline,
            "source": doc_row.source,
            "timestamp": _iso(doc_row.ts),
            "score": (
                float(doc_row.relevance_score)
                if doc_row.relevance_score is not None
                else None
            ),
            "extra": {},
        })

    return {
        "highlights": highlights,
        "as_of": datetime.utcnow().isoformat(),
    }


# ── Brief history ─────────────────────────────────────────────────────────────

@brief_router.get("/history/list")
async def get_brief_history(
    user: dict = Depends(require_page("brief")),
    limit: int = Query(_HISTORY_DEFAULT_LIMIT, ge=1, le=_HISTORY_MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> dict:
    """Return a page of past brief dates (no content). Capped at 100 per page."""
    async with get_db() as db:
        count_result = await db.execute(
            text(
                "SELECT COUNT(*) AS n FROM briefs WHERE user_id = :user_id"
            ),
            {"user_id": user["id"]},
        )
        total = int(count_result.scalar() or 0)

        result = await db.execute(
            text(
                """
                SELECT brief_date, articles_used, generated_at
                FROM briefs
                WHERE user_id = :user_id
                ORDER BY brief_date DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {
                "user_id": user["id"],
                "limit": limit,
                "offset": offset,
            },
        )
        rows = result.fetchall()

    return {
        "briefs": [
            {
                "date": r._mapping["brief_date"].isoformat(),
                "articles_used": r._mapping["articles_used"],
                "generated_at": r._mapping["generated_at"].isoformat(),
            }
            for r in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
