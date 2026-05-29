"""Super-admin only endpoints — invite issuance + org management.

Endpoints:
    POST /api/admin/invites          — create a new invite, returns the link
    GET  /api/admin/invites          — list pending + consumed invites
    POST /api/admin/orgs             — create an org (call before issuing first invite for it)
    GET  /api/admin/orgs             — list orgs
    POST /api/admin/bootstrap        — one-shot: seed the FIRST super-admin user row
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text

from auth.invites import (
    build_invite_link,
    db_create_invite,
    db_list_invites,
    mint_invite_token,
)
from auth.middleware import get_current_user, require_super_admin
from db import get_db

router = APIRouter(prefix="/api/admin", tags=["admin"])

VALID_ROLE_TEMPLATES = {"govt", "pr", "journalist", "academic", "corporate"}
_BOOTSTRAP_EMAIL = os.getenv("OSINT_BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()


# ─── Schemas ────────────────────────────────────────────────────────────────

class CreateOrgIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    role_template: str = Field(pattern="^(govt|pr|journalist|academic|corporate)$")
    notes: str | None = None


class CreateInviteIn(BaseModel):
    email: EmailStr
    org_id: str
    role_template: str = Field(pattern="^(govt|pr|journalist|academic|corporate)$")
    expires_in_days: int = Field(default=14, ge=1, le=90)
    notes: str | None = None


class BootstrapIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    designation: str | None = None


# ─── Orgs ────────────────────────────────────────────────────────────────────

@router.post("/orgs")
async def create_org(
    body: CreateOrgIn,
    _: dict[str, Any] = Depends(require_super_admin),
) -> dict[str, Any]:
    async with get_db() as db:
        async with db.begin():
            row = (await db.execute(text("""
                INSERT INTO analytics.orgs (name, role_template, notes)
                VALUES (:n, :r, :no)
                RETURNING id::text AS id, name, role_template, notes, created_at
            """), {"n": body.name, "r": body.role_template, "no": body.notes})).fetchone()
    return {
        "id": row.id, "name": row.name,
        "role_template": row.role_template, "notes": row.notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/orgs")
async def list_orgs(
    _: dict[str, Any] = Depends(require_super_admin),
) -> dict[str, Any]:
    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT id::text AS id, name, role_template, notes, created_at
              FROM analytics.orgs ORDER BY created_at DESC
        """))).fetchall()
    return {"orgs": [{
        "id": r.id, "name": r.name,
        "role_template": r.role_template, "notes": r.notes,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]}


# ─── Invites ─────────────────────────────────────────────────────────────────

@router.post("/invites")
async def create_invite(
    body: CreateInviteIn,
    principal: dict[str, Any] = Depends(require_super_admin),
) -> dict[str, Any]:
    if body.role_template not in VALID_ROLE_TEMPLATES:
        raise HTTPException(status_code=400, detail="Invalid role_template")

    # Verify org exists
    async with get_db() as db:
        org = (await db.execute(text(
            "SELECT id::text AS id, name FROM analytics.orgs WHERE id = CAST(:o AS uuid)"
        ), {"o": body.org_id})).fetchone()
    if org is None:
        raise HTTPException(status_code=404, detail="org_id not found")

    token, token_hash, exp_unix = mint_invite_token(
        email=str(body.email),
        org_id=body.org_id,
        role_template=body.role_template,
        expires_in_days=body.expires_in_days,
    )
    await db_create_invite(
        token_hash=token_hash, email=str(body.email),
        org_id=body.org_id, role_template=body.role_template,
        invited_by=principal["id"], expires_at_unix=exp_unix,
        notes=body.notes,
    )
    return {
        "email": str(body.email),
        "org_id": body.org_id,
        "org_name": org.name,
        "role_template": body.role_template,
        "link": build_invite_link(token),
        "expires_at_unix": exp_unix,
        "notes": body.notes,
    }


@router.get("/invites")
async def list_invites(
    include_consumed: bool = True,
    _: dict[str, Any] = Depends(require_super_admin),
) -> dict[str, Any]:
    rows = await db_list_invites(include_consumed=include_consumed)
    return {"invites": rows}


# ─── Bootstrap ───────────────────────────────────────────────────────────────

@router.post("/bootstrap")
async def bootstrap_super_admin(
    body: BootstrapIn,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, Any]:
    """One-shot: seed the FIRST super-admin row.

    Auth: caller must be signed in via Supabase (have a JWT) AND their email
    must match OSINT_BOOTSTRAP_ADMIN_EMAIL. Only works if no super-admin
    currently exists in analytics.users.
    """
    if not _BOOTSTRAP_EMAIL:
        raise HTTPException(status_code=503, detail="Bootstrap email not configured")
    if user["email"].strip().lower() != _BOOTSTRAP_EMAIL:
        raise HTTPException(status_code=403, detail="Caller is not the bootstrap admin")

    async with get_db() as db:
        existing = (await db.execute(text(
            "SELECT COUNT(*) AS n FROM analytics.users WHERE is_super_admin"
        ))).fetchone()
    if existing and existing.n > 0:
        raise HTTPException(status_code=409, detail="A super-admin already exists")

    async with get_db() as db:
        async with db.begin():
            org = (await db.execute(text("""
                SELECT id::text AS id FROM analytics.orgs
                WHERE name = 'RIG 360 Media (internal)' LIMIT 1
            """))).fetchone()
            if org is None:
                org_row = (await db.execute(text("""
                    INSERT INTO analytics.orgs (name, role_template, notes)
                    VALUES ('RIG 360 Media (internal)', 'corporate', 'Bootstrap org')
                    RETURNING id::text AS id
                """))).fetchone()
                org_id = org_row.id
            else:
                org_id = org.id

            await db.execute(text("""
                INSERT INTO analytics.users (
                    id, org_id, email, full_name, designation,
                    is_super_admin, onboarded_at
                ) VALUES (
                    CAST(:uid AS uuid), CAST(:org AS uuid), :em, :fn, :des,
                    TRUE, NOW()
                )
                ON CONFLICT (id) DO UPDATE
                  SET is_super_admin = TRUE,
                      org_id = EXCLUDED.org_id,
                      full_name = COALESCE(analytics.users.full_name, EXCLUDED.full_name),
                      designation = COALESCE(analytics.users.designation, EXCLUDED.designation)
            """), {
                "uid": user["id"], "org": org_id, "em": user["email"],
                "fn": body.full_name, "des": body.designation,
            })

    return {"status": "bootstrapped", "user_id": user["id"], "email": user["email"], "org_id": org_id}
