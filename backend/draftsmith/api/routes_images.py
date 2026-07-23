"""backend.draftsmith.api.routes_images — POST /jobs/{id}/images/select.

Selecting a `origin='web'` candidate requires `acknowledged=true` in the
body — those images always carry `needs_license_review=true`
(migrations/001_draftsmith.sql), and the editor must explicitly confirm
they've seen that before it becomes the job's hero image.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text

from backend.database import get_db
from backend.draftsmith import db
from backend.draftsmith._db_serialize import image_candidate_from_row
from backend.draftsmith.api._envelope import ApiError, ok
from backend.draftsmith.api.auth import get_editor_id
from backend.draftsmith.db._common import DraftsmithDBError
from backend.draftsmith.models import ImageCandidate

router = APIRouter(prefix="/jobs", tags=["images"])


class SelectImageRequest(BaseModel):
    slot: int = Field(..., ge=1, le=6)
    acknowledged: bool = False


async def _get_candidate(job_id: str, slot: int) -> Optional[ImageCandidate]:
    async with get_db() as session:
        result = await session.execute(
            text(
                "SELECT * FROM rigwire.draft_images WHERE job_id = :job_id AND slot = :slot"
            ),
            {"job_id": job_id, "slot": slot},
        )
        row = result.mappings().first()
    return image_candidate_from_row(row) if row else None


@router.post("/{job_id}/images/select")
async def select_image(
    job_id: str, body: SelectImageRequest, _editor_id: str = Depends(get_editor_id),
) -> Any:
    candidate = await _get_candidate(job_id, body.slot)
    if candidate is None:
        raise ApiError(
            404, "image_not_found", f"no image candidate for job {job_id} slot {body.slot}",
        )
    if candidate.origin == "web" and not body.acknowledged:
        raise ApiError(
            422,
            "license_ack_required",
            "this candidate's origin is 'web' (needs_license_review) — "
            "resend with acknowledged=true to confirm the license has been reviewed",
        )
    try:
        selected = await db.select_image(job_id, body.slot)
    except DraftsmithDBError as exc:
        raise ApiError(409, "select_image_failed", str(exc)) from exc
    return ok(selected)
