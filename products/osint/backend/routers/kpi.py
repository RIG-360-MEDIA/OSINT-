"""GET /api/brief/kpi — the 4 KPI tiles at the top of the brief.

Ported from backend/routers/brief_router.py (parallel session). Reads from
public.articles + public.article_stances as analytics_user (read-only).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from db import get_db

router = APIRouter(prefix="/api/brief", tags=["brief"])


@router.get("/kpi")
async def get_kpi() -> dict[str, Any]:
    async with get_db() as db:
        row = (await db.execute(text("""
            WITH last24 AS (
              SELECT a.id, a.language_detected, a.source_id
                FROM articles a
               WHERE a.collected_at >= analytics.now_sim() - INTERVAL '24 hours'
                 AND a.substrate_status = 'ok'
            )
            SELECT
              (SELECT COUNT(*) FROM last24)                                  AS articles_parsed,
              (SELECT COUNT(DISTINCT source_id) FROM last24)                 AS outlets,
              (SELECT COUNT(DISTINCT language_detected) FROM last24
                WHERE language_detected IS NOT NULL)                         AS languages,
              (SELECT AVG(intensity) FROM article_stances asn
                JOIN last24 l ON l.id = asn.article_id
               WHERE asn.intensity IS NOT NULL)                              AS sentiment_avg
        """))).fetchone()

        langs = (await db.execute(text("""
            SELECT UPPER(language_detected) AS code, COUNT(*) AS n
              FROM articles
             WHERE collected_at >= analytics.now_sim() - INTERVAL '24 hours'
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
