"""War Room endpoint — served from the 30-min precompute cache (lazy-fills on miss)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from auth.middleware import get_optional_user
from brief_prefs import load_prefs
from db import get_db
from home_cache import get_page
from war_room import build_war_room

router = APIRouter(prefix="/api/brief", tags=["brief"])


@router.get("/warroom")
async def warroom(user: dict[str, str] | None = Depends(get_optional_user)) -> dict[str, Any]:
    if not user:
        return {"personalized": False}
    async with get_db() as db:
        prefs = await load_prefs(db, user["id"])
        if not prefs:
            return {"personalized": False}
        return await get_page(db, user["id"], "warroom", lambda d: build_war_room(d, prefs))
