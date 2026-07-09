"""YouTube clip transcript — strict on-demand.

A full transcript is served ONLY for a clip the caller surfaced via a keyword or
entity query within the grant window (analytics.api_clip_grants). This keeps
YouTube keyword-driven: no bulk feed, no browsing — a client can read the full
transcript of a clip its own query returned, and nothing else. An unknown clip,
or one never surfaced to this org (or whose grant expired), returns an identical
404 so the endpoint is not an existence oracle.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from db import get_db

from .. import queries
from ..errors import not_found, ok
from ..scope import ApiContext, get_context
from ..serializers import serialize_clip_transcript
from ..settings import CLIP_GRANT_WINDOW_HOURS

router = APIRouter(prefix="/v1", tags=["clips"])


@router.get("/clips/{clip_id}",
            summary="Full transcript of a clip you surfaced (strict on-demand)")
async def get_clip_transcript(
    clip_id: str, request: Request, ctx: ApiContext = Depends(get_context)
) -> dict:
    async with get_db() as db:
        # The ONLY authorisation: this org surfaced this clip via a recent query.
        if not await queries.clip_grant_fresh(
            db, ctx.principal.org_id, clip_id, CLIP_GRANT_WINDOW_HOURS
        ):
            raise not_found()
        row = await queries.clip_transcript_by_id(db, clip_id)
    if row is None:
        raise not_found()
    request.state.result_count = 1
    return ok(serialize_clip_transcript(row))
