"""brief_router.py — /api/brief/* endpoints powering the boss's Morning Brief.

NEW namespace, completely separate from /api/observe/*. Built feature-by-feature
as we wire each section of the brief from mock data to real DB queries.

CORS: localhost:5173 (the brief-app dev server) is whitelisted in backend/main.py.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from backend.database import get_db
from backend.observability.brief_entities import get_watched_entities
from backend.observability.brief_emerging import get_emerging_signals
from backend.observability.brief_stories import get_defining_stories

logger = logging.getLogger(__name__)

brief_router = APIRouter(prefix="/api/brief", tags=["brief"])


@brief_router.get("/entities")
async def get_entities() -> dict[str, Any]:
    """The 4 Watched Entity cards (Naidu, Rahul, Akhilesh, Owaisi)."""
    async with get_db() as db:
        return await get_watched_entities(db)


@brief_router.get("/emerging")
async def get_emerging(limit: int = 5) -> dict[str, Any]:
    """Top surging entities for the Emerging Signals chips."""
    async with get_db() as db:
        return await get_emerging_signals(db, limit=limit)


@brief_router.get("/stories")
async def get_stories(limit: int = 5) -> dict[str, Any]:
    """Top N defining stories from event_clusters (T5 importance_score)."""
    async with get_db() as db:
        return await get_defining_stories(db, limit=limit)


@brief_router.get("/kpi")
async def get_kpi() -> dict[str, Any]:
    """The 4 KPI tiles at the top of the brief.

    Returns articles parsed in last 24h, distinct outlets, distinct
    languages with per-lang counts, and the average sentiment.
    """
    async with get_db() as db:
        row = (await db.execute(text("""
            WITH last24 AS (
              SELECT a.id, a.language_detected, a.source_id
                FROM articles a
               WHERE a.collected_at >= NOW() - INTERVAL '24 hours'
                 AND a.substrate_status = 'ok'
            )
            SELECT
              (SELECT COUNT(*) FROM last24)                AS articles_parsed,
              (SELECT COUNT(DISTINCT source_id) FROM last24) AS outlets,
              (SELECT COUNT(DISTINCT language_detected) FROM last24
                WHERE language_detected IS NOT NULL)        AS languages,
              (SELECT AVG(intensity) FROM article_stances asn
                JOIN last24 l ON l.id = asn.article_id
               WHERE asn.intensity IS NOT NULL)             AS sentiment_avg
        """))).fetchone()

        # Per-language breakdown (TE 142 / HI 38 / EN 67 style)
        langs = (await db.execute(text("""
            SELECT UPPER(language_detected) AS code, COUNT(*) AS n
              FROM articles
             WHERE collected_at >= NOW() - INTERVAL '24 hours'
               AND substrate_status='ok'
               AND language_detected IS NOT NULL
             GROUP BY 1 ORDER BY 2 DESC LIMIT 6
        """))).fetchall()

    return {
        "articlesParsed": int(row.articles_parsed or 0),
        "outlets":        int(row.outlets or 0),
        "languages":      int(row.languages or 0),
        "sentiment":      round(float(row.sentiment_avg or 0), 2),
        "lang_breakdown": [{"code": l.code, "n": int(l.n)} for l in langs],
    }
