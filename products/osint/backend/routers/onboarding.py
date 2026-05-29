"""Onboarding endpoints — invite acceptance + preferences save.

Endpoints:
    GET  /api/onboarding/invite/{token}    — public: peek at invite shape (email, org name, role)
    POST /api/onboarding/accept            — public: validate invite + create Supabase user + analytics.users row
    POST /api/onboarding/complete          — authenticated: save user_brief_prefs (12-step wizard output)
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text

from auth.invites import (
    _hash,
    db_lookup_invite,
    db_mark_invite_consumed,
    decode_invite_token,
)
from auth.middleware import get_current_user
from auth.supabase_admin import create_user as supabase_create_user
from auth.supabase_admin import get_user_by_email, sign_in_with_password
from db import get_db

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


# ─── Entity typeahead (used by wizard Step 2 + Step 3) ───────────────────────

@router.get("/search_entities")
async def search_entities(
    q: str,
    limit: int = 20,
    types: str = "person,politician",
) -> dict[str, Any]:
    """Search entity_dictionary for the wizard's typeahead.

    Returns rows where canonical_name OR any alias starts with `q` (case-
    insensitive), restricted to the comma-list of entity_types (default
    person+politician). Limits to 20 — small enough to render as chips.
    """
    if not q or len(q.strip()) < 2:
        return {"results": []}
    needle = f"{q.strip().lower()}%"
    type_set = [t.strip().lower() for t in (types or "").split(",") if t.strip()]
    if not type_set:
        type_set = ["person", "politician"]
    placeholders = ", ".join(f":t{i}" for i in range(len(type_set)))
    params: dict[str, Any] = {"n": needle, "limit": int(limit)}
    for i, t in enumerate(type_set):
        params[f"t{i}"] = t

    async with get_db() as db:
        rows = (await db.execute(text(f"""
            SELECT id::text AS id, canonical_name, entity_type, party, state, country, aliases
              FROM entity_dictionary
             WHERE LOWER(entity_type) IN ({placeholders})
               AND (
                 LOWER(canonical_name) LIKE :n
                 OR EXISTS (
                   SELECT 1 FROM unnest(aliases) a
                    WHERE LOWER(a) LIKE :n
                 )
               )
             ORDER BY
               -- 1. exact name match wins (e.g., 'Modi' search → 'Modi' before 'Modi Govt Initiative')
               CASE WHEN LOWER(canonical_name) = LEFT(:n, GREATEST(LENGTH(:n)-1, 1)) THEN 0 ELSE 1 END,
               -- 2. national politicians (party set, no state) rank above regional
               CASE WHEN party IS NOT NULL AND party != '' AND state IS NULL THEN 0 ELSE 1 END,
               -- 3. politicians with party (regional) above unaffiliated persons
               CASE WHEN party IS NOT NULL AND party != '' THEN 0 ELSE 1 END,
               LENGTH(canonical_name)
             LIMIT :limit
        """), params)).fetchall()

    return {
        "results": [{
            "id": r.id,
            "name": r.canonical_name,
            "type": r.entity_type,
            "party": r.party,
            "state": r.state,
            "country": (r.country or "").strip() or None,
            "aliases": list(r.aliases) if r.aliases else [],
        } for r in rows],
        "query": q,
        "types": type_set,
    }


# ─── Schemas ─────────────────────────────────────────────────────────────────

class AcceptInviteIn(BaseModel):
    invite_token: str = Field(min_length=10)
    password: str = Field(min_length=8, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)
    designation: str | None = None


class PrefsIn(BaseModel):
    primary_subject_id: str | None = None
    primary_subject_meta: dict[str, Any] | None = None
    watchlist: dict[str, Any] = Field(default_factory=dict)
    regions: dict[str, Any] = Field(default_factory=dict)
    topics: dict[str, Any] = Field(default_factory=dict)
    languages: dict[str, Any] = Field(default_factory=dict)
    sources: dict[str, Any] = Field(default_factory=dict)
    stance: dict[str, Any] = Field(default_factory=dict)
    events: dict[str, Any] = Field(default_factory=dict)
    delivery: dict[str, Any] = Field(default_factory=dict)
    personality: dict[str, Any] = Field(default_factory=dict)


def _require_active_invite(inv: dict[str, Any]) -> None:
    if inv["consumed_at"] is not None:
        raise HTTPException(status_code=409, detail="Invite already used")
    if inv["expires_at"] and inv["expires_at"] < dt.datetime.now(dt.timezone.utc):
        raise HTTPException(status_code=410, detail="Invite expired")


# ─── Invite peek (for the signup landing page) ───────────────────────────────

@router.get("/invite/{token}")
async def peek_invite(token: str) -> dict[str, Any]:
    payload = decode_invite_token(token)
    inv = await db_lookup_invite(_hash(token))
    if inv is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    _require_active_invite(inv)

    async with get_db() as db:
        org = (await db.execute(text(
            "SELECT name FROM analytics.orgs WHERE id = CAST(:o AS uuid)"
        ), {"o": inv["org_id"]})).fetchone()

    return {
        "email": inv["email"],
        "role_template": inv["role_template"],
        "org_id": inv["org_id"],
        "org_name": org.name if org else None,
        "expires_at": inv["expires_at"].isoformat() if inv["expires_at"] else None,
        "iat": payload.get("iat"),
    }


# ─── Accept invite (signup flow) ─────────────────────────────────────────────

@router.post("/accept")
async def accept_invite(body: AcceptInviteIn) -> dict[str, Any]:
    payload = decode_invite_token(body.invite_token)
    inv = await db_lookup_invite(_hash(body.invite_token))
    if inv is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    _require_active_invite(inv)

    email = inv["email"]
    org_id = inv["org_id"]

    # Either reuse an existing Supabase user (rare — they had account before)
    # or create a fresh one.
    existing = await get_user_by_email(email)
    if existing:
        user_id = existing.get("id")
        if not user_id:
            raise HTTPException(status_code=500, detail="Supabase user has no id")
    else:
        created = await supabase_create_user(
            email=email,
            password=body.password,
            user_metadata={"full_name": body.full_name, "role_template": inv["role_template"]},
        )
        user_id = created.get("id")
        if not user_id:
            raise HTTPException(status_code=500, detail="Supabase create returned no id")

    # Insert (or upsert) the analytics.users row
    async with get_db() as db:
        async with db.begin():
            await db.execute(text("""
                INSERT INTO analytics.users (
                    id, org_id, email, full_name, designation, invited_by
                ) VALUES (
                    CAST(:uid AS uuid), CAST(:org AS uuid), :em, :fn, :des,
                    CAST(:ib AS uuid)
                )
                ON CONFLICT (id) DO UPDATE
                  SET org_id      = EXCLUDED.org_id,
                      full_name   = COALESCE(EXCLUDED.full_name, analytics.users.full_name),
                      designation = COALESCE(EXCLUDED.designation, analytics.users.designation),
                      invited_by  = COALESCE(analytics.users.invited_by, EXCLUDED.invited_by)
            """), {
                "uid": user_id, "org": org_id, "em": email,
                "fn": body.full_name, "des": body.designation, "ib": inv["invited_by"],
            })

    await db_mark_invite_consumed(inv["token_hash"], user_id)

    # Sign the user in immediately so the frontend gets a session
    session = await sign_in_with_password(email=email, password=body.password)
    return {
        "user_id": user_id,
        "email": email,
        "org_id": org_id,
        "role_template": inv["role_template"],
        "session": {
            "access_token": session.get("access_token"),
            "refresh_token": session.get("refresh_token"),
            "expires_in": session.get("expires_in"),
            "token_type": session.get("token_type", "bearer"),
        },
    }


# ─── Complete onboarding (save the wizard's prefs payload) ──────────────────

@router.post("/complete")
async def complete_onboarding(
    body: PrefsIn,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, Any]:
    async with get_db() as db:
        async with db.begin():
            # Ensure user row exists (caller is authenticated via Supabase — might not yet be in analytics.users)
            row = (await db.execute(text(
                "SELECT 1 FROM analytics.users WHERE id = CAST(:uid AS uuid)"
            ), {"uid": user["id"]})).fetchone()
            if row is None:
                raise HTTPException(status_code=403, detail="User not provisioned — call /accept first")

            await db.execute(text("""
                INSERT INTO analytics.user_brief_prefs (
                    user_id, primary_subject_id, primary_subject_meta,
                    watchlist, regions, topics, languages,
                    sources, stance, events, delivery, personality
                ) VALUES (
                    CAST(:uid AS uuid),
                    -- CAST(NULL AS uuid) is just NULL::uuid; the explicit cast makes
                    -- the param type unambiguous. A bare CASE/:psid left asyncpg
                    -- unable to infer the type when primary_subject_id is None
                    -- (AmbiguousParameterError → 500 on every onboarding-complete).
                    CAST(:psid AS uuid),
                    CAST(:psmeta AS jsonb),
                    CAST(:watch AS jsonb), CAST(:reg AS jsonb), CAST(:top AS jsonb),
                    CAST(:lang AS jsonb), CAST(:src AS jsonb), CAST(:st AS jsonb),
                    CAST(:ev AS jsonb), CAST(:del AS jsonb), CAST(:pers AS jsonb)
                )
                ON CONFLICT (user_id) DO UPDATE SET
                    primary_subject_id   = EXCLUDED.primary_subject_id,
                    primary_subject_meta = EXCLUDED.primary_subject_meta,
                    watchlist  = EXCLUDED.watchlist,
                    regions    = EXCLUDED.regions,
                    topics     = EXCLUDED.topics,
                    languages  = EXCLUDED.languages,
                    sources    = EXCLUDED.sources,
                    stance     = EXCLUDED.stance,
                    events     = EXCLUDED.events,
                    delivery   = EXCLUDED.delivery,
                    personality = EXCLUDED.personality
            """), {
                "uid": user["id"],
                "psid": body.primary_subject_id,
                "psmeta": _json(body.primary_subject_meta or {}),
                "watch": _json(body.watchlist),
                "reg":   _json(body.regions),
                "top":   _json(body.topics),
                "lang":  _json(body.languages),
                "src":   _json(body.sources),
                "st":    _json(body.stance),
                "ev":    _json(body.events),
                "del":   _json(body.delivery),
                "pers":  _json(body.personality),
            })

            await db.execute(text(
                "UPDATE analytics.users SET onboarded_at = NOW() WHERE id = CAST(:uid AS uuid)"
            ), {"uid": user["id"]})

    return {"status": "onboarded"}


def _json(d: Any) -> str:
    import json
    return json.dumps(d, default=str)
