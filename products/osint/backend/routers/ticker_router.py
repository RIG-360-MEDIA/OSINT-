"""GET /api/brief/ticker — newest PERSONA headlines for the Home "Breaking" marquee.

Priority order so the marquee reads as the persona's OWN news, not national noise:
  1. articles that NAME the persona's primary subject (blocks national stories that
     only pass through because they reference a co-watched party like BJP/Congress);
  2. the broader watchlist, when the subject is quiet in the window;
  3. generic newest-Indian headlines for the public / unauth view (never empty).
Titles are returned in their original language (instant — translating ~20 regional
headlines per load made the marquee hang).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text

from auth.middleware import get_optional_user
from brief_prefs import load_prefs
from db import get_db

router = APIRouter(prefix="/api/brief", tags=["brief"])

_SELECT = """
    SELECT a.id::text AS id, a.title, a.url, s.name AS source, a.collected_at AS when_ts
      FROM articles a
      JOIN sources s ON s.id = a.source_id
     WHERE a.source_country = 'IN'
       AND a.collected_at >= analytics.now_sim() - interval '48 hours'
       AND a.title IS NOT NULL AND LENGTH(a.title) > 0
       {extra}
     ORDER BY a.collected_at DESC
     LIMIT 20
"""


async def _rows(db, extra: str, params: dict[str, Any]):
    return (await db.execute(text(_SELECT.format(extra=extra)), params)).fetchall()


@router.get("/ticker")
async def get_ticker(
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    async with get_db() as db:
        pid: str | None = None
        eids: list[str] = []
        if user:
            prefs = await load_prefs(db, user["id"])
            if prefs:
                pid = prefs.get("primary_subject_id")
                eids = list((prefs.get("watchlist") or {}).get("entity_ids") or [])

        rows: list[Any] = []
        if pid:
            rows = await _rows(db, "AND EXISTS (SELECT 1 FROM article_entity_mentions m "
                                   "WHERE m.article_id = a.id AND m.entity_id = CAST(:pid AS uuid))",
                               {"pid": pid})
        if not rows and eids:
            rows = await _rows(db, "AND EXISTS (SELECT 1 FROM article_entity_mentions m "
                                   "WHERE m.article_id = a.id AND m.entity_id = ANY(CAST(:eids AS uuid[])))",
                               {"eids": eids})
        if not rows:
            rows = await _rows(db, "", {})

        items: list[dict[str, Any]] = [{
            "id": r.id, "title": r.title, "url": r.url, "source": r.source,
            "when": r.when_ts.isoformat() if r.when_ts is not None else None,
        } for r in rows]
        return {"items": items}
