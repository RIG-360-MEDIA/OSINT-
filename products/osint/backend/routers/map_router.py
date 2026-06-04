"""Situation-Map endpoint — persona-scoped district/state bubbles, served from cache."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from auth.middleware import get_optional_user
from brief_prefs import load_prefs
from db import get_db
from home_cache import get_page
from map_page import build_map

router = APIRouter(prefix="/api/brief", tags=["brief"])


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
