"""
Coverage Room router — ranked feed, full-text search, on-demand summary.

All endpoints scoped to the authenticated user's user_article_relevance rows.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from backend.auth.auth_middleware import get_current_user
from backend.database import get_db
from backend.nlp.groq_client import FAST_MODEL, call_groq

logger = logging.getLogger(__name__)

coverage_router = APIRouter(prefix="/api/coverage", tags=["coverage"])


# ── Feed endpoint ─────────────────────────────────────────────────────────────

@coverage_router.get("/feed")
async def get_feed(
    tier: str = Query(
        default="1,2,3",
        description="Comma-separated tiers",
    ),
    topic: str = Query(
        default="",
        description="Comma-separated topic categories",
    ),
    days: int = Query(
        default=0,
        description="0=all time, 7=week, 1=today",
    ),
    sentiment: str = Query(
        default="all",
        description="all | FOR_USER | AGAINST_USER | NEUTRAL",
    ),
    sort: str = Query(
        default="relevance",
        description="relevance | recency",
    ),
    cursor: str = Query(
        default="",
        description="Pagination cursor: {score_final:.6f}_{article_id}",
    ),
    limit: int = Query(default=20, ge=1, le=50),
    user: dict = Depends(get_current_user),
) -> dict:
    """
    Paginated ranked article feed for the authenticated user.

    Cursor format: "{score:.6f}_{article_id}" for relevance sort.
    Returns limit+1 internally to detect has_more.
    """
    async with get_db() as db:
        tier_list = [
            int(t.strip()) for t in tier.split(",") if t.strip().isdigit()
        ]
        topic_list = [
            t.strip().upper() for t in topic.split(",") if t.strip()
        ]

        conditions = ["uar.user_id = :user_id"]
        params: dict = {
            "user_id": user["id"],
            "limit": limit + 1,
        }

        if tier_list:
            conditions.append("uar.relevance_tier = ANY(:tiers)")
            params["tiers"] = tier_list

        if topic_list:
            conditions.append("a.topic_category = ANY(:topics)")
            params["topics"] = topic_list

        if days > 0:
            conditions.append(
                "a.collected_at > NOW() - :days * INTERVAL '1 day'"
            )
            params["days"] = days

        if sentiment != "all":
            conditions.append("uar.sentiment_for_user = :sentiment")
            params["sentiment"] = sentiment

        if cursor:
            try:
                parts = cursor.rsplit("_", 1)
                cursor_score = float(parts[0])
                cursor_id = parts[1]
                if sort == "relevance":
                    conditions.append(
                        "(uar.score_final < :cursor_score OR "
                        "(uar.score_final = :cursor_score AND "
                        "uar.article_id::text > :cursor_id))"
                    )
                else:
                    conditions.append(
                        "a.collected_at < "
                        "(SELECT collected_at FROM articles "
                        "WHERE id = CAST(:cursor_id AS uuid))"
                    )
                params["cursor_score"] = cursor_score
                params["cursor_id"] = cursor_id
            except (ValueError, IndexError):
                pass

        where_clause = " AND ".join(conditions)
        order_by = (
            "uar.score_final DESC, uar.article_id ASC"
            if sort == "relevance"
            else "a.collected_at DESC"
        )

        query = text(f"""
            SELECT
              a.id::text AS article_id,
              a.title,
              a.url,
              a.thumbnail_url,
              a.author_name,
              a.topic_category,
              a.geo_primary,
              a.published_at,
              a.collected_at,
              a.language_detected,
              LENGTH(a.lead_text_translated) AS text_length,
              s.name AS source_name,
              s.domain AS source_domain,
              uar.score_final,
              uar.score_stage1,
              uar.relevance_tier,
              uar.relevance_explanation,
              uar.matched_entity_names,
              uar.geo_multiplier_applied,
              uar.sentiment_for_user,
              uar.scored_at
            FROM user_article_relevance uar
            JOIN articles a ON a.id = uar.article_id
            JOIN sources s ON a.source_id = s.id
            WHERE {where_clause}
            ORDER BY {order_by}
            LIMIT :limit
        """)

        result = await db.execute(query, params)
        rows = result.fetchall()

        has_more = len(rows) > limit
        rows = rows[:limit]

        next_cursor: str | None = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = f"{last.score_final:.6f}_{last.article_id}"

        count_result = await db.execute(
            text("""
                SELECT
                  COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE relevance_tier = 1) AS tier1,
                  COUNT(*) FILTER (WHERE relevance_tier = 2) AS tier2,
                  COUNT(*) FILTER (WHERE relevance_tier = 3) AS tier3
                FROM user_article_relevance
                WHERE user_id = :user_id
            """),
            {"user_id": user["id"]},
        )
        counts = count_result.fetchone()

        return {
            "articles": [
                {
                    "article_id": r.article_id,
                    "title": r.title,
                    "url": r.url,
                    "thumbnail_url": r.thumbnail_url,
                    "author_name": r.author_name,
                    "topic_category": r.topic_category,
                    "geo_primary": r.geo_primary,
                    "published_at": (
                        r.published_at.isoformat()
                        if r.published_at else None
                    ),
                    "collected_at": (
                        r.collected_at.isoformat()
                        if r.collected_at else None
                    ),
                    "source_name": r.source_name,
                    "source_domain": r.source_domain,
                    "has_full_text": (r.text_length or 0) > 100,
                    "score_final": float(r.score_final),
                    "relevance_tier": r.relevance_tier,
                    "relevance_explanation": r.relevance_explanation,
                    "matched_entity_names": r.matched_entity_names or [],
                    "geo_multiplier": float(r.geo_multiplier_applied or 1.0),
                    "sentiment_for_user": r.sentiment_for_user or "NEUTRAL",
                }
                for r in rows
            ],
            "pagination": {
                "has_more": has_more,
                "next_cursor": next_cursor,
                "returned": len(rows),
            },
            "totals": {
                "total": counts.total if counts else 0,
                "tier1": counts.tier1 if counts else 0,
                "tier2": counts.tier2 if counts else 0,
                "tier3": counts.tier3 if counts else 0,
            },
        }


# ── Search endpoint ───────────────────────────────────────────────────────────

@coverage_router.get("/search")
async def search_articles(
    q: str = Query(..., min_length=2, description="Search query"),
    tier: str = Query(default="1,2,3"),
    limit: int = Query(default=30, le=50),
    user: dict = Depends(get_current_user),
) -> dict:
    """
    Full-text search across article title + translated body.
    Ranked by user relevance score, then ts_rank.
    """
    async with get_db() as db:
        tier_list = [
            int(t.strip()) for t in tier.split(",") if t.strip().isdigit()
        ] or [1, 2, 3]

        result = await db.execute(
            text("""
                SELECT
                  a.id::text AS article_id,
                  a.title,
                  a.url,
                  a.thumbnail_url,
                  a.topic_category,
                  a.geo_primary,
                  a.collected_at,
                  s.name AS source_name,
                  s.domain AS source_domain,
                  uar.score_final,
                  uar.relevance_tier,
                  uar.relevance_explanation,
                  uar.matched_entity_names,
                  uar.sentiment_for_user,
                  ts_rank(
                    to_tsvector(
                      'english',
                      COALESCE(a.title, '') || ' ' ||
                      COALESCE(a.lead_text_translated, '')
                    ),
                    plainto_tsquery('english', :query)
                  ) AS text_rank
                FROM user_article_relevance uar
                JOIN articles a ON a.id = uar.article_id
                JOIN sources s ON a.source_id = s.id
                WHERE uar.user_id = :user_id
                  AND uar.relevance_tier = ANY(:tiers)
                  AND (
                    to_tsvector(
                      'english',
                      COALESCE(a.title, '') || ' ' ||
                      COALESCE(a.lead_text_translated, '')
                    ) @@ plainto_tsquery('english', :query)
                    OR a.title ILIKE :like_query
                  )
                ORDER BY uar.score_final DESC, text_rank DESC
                LIMIT :limit
            """),
            {
                "user_id": user["id"],
                "query": q,
                "like_query": f"%{q}%",
                "tiers": tier_list,
                "limit": limit,
            },
        )
        rows = result.fetchall()

        return {
            "query": q,
            "count": len(rows),
            "articles": [
                {
                    "article_id": r.article_id,
                    "title": r.title,
                    "url": r.url,
                    "thumbnail_url": r.thumbnail_url,
                    "topic_category": r.topic_category,
                    "geo_primary": r.geo_primary,
                    "collected_at": (
                        r.collected_at.isoformat()
                        if r.collected_at else None
                    ),
                    "source_name": r.source_name,
                    "source_domain": r.source_domain,
                    "score_final": float(r.score_final),
                    "relevance_tier": r.relevance_tier,
                    "relevance_explanation": r.relevance_explanation,
                    "matched_entity_names": r.matched_entity_names or [],
                    "sentiment_for_user": r.sentiment_for_user or "NEUTRAL",
                }
                for r in rows
            ],
        }


# ── Summary endpoint ──────────────────────────────────────────────────────────

@coverage_router.post("/summary/{article_id}")
async def generate_summary(
    article_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """
    On-demand 3–4 sentence summary via Groq FAST_MODEL.
    Only works for articles in the user's scored feed.
    """
    async with get_db() as db:
        check = await db.execute(
            text("""
                SELECT
                  a.title,
                  a.lead_text_translated,
                  a.lead_text_original,
                  a.topic_category,
                  a.geo_primary,
                  uar.relevance_explanation
                FROM user_article_relevance uar
                JOIN articles a ON a.id = uar.article_id
                WHERE uar.user_id = :user_id
                  AND a.id = CAST(:article_id AS uuid)
            """),
            {"user_id": user["id"], "article_id": article_id},
        )
        article = check.fetchone()

        if not article:
            raise HTTPException(
                status_code=404,
                detail="Article not found in your feed",
            )

        text_to_summarise = (
            article.lead_text_translated
            or article.lead_text_original
            or article.title
        )

        if not text_to_summarise or len(text_to_summarise) < 50:
            return {
                "summary": (
                    "Full article text unavailable — read the original "
                    "source for complete details."
                ),
                "cached": False,
            }

        try:
            summary = await call_groq(
                system=(
                    "Summarise this news article in exactly 3-4 sentences. "
                    "Be specific — include names, numbers, places. "
                    "Do not use vague language. "
                    "Do not start with 'The article' or 'This article'."
                ),
                user=(
                    f"Title: {article.title}\n\n"
                    f"{text_to_summarise[:1500]}"
                ),
                task_type="brief_generation",
                model=FAST_MODEL,
            )
            return {"summary": summary, "cached": False}
        except Exception as exc:
            logger.error("Summary generation failed: %s", exc)
            raise HTTPException(
                status_code=500,
                detail="Summary generation failed",
            ) from exc


# ── Single article fetch ──────────────────────────────────────────────────────

@coverage_router.get("/article/{article_id}")
async def get_article(
    article_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Fetch a single article from the user's feed by ID."""
    async with get_db() as db:
        result = await db.execute(
            text("""
                SELECT
                  a.id::text AS article_id,
                  a.title,
                  a.url,
                  a.thumbnail_url,
                  a.author_name,
                  a.topic_category,
                  a.geo_primary,
                  a.published_at,
                  a.collected_at,
                  LENGTH(a.lead_text_translated) AS text_length,
                  s.name AS source_name,
                  s.domain AS source_domain,
                  uar.score_final,
                  uar.relevance_tier,
                  uar.relevance_explanation,
                  uar.matched_entity_names,
                  uar.geo_multiplier_applied,
                  uar.sentiment_for_user
                FROM user_article_relevance uar
                JOIN articles a ON a.id = uar.article_id
                JOIN sources s ON a.source_id = s.id
                WHERE uar.user_id = :user_id
                  AND a.id = CAST(:article_id AS uuid)
            """),
            {"user_id": user["id"], "article_id": article_id},
        )
        row = result.fetchone()

        if not row:
            raise HTTPException(
                status_code=404,
                detail="Article not found in your feed",
            )

        return {
            "article_id": row.article_id,
            "title": row.title,
            "url": row.url,
            "thumbnail_url": row.thumbnail_url,
            "author_name": row.author_name,
            "topic_category": row.topic_category,
            "geo_primary": row.geo_primary,
            "published_at": row.published_at.isoformat() if row.published_at else None,
            "collected_at": row.collected_at.isoformat() if row.collected_at else None,
            "source_name": row.source_name,
            "source_domain": row.source_domain,
            "has_full_text": (row.text_length or 0) > 100,
            "score_final": float(row.score_final),
            "relevance_tier": row.relevance_tier,
            "relevance_explanation": row.relevance_explanation,
            "matched_entity_names": row.matched_entity_names or [],
            "geo_multiplier": float(row.geo_multiplier_applied or 1.0),
            "sentiment_for_user": row.sentiment_for_user or "NEUTRAL",
        }
