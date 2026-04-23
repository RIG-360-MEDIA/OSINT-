"""
Thread API router — story thread nodes, edges, detail, and analyst integration.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from backend.auth.auth_middleware import get_current_user
from backend.database import get_db


def _coerce_jsonb(value):
    """JSONB columns may surface as str or already-decoded list/dict."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value

logger = logging.getLogger(__name__)

thread_router = APIRouter(prefix="/api/threads", tags=["threads"])


@thread_router.get("")
async def get_threads(
    include_fading: bool = Query(default=True),
    limit: int = Query(default=50, le=100),
    user: dict = Depends(get_current_user),
) -> dict:
    """
    Get all active story threads as force-graph nodes + edges.
    Edges are derived from centroid similarity (entity edges disabled — NER artifacts).
    """
    async with get_db() as db:
        momentum_filter = "" if include_fading else "AND momentum != 'fading'"

        # Single round-trip: select top-N threads, then compute edges ONLY among
        # those N (O(N^2)) instead of the full active-thread cross-product
        # (which was the 24s bottleneck — O(M^2) over all active threads).
        combined_sql = f"""
            WITH top_threads AS (
              SELECT
                id,
                title,
                primary_entities,
                article_count,
                source_count,
                momentum,
                centroid_embedding,
                first_seen_at,
                last_updated_at
              FROM story_threads
              WHERE is_active = TRUE
              {momentum_filter}
              ORDER BY
                CASE momentum
                  WHEN 'escalating' THEN 1
                  WHEN 'stable'     THEN 2
                  WHEN 'fading'     THEN 3
                END,
                article_count DESC
              LIMIT :limit
            ),
            nodes AS (
              SELECT
                id::text                AS thread_id,
                title,
                primary_entities,
                article_count,
                source_count,
                momentum,
                first_seen_at,
                last_updated_at
              FROM top_threads
            ),
            edges AS (
              SELECT
                t1.id::text                                                       AS source,
                t2.id::text                                                       AS target,
                ROUND(CAST(1 - (t1.centroid_embedding <=> t2.centroid_embedding)
                           AS numeric), 3)                                        AS weight,
                ROUND(CAST(t1.centroid_embedding <=> t2.centroid_embedding
                           AS numeric), 3)                                        AS distance
              FROM top_threads t1
              JOIN top_threads t2 ON t1.id < t2.id
              WHERE t1.centroid_embedding IS NOT NULL
                AND t2.centroid_embedding IS NOT NULL
                AND (t1.centroid_embedding <=> t2.centroid_embedding) < 0.50
              ORDER BY distance ASC
              LIMIT 300
            )
            SELECT
              (SELECT COALESCE(jsonb_agg(to_jsonb(n)), '[]'::jsonb) FROM nodes n) AS nodes_json,
              (SELECT COALESCE(jsonb_agg(to_jsonb(e)), '[]'::jsonb) FROM edges e) AS edges_json
        """
        result = await db.execute(text(combined_sql), {"limit": limit})
        row = result.fetchone()
        nodes_raw = _coerce_jsonb(row.nodes_json) or []
        edges_raw = _coerce_jsonb(row.edges_json) or []

        if not nodes_raw:
            return {"nodes": [], "edges": [], "thread_count": 0, "escalating_count": 0}

        threads = nodes_raw  # list[dict] from jsonb_agg
        edges = [
            {
                "source": e["source"],
                "target": e["target"],
                "weight": float(e["weight"]),
                "distance": float(e["distance"]),
            }
            for e in edges_raw
        ]

        escalating_count = sum(1 for t in threads if t.get("momentum") == "escalating")

        return {
            "nodes": [
                {
                    "thread_id": t["thread_id"],
                    "title": t.get("title"),
                    "primary_entities": t.get("primary_entities") or [],
                    "article_count": t.get("article_count"),
                    "momentum": t.get("momentum"),
                    # jsonb_agg already serializes timestamps to ISO strings.
                    "first_seen_at": t.get("first_seen_at"),
                    "last_updated_at": t.get("last_updated_at"),
                }
                for t in threads
            ],
            "edges": edges,
            "thread_count": len(threads),
            "escalating_count": escalating_count,
        }


@thread_router.get("/{thread_id}")
async def get_thread_detail(
    thread_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Get thread detail with up to 50 most recent articles."""
    async with get_db() as db:
        thread_result = await db.execute(
            text("""
            SELECT
              id::text,
              title,
              primary_entities,
              article_count,
              momentum,
              first_seen_at,
              last_updated_at
            FROM story_threads
            WHERE id = CAST(:tid AS uuid)
            AND is_active = TRUE
            """),
            {"tid": thread_id},
        )
        thread = thread_result.fetchone()

        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")

        articles_result = await db.execute(
            text("""
            SELECT
              a.id::text as article_id,
              a.title,
              a.url,
              a.thumbnail_url,
              a.topic_category,
              a.geo_primary,
              a.collected_at,
              a.published_at,
              s.name   as source_name,
              s.domain as source_domain,
              uar.score_final,
              uar.relevance_tier
            FROM articles a
            JOIN sources s ON a.source_id = s.id
            LEFT JOIN user_article_relevance uar
              ON uar.article_id = a.id AND uar.user_id = :user_id
            WHERE a.thread_id = CAST(:tid AS uuid)
            ORDER BY a.collected_at DESC
            LIMIT 50
            """),
            {"tid": thread_id, "user_id": user["id"]},
        )

        return {
            "thread_id": thread.id,
            "title": thread.title,
            "primary_entities": thread.primary_entities or [],
            "article_count": thread.article_count,
            "momentum": thread.momentum,
            "first_seen_at": thread.first_seen_at.isoformat(),
            "last_updated_at": thread.last_updated_at.isoformat(),
            "articles": [
                {
                    "article_id": a.article_id,
                    "title": a.title,
                    "url": a.url,
                    "thumbnail_url": a.thumbnail_url,
                    "topic_category": a.topic_category,
                    "geo_primary": a.geo_primary,
                    "collected_at": a.collected_at.isoformat() if a.collected_at else None,
                    "source_name": a.source_name,
                    "source_domain": a.source_domain,
                    "score_final": float(a.score_final) if a.score_final else None,
                    "relevance_tier": a.relevance_tier,
                }
                for a in articles_result.fetchall()
            ],
        }


@thread_router.post("/{thread_id}/investigate")
async def investigate_thread(
    thread_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """
    Pre-load thread into RAG Analyst.
    Creates a new analyst session and returns redirect URL with
    thread title as the pre-loaded question.
    """
    async with get_db() as db:
        thread_result = await db.execute(
            text("""
            SELECT id::text, title
            FROM story_threads
            WHERE id = CAST(:tid AS uuid) AND is_active = TRUE
            """),
            {"tid": thread_id},
        )
        thread = thread_result.fetchone()

        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")

        sess_result = await db.execute(
            text("""
            INSERT INTO analyst_sessions (user_id)
            VALUES (:user_id)
            RETURNING id::text as session_id
            """),
            {"user_id": user["id"]},
        )
        await db.commit()
        session_id = sess_result.fetchone().session_id

        question = f"What is the developing situation in this story: {thread.title}"

        return {
            "session_id": session_id,
            "question": question,
            "redirect_url": (
                f"/analyst?session={session_id}&question={thread.title[:100]}"
            ),
        }
