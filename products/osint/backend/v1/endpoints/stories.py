"""Stories endpoint — surfaceable grouped-intelligence (v9 clusters), scoped.

The flagship differentiator: the ≥3-independent-source, non-template story tier,
narrowed to the caller's provisioned scope (their entities and/or regions) exactly
like /articles — a Telangana govt org sees Telangana stories, a corporate org sees
its brand/competitor stories, never the global top-N.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from db import get_db

from .. import queries
from ..errors import not_found, ok
from ..scope import ApiContext, effective_entity_ids, get_context
from ..serializers import serialize_story, serialize_story_detail
from ..settings import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from ..util import as_uuid

router = APIRouter(prefix="/v1", tags=["stories"])


@router.get("/stories", summary="Surfaceable grouped stories (v9 clusters), scoped to your provisioning")
async def list_stories(
    request: Request,
    entity: list[str] | None = Query(
        None, description="Narrow to one or more of your entities (entity-only view)"),
    country: str | None = Query(
        None, min_length=2, max_length=2, description="ISO 2-letter subject country filter"),
    cursor: str | None = Query(None),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    ctx: ApiContext = Depends(get_context),
) -> dict:
    eids = effective_entity_ids(ctx.scope, tuple(entity) if entity else None)
    # Explicit ?entity= means "stories about these entities" — drop the region OR so the
    # narrowing is real. No ?entity => the org's whole world (scoped entities OR regions).
    regions = () if entity else ctx.scope.regions

    if not ctx.scope.all_entities and not eids and not regions:
        request.state.result_count = 0
        return ok([], meta={"count": 0, "next_cursor": None})

    async with get_db() as db:
        rows, next_cursor = await queries.list_scoped_stories(
            db,
            entity_ids=eids,
            all_entities=ctx.scope.all_entities,
            regions=regions,
            country=country,
            cursor=cursor,
            limit=limit,
            mute_terms=ctx.scope.mute_terms,
        )
    request.state.result_count = len(rows)
    return ok(
        [serialize_story(r) for r in rows],
        meta={"count": len(rows), "next_cursor": next_cursor},
    )


@router.get("/stories/{story_id}", summary="One story: metadata + timeline + outlet breakdown")
async def get_story(
    story_id: str,
    request: Request,
    limit: int = Query(60, ge=1, le=200, description="Max timeline (member) articles"),
    ctx: ApiContext = Depends(get_context),
) -> dict:
    sid = as_uuid(story_id)
    if sid is None:
        raise not_found()
    async with get_db() as db:
        data = await queries.story_detail(
            db,
            story_id=sid,
            entity_ids=list(ctx.scope.entity_ids),
            all_entities=ctx.scope.all_entities,
            regions=ctx.scope.regions,
            limit=limit,
        )
        if data is None:
            raise not_found()  # unknown / out-of-scope / unsurfaceable — identical 404
        # Full-field parity: enrich the member timeline to the same 16 fields as /articles.
        full = await queries.articles_full_by_ids(db, [t["id"] for t in data["timeline"]])
    data["timeline"] = [
        {**full[t["id"]], "is_representative": t.get("is_representative")}
        for t in data["timeline"] if t["id"] in full
    ]
    request.state.result_count = 1
    return ok(serialize_story_detail(data))
