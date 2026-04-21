"""
Cutting Room API — newspaper clippings feed (P16).

Endpoints:
    GET  /api/clippings/feed            — paginated clipping feed
    GET  /api/clippings/{id}/image      — base64 PNG of rendered clipping
    GET  /api/clippings/{id}/full       — full clipping (both languages)
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from backend.auth.auth_middleware import get_current_user
from backend.database import get_db

logger = logging.getLogger(__name__)

clippings_router = APIRouter(
    prefix="/api/clippings",
    tags=["clippings"],
)


@clippings_router.get("/feed")
async def get_clippings_feed(
    newspaper: str = Query(default="all"),
    language: str = Query(default="all"),
    days: int = Query(default=7),
    limit: int = Query(default=20, le=50),
    cursor: str = Query(default=""),
    user: dict = Depends(get_current_user),
):
    """Return recent relevant clippings grouped-ready for display."""
    async with get_db() as db:
        conditions: list[str] = [
            "nc.collected_at > NOW() - (:days * INTERVAL '1 day')",
            "nc.relevance_score >= 0.3",
        ]
        params: dict = {"days": days, "limit": limit + 1}

        if newspaper != "all":
            conditions.append("nc.newspaper_name = :paper")
            params["paper"] = newspaper

        if language != "all":
            conditions.append("nc.newspaper_language = :lang")
            params["lang"] = language

        if cursor:
            conditions.append("nc.collected_at < :cursor::timestamptz")
            params["cursor"] = cursor

        where = " AND ".join(conditions)

        result = await db.execute(
            text(
                f"""
                SELECT
                    nc.id::text AS clipping_id,
                    nc.newspaper_name,
                    nc.newspaper_language,
                    nc.edition_date,
                    nc.page_number,
                    nc.headline,
                    nc.headline_translated,
                    LEFT(nc.article_text, 300) AS text_preview,
                    LEFT(nc.article_text_translated, 300)
                        AS translated_preview,
                    (nc.clipping_image_b64 IS NOT NULL) AS has_image,
                    nc.relevance_score,
                    nc.relevance_explanation,
                    nc.collected_at
                FROM newspaper_clippings nc
                WHERE {where}
                ORDER BY nc.relevance_score DESC, nc.collected_at DESC
                LIMIT :limit
                """
            ),
            params,
        )
        clippings = result.fetchall()
        has_more = len(clippings) > limit
        clippings = clippings[:limit]

        next_cursor: str | None = None
        if has_more and clippings:
            next_cursor = clippings[-1].collected_at.isoformat()

        papers_result = await db.execute(
            text(
                """
                SELECT
                    newspaper_name,
                    newspaper_language,
                    COUNT(*) AS count
                FROM newspaper_clippings
                WHERE collected_at > NOW() - INTERVAL '7 days'
                GROUP BY newspaper_name, newspaper_language
                ORDER BY count DESC
                """
            )
        )
        papers = papers_result.fetchall()

        return {
            "clippings": [
                {
                    "clipping_id": c.clipping_id,
                    "newspaper_name": c.newspaper_name,
                    "newspaper_language": c.newspaper_language,
                    "edition_date": (
                        c.edition_date.isoformat()
                        if c.edition_date
                        else None
                    ),
                    "page_number": c.page_number,
                    "headline": c.headline,
                    "headline_translated": c.headline_translated,
                    "text_preview": c.text_preview,
                    "translated_preview": c.translated_preview,
                    "has_image": c.has_image,
                    "relevance_score": c.relevance_score,
                    "relevance_explanation": c.relevance_explanation,
                    "collected_at": c.collected_at.isoformat(),
                }
                for c in clippings
            ],
            "has_more": has_more,
            "next_cursor": next_cursor,
            "newspapers": [
                {
                    "name": p.newspaper_name,
                    "language": p.newspaper_language,
                    "count": p.count,
                }
                for p in papers
            ],
        }


@clippings_router.get("/{clipping_id}/image")
async def get_clipping_image(
    clipping_id: str,
    user: dict = Depends(get_current_user),
):
    """Return the base64 PNG of the rendered clipping."""
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT clipping_image_b64
                FROM newspaper_clippings
                WHERE id = :cid::uuid
                """
            ),
            {"cid": clipping_id},
        )
        row = result.fetchone()
        if not row:
            raise HTTPException(
                status_code=404, detail="Clipping not found"
            )
        return {"image_b64": row.clipping_image_b64}


@clippings_router.get("/{clipping_id}/full")
async def get_clipping_full(
    clipping_id: str,
    user: dict = Depends(get_current_user),
):
    """Return full clipping text (original + translated)."""
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT
                    id,
                    headline,
                    headline_translated,
                    article_text,
                    article_text_translated,
                    newspaper_name,
                    edition_date
                FROM newspaper_clippings
                WHERE id = :cid::uuid
                """
            ),
            {"cid": clipping_id},
        )
        row = result.fetchone()
        if not row:
            raise HTTPException(
                status_code=404, detail="Clipping not found"
            )
        return {
            "clipping_id": str(row.id),
            "headline": row.headline,
            "headline_translated": row.headline_translated,
            "article_text": row.article_text,
            "article_text_translated": row.article_text_translated,
            "newspaper_name": row.newspaper_name,
            "edition_date": (
                row.edition_date.isoformat()
                if row.edition_date
                else None
            ),
        }
