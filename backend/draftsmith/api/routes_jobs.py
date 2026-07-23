"""backend.draftsmith.api.routes_jobs — POST/GET /jobs, GET /jobs/{id}, POST /jobs/{id}/cancel.

Creating a job enqueues backend.draftsmith.worker.run_job for that job_id —
via the Celery task when the box's Celery app was importable (production),
else an in-process asyncio background task (local/dev fallback; NOT durable
across a process restart, since nothing re-claims it — see worker.py's
module docstring on the two run modes).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from backend.draftsmith import db, worker
from backend.draftsmith.api._envelope import ApiError, ok
from backend.draftsmith.api.auth import get_editor_id
from backend.draftsmith.db._common import DraftsmithDBError
from backend.draftsmith.models import Dials, JobState

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["jobs"])

_CANCELLABLE_STATES: frozenset[JobState] = frozenset(
    {
        "queued", "planning", "gathering", "ranking", "drafting",
        "verifying", "repairing", "images", "ready", "failed",
    }
)


class DialsIn(BaseModel):
    creativity: int = 5
    moxy: int = 3
    length_target: int = 1200
    spot_check: bool = True


class CreateJobRequest(BaseModel):
    input_text: str = Field(..., min_length=1)
    dials: Optional[DialsIn] = None


def _dispatch(job_id: str) -> None:
    """Hand the job off to whichever run_job entrypoint is live in this
    process. Prefers Celery (durable, survives an API process restart);
    falls back to an in-process asyncio task only when no Celery app could
    be imported (dev convenience, not a production posture).

    NOTE (see worker.py's operational-gap comment): even when Celery IS
    importable, nothing consumes the 'draftsmith' queue until celery_app.py's
    include=[...] and start.sh gain a worker for it — until then, dispatched
    tasks queue up but never run. Explicit queue= here (not .delay()) so
    routing is correct the moment that consumer exists, without another code
    change.
    """
    if worker.run_job_task is not None:
        worker.run_job_task.apply_async(args=[job_id], queue="draftsmith")
        return
    logger.warning(
        "draftsmith: no Celery app importable — dispatching job %s via an "
        "in-process asyncio task (dev-only fallback, not durable across a "
        "process restart). Configure backend.celery_app for production.",
        job_id,
    )
    asyncio.create_task(worker.run_job(job_id))


@router.post("")
async def create_job(body: CreateJobRequest, editor_id: str = Depends(get_editor_id)) -> Any:
    dials = Dials.from_json(body.dials.model_dump() if body.dials else None)
    try:
        job = await db.create_job(editor_id, body.input_text, dials)
    except DraftsmithDBError as exc:
        raise ApiError(400, "invalid_job", str(exc)) from exc
    _dispatch(job.id)
    return ok(job, status_code=201)


@router.get("")
async def list_jobs(
    state: Optional[JobState] = Query(default=None),
    created_by: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _editor_id: str = Depends(get_editor_id),
) -> Any:
    jobs = await db.list_jobs(state=state, created_by=created_by, limit=limit, offset=offset)
    return ok(jobs)


@router.get("/{job_id}")
async def get_job(job_id: str, _editor_id: str = Depends(get_editor_id)) -> Any:
    job = await db.get_job(job_id)
    if job is None:
        raise ApiError(404, "job_not_found", f"no job with id {job_id}")
    return ok(job)


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str, _editor_id: str = Depends(get_editor_id)) -> Any:
    job = await db.get_job(job_id)
    if job is None:
        raise ApiError(404, "job_not_found", f"no job with id {job_id}")
    if job.state not in _CANCELLABLE_STATES:
        raise ApiError(
            409, "not_cancellable", f"job {job_id} is in terminal state {job.state!r}",
        )
    updated = await db.update_job_state(job_id, "cancelled")
    return ok(updated)
