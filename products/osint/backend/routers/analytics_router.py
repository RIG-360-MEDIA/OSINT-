"""Analytics endpoint — 20 data cards, served from the 30-min precompute cache."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from auth.middleware import get_optional_user
from brief_prefs import load_prefs
from db import get_db
from home_cache import get_page
from analytics_page import build_analytics

router = APIRouter(prefix="/api/brief", tags=["brief"])


@router.get("/analytics")
async def analytics(user: dict[str, str] | None = Depends(get_optional_user)) -> dict[str, Any]:
    if not user:
        return {"personalized": False}
    async with get_db() as db:
        prefs = await load_prefs(db, user["id"])
        if not prefs:
            return {"personalized": False}
        return await get_page(db, user["id"], "analytics", lambda d: build_analytics(d, prefs))
