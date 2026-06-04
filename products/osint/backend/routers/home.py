"""GET /api/brief/home — the full Night Desk Home payload for the persona.

Returns masthead + THE BRIEFING + PEOPLE TO WATCH + THE SIX in one call, so the
home page loads as a unit with cross-section-consistent numbers (all derived
from a single posture + relevance computation). Honest, source-grounded; degrades
to {"personalized": false} when there's no signed-in persona.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text

from auth.middleware import get_optional_user
from brief_prefs import load_prefs
from db import get_db
from home_cache import get_home as get_home_cached

router = APIRouter(prefix="/api/brief", tags=["brief"])


@router.get("/home")
async def get_home(user: dict[str, str] | None = Depends(get_optional_user)) -> dict[str, Any]:
    if not user:
        return {"personalized": False}
    async with get_db() as db:
        prefs = await load_prefs(db, user["id"])
        if not prefs:
            return {"personalized": False}
        display_name = (await db.execute(
            text("SELECT full_name FROM analytics.users WHERE id = CAST(:u AS uuid)"),
            {"u": user["id"]},
        )).scalar()
        # Served from the 30-min precomputed cache (lazy-fills on a cold miss).
        return await get_home_cached(db, user["id"], prefs, display_name)
