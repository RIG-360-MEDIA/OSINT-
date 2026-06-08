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
from home_sections import sentiment_explain
from posture import principal_of

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


@router.get("/home/sentiment-explain")
async def get_sentiment_explain(
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    """Top +/- stories driving the Coverage Sentiment number (lazy-loaded on
    click). Same 72h window + principal as the Home sentiment series."""
    if not user:
        return {"top_positive": [], "top_negative": []}
    async with get_db() as db:
        prefs = await load_prefs(db, user["id"])
        if not prefs:
            return {"top_positive": [], "top_negative": []}
        pid, _ = principal_of(prefs)
        if not pid:
            return {"top_positive": [], "top_negative": []}
        return await sentiment_explain(db, pid, 72)


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
        # People to Watch is about individuals. Reject places/orgs/parties so a
        # district or "Government of …" can never pollute the panel as a person.
        etype = (ent.entity_type or "").lower()
        if etype not in ("person", "politician"):
            raise HTTPException(
                status_code=400,
                detail="Only individuals can be added to People to Watch",
            )

        row = (await db.execute(text("""
            SELECT watchlist, primary_subject_id::text AS sid
              FROM analytics.user_brief_prefs
             WHERE user_id = CAST(:uid AS uuid)
        """), {"uid": user["id"]})).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User prefs not found")
        # Can't "watch" yourself — the principal is the dashboard's whole focus,
        # and People to Watch deliberately excludes them, so adding the principal
        # would silently show nothing. Reject with a clear message instead.
        if row.sid and row.sid == ent.id:
            raise HTTPException(
                status_code=400,
                detail="That's your primary subject — already the focus of the whole dashboard.",
            )

        wl = jsonify(row.watchlist)
        ids = list(wl.get("entity_ids") or [])
        meta = list(wl.get("entity_meta") or [])

        entry = {
            "id": ent.id, "name": ent.canonical_name, "type": etype or "person",
            "party": ent.party or "", "state": ent.state or "",
            "pinned": True,
        }
        # Whether the entity is new OR already on the watchlist (commonly an
        # onboarding pick), adding it via the modal is an explicit request to
        # watch them. Drop any existing copy and re-append at the end so it is
        # pinned AND newest — guaranteeing it surfaces at the top of the manually-
        # curated People to Watch. Without this, re-adding an existing member
        # returned 200 but changed nothing (the silent "add does nothing" bug).
        already = ent.id in ids
        new_ids = [x for x in ids if x != ent.id] + [ent.id]
        new_meta = [m for m in meta if m.get("id") != ent.id] + [entry]
        new_wl = {**wl, "entity_ids": new_ids, "entity_meta": new_meta}
        await db.execute(text("""
            UPDATE analytics.user_brief_prefs
               SET watchlist = CAST(:wl AS jsonb)
             WHERE user_id = CAST(:uid AS uuid)
        """), {"wl": json.dumps(new_wl), "uid": user["id"]})
        await _bust_cache(db, user["id"])
    return {"ok": True, "already_present": already,
            "entity": {"id": ent.id, "name": ent.canonical_name}}


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
