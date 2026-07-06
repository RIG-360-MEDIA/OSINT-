"""GET /api/keywords/search — the Keyword Dossier.

One free-text keyword → unified cross-source intelligence (volume, sentiment,
top articles, cross-platform social, related entities). The flagship search.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import text

from db import get_db
from keyword_dossier import build_keyword_dossier
from tasking_brain import build_task_plan

router = APIRouter(prefix="/api/keywords", tags=["keywords"])


@router.get("/plan")
async def keyword_plan(
    q: str = Query(..., min_length=1, max_length=120, description="keyword/phrase"),
) -> dict[str, Any]:
    """The Tasking brain's decision: classify the keyword + the justified source plan."""
    async with get_db() as db:
        return await build_task_plan(db, q)


@router.get("/search")
async def keyword_search(
    q: str = Query(..., min_length=1, max_length=120, description="keyword/phrase"),
    days: int = Query(default=7, ge=1, le=90),
) -> dict[str, Any]:
    """Cross-source dossier for a keyword over the last `days`.

    The aggregation runs several trigram-indexed scans; raise the statement
    timeout above the 20s request default so wide windows complete. The Tasking
    brain's classification + source plan are merged in so the UI knows what the
    keyword IS and which sources are (or will be) searched.
    """
    async with get_db() as db:
        await db.execute(text("SET statement_timeout='30s'"))
        dossier = await build_keyword_dossier(db, q, days)
        plan = await build_task_plan(db, q)
        dossier["classification"] = plan["classification"]
        dossier["perspective_default"] = plan["perspective_default"]
        dossier["source_plan"] = plan["source_plan"]
        return dossier
