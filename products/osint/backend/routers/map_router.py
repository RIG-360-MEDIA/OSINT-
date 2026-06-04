"""Situation-Map endpoint — persona-scoped district/state bubbles, served from cache."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from auth.middleware import get_optional_user
from brief_prefs import load_prefs
from db import get_db
from home_cache import get_page
from map_page import build_map, STATE_CODE
import district as district_mod
import country as country_mod
import live_channels

router = APIRouter(prefix="/api/brief", tags=["brief"])


def _allowed_states(prefs) -> set[str]:
    return {STATE_CODE.get((s or "").strip().lower()) for s in (prefs.get("regions") or {}).get("states", [])} - {None}


def _primary_state(prefs) -> str:
    """The persona's primary state code (order-preserving), default AP."""
    for s in (prefs.get("regions") or {}).get("states", []):
        code = STATE_CODE.get((s or "").strip().lower())
        if code:
            return code
    return "AP"


async def _gate_district(db, prefs, did: str) -> None:
    """A persona may only open districts within their own region states."""
    sc = (await db.execute(text("SELECT state_code FROM districts WHERE id = :d"), {"d": did})).scalar()
    allowed = _allowed_states(prefs)
    if sc and allowed and sc not in allowed:
        raise HTTPException(status_code=403, detail="District outside your region")


@router.get("/map")
async def situation_map(
    scope: str = Query(default="mine", pattern="^(mine|global)$"),
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    if not user:
        return {"personalized": False}
    async with get_db() as db:
        prefs = await load_prefs(db, user["id"])
        if not prefs:
            return {"personalized": False}
        return await get_page(db, user["id"], f"map_{scope}", lambda d: build_map(d, prefs, scope))


@router.get("/channels")
async def channels(
    scope: str = Query(default="mine", pattern="^(mine|global)$"),
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    """Currently-live, embeddable news channels for the scope (cached 25 min)."""
    state = "AP"
    if scope == "mine" and user:
        async with get_db() as db:
            prefs = await load_prefs(db, user["id"])
            if prefs:
                state = _primary_state(prefs)
    items = await live_channels.resolve_channels(scope, state)
    return {"channels": items, "scope": scope, "state": state}


@router.get("/country/{iso}")
async def country_file(iso: str, user: dict[str, str] | None = Depends(get_optional_user)) -> dict[str, Any]:
    if not user:
        raise HTTPException(status_code=401, detail="Not signed in")
    async with get_db() as db:
        return await country_mod.build_country_file(db, iso)


@router.get("/country/{iso}/articles")
async def country_articles(
    iso: str,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    if not user:
        raise HTTPException(status_code=401, detail="Not signed in")
    async with get_db() as db:
        return await country_mod.country_articles(db, iso, cursor, limit)


@router.get("/district/{did}")
async def district_file(did: str, user: dict[str, str] | None = Depends(get_optional_user)) -> dict[str, Any]:
    if not user:
        raise HTTPException(status_code=401, detail="Not signed in")
    async with get_db() as db:
        prefs = await load_prefs(db, user["id"])
        if not prefs:
            raise HTTPException(status_code=403, detail="No persona")
        await _gate_district(db, prefs, did)
        return await district_mod.build_district_file(db, did)


@router.get("/district/{did}/articles")
async def district_articles(
    did: str,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    if not user:
        raise HTTPException(status_code=401, detail="Not signed in")
    async with get_db() as db:
        prefs = await load_prefs(db, user["id"])
        if not prefs:
            raise HTTPException(status_code=403, detail="No persona")
        await _gate_district(db, prefs, did)
        return await district_mod.district_articles(db, did, cursor, limit)
