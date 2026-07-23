"""backend.draftsmith.api.routes_draft — the draft-review surface.

GET  /jobs/{id}/draft                 — latest DraftVersion
GET  /jobs/{id}/evidence/{source_id}  — one frozen evidence snapshot
POST /jobs/{id}/edit                  — editor overwrite -> new 'editor' version
POST /jobs/{id}/verify                — on-demand re-verify of the latest draft
POST /jobs/{id}/finalize              — 422 if any RED flag is still open;
                                         else returns models.PublishPayload
POST /jobs/{id}/published             — CMS confirms its Neon write landed;
                                         records the box-side publish audit
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.draftsmith import config, db
from backend.draftsmith._verify_flags import flags_from_report
from backend.draftsmith.api import _brief, _finalize
from backend.draftsmith.api._envelope import ApiError, ok
from backend.draftsmith.api.auth import get_editor_id
from backend.draftsmith.db._common import DraftsmithDBError
from backend.draftsmith.models import (
    Draft,
    DraftBeat,
    DraftVersion,
    KeyFact,
    PublishPayload,
    PullQuote,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["draft"])


# --- request bodies ----------------------------------------------------------

class DraftBeatIn(BaseModel):
    subhead: str
    text: str
    source_ids: list[str] = Field(default_factory=list)


class KeyFactIn(BaseModel):
    fact: str
    source_ids: list[str] = Field(default_factory=list)


class PullQuoteIn(BaseModel):
    text: str
    speaker: str = ""
    source_id: str = ""


class EditDraftRequest(BaseModel):
    headline: str = Field(..., min_length=1)
    dek: str = ""
    beats: list[DraftBeatIn] = Field(..., min_length=1)
    key_facts: list[KeyFactIn] = Field(default_factory=list)
    pull_quote: Optional[PullQuoteIn] = None
    unsourced_gaps: list[str] = Field(default_factory=list)


class PublishedRequest(BaseModel):
    neon_story_id: str = Field(..., min_length=1)
    version: int = Field(..., ge=1)


# --- routes -------------------------------------------------------------------

@router.get("/{job_id}/draft")
async def get_draft(job_id: str, _editor_id: str = Depends(get_editor_id)) -> Any:
    stored = await db.latest_version(job_id)
    if stored is None:
        raise ApiError(404, "no_draft", f"job {job_id} has no draft version yet")
    return ok(stored)


@router.get("/{job_id}/evidence/{source_id}")
async def get_evidence(job_id: str, source_id: str, _editor_id: str = Depends(get_editor_id)) -> Any:
    items = await db.select_evidence(job_id, [source_id])
    if not items:
        raise ApiError(404, "evidence_not_found", f"no evidence {source_id} for job {job_id}")
    return ok(items[0])


@router.post("/{job_id}/edit")
async def edit_draft(
    job_id: str, body: EditDraftRequest, editor_id: str = Depends(get_editor_id),
) -> Any:
    job = await db.get_job(job_id)
    if job is None:
        raise ApiError(404, "job_not_found", f"no job with id {job_id}")
    stored = await db.latest_version(job_id)
    if stored is None:
        raise ApiError(409, "no_draft", f"job {job_id} has no draft version yet")

    draft = Draft(
        headline=body.headline,
        dek=body.dek,
        beats=tuple(DraftBeat(**beat.model_dump()) for beat in body.beats),
        key_facts=tuple(KeyFact(**fact.model_dump()) for fact in body.key_facts),
        pull_quote=PullQuote(**body.pull_quote.model_dump()) if body.pull_quote else None,
        unsourced_gaps=tuple(body.unsourced_gaps),
    )
    new_version = DraftVersion(
        version=stored.version.version + 1,
        kind="editor",
        draft=draft,
        # Unverified until POST /verify runs again — an editor edit can
        # introduce exactly the kind of unsupported claim verify exists to
        # catch, so we never carry the OLD verify_report forward onto it.
        verify_report=None,
        created_by=editor_id,
    )
    saved = await db.save_version(job_id, new_version)
    return ok(saved, status_code=201)


@router.post("/{job_id}/verify")
async def verify_draft(job_id: str, _editor_id: str = Depends(get_editor_id)) -> Any:
    job = await db.get_job(job_id)
    if job is None:
        raise ApiError(404, "job_not_found", f"no job with id {job_id}")
    stored = await db.latest_version(job_id)
    if stored is None:
        raise ApiError(409, "no_draft", f"job {job_id} has no draft version yet")

    # backend.draftsmith.stages re-exports the FUNCTION `verify`, not a
    # `verify` submodule — `from ... import verify` binds the callable
    # directly (stages/__init__.py's `from .verify import verify` shadows
    # the submodule attribute; see worker.py's module docstring for the
    # same pattern with stages.plan / stages.rank / etc.).
    from backend.draftsmith.stages import verify as run_verify

    evidence = await _brief.selected_evidence(job_id)
    brief = _brief.rebuild_brief(job.query_plan, evidence)
    try:
        report = await asyncio.wait_for(
            run_verify(brief, stored.version.draft), timeout=config.TIMEOUTS["verify"],
        )
    except Exception as exc:  # noqa: BLE001
        raise ApiError(502, "verify_failed", f"verify stage failed: {exc}") from exc

    updated_version = DraftVersion(
        version=stored.version.version,
        kind=stored.version.kind,
        draft=stored.version.draft,
        verify_report=report,
        created_by=stored.version.created_by,
    )
    saved = await db.save_version(job_id, updated_version)
    flags = flags_from_report(report)
    if flags:
        await db.create_flags(job_id, saved.id, flags)
    return ok(saved)


@router.post("/{job_id}/finalize")
async def finalize_job(job_id: str, _editor_id: str = Depends(get_editor_id)) -> Any:
    job = await db.get_job(job_id)
    if job is None:
        raise ApiError(404, "job_not_found", f"no job with id {job_id}")
    if job.state != "ready":
        raise ApiError(409, "not_ready", f"job {job_id} is in state {job.state!r}, not 'ready'")
    stored = await db.latest_version(job_id)
    if stored is None:
        raise ApiError(409, "no_draft", f"job {job_id} has no draft version")

    red_open = await _finalize.count_open_red_flags(job_id)
    if red_open > 0:
        raise ApiError(
            422, "red_flags_open",
            f"{red_open} open red flag(s) must be resolved before finalize",
        )

    draft = stored.version.draft
    body_markdown = await _finalize.render_body_markdown(job_id, draft)
    image = await _finalize.selected_image(job_id)
    summary = await _finalize.flags_summary(job_id)

    payload = PublishPayload(
        job_id=job_id,
        version=stored.version.version,
        headline=draft.headline,
        dek=draft.dek,
        body_markdown=body_markdown,
        topic=job.query_plan.topic_summary if job.query_plan else "",
        country=(job.query_plan.geo_hints[0] if job.query_plan and job.query_plan.geo_hints else None),
        image_url=image.url if image else None,
        importance_suggested=0.5,
        flags_summary=summary,
    )
    return ok(payload)


@router.post("/{job_id}/published")
async def mark_published(
    job_id: str, body: PublishedRequest, editor_id: str = Depends(get_editor_id),
) -> Any:
    job = await db.get_job(job_id)
    if job is None:
        raise ApiError(404, "job_not_found", f"no job with id {job_id}")
    stored = await db.latest_version(job_id)
    if stored is None or stored.version.version != body.version:
        raise ApiError(
            409, "version_mismatch",
            "the version being confirmed no longer matches the job's latest draft version",
        )
    summary = await _finalize.flags_summary(job_id)
    try:
        await db.record_publish(job_id, stored.id, body.neon_story_id, editor_id, summary)
    except DraftsmithDBError as exc:
        raise ApiError(409, "publish_failed", str(exc)) from exc
    updated = await db.get_job(job_id)
    return ok(updated)
