"""Analytics endpoints — directed sentiment + coverage volume, scoped."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from db import get_db

from .. import queries
from ..errors import bad_request, not_found, ok
from ..scope import ApiContext, get_context, require_entity_in_scope
from ..serializers import serialize_outlets, serialize_sentiment
from ..settings import DEFAULT_WINDOW_DAYS, MAX_WINDOW_DAYS
from ..util import as_uuid
from .keyword_sentiment import youtube_sentiment_for

router = APIRouter(prefix="/v1", tags=["analytics"])


@router.get("/analytics/topics", summary="Most-covered topics in your scope")
async def analytics_topics(
    request: Request,
    window: int = Query(DEFAULT_WINDOW_DAYS, ge=1, le=MAX_WINDOW_DAYS),
    limit: int = Query(10, ge=1, le=50),
    ctx: ApiContext = Depends(get_context),
) -> dict:
    async with get_db() as db:
        topics = await queries.topics_breakdown(
            db, list(ctx.scope.entity_ids), ctx.scope.all_entities, window * 24, limit
        )
    request.state.result_count = len(topics)
    return ok({"window_days": window, "topics": topics})


@router.get("/analytics/outlets", summary="Per-outlet coverage & lean toward an entity")
async def analytics_outlets(
    request: Request,
    entity: str = Query(..., description="Entity id whose per-outlet coverage to break down"),
    window: int = Query(DEFAULT_WINDOW_DAYS, ge=1, le=MAX_WINDOW_DAYS),
    limit: int = Query(20, ge=1, le=100),
    ctx: ApiContext = Depends(get_context),
) -> dict:
    eid = as_uuid(entity)
    if eid is None:
        raise bad_request("'entity' must be a valid entity id")
    require_entity_in_scope(ctx.scope, eid)  # out-of-scope => 404
    async with get_db() as db:
        row = await queries.get_entity_row(db, eid)
        if row is None:
            raise not_found()
        outlets = await queries.outlets_for_entity(db, eid, window * 24, limit)
    request.state.result_count = len(outlets)
    return ok(serialize_outlets(row["name"], outlets, window))


@router.get("/analytics/sentiment", summary="Directed sentiment toward an entity (name or id) + daily trend")
async def analytics_sentiment(
    request: Request,
    entity: str = Query(..., description="Entity id OR name to measure sentiment toward"),
    window: int = Query(DEFAULT_WINDOW_DAYS, ge=1, le=MAX_WINDOW_DAYS),
    include_youtube: bool = Query(False, description="Also live-score YouTube clips for this "
                                  "entity's name and add a 'youtube' pillar (slower; on-demand "
                                  "LLM, not pre-computed)"),
    ctx: ApiContext = Depends(get_context),
) -> dict:
    async with get_db() as db:
        eid = as_uuid(entity)
        if eid is not None:
            require_entity_in_scope(ctx.scope, eid)  # out-of-scope => 404
        else:
            eid = await queries.resolve_entity_by_name(
                db, entity, list(ctx.scope.entity_ids), ctx.scope.all_entities)
            if eid is None:
                raise not_found()  # unknown OR out-of-scope name — identical 404
        row = await queries.get_entity_row(db, eid)
        if row is None:
            raise not_found()
        split = await queries.sentiment_split(db, eid, window * 24)
        daily = await queries.sentiment_daily(db, eid, window * 24)
        if include_youtube:
            # keyword-driven YT sentiment for this entity's name (on-demand); scoped to
            # this entity's clip mentions unless the org sees everything. Added as its own
            # pillar — NOT folded into the pre-computed combined headline.
            eids = None if ctx.scope.all_entities else [eid]
            yt = await youtube_sentiment_for(db, row["name"], window, eids)
            split.setdefault("by_pillar", {})["youtube"] = yt
            # Strict on-demand: authorise transcript pulls for the clips just surfaced.
            if yt.get("clip_ids"):
                await queries.record_clip_grants(ctx.principal.org_id, yt["clip_ids"])
    request.state.result_count = split["total"]
    return ok(serialize_sentiment(split, row["name"], window, daily))


@router.get("/analytics/coverage", summary="Coverage volume over time")
async def analytics_coverage(
    request: Request,
    window: int = Query(DEFAULT_WINDOW_DAYS, ge=1, le=MAX_WINDOW_DAYS),
    ctx: ApiContext = Depends(get_context),
) -> dict:
    async with get_db() as db:
        data = await queries.coverage_daily(
            db, list(ctx.scope.entity_ids), ctx.scope.all_entities, window * 24
        )
    data["window_days"] = window
    request.state.result_count = data["total"]
    return ok(data)
