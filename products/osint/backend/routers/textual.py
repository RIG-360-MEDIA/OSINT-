"""GET /api/brief/textual — Category-2 textual intelligence (LLM, faithfulness-gated).

Generic + English-pinned + cold-start safe. `?features=a,b` runs a subset to bound
LLM cost (each LLM feature is one grounded call); omit to run all.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from auth.middleware import get_optional_user
from brief_prefs import load_prefs
from db import get_db
from textual import compute_textual

router = APIRouter(prefix="/api/brief", tags=["brief"])


@router.get("/textual")
async def get_textual(
    window_hours: int = Query(default=504, ge=24, le=2160),
    features: str | None = Query(default=None, description="comma-separated subset; omit for all"),
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    feats = [f.strip() for f in features.split(",") if f.strip()] if features else None
    async with get_db() as db:
        prefs = await load_prefs(db, user["id"]) if user else None
        if not prefs:
            return {"personalized": False, "features": {}}
        return await compute_textual(db, prefs, window_hours, feats)
