"""Dossier API — entity enrichment over free OSINT sources.

Endpoints:
    POST   /api/dossier/run              create + dispatch background run
    GET    /api/dossier/                  list current user's dossiers
    GET    /api/dossier/{id}              fetch dossier with findings
    POST   /api/dossier/{id}/refresh      wipe findings, re-run

Mounted only when DOSSIER_ENABLED=true (gated in main.py). Feature flag means
the router is invisible to existing API surface when disabled.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import text

from backend.auth.auth_middleware import get_current_user
from backend.database import get_db
from backend.dossier import audit
from backend.dossier.models import (
    DossierListItem,
    DossierOut,
    DossierRunRequest,
    FindingOut,
)
from backend.dossier.worker import run_dossier

log = logging.getLogger(__name__)

dossier_router = APIRouter(prefix="/api/dossier", tags=["dossier"])

_SENSITIVE_TYPES = {"image"}


@dossier_router.post("/run", response_model=DossierOut)
async def run(
    req: DossierRunRequest,
    background: BackgroundTasks,
    user: dict = Depends(get_current_user),
) -> DossierOut:
    user_id = user["id"]

    if req.target_type in _SENSITIVE_TYPES or req.allow_sensitive:
        if not (req.purpose_note and req.purpose_note.strip()):
            raise HTTPException(
                status_code=400,
                detail="purpose_note is required for sensitive sub-actions",
            )

    async with get_db() as db:
        result = await db.execute(
            text(
                """
                INSERT INTO entity_dossier
                    (user_id, target, target_type, status, purpose_note)
                VALUES
                    (:user_id, :target, :target_type, 'pending', :purpose_note)
                RETURNING id, target, target_type, status, summary, error,
                          purpose_note, started_at, completed_at, created_at
                """
            ),
            {
                "user_id": user_id,
                "target": req.target,
                "target_type": req.target_type,
                "purpose_note": req.purpose_note,
            },
        )
        row = result.mappings().one()
        await db.commit()

    dossier_id = row["id"]

    await audit.record(
        user_id=user_id,
        action="dossier.run",
        dossier_id=dossier_id,
        target=req.target,
        purpose_note=req.purpose_note,
        metadata={"target_type": req.target_type, "allow_sensitive": req.allow_sensitive},
    )

    background.add_task(
        run_dossier,
        dossier_id=dossier_id,
        target=req.target,
        target_type=req.target_type,
        purpose_note=req.purpose_note,
        allow_sensitive=req.allow_sensitive,
    )

    return DossierOut(**dict(row), findings=[])


@dossier_router.get("/", response_model=list[DossierListItem])
async def list_dossiers(
    user: dict = Depends(get_current_user),
    limit: int = 50,
) -> list[DossierListItem]:
    user_id = user["id"]
    limit = max(1, min(limit, 200))
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT
                    d.id, d.target, d.target_type, d.status,
                    d.created_at, d.completed_at,
                    COALESCE(f.cnt, 0) AS finding_count
                FROM entity_dossier d
                LEFT JOIN (
                    SELECT dossier_id, COUNT(*)::int AS cnt
                    FROM dossier_finding
                    GROUP BY dossier_id
                ) f ON f.dossier_id = d.id
                WHERE d.user_id = :user_id
                ORDER BY d.created_at DESC
                LIMIT :limit
                """
            ),
            {"user_id": user_id, "limit": limit},
        )
        rows = result.mappings().all()
    return [DossierListItem(**dict(r)) for r in rows]


@dossier_router.get("/{dossier_id}", response_model=DossierOut)
async def get_dossier(
    dossier_id: UUID,
    user: dict = Depends(get_current_user),
) -> DossierOut:
    user_id = user["id"]
    async with get_db() as db:
        d_result = await db.execute(
            text(
                """
                SELECT id, target, target_type, status, summary, error,
                       purpose_note, started_at, completed_at, created_at
                FROM entity_dossier
                WHERE id = :id AND user_id = :user_id
                """
            ),
            {"id": str(dossier_id), "user_id": user_id},
        )
        d_row = d_result.mappings().first()
        if not d_row:
            raise HTTPException(status_code=404, detail="dossier not found")

        f_result = await db.execute(
            text(
                """
                SELECT source, field, value, source_url, confidence, found_at
                FROM dossier_finding
                WHERE dossier_id = :id
                ORDER BY confidence DESC, found_at ASC
                """
            ),
            {"id": str(dossier_id)},
        )
        f_rows = f_result.mappings().all()

    findings = [FindingOut(**dict(r)) for r in f_rows]
    return DossierOut(**dict(d_row), findings=findings)


@dossier_router.post("/{dossier_id}/refresh", response_model=DossierOut)
async def refresh_dossier(
    dossier_id: UUID,
    background: BackgroundTasks,
    user: dict = Depends(get_current_user),
) -> DossierOut:
    user_id = user["id"]
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT id, target, target_type, purpose_note
                FROM entity_dossier
                WHERE id = :id AND user_id = :user_id
                """
            ),
            {"id": str(dossier_id), "user_id": user_id},
        )
        row = result.mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="dossier not found")

        await db.execute(
            text("DELETE FROM dossier_finding WHERE dossier_id = :id"),
            {"id": str(dossier_id)},
        )
        await db.execute(
            text(
                """
                UPDATE entity_dossier
                SET status = 'pending', summary = NULL, error = NULL,
                    started_at = NULL, completed_at = NULL, updated_at = NOW()
                WHERE id = :id
                """
            ),
            {"id": str(dossier_id)},
        )
        await db.commit()

    await audit.record(
        user_id=user_id,
        action="dossier.refresh",
        dossier_id=dossier_id,
        target=row["target"],
    )

    background.add_task(
        run_dossier,
        dossier_id=dossier_id,
        target=row["target"],
        target_type=row["target_type"],
        purpose_note=row["purpose_note"],
        allow_sensitive=False,
    )

    return await get_dossier(dossier_id, user)
