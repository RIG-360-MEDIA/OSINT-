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

router = APIRouter(prefix="/api/keywords", tags=["keywords"])


@router.get("/search")
async def keyword_search(
    q: str = Query(..., min_length=1, max_length=120, description="keyword/phrase"),
    days: int = Query(default=7, ge=1, le=90),
) -> dict[str, Any]:
    """Cross-source dossier for a keyword over the last `days`.

    The aggregation runs several trigram-indexed scans; raise the statement
    timeout above the 20s request default so wide windows complete.
    """
    async with get_db() as db:
        await db.execute(text("SET statement_timeout='30s'"))
        return await build_keyword_dossier(db, q, days)
