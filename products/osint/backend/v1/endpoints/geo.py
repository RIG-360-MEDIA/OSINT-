"""Geography endpoints — district-level coverage, scoped.

Backed by the night-desk district gazetteer (`districts` + `article_districts`),
which currently covers Telangana + Andhra Pradesh (India, source_country='IN').
A govt org provisioned with region 'Telangana' sees Telangana districts; district
detail is 404 for out-of-scope states (no cross-scope probing).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from db import get_db

from .. import queries
from ..errors import not_found, ok
from ..scope import ApiContext, get_context
from ..serializers import serialize_article
from ..settings import DEFAULT_WINDOW_DAYS, MAX_WINDOW_DAYS

router = APIRouter(prefix="/v1", tags=["geography"])

# Region name -> Indian state_code (mirrors night-desk map_page.STATE_CODE).
_STATE_CODE = {
    "andhra pradesh": "AP", "telangana": "TG", "karnataka": "KA", "tamil nadu": "TN",
    "kerala": "KL", "maharashtra": "MH", "delhi": "DL", "uttar pradesh": "UP",
    "west bengal": "WB", "gujarat": "GJ", "rajasthan": "RJ", "madhya pradesh": "MP",
    "bihar": "BR", "odisha": "OD", "punjab": "PB", "haryana": "HR", "goa": "GA",
}


def _scoped_state_codes(regions: tuple[str, ...]) -> list[str]:
    """Map the org's provisioned region names to Indian state codes (2-letter codes pass through)."""
    codes: set[str] = set()
    for r in regions or ():
        s = str(r).strip()
        c = _STATE_CODE.get(s.lower())
        if c:
            codes.add(c)
        elif len(s) == 2:
            codes.add(s.upper())
    return list(codes)


@router.get("/geo/coverage", summary="District-level coverage counts by state, scoped")
async def geo_coverage(
    request: Request,
    window: int = Query(DEFAULT_WINDOW_DAYS, ge=1, le=MAX_WINDOW_DAYS),
    ctx: ApiContext = Depends(get_context),
) -> dict:
    state_codes = _scoped_state_codes(ctx.scope.regions)
    # Region takes precedence for geo (a Telangana org sees Telangana, not entity-tagged
    # districts elsewhere); fall back to entity scope only when the org has no regions.
    eids = [] if state_codes else list(ctx.scope.entity_ids)
    if not ctx.scope.all_entities and not eids and not state_codes:
        request.state.result_count = 0
        return ok({"window_days": window, "states": []})
    async with get_db() as db:
        states = await queries.geo_coverage(
            db,
            entity_ids=eids,
            all_entities=ctx.scope.all_entities,
            state_codes=state_codes,
            window_hours=window * 24,
        )
    request.state.result_count = sum(s["articles"] for s in states)
    return ok({"window_days": window, "states": states})


@router.get("/geo/district/{district_id}", summary="Coverage for one district (slug)")
async def geo_district(
    district_id: str,
    request: Request,
    window: int = Query(DEFAULT_WINDOW_DAYS, ge=1, le=MAX_WINDOW_DAYS),
    limit: int = Query(20, ge=1, le=100),
    ctx: ApiContext = Depends(get_context),
) -> dict:
    async with get_db() as db:
        data = await queries.geo_district(db, district_id, window * 24, limit)
        if data is None:
            raise not_found()
        # Scope guard: the district's state must be in the caller's scope (or all_entities).
        if not ctx.scope.all_entities and data["state_code"] not in set(_scoped_state_codes(ctx.scope.regions)):
            raise not_found()  # out-of-scope district — identical 404
        # Full-field parity: enrich recent items to the same 16 fields as /articles.
        full = await queries.articles_full_by_ids(db, [r["id"] for r in data["recent"]])
    data["recent"] = [serialize_article(full[r["id"]]) for r in data["recent"] if r["id"] in full]
    request.state.result_count = data["articles"]
    return ok(data)
