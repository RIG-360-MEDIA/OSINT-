"""Entity endpoints — list the org's entities, profile one, its coverage."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from db import get_db

from .. import queries
from ..errors import not_found, ok
from ..filters import CoverageFilters, coverage_filters
from ..scope import ApiContext, get_context, require_entity_in_scope
from ..serializers import serialize_article, serialize_coverage_item, serialize_entity
from ..settings import DEFAULT_WINDOW_DAYS
from ..util import as_uuid

router = APIRouter(prefix="/v1", tags=["entities"])

_SNAPSHOT_HOURS = DEFAULT_WINDOW_DAYS * 24

# pillar query value -> the internal pillar keys to union.
_PILLAR_MAP = {
    "all": ["article", "clip", "cutting"],
    "articles": ["article"],
    "clips": ["clip"],
    "cuttings": ["cutting"],
}


@router.get("/entities", summary="List your provisioned entities")
async def list_entities(request: Request, ctx: ApiContext = Depends(get_context)) -> dict:
    async with get_db() as db:
        rows = await queries.list_scoped_entities(
            db, list(ctx.scope.entity_ids), ctx.scope.all_entities, limit=500
        )
    request.state.result_count = len(rows)
    return ok([serialize_entity(r) for r in rows], meta={"count": len(rows)})


@router.get("/entities/{entity_id}", summary="Profile of one entity")
async def get_entity(entity_id: str, request: Request, ctx: ApiContext = Depends(get_context)) -> dict:
    eid = as_uuid(entity_id)
    if eid is None:
        raise not_found()
    require_entity_in_scope(ctx.scope, eid)  # out-of-scope => identical 404
    async with get_db() as db:
        row = await queries.get_entity_row(db, eid)
        if row is None:
            raise not_found()
        coverage = await queries.entity_coverage_count(db, eid, _SNAPSHOT_HOURS)
        sent = await queries.sentiment_split(db, eid, _SNAPSHOT_HOURS)
    request.state.result_count = 1
    data = serialize_entity(row)
    data["snapshot"] = {
        "coverage_7d": coverage,
        "sentiment_7d": {
            "supportive": sent["supportive"],
            "neutral": sent["neutral"],
            "critical": sent["critical"],
        },
    }
    return ok(data)


@router.get("/entities/{entity_id}/coverage", summary="All coverage about one entity (articles + clips + cuttings)")
async def entity_coverage(
    entity_id: str,
    request: Request,
    ctx: ApiContext = Depends(get_context),
    filters: CoverageFilters = Depends(coverage_filters),
    pillar: str = Query("all", pattern="^(all|articles|clips|cuttings)$",
                        description="Which pillars to include"),
) -> dict:
    eid = as_uuid(entity_id)
    if eid is None:
        raise not_found()
    require_entity_in_scope(ctx.scope, eid)  # out-of-scope => identical 404
    pillars = _PILLAR_MAP[pillar]
    async with get_db() as db:
        rows = await queries.entity_multi_coverage(
            db,
            entity_id=eid,
            window_hours=filters.window_hours,
            language=filters.language,
            pillars=pillars,
            limit=filters.limit,
        )
        # Full-field parity: article items get the same 16 fields as /articles;
        # clips/cuttings keep their (genuinely different) coverage-item shape.
        full = await queries.articles_full_by_ids(
            db, [r["id"] for r in rows if r.get("type") == "article"]
        )

    # Strict on-demand: entity coverage is a surfacing path too — authorise transcript
    # pulls for any clips it just returned to this org.
    clip_ids = [r["id"] for r in rows if r.get("type") == "clip" and r.get("id")]
    if clip_ids:
        await queries.record_clip_grants(ctx.principal.org_id, clip_ids)

    def _ser(r: dict) -> dict:
        if r.get("type") == "article" and r["id"] in full:
            return {"type": "article", **serialize_article(full[r["id"]])}
        return serialize_coverage_item(r)

    request.state.result_count = len(rows)
    return ok(
        [_ser(r) for r in rows],
        meta={"count": len(rows), "pillars": pillars},
    )
