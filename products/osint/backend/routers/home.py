"""GET /api/brief/home — the full Night Desk Home payload for the persona.

Returns masthead + THE BRIEFING + PEOPLE TO WATCH + THE SIX in one call, so the
home page loads as a unit with cross-section-consistent numbers (all derived
from a single posture + relevance computation). Honest, source-grounded; degrades
to {"personalized": false} when there's no signed-in persona.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from auth.middleware import get_optional_user
from brief_prefs import load_prefs, jsonify
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


async def _bust_cache(db, uid: str) -> None:
    await db.execute(text(
        "DELETE FROM analytics.home_cache WHERE user_id = CAST(:u AS uuid)"
    ), {"u": uid})
    await db.commit()


class WatchlistAddIn(BaseModel):
    entity_id: str


@router.post("/watchlist/add")
async def watchlist_add(
    body: WatchlistAddIn,
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    async with get_db() as db:
        ent = (await db.execute(text("""
            SELECT id::text, canonical_name, entity_type, party, state
              FROM entity_dictionary
             WHERE id = CAST(:eid AS uuid) AND redirected_to IS NULL
        """), {"eid": body.entity_id})).fetchone()
        if not ent:
            raise HTTPException(status_code=404, detail="Entity not found")

        row = (await db.execute(text("""
            SELECT watchlist FROM analytics.user_brief_prefs
             WHERE user_id = CAST(:uid AS uuid)
        """), {"uid": user["id"]})).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User prefs not found")

        wl = jsonify(row.watchlist)
        ids = list(wl.get("entity_ids") or [])
        meta = list(wl.get("entity_meta") or [])

        if ent.id in ids:
            return {"ok": True, "already_present": True}

        ids.append(ent.id)
        meta.append({
            "id": ent.id, "name": ent.canonical_name, "type": ent.entity_type,
            "party": ent.party or "", "state": ent.state or "",
        })
        new_wl = {**wl, "entity_ids": ids, "entity_meta": meta}
        await db.execute(text("""
            UPDATE analytics.user_brief_prefs
               SET watchlist = CAST(:wl AS jsonb)
             WHERE user_id = CAST(:uid AS uuid)
        """), {"wl": json.dumps(new_wl), "uid": user["id"]})
        await _bust_cache(db, user["id"])
    return {"ok": True, "entity": {"id": ent.id, "name": ent.canonical_name}}


@router.delete("/watchlist/{entity_id}")
async def watchlist_remove(
    entity_id: str,
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    async with get_db() as db:
        row = (await db.execute(text("""
            SELECT watchlist FROM analytics.user_brief_prefs
             WHERE user_id = CAST(:uid AS uuid)
        """), {"uid": user["id"]})).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User prefs not found")

        wl = jsonify(row.watchlist)
        new_wl = {
            **wl,
            "entity_ids": [x for x in (wl.get("entity_ids") or []) if x != entity_id],
            "entity_meta": [m for m in (wl.get("entity_meta") or []) if m.get("id") != entity_id],
        }
        await db.execute(text("""
            UPDATE analytics.user_brief_prefs
               SET watchlist = CAST(:wl AS jsonb)
             WHERE user_id = CAST(:uid AS uuid)
        """), {"wl": json.dumps(new_wl), "uid": user["id"]})
        await _bust_cache(db, user["id"])
    return {"ok": True}
