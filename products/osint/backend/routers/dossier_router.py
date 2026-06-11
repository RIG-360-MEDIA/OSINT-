"""Dossier endpoints — roster, per-entity file, and the live whole-corpus article feed.

  GET /api/brief/dossier/roster                  -> every watched entity (+ photo)
  GET /api/brief/dossier/entity/{eid}            -> the open file (14 panels)
  GET /api/brief/dossier/entity/{eid}/articles   -> newest-first, cursor-paginated feed

RBAC: a persona may only open entities on their own watchlist (or their principal) —
matches the per-user view-by-entity scope. Served live (file ~0.7s, feed ~0.15s).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from auth.middleware import get_optional_user
from brief_prefs import load_prefs
from db import get_db
import dossier

router = APIRouter(prefix="/api/brief/dossier", tags=["dossier"])


def _allowed(prefs: dict[str, Any], eid: str) -> bool:
    if eid == prefs.get("primary_subject_id"):
        return True
    return eid in (prefs.get("watchlist", {}).get("entity_ids") or [])


@router.get("/roster")
async def roster(user: dict[str, str] | None = Depends(get_optional_user)) -> dict[str, Any]:
    if not user:
        return {"personalized": False, "roster": []}
    async with get_db() as db:
        prefs = await load_prefs(db, user["id"])
        if not prefs:
            return {"personalized": False, "roster": []}
        return {"personalized": True, **(await dossier.build_roster(db, prefs))}


@router.get("/entity/{eid}")
async def entity_file(eid: str, user: dict[str, str] | None = Depends(get_optional_user)) -> dict[str, Any]:
    if not user:
        raise HTTPException(status_code=401, detail="Not signed in")
    async with get_db() as db:
        prefs = await load_prefs(db, user["id"])
        if not prefs:
            raise HTTPException(status_code=403, detail="No persona")
        if not _allowed(prefs, eid):
            raise HTTPException(status_code=403, detail="Entity not on your watchlist")
        return await dossier.build_entity_file(db, eid, prefs)


@router.get("/entity/{eid}/articles")
async def entity_articles(
    eid: str,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    if not user:
        raise HTTPException(status_code=401, detail="Not signed in")
    async with get_db() as db:
        prefs = await load_prefs(db, user["id"])
        if not prefs or not _allowed(prefs, eid):
            raise HTTPException(status_code=403, detail="Entity not on your watchlist")
        return await dossier.entity_articles(db, eid, cursor, limit)
