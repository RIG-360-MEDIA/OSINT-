"""GET /api/brief/posture — Category-1 posture-scoring metrics.

Generic: principal = the user's `primary_subject_id`, targets = their watchlist.
A new user with a prefs row gets all 15 metrics with zero code changes. Every
metric carries `n` + a `confidence` band so the UI can hide/soften thin scores.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from auth.middleware import get_optional_user
from brief_prefs import load_prefs
from db import get_db
from posture import compute_posture

router = APIRouter(prefix="/api/brief", tags=["brief"])


@router.get("/posture")
async def get_posture(
    window_hours: int = Query(default=504, ge=24, le=2160),
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    """All posture metrics for the authenticated user's principal + watchlist."""
    async with get_db() as db:
        prefs = await load_prefs(db, user["id"]) if user else None
        if not prefs:
            return {"personalized": False, "metrics": {}}
        return await compute_posture(db, prefs, window_hours)
