"""
Government documents API.

  GET  /api/documents/feed              — paginated, filtered feed
  GET  /api/documents/{doc_id}          — full document detail
  POST /api/documents/{doc_id}/summary  — Groq-generated 3-4 sentence summary
                                          (cached on first call)
"""
from __future__ import annotations

import base64
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from backend.auth.auth_middleware import get_current_user, require_page
from backend.database import get_db
from backend.nlp.groq_client import (
    GroqCallFailed,
    GroqQuotaExhausted,
    call_groq,
)


def _encode_cursor(row: Any) -> str:
    """Pack the full ORDER BY tuple into an opaque base64 cursor.

    Matches the feed query's ORDER BY:
      (score_final IS NULL, score_final DESC, intrinsic_importance DESC,
       collected_at DESC, id DESC).
    """
    payload = {
        "s_null": row.r_score_final is None,
        "s": float(row.r_score_final) if row.r_score_final is not None else None,
        "i": (
            float(row.intrinsic_importance)
            if row.intrinsic_importance is not None
            else None
        ),
        "c": row.collected_at.isoformat(),
        "d": row.doc_id,
    }
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def _decode_cursor(cursor: str) -> dict | None:
    """Inverse of _encode_cursor. Returns None on malformed input rather
    than raising — a bad cursor degrades to "first page" instead of 500."""
    if not cursor:
        return None
    try:
        return json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (ValueError, json.JSONDecodeError):
        return None

logger = logging.getLogger(__name__)

documents_router = APIRouter(
    prefix="/api/documents",
    tags=["documents"],
    dependencies=[Depends(require_page("documents"))],
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
        # `base_conditions` apply to both the feed query and the
        # geography-counts query. `feed_only_conditions` (geography filter,
        # cursor predicate) apply only to the feed.
        base_conditions: list[str] = ["d.nlp_processed = TRUE"]
        feed_only_conditions: list[str] = []
        params: dict = {
            "limit": limit + 1,
            "user_id": str(user["id"]),
        }

        # D-2: drop the `days` floor once a cursor is supplied — the cursor
        # itself bounds the window. Otherwise users can never reach docs
        # older than `days` even when `has_more=true`.
        cursor_state = _decode_cursor(cursor)
        if not cursor_state:
            base_conditions.append(
                "d.collected_at > NOW() - (:days * INTERVAL '1 day')"
            )
            params["days"] = days

        if geography != "all":
            feed_only_conditions.append("d.source_geography = :geo")
            params["geo"] = geography.upper()

        if doc_type != "all":
            base_conditions.append("d.document_type = :dtype")
            params["dtype"] = doc_type

        if search:
            base_conditions.append(
                "(d.title ILIKE :search "
                "OR d.full_text_translated ILIKE :search "
                "OR d.full_text ILIKE :search)"
            )
            params["search"] = f"%{search}%"

        # D-1: composite-key cursor. Strict-less-than over the full ORDER BY
        # tuple (score_null, score, intrinsic, collected_at, doc_id) so
        # pagination matches the sort order — no skips, no duplicates.
        if cursor_state is not None:
            feed_only_conditions.append("""(
                (
                  CASE WHEN r.score_final IS NULL THEN 1 ELSE 0 END,
                  COALESCE(-r.score_final, 9e18),
                  COALESCE(-d.intrinsic_importance, 9e18),
                  -EXTRACT(EPOCH FROM d.collected_at),
                  CAST(d.id AS text)
                )
                >
                (
                  :cur_s_null,
                  :cur_s_neg,
                  :cur_i_neg,
                  :cur_c_neg,
                  :cur_doc_id
                )
            )""")
            params["cur_s_null"] = 1 if cursor_state["s_null"] else 0
            params["cur_s_neg"] = (
                -cursor_state["s"] if cursor_state["s"] is not None else 9e18
            )
            params["cur_i_neg"] = (
                -cursor_state["i"] if cursor_state["i"] is not None else 9e18
            )
            from datetime import datetime
            cur_dt = datetime.fromisoformat(cursor_state["c"])
            params["cur_c_neg"] = -cur_dt.timestamp()
            params["cur_doc_id"] = cursor_state["d"]

        where = " AND ".join(base_conditions + feed_only_conditions)

        # D-3: filter-aware total via window function in the same query.
        # No second COUNT roundtrip; no drift between feed rows and total.
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
                    d.intrinsic_importance,
                    d.published_at,
                    d.collected_at,
                    r.score_final             AS r_score_final,
                    r.relevance_tier          AS r_relevance_tier,
                    r.urgency                 AS r_urgency,
                    r.why_it_matters          AS r_why_it_matters,
                    r.suggested_action        AS r_suggested_action,
                    r.matched_entity_names    AS r_matched_entity_names,
                    COUNT(*) OVER ()          AS filtered_total
                FROM govt_documents d
                LEFT JOIN user_govt_doc_relevance r
                       ON r.doc_id = d.id
                      AND r.user_id = CAST(:user_id AS uuid)
                WHERE {where}
                ORDER BY
                    (r.score_final IS NULL) ASC,
                    r.score_final DESC NULLS LAST,
                    d.intrinsic_importance DESC NULLS LAST,
                    d.collected_at DESC,
                    d.id DESC
                LIMIT :limit
                """
            ),
            params,
        )

        rows = result.fetchall()
        has_more = len(rows) > limit
        rows = rows[:limit]

        next_cursor = (
            _encode_cursor(rows[-1]) if has_more and rows else None
        )

        # D-9 (deferred): only enqueue scoring on the first page of a feed
        # request, never on cursor pagination. Cuts queue thrash from rapid
        # filter clicks.
        if cursor_state is None:
            unscored_doc_ids = [
                d.doc_id for d in rows if d.r_score_final is None
            ]
            if unscored_doc_ids:
                try:
                    from backend.tasks.govt_relevance_task import (
                        score_govt_doc_for_all_users,
                    )

                    for did in unscored_doc_ids:
                        score_govt_doc_for_all_users.apply_async(args=[did])
                except Exception as exc:  # noqa: BLE001 - best-effort
                    logger.warning(
                        "Failed to queue govt-doc relevance scoring: %s", exc
                    )

        total = int(rows[0].filtered_total) if rows else 0

        # D-3: geography_counts reflect base filters (window/type/search)
        # but NOT the geography filter itself, so each chip's number is
        # "what would this desk show if you clicked it." Always run with
        # the same `days` window the user is currently looking at.
        geo_where = " AND ".join(base_conditions) if base_conditions else "TRUE"
        geo_params: dict = {
            k: v for k, v in params.items()
            if k in {"days", "dtype", "search"}
        }
        # Force include `days` for the geo-counts query even when paginating
        # the feed (where we drop it). Counts always span the user's window.
        if "days" not in geo_params:
            geo_params["days"] = days
            geo_where = (
                "d.collected_at > NOW() - (:days * INTERVAL '1 day') AND "
                + geo_where
            )
        count_result = await db.execute(
            text(
                f"""
                SELECT d.source_geography, COUNT(*) AS count
                FROM govt_documents d
                WHERE {geo_where}
                GROUP BY d.source_geography
                ORDER BY count DESC
                """
            ),
            geo_params,
        )
        geo_counts = count_result.fetchall()

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
                    "score_final": (
                        float(d.r_score_final)
                        if d.r_score_final is not None else None
                    ),
                    "relevance_tier": d.r_relevance_tier,
                    "urgency": d.r_urgency,
                    "why_it_matters": d.r_why_it_matters,
                    "suggested_action": d.r_suggested_action,
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
