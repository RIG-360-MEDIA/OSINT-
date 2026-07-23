"""backend.draftsmith.api.routes_flags — POST /jobs/{id}/flags/{flag_id}.

Resolves exactly ONE flag per call — the DB's draft_flags_single_resolve
trigger (migrations/001_draftsmith.sql) independently enforces this at the
statement level, so this route can never be the sole guard against a
bulk-acknowledge-as-auto-publish shortcut, but it keeps the API surface
matching that guarantee (one flag_id per request body, no bulk-array shape).
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from backend.database import get_db
from backend.draftsmith import db
from backend.draftsmith.api._envelope import ApiError, ok
from backend.draftsmith.api.auth import get_editor_id
from backend.draftsmith.db._common import DraftsmithDBError

router = APIRouter(prefix="/jobs", tags=["flags"])


class ResolveFlagRequest(BaseModel):
    action: Literal["dismissed", "fixed"]
    note: Optional[str] = None


async def _flag_belongs_to_job(flag_id: str, job_id: str) -> bool:
    """db.resolve_flag() only takes a flag_id — it has no job_id to cross-
    check. Guard here against a copy-pasted URL silently resolving a flag
    that belongs to a DIFFERENT job than the one in the path."""
    async with get_db() as session:
        result = await session.execute(
            text("SELECT job_id FROM rigwire.draft_flags WHERE id = :flag_id"),
            {"flag_id": flag_id},
        )
        row = result.mappings().first()
    return row is not None and str(row["job_id"]) == job_id


@router.post("/{job_id}/flags/{flag_id}")
async def resolve_flag(
    job_id: str, flag_id: str, body: ResolveFlagRequest, editor_id: str = Depends(get_editor_id),
) -> Any:
    if not await _flag_belongs_to_job(flag_id, job_id):
        raise ApiError(404, "flag_not_found", f"no flag {flag_id} on job {job_id}")
    try:
        flag = await db.resolve_flag(flag_id, body.action, editor_id, body.note)
    except DraftsmithDBError as exc:
        raise ApiError(409, "flag_resolve_failed", str(exc)) from exc
    return ok(flag)
