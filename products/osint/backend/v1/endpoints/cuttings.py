"""Newspaper cuttings — full-text feed + single item.

Newspapers are a stored, store-everything pillar (unlike keyword-driven YouTube),
so they get a first-class feed and single-item endpoint with the FULL text (native
+ English) — parity with /articles.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request

from db import get_db

from .. import queries
from ..errors import bad_request, not_found, ok
from ..filters import CoverageFilters, coverage_filters
from ..scope import ApiContext, get_context
from ..serializers import serialize_cutting
from ..util import as_uuid

router = APIRouter(prefix="/v1", tags=["cuttings"])


@router.get("/cuttings", summary="Newspaper cuttings feed (full text), scoped")
async def list_cuttings(
    request: Request,
    ctx: ApiContext = Depends(get_context),
    filters: CoverageFilters = Depends(coverage_filters),
    before: str | None = Query(None, description="ISO timestamp cursor — return cuttings "
                               "collected strictly before this (from the previous page's next_before)"),
) -> dict:
    before_dt: datetime | None = None
    if before:
        try:
            before_dt = datetime.fromisoformat(before)
        except ValueError:
            raise bad_request("'before' must be an ISO-8601 timestamp")
    async with get_db() as db:
        rows = await queries.list_scoped_cuttings(
            db,
            entity_ids=list(ctx.scope.entity_ids),
            all_entities=ctx.scope.all_entities,
            regions=list(ctx.scope.regions),
            window_hours=filters.window_hours,
            language=filters.language,
            limit=filters.limit,
            before=before_dt,
        )
    # next_before cursor from the raw collected_at, before we drop it in serialization.
    next_before = None
    if len(rows) == filters.limit and rows:
        last = rows[-1].get("collected_at")
        next_before = last.isoformat() if hasattr(last, "isoformat") else None
    request.state.result_count = len(rows)
    return ok(
        [serialize_cutting(r) for r in rows],
        meta={"count": len(rows), "next_before": next_before},
    )


@router.get("/cuttings/{cutting_id}", summary="One newspaper cutting, full text")
async def get_cutting(
    cutting_id: str, request: Request, ctx: ApiContext = Depends(get_context)
) -> dict:
    cid = as_uuid(cutting_id)
    if cid is None:
        raise not_found()
    async with get_db() as db:
        row = await queries.cutting_full_by_id(
            db, cid, list(ctx.scope.entity_ids), ctx.scope.all_entities,
            regions=list(ctx.scope.regions),
        )
    if row is None:
        raise not_found()
    request.state.result_count = 1
    return ok(serialize_cutting(row))
