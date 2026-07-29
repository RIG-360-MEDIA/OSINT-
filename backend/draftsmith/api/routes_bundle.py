"""backend.draftsmith.api.routes_bundle — list reads the CMS needs to assemble
the review bundle (flags / images / all evidence). Additive; returns the same
dataclasses the rest of the API already uses, so shapes match the wire contract.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text

from backend.database import get_db
from backend.draftsmith import db
from backend.draftsmith._db_serialize import flag_from_row, image_candidate_from_row
from backend.draftsmith.api._envelope import ok
from backend.draftsmith.api.auth import get_editor_id

router = APIRouter(prefix="/jobs", tags=["bundle"])


@router.get("/{job_id}/flags")
async def list_flags(job_id: str, _editor_id: str = Depends(get_editor_id)) -> Any:
    async with get_db() as session:
        result = await session.execute(
            text("SELECT * FROM rigwire.draft_flags WHERE job_id = :j ORDER BY beat_index, id"),
            {"j": job_id},
        )
        rows = result.mappings().all()
    return ok([flag_from_row(r) for r in rows])


@router.get("/{job_id}/images")
async def list_images(job_id: str, _editor_id: str = Depends(get_editor_id)) -> Any:
    async with get_db() as session:
        result = await session.execute(
            text("SELECT * FROM rigwire.draft_images WHERE job_id = :j ORDER BY slot"),
            {"j": job_id},
        )
        rows = result.mappings().all()
    return ok([image_candidate_from_row(r) for r in rows])


@router.get("/{job_id}/evidence")
async def list_evidence(job_id: str, _editor_id: str = Depends(get_editor_id)) -> Any:
    items = await db.select_evidence(job_id)  # no source_ids -> every row for the job
    return ok(items)
