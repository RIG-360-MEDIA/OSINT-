"""Analytics endpoints — directed sentiment + coverage volume, scoped."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from db import get_db

from .. import queries
from ..errors import bad_request, not_found, ok
from ..scope import ApiContext, get_context, require_entity_in_scope
from ..serializers import serialize_sentiment
from ..settings import DEFAULT_WINDOW_DAYS, MAX_WINDOW_DAYS
from ..util import as_uuid

router = APIRouter(prefix="/v1", tags=["analytics"])


@router.get("/analytics/sentiment", summary="Directed sentiment toward an entity")
async def analytics_sentiment(
    request: Request,
    entity: str = Query(..., description="Entity id to measure sentiment toward"),
    window: int = Query(DEFAULT_WINDOW_DAYS, ge=1, le=MAX_WINDOW_DAYS),
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
        split = await queries.sentiment_split(db, eid, window * 24)
    request.state.result_count = split["total"]
    return ok(serialize_sentiment(split, row["name"], window))


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
