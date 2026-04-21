"""
Government documents API.

  GET  /api/documents/feed              — paginated, filtered feed
  GET  /api/documents/{doc_id}          — full document detail
  POST /api/documents/{doc_id}/summary  — Groq-generated 3-4 sentence summary
                                          (cached on first call)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from backend.auth.auth_middleware import get_current_user
from backend.database import get_db
from backend.nlp.groq_client import (
    GroqCallFailed,
    GroqQuotaExhausted,
    call_groq,
)

logger = logging.getLogger(__name__)

documents_router = APIRouter(
    prefix="/api/documents",
    tags=["documents"],
)


_SUMMARY_SYSTEM = (
    "You are a policy analyst. Summarize the following government document "
    "in 3 to 4 plain-language sentences. Focus on what action the document "
    "takes, who is affected, and any specific numbers or deadlines. "
    "Output only the summary, nothing else."
)


@documents_router.get("/feed")
async def get_documents_feed(
    geography: str = Query(default="all"),
    doc_type: str = Query(default="all"),
    days: int = Query(default=30, ge=1, le=365),
    search: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str = Query(default=""),
    user: dict = Depends(get_current_user),
):
    """Ranked government document feed."""
    async with get_db() as db:
        conditions = ["d.nlp_processed = TRUE"]
        params: dict = {"limit": limit + 1, "days": days}

        conditions.append(
            "d.collected_at > NOW() - (:days * INTERVAL '1 day')"
        )

        if geography != "all":
            conditions.append("d.source_geography = :geo")
            params["geo"] = geography.upper()

        if doc_type != "all":
            conditions.append("d.document_type = :dtype")
            params["dtype"] = doc_type

        if search:
            conditions.append(
                "(d.title ILIKE :search "
                "OR d.full_text_translated ILIKE :search "
                "OR d.full_text ILIKE :search)"
            )
            params["search"] = f"%{search}%"

        if cursor:
            conditions.append("d.collected_at < CAST(:cursor AS timestamptz)")
            params["cursor"] = cursor

        where = " AND ".join(conditions)

        result = await db.execute(
            text(
                f"""
                SELECT
                    CAST(d.id AS text)        AS doc_id,
                    d.title,
                    d.document_url,
                    d.source_name,
                    d.source_geography,
                    d.document_type,
                    d.topic_category,
                    d.geo_primary,
                    d.entities_extracted,
                    LEFT(
                        COALESCE(d.full_text_translated, d.full_text, ''),
                        400
                    )                         AS summary_preview,
                    d.summary,
                    d.page_count,
                    d.published_at,
                    d.collected_at
                FROM govt_documents d
                WHERE {where}
                ORDER BY d.collected_at DESC
                LIMIT :limit
                """
            ),
            params,
        )

        rows = result.fetchall()
        has_more = len(rows) > limit
        rows = rows[:limit]

        next_cursor = (
            rows[-1].collected_at.isoformat()
            if has_more and rows
            else None
        )

        # Geography counts (last 30 days) — used for filter chips
        count_result = await db.execute(
            text(
                """
                SELECT source_geography, COUNT(*) AS count
                FROM govt_documents
                WHERE collected_at > NOW() - INTERVAL '30 days'
                GROUP BY source_geography
                ORDER BY count DESC
                """
            )
        )
        geo_counts = count_result.fetchall()

        total_result = await db.execute(
            text("SELECT COUNT(*) AS total FROM govt_documents")
        )
        total_row = total_result.fetchone()
        total = int(total_row.total) if total_row else 0

        return {
            "documents": [
                {
                    "doc_id": d.doc_id,
                    "title": d.title,
                    "document_url": d.document_url,
                    "source_name": d.source_name,
                    "source_geography": d.source_geography,
                    "document_type": d.document_type,
                    "topic_category": d.topic_category,
                    "geo_primary": d.geo_primary,
                    "summary_preview": d.summary_preview,
                    "summary": d.summary,
                    "page_count": d.page_count,
                    "published_at": (
                        d.published_at.isoformat()
                        if d.published_at else None
                    ),
                    "collected_at": d.collected_at.isoformat(),
                }
                for d in rows
            ],
            "has_more": has_more,
            "next_cursor": next_cursor,
            "total": total,
            "geography_counts": [
                {"geography": g.source_geography, "count": int(g.count)}
                for g in geo_counts
            ],
        }


@documents_router.get("/{doc_id}")
async def get_document_detail(
    doc_id: str,
    user: dict = Depends(get_current_user),
):
    """Return the full document text and metadata."""
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT
                    CAST(id AS text) AS doc_id,
                    title,
                    document_url,
                    source_name,
                    source_geography,
                    document_type,
                    topic_category,
                    geo_primary,
                    entities_extracted,
                    full_text,
                    full_text_translated,
                    language_detected,
                    page_count,
                    summary,
                    published_at,
                    collected_at
                FROM govt_documents
                WHERE id = CAST(:did AS uuid)
                """
            ),
            {"did": doc_id},
        )
        doc = result.fetchone()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        return {
            "doc_id": doc.doc_id,
            "title": doc.title,
            "document_url": doc.document_url,
            "source_name": doc.source_name,
            "source_geography": doc.source_geography,
            "document_type": doc.document_type,
            "topic_category": doc.topic_category,
            "geo_primary": doc.geo_primary,
            "entities_extracted": doc.entities_extracted,
            "full_text": doc.full_text_translated or doc.full_text,
            "language_detected": doc.language_detected,
            "page_count": doc.page_count,
            "summary": doc.summary,
            "published_at": (
                doc.published_at.isoformat() if doc.published_at else None
            ),
            "collected_at": doc.collected_at.isoformat(),
        }


@documents_router.post("/{doc_id}/summary")
async def generate_document_summary(
    doc_id: str,
    user: dict = Depends(get_current_user),
):
    """
    Generate a plain-language summary via Groq fast model.
    Cached on first generation by writing back to govt_documents.summary.
    """
    async with get_db() as db:
        existing = await db.execute(
            text(
                """
                SELECT summary,
                       COALESCE(full_text_translated, full_text) AS body
                FROM govt_documents
                WHERE id = CAST(:did AS uuid)
                """
            ),
            {"did": doc_id},
        )
        row = existing.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")

        if row.summary:
            return {"summary": row.summary, "cached": True}

        body = (row.body or "")[:3000]
        if not body:
            raise HTTPException(
                status_code=422,
                detail="Document has no extractable text",
            )

        try:
            summary = await call_groq(
                system=_SUMMARY_SYSTEM,
                user=body,
                task_type="relevance_explanation",
            )
        except GroqQuotaExhausted as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except GroqCallFailed as exc:
            logger.error("Summary generation failed: %s", exc)
            raise HTTPException(
                status_code=502,
                detail="Summary generation failed",
            ) from exc

        summary = summary.strip()

        await db.execute(
            text(
                """
                UPDATE govt_documents
                SET summary = :s, updated_at = NOW()
                WHERE id = CAST(:did AS uuid)
                """
            ),
            {"s": summary, "did": doc_id},
        )
        await db.commit()

        return {"summary": summary, "cached": False}
