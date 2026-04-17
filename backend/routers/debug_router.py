"""
Debug endpoints for operational monitoring.
All routes gated by require_dev_environment dependency.
Register in main.py: app.include_router(debug_router)
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from backend.database import get_db


def require_dev_environment() -> None:
    env = os.getenv("ENVIRONMENT", "development")
    if env == "production":
        raise HTTPException(
            status_code=403,
            detail="Debug endpoints disabled in production",
        )


debug_router = APIRouter(
    prefix="/debug",
    tags=["debug"],
    dependencies=[Depends(require_dev_environment)],
)


# ── Panel 1: Pipeline Health ──────────────────────────────────────────────────

@debug_router.get("/pipeline-health")
async def pipeline_health() -> dict:
    async with get_db() as db:
        row = (await db.execute(text("""
            SELECT
              COUNT(*) AS total_articles,
              COUNT(*) FILTER (
                WHERE nlp_processed = TRUE AND nlp_confidence = 'normal'
              ) AS processed_normal,
              COUNT(*) FILTER (
                WHERE nlp_processed = TRUE AND nlp_confidence = 'low'
              ) AS processed_low,
              COUNT(*) FILTER (
                WHERE nlp_processed = TRUE AND nlp_confidence = 'error'
              ) AS processed_error,
              COUNT(*) FILTER (
                WHERE nlp_processed = FALSE
              ) AS pending_nlp,
              COUNT(*) FILTER (
                WHERE nlp_processed = FALSE
                AND lead_text_original IS NOT NULL
                AND LENGTH(lead_text_original) > 100
              ) AS pending_with_text,
              MAX(collected_at) AS newest_article,
              MIN(collected_at) FILTER (
                WHERE nlp_processed = FALSE
              ) AS oldest_pending
            FROM articles
        """))).fetchone()

        # Proxy: relevance rows scored in last hour as NLP throughput indicator
        rate_row = (await db.execute(text("""
            SELECT COUNT(*) AS per_hour
            FROM user_article_relevance
            WHERE scored_at > NOW() - INTERVAL '1 hour'
        """))).fetchone()

        total = max(row.total_articles, 1)
        return {
            "total_articles": row.total_articles,
            "processed_normal": row.processed_normal,
            "processed_low": row.processed_low,
            "processed_error": row.processed_error,
            "pending_nlp": row.pending_nlp,
            "pending_with_text": row.pending_with_text,
            "newest_article": (
                row.newest_article.isoformat() if row.newest_article else None
            ),
            "oldest_pending": (
                row.oldest_pending.isoformat() if row.oldest_pending else None
            ),
            "processing_rate_per_hour": rate_row.per_hour,
            "pct_processed": round(
                100 * (row.processed_normal + row.processed_low) / total, 1
            ),
        }


# ── Panel 2: Recent Articles ──────────────────────────────────────────────────

@debug_router.get("/recent-articles")
async def recent_articles() -> dict:
    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT
              a.id,
              a.title,
              s.name AS source_name,
              a.language_detected,
              a.topic_category,
              a.geo_primary,
              a.nlp_processed,
              a.nlp_confidence,
              jsonb_array_length(
                COALESCE(a.entities_extracted, '[]')
              ) AS entity_count,
              a.collected_at
            FROM articles a
            JOIN sources s ON a.source_id = s.id
            ORDER BY a.collected_at DESC
            LIMIT 20
        """))).fetchall()

        return {
            "articles": [
                {
                    "id": str(r.id),
                    "title": r.title,
                    "source": r.source_name,
                    "language": r.language_detected,
                    "topic": r.topic_category,
                    "geo": r.geo_primary,
                    "nlp_processed": r.nlp_processed,
                    "nlp_confidence": r.nlp_confidence,
                    "entity_count": r.entity_count,
                    "collected_at": (
                        r.collected_at.isoformat() if r.collected_at else None
                    ),
                }
                for r in rows
            ]
        }


# ── Panel 3: NLP Quality ──────────────────────────────────────────────────────

@debug_router.get("/nlp-quality")
async def nlp_quality() -> dict:
    async with get_db() as db:
        topic_rows = (await db.execute(text("""
            SELECT topic_category, COUNT(*) AS count
            FROM articles
            WHERE nlp_processed = TRUE AND nlp_confidence = 'normal'
            GROUP BY topic_category
            ORDER BY count DESC
        """))).fetchall()

        q = (await db.execute(text("""
            SELECT
              COUNT(*) AS total_processed,
              COUNT(*) FILTER (
                WHERE jsonb_array_length(
                  COALESCE(entities_extracted, '[]')
                ) > 0
              ) AS has_entities,
              COUNT(*) FILTER (
                WHERE geo_primary IS NOT NULL
              ) AS has_geo,
              COUNT(*) FILTER (
                WHERE labse_embedding IS NOT NULL
              ) AS has_embedding,
              COUNT(*) FILTER (
                WHERE language_detected != 'en'
                AND language_detected IS NOT NULL
              ) AS non_english
            FROM articles
            WHERE nlp_processed = TRUE AND nlp_confidence = 'normal'
        """))).fetchone()

        total = max(q.total_processed, 1)
        return {
            "total_processed": q.total_processed,
            "entity_extraction_rate": round(100 * q.has_entities / total, 1),
            "geo_tagging_rate": round(100 * q.has_geo / total, 1),
            "embedding_rate": round(100 * q.has_embedding / total, 1),
            "non_english_count": q.non_english,
            "topic_distribution": [
                {
                    "topic": r.topic_category or "UNCLASSIFIED",
                    "count": r.count,
                }
                for r in topic_rows
            ],
        }


# ── Panel 4: Relevance Quality ────────────────────────────────────────────────

@debug_router.get("/relevance-quality")
async def relevance_quality() -> dict:
    async with get_db() as db:
        tier_rows = (await db.execute(text("""
            SELECT
              relevance_tier,
              COUNT(*) AS count,
              ROUND(AVG(score_final)::numeric, 3) AS avg_score,
              ROUND(MAX(score_final)::numeric, 3) AS max_score
            FROM user_article_relevance
            GROUP BY relevance_tier
            ORDER BY relevance_tier
        """))).fetchall()

        top_rows = (await db.execute(text("""
            SELECT
              a.title,
              uar.score_final,
              uar.relevance_tier,
              uar.relevance_explanation,
              a.topic_category,
              a.geo_primary
            FROM user_article_relevance uar
            JOIN articles a ON a.id = uar.article_id
            ORDER BY uar.score_final DESC
            LIMIT 10
        """))).fetchall()

        return {
            "tier_distribution": [
                {
                    "tier": r.relevance_tier,
                    "count": r.count,
                    "avg_score": float(r.avg_score or 0),
                    "max_score": float(r.max_score or 0),
                }
                for r in tier_rows
            ],
            "top_articles": [
                {
                    "title": r.title,
                    "score": float(r.score_final),
                    "tier": r.relevance_tier,
                    "explanation": r.relevance_explanation,
                    "topic": r.topic_category,
                    "geo": r.geo_primary,
                }
                for r in top_rows
            ],
        }


# ── Panel 5: Source Health ────────────────────────────────────────────────────

@debug_router.get("/source-health")
async def source_health() -> dict:
    async with get_db() as db:
        summary = (await db.execute(text("""
            SELECT
              COUNT(*) AS total_sources,
              COUNT(*) FILTER (WHERE is_active = TRUE) AS active_sources,
              COUNT(*) FILTER (WHERE is_active = FALSE) AS disabled_sources,
              COUNT(*) FILTER (
                WHERE health_score < 0.5 AND is_active = TRUE
              ) AS degraded_sources,
              COUNT(*) FILTER (
                WHERE last_collected_at > NOW() - INTERVAL '1 hour'
              ) AS collected_last_hour,
              COUNT(*) FILTER (
                WHERE last_collected_at > NOW() - INTERVAL '24 hours'
              ) AS collected_today
            FROM sources
        """))).fetchone()

        sick_rows = (await db.execute(text("""
            SELECT name, domain, health_score, consecutive_failures,
                   last_collected_at, is_active
            FROM sources
            WHERE (health_score < 0.7 OR consecutive_failures > 2)
              AND is_active = TRUE
            ORDER BY health_score ASC
            LIMIT 15
        """))).fetchall()

        return {
            "summary": {
                "total": summary.total_sources,
                "active": summary.active_sources,
                "disabled": summary.disabled_sources,
                "degraded": summary.degraded_sources,
                "collected_last_hour": summary.collected_last_hour,
                "collected_today": summary.collected_today,
            },
            "degraded_sources": [
                {
                    "name": r.name,
                    "domain": r.domain,
                    "health_score": float(r.health_score or 0),
                    "consecutive_failures": r.consecutive_failures,
                    "last_collected": (
                        r.last_collected_at.isoformat()
                        if r.last_collected_at
                        else None
                    ),
                }
                for r in sick_rows
            ],
        }


# ── Panel 6: Queue Status ─────────────────────────────────────────────────────

@debug_router.get("/queue-status")
async def queue_status() -> dict:
    worker_status = "unknown"
    registered_tasks: list[str] = []
    active_tasks: list[dict] = []

    try:
        from backend.celery_app import app as celery_app  # noqa: PLC0415

        inspect = celery_app.control.inspect(timeout=3.0)
        registered = inspect.registered()
        if registered:
            worker_status = "online"
            for tasks in registered.values():
                registered_tasks.extend(tasks)
        else:
            worker_status = "offline"

        active = inspect.active()
        if active:
            for tasks in active.values():
                active_tasks.extend(tasks)

    except Exception as exc:
        worker_status = f"error: {exc}"

    async with get_db() as db:
        stats = (await db.execute(text("""
            SELECT
              COUNT(*) FILTER (WHERE nlp_processed = FALSE) AS nlp_queue_depth,
              (
                SELECT COUNT(*) FROM user_article_relevance
                WHERE scored_at > NOW() - INTERVAL '5 minutes'
              ) AS scored_last_5min,
              (
                SELECT COUNT(*) FROM user_article_relevance
                WHERE scored_at > NOW() - INTERVAL '1 hour'
              ) AS scored_last_hour
            FROM articles
        """))).fetchone()

        relevance_pending = (await db.execute(text("""
            SELECT COUNT(*) AS pending
            FROM articles
            WHERE nlp_processed = TRUE
              AND id NOT IN (
                SELECT DISTINCT article_id FROM user_article_relevance
              )
        """))).fetchone()

    return {
        "worker_status": worker_status,
        "registered_task_count": len(set(registered_tasks)),
        "active_task_count": len(active_tasks),
        "nlp_queue_depth": stats.nlp_queue_depth,
        "scored_last_5min": stats.scored_last_5min,
        "scored_last_hour": stats.scored_last_hour,
        "relevance_pending_score": (
            relevance_pending.pending if relevance_pending else 0
        ),
    }


# ── Panel 7: Intelligence Status ──────────────────────────────────────────────

@debug_router.get("/intelligence-status")
async def intelligence_status() -> dict:
    async with get_db() as db:
        user_row = (await db.execute(text("""
            SELECT
              COUNT(DISTINCT up.user_id) AS total_users,
              COUNT(DISTINCT ue.user_id) AS users_with_entities
            FROM user_profiles up
            LEFT JOIN user_entities ue ON ue.user_id = up.user_id
        """))).fetchone()

        brief_row = (await db.execute(text("""
            SELECT COUNT(*) AS total_briefs, MAX(generated_at) AS last_generated
            FROM briefs
        """))).fetchone()

        entity_rows = (await db.execute(text("""
            SELECT
              e.value->>'name' AS entity,
              COUNT(*) AS article_count
            FROM articles a,
              jsonb_array_elements(COALESCE(a.entities_extracted, '[]')) e
            WHERE a.nlp_processed = TRUE AND a.nlp_confidence = 'normal'
            GROUP BY e.value->>'name'
            ORDER BY article_count DESC
            LIMIT 10
        """))).fetchall()

        return {
            "users": {
                "total": user_row.total_users,
                "with_entities": user_row.users_with_entities,
            },
            "briefs": {
                "total": brief_row.total_briefs,
                "last_generated": (
                    brief_row.last_generated.isoformat()
                    if brief_row.last_generated
                    else None
                ),
            },
            "top_entities_in_coverage": [
                {"entity": r.entity, "article_count": r.article_count}
                for r in entity_rows
                if r.entity and r.entity != "None"
            ],
        }
