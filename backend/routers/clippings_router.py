"""
Cuttings pillar — newspaper clipping feed + newsstand mastheads + PDF proxy.

Routers exported:
    clippings_router  — /api/clippings/…
    newspapers_router — /api/newspapers/…
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from backend.auth.auth_middleware import get_current_principal, get_current_user
from backend.collectors.newspaper_collector import get_pdf_url_from_careerswave
from backend.database import get_db

logger = logging.getLogger(__name__)

clippings_router = APIRouter(prefix="/api/clippings", tags=["clippings"])
newspapers_router = APIRouter(prefix="/api/newspapers", tags=["newspapers"])

_PDF_CACHE_TTL_SECONDS = 6 * 3600
_RELEVANCE_MIN = 0.3


# ── /api/clippings/papers ─────────────────────────────────────────────────────

@clippings_router.get("/papers")
async def list_papers(
    days: int = Query(7, ge=1, le=365),
    _user: dict = Depends(get_current_user),
    principal: dict = Depends(get_current_principal),
) -> dict:
    """One row per active newspaper with clipping count and PDF availability."""
    async with get_db() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT
                        ns.id          AS newspaper_id,
                        ns.name        AS name,
                        ns.language    AS language,
                        MAX(nc.edition_date) AS edition_date,
                        COUNT(nc.id) FILTER (WHERE nc.relevance_score >= 0.3)
                                                AS clip_count,
                        BOOL_OR(ne.pdf_url IS NOT NULL) AS pdf_available
                    FROM newspaper_sources ns
                    LEFT JOIN newspaper_clippings nc
                           ON nc.newspaper_id = ns.id
                          AND nc.edition_date >= CURRENT_DATE - INTERVAL '1 day' * :days
                    LEFT JOIN newspaper_editions ne
                           ON ne.newspaper_id = ns.id
                          AND ne.edition_date >= CURRENT_DATE - INTERVAL '1 day' * :days
                    WHERE ns.is_active = TRUE
                    GROUP BY ns.id, ns.name, ns.language
                    HAVING COUNT(nc.id) FILTER (WHERE nc.relevance_score >= 0.3) > 0
                        OR BOOL_OR(ne.pdf_url IS NOT NULL)
                    ORDER BY clip_count DESC
                    """
                ),
                {"days": days},
            )
        ).fetchall()

    return {
        "papers": [
            {
                "newspaper_id": str(r.newspaper_id),
                "name": r.name,
                "language": r.language,
                "edition_date": str(r.edition_date) if r.edition_date else None,
                "clip_count": r.clip_count or 0,
                "pdf_available": bool(r.pdf_available),
            }
            for r in rows
        ]
    }


# ── /api/clippings/feed ───────────────────────────────────────────────────────

@clippings_router.get("/feed")
async def clippings_feed(
    limit: int = Query(20, ge=1, le=100),
    days: int = Query(7, ge=1, le=365),
    newspaper: Optional[str] = Query(None),
    language: Optional[str] = Query(None),
    cursor: Optional[str] = Query(None),
    _user: dict = Depends(get_current_user),
    principal: dict = Depends(get_current_principal),
) -> dict:
    """Cursor-paginated feed of relevant newspaper clippings."""
    conditions = ["nc.relevance_score >= 0.3"]
    params: dict = {"limit": limit + 1, "days": days}

    if newspaper:
        conditions.append("nc.newspaper_name = :paper")
        params["paper"] = newspaper

    if language:
        conditions.append("nc.newspaper_language = :lang")
        params["lang"] = language

    if cursor:
        conditions.append("nc.collected_at < :cursor::timestamptz")
        params["cursor"] = cursor

    where_sql = " AND ".join(conditions)

    async with get_db() as db:
        all_rows = (
            await db.execute(
                text(
                    f"""
                    SELECT
                        nc.id                              AS clipping_id,
                        nc.newspaper_name                  AS newspaper_name,
                        nc.newspaper_language              AS newspaper_language,
                        nc.edition_date                    AS edition_date,
                        nc.page_number                     AS page_number,
                        nc.headline                        AS headline,
                        nc.headline_translated             AS headline_translated,
                        LEFT(nc.article_text, 300)         AS text_preview,
                        LEFT(nc.article_text_translated, 300) AS translated_preview,
                        (nc.clipping_image_b64 IS NOT NULL
                         AND LENGTH(nc.clipping_image_b64) > 0) AS has_image,
                        nc.relevance_score                 AS relevance_score,
                        nc.relevance_explanation           AS relevance_explanation,
                        nc.collected_at                    AS collected_at
                    FROM newspaper_clippings nc
                    WHERE {where_sql}
                    ORDER BY nc.collected_at DESC
                    LIMIT :limit
                    """
                ),
                params,
            )
        ).fetchall()

        has_more = len(all_rows) > limit
        rows = all_rows[:limit]
        next_cursor = (
            rows[-1].collected_at.isoformat() if has_more and rows else None
        )

        news_rows = (
            await db.execute(
                text(
                    """
                    SELECT newspaper_name, newspaper_language,
                           COUNT(*) AS count
                    FROM newspaper_clippings
                    WHERE edition_date >= CURRENT_DATE - INTERVAL '1 day' * :days
                      AND relevance_score >= 0.3
                    GROUP BY newspaper_name, newspaper_language
                    ORDER BY count DESC
                    """
                ),
                {"days": days},
            )
        ).fetchall()

    return {
        "clippings": [
            {
                "clipping_id": str(r.clipping_id),
                "newspaper_name": r.newspaper_name,
                "newspaper_language": r.newspaper_language,
                "edition_date": str(r.edition_date),
                "page_number": r.page_number,
                "headline": r.headline,
                "headline_translated": r.headline_translated,
                "text_preview": r.text_preview,
                "translated_preview": r.translated_preview,
                "has_image": bool(r.has_image),
                "relevance_score": r.relevance_score,
                "relevance_explanation": r.relevance_explanation,
                "collected_at": (
                    r.collected_at.isoformat() if r.collected_at else None
                ),
            }
            for r in rows
        ],
        "has_more": has_more,
        "next_cursor": next_cursor,
        "newspapers": [
            {
                "name": r.newspaper_name,
                "language": r.newspaper_language,
                "count": r.count,
            }
            for r in news_rows
        ],
    }


# ── /api/clippings/{id}/image ─────────────────────────────────────────────────

@clippings_router.get("/{clipping_id}/image")
async def clipping_image(
    clipping_id: UUID,
    _user: dict = Depends(get_current_user),
    principal: dict = Depends(get_current_principal),
) -> dict:
    """Return the base64-encoded clipping image."""
    async with get_db() as db:
        row = (
            await db.execute(
                text(
                    "SELECT clipping_image_b64"
                    " FROM newspaper_clippings WHERE id = :cid"
                ),
                {"cid": str(clipping_id)},
            )
        ).fetchone()

    if not row or not row.clipping_image_b64:
        raise HTTPException(status_code=404, detail="Image not found")

    return {"image_b64": row.clipping_image_b64}


# ── /api/clippings/{id}/full ──────────────────────────────────────────────────

@clippings_router.get("/{clipping_id}/full")
async def clipping_full(
    clipping_id: UUID,
    _user: dict = Depends(get_current_user),
    principal: dict = Depends(get_current_principal),
) -> dict:
    """Full clipping text (both languages if available)."""
    async with get_db() as db:
        row = (
            await db.execute(
                text(
                    """
                    SELECT headline, headline_translated,
                           article_text, article_text_translated,
                           newspaper_name, edition_date
                    FROM newspaper_clippings
                    WHERE id = :cid
                    """
                ),
                {"cid": str(clipping_id)},
            )
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Clipping not found")

    return {
        "headline": row.headline,
        "headline_translated": row.headline_translated,
        "article_text": row.article_text,
        "article_text_translated": row.article_text_translated,
        "newspaper_name": row.newspaper_name,
        "edition_date": str(row.edition_date),
    }


# ── /api/newspapers/{id}/pdf ──────────────────────────────────────────────────

@newspapers_router.get("/{newspaper_id}/pdf")
async def newspaper_pdf(
    newspaper_id: UUID,
    date_param: Optional[str] = Query(None, alias="date"),
    _user: dict = Depends(get_current_user),
    principal: dict = Depends(get_current_principal),
) -> StreamingResponse:
    """Stream today's (or a specified date's) PDF edition, using a 6-hour URL cache."""
    if date_param is not None:
        try:
            target_date = date.fromisoformat(date_param)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid date format. Use YYYY-MM-DD."
            )
    else:
        target_date = date.today()

    nid = str(newspaper_id)

    async with get_db() as db:
        cache_row = (
            await db.execute(
                text(
                    """
                    SELECT pdf_url, fetched_at
                    FROM newspaper_editions
                    WHERE newspaper_id = :nid AND edition_date = :dt
                    """
                ),
                {"nid": nid, "dt": str(target_date)},
            )
        ).fetchone()

        pdf_url: str | None = None

        if cache_row:
            fetched_at = cache_row.fetched_at
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - fetched_at).total_seconds()
            if age < _PDF_CACHE_TTL_SECONDS:
                pdf_url = cache_row.pdf_url

        if not pdf_url:
            src = (
                await db.execute(
                    text(
                        "SELECT careerswave_url"
                        " FROM newspaper_sources WHERE id = :nid"
                    ),
                    {"nid": nid},
                )
            ).fetchone()

            if not src or not src.careerswave_url:
                raise HTTPException(
                    status_code=404, detail="No PDF available for this edition."
                )

            pdf_url = await get_pdf_url_from_careerswave(src.careerswave_url)
            if not pdf_url:
                raise HTTPException(
                    status_code=404, detail="No PDF available for this edition."
                )

            await db.execute(
                text(
                    """
                    INSERT INTO newspaper_editions (newspaper_id, edition_date, pdf_url, fetched_at)
                    VALUES (:nid, :dt, :url, NOW())
                    ON CONFLICT (newspaper_id, edition_date) DO UPDATE
                        SET pdf_url = EXCLUDED.pdf_url, fetched_at = NOW()
                    """
                ),
                {"nid": nid, "dt": str(target_date), "url": pdf_url},
            )
            await db.commit()

    async def _pdf_stream():
        client = httpx.AsyncClient()
        try:
            async with client.stream("GET", pdf_url) as resp:
                async for chunk in resp.aiter_bytes(65536):
                    yield chunk
        finally:
            await client.aclose()

    return StreamingResponse(_pdf_stream(), media_type="application/pdf")
