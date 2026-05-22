"""
Super-admin observability endpoints powering the `/observe` page.

All endpoints require the caller's *real* identity to be a super_admin via
`require_super_admin` (impersonation cannot grant access — same pattern as
backend/routers/rbac_admin_router.py).

Owned by: backend/routers/observe_router.py.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text  # noqa: F401  (re-exported for tests)

from backend.auth.auth_middleware import require_super_admin
from backend.database import get_db
from backend.observability.article_quality import (
    crosstab,
    geo_heatmap,
    ingest_pulse,
    live_tail,
    quality_monitor,
    source_scorecard,
    story_pulse,
)
from backend.observability.audit_queue import audit_queue, record_decision

logger = logging.getLogger(__name__)

observe_router = APIRouter(
    prefix="/api/observe",
    tags=["observe"],
    dependencies=[Depends(require_super_admin)],
)


# ── Request models ────────────────────────────────────────────────────────────

class AuditDecisionRequest(BaseModel):
    article_id: str
    field_name: str
    extraction_version: int
    verdict: str = Field(..., pattern="^(correct|wrong|unsure)$")
    note: str | None = None


# ── 1. Ingest pulse ──────────────────────────────────────────────────────────

@observe_router.get("/ingest-pulse")
async def get_ingest_pulse(_p: dict = Depends(require_super_admin)) -> dict:
    async with get_db() as db:
        return await ingest_pulse(db)


# ── 2. Source scorecard ──────────────────────────────────────────────────────

@observe_router.get("/source-scorecard")
async def get_source_scorecard(_p: dict = Depends(require_super_admin)) -> dict:
    async with get_db() as db:
        return await source_scorecard(db)


# ── 3. Quality monitor ───────────────────────────────────────────────────────

@observe_router.get("/quality-monitor")
async def get_quality_monitor(_p: dict = Depends(require_super_admin)) -> dict:
    async with get_db() as db:
        return await quality_monitor(db)


# ── 4. Geo heatmap ───────────────────────────────────────────────────────────

@observe_router.get("/geo-heatmap")
async def get_geo_heatmap(
    level: str = Query("country", pattern="^(country|state|district)$"),
    _p: dict = Depends(require_super_admin),
) -> dict:
    async with get_db() as db:
        return await geo_heatmap(db, level=level)


# ── 5. Story pulse ───────────────────────────────────────────────────────────

@observe_router.get("/story-pulse")
async def get_story_pulse(
    limit: int = Query(30, ge=1, le=200),
    _p: dict = Depends(require_super_admin),
) -> dict:
    async with get_db() as db:
        return await story_pulse(db, limit=limit)


# ── 6. Cross-tab ─────────────────────────────────────────────────────────────

@observe_router.get("/crosstab")
async def get_crosstab(
    actor: str | None = Query(None, max_length=120),
    time_window_days: int = Query(30, ge=1, le=365),
    _p: dict = Depends(require_super_admin),
) -> dict:
    async with get_db() as db:
        return await crosstab(db, actor=actor, time_window_days=time_window_days)


# ── 7. Live tail ─────────────────────────────────────────────────────────────

@observe_router.get("/live-tail")
async def get_live_tail(
    after: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    _p: dict = Depends(require_super_admin),
) -> dict:
    async with get_db() as db:
        return await live_tail(db, after=after, limit=limit)


# ── 8. Audit queue ───────────────────────────────────────────────────────────

@observe_router.get("/audit-queue")
async def get_audit_queue(
    limit: int = Query(30, ge=1, le=200),
    _p: dict = Depends(require_super_admin),
) -> dict:
    async with get_db() as db:
        return await audit_queue(db, limit=limit)


@observe_router.post("/audit-decision")
async def post_audit_decision(
    body: AuditDecisionRequest,
    principal: dict = Depends(require_super_admin),
) -> dict:
    decided_by = principal.get("user_id") or principal.get("id")
    try:
        async with get_db() as db:
            result = await record_decision(
                db,
                article_id=body.article_id,
                field_name=body.field_name,
                extraction_version=body.extraction_version,
                verdict=body.verdict,
                note=body.note,
                decided_by=decided_by,
            )
        return {"ok": True, **result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
