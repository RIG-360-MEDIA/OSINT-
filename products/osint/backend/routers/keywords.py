"""GET /api/keywords/search — the Keyword Dossier.

One free-text keyword → unified cross-source intelligence (volume, sentiment,
top articles, cross-platform social, related entities). The flagship search.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from auth.middleware import get_optional_user
from db import get_db
from keyword_dossier import build_keyword_dossier
from keyword_alerts import evaluate_watch
from keyword_tracking import list_alerts, list_tracked, track_keyword, untrack_keyword
from perspective import build_perspective
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


@router.get("/perspective")
async def perspective(
    q: str = Query(..., min_length=1, max_length=120),
    days: int = Query(default=7, ge=1, le=90),
) -> dict[str, Any]:
    """Perspective Lens — framing divergence across languages/origins for a keyword."""
    async with get_db() as db:
        await db.execute(text("SET statement_timeout='30s'"))
        return await build_perspective(db, q, days)


@router.post("/track")
async def track(
    q: str = Query(..., min_length=1, max_length=120),
    days: int = Query(default=7, ge=1, le=90),
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    """Track a keyword for the authenticated user → standing watch for alerts."""
    if not user:
        raise HTTPException(status_code=401, detail="auth required to track")
    async with get_db() as db:
        plan = await build_task_plan(db, q)
        wid = await track_keyword(db, user["id"], q, plan["classification"],
                                  plan["perspective_default"], days)
        return {"tracked": True, "watch_id": wid, "keyword": q,
                "classification": plan["classification"]}


@router.delete("/track")
async def untrack(
    q: str = Query(..., min_length=1, max_length=120),
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    if not user:
        raise HTTPException(status_code=401, detail="auth required")
    async with get_db() as db:
        changed = await untrack_keyword(db, user["id"], q)
        return {"untracked": changed, "keyword": q}


@router.get("/tracked")
async def tracked(
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    """List the user's tracked keywords + unseen-alert counts."""
    if not user:
        return {"tracked": []}
    async with get_db() as db:
        return {"tracked": await list_tracked(db, user["id"])}


@router.get("/alerts")
async def alerts(
    unseen: bool = Query(default=False),
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    """Alerts across the user's tracked keywords (newest first)."""
    if not user:
        return {"alerts": []}
    async with get_db() as db:
        return {"alerts": await list_alerts(db, user["id"], unseen)}
