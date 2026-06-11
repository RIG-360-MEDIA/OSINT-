"""Invite-link minting + verification.

Pattern: super-admin generates an invite. We sign a JWT with the invite's
identity (email, org, role, expires_at). We store SHA-256(JWT) in
analytics.invites — so the raw token never lives in our DB, but we can still
look it up by hash on acceptance. The JWT signature ensures the link itself
can't be forged; the DB row lets us mark it consumed and enforce single-use.
"""
from __future__ import annotations

import hashlib
import os
import time
import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text

from db import get_db

_JWT_SECRET = os.getenv("OSINT_SUPABASE_JWT_SECRET", "") or os.getenv("SUPABASE_JWT_SECRET", "")
_FRONTEND_BASE = os.getenv("OSINT_FRONTEND_BASE", "https://brief.rig360media.com").rstrip("/")


def _jose():
    """Lazy import — keeps module importable without python-jose at runtime."""
    from jose import jwt, JWTError  # noqa: PLC0415
    return jwt, JWTError


def _hash(token: str) -> str:
    """Stable hash of the JWT for DB lookup."""
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()


def mint_invite_token(
    *,
    email: str,
    org_id: str,
    role_template: str,
    expires_in_days: int = 14,
) -> tuple[str, str, int]:
    """Mint an invite JWT. Returns (raw_token, sha256_hash, exp_unix)."""
    if not _JWT_SECRET:
        raise HTTPException(status_code=500, detail="SUPABASE_JWT_SECRET not configured")
    jwt, _ = _jose()
    exp = int(time.time()) + expires_in_days * 86400
    payload = {
        "scope": "osint_invite",
        "jti": str(uuid.uuid4()),
        "email": email.strip().lower(),
        "org_id": org_id,
        "role_template": role_template,
        "iat": int(time.time()),
        "exp": exp,
    }
    token = jwt.encode(payload, _JWT_SECRET, algorithm="HS256")
    return token, _hash(token), exp


def decode_invite_token(token: str) -> dict[str, Any]:
    """Verify signature + check scope=osint_invite. Raises 401 otherwise."""
    if not _JWT_SECRET:
        raise HTTPException(status_code=500, detail="SUPABASE_JWT_SECRET not configured")
    jwt, JWTError = _jose()
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=["HS256"], options={"verify_aud": False})
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid invite token: {exc}") from exc
    if payload.get("scope") != "osint_invite":
        raise HTTPException(status_code=401, detail="Token is not an osint invite")
    return payload


def build_invite_link(token: str) -> str:
    """Format the email-able link for the invite."""
    return f"{_FRONTEND_BASE}/signup?invite={token}"


# ─── DB helpers ──────────────────────────────────────────────────────────────

async def db_create_invite(
    *,
    token_hash: str,
    email: str,
    org_id: str,
    role_template: str,
    invited_by: str,
    expires_at_unix: int,
    notes: str | None,
) -> None:
    async with get_db() as db:
        async with db.begin():
            await db.execute(text("""
                INSERT INTO analytics.invites (
                    token_hash, email, org_id, role_template,
                    invited_by, expires_at, notes
                ) VALUES (
                    :h, :e, CAST(:o AS uuid), :r,
                    CAST(:ib AS uuid), to_timestamp(:exp), :n
                )
            """), {
                "h": token_hash, "e": email.lower(),
                "o": org_id, "r": role_template,
                "ib": invited_by, "exp": expires_at_unix, "n": notes,
            })


async def db_lookup_invite(token_hash: str) -> dict[str, Any] | None:
    async with get_db() as db:
        row = (await db.execute(text("""
            SELECT token_hash, email, org_id::text AS org_id, role_template,
                   invited_by::text AS invited_by, expires_at, consumed_at,
                   consumed_by::text AS consumed_by, notes, created_at
              FROM analytics.invites
             WHERE token_hash = :h
        """), {"h": token_hash})).fetchone()
    if row is None:
        return None
    return {
        "token_hash": row.token_hash,
        "email": row.email,
        "org_id": row.org_id,
        "role_template": row.role_template,
        "invited_by": row.invited_by,
        "expires_at": row.expires_at,
        "consumed_at": row.consumed_at,
        "consumed_by": row.consumed_by,
        "notes": row.notes,
        "created_at": row.created_at,
    }


async def db_mark_invite_consumed(token_hash: str, user_id: str) -> None:
    async with get_db() as db:
        async with db.begin():
            await db.execute(text("""
                UPDATE analytics.invites
                   SET consumed_at = NOW(),
                       consumed_by = CAST(:u AS uuid)
                 WHERE token_hash = :h
            """), {"h": token_hash, "u": user_id})


async def db_list_invites(*, include_consumed: bool = True) -> list[dict[str, Any]]:
    where = "" if include_consumed else "WHERE consumed_at IS NULL AND expires_at > NOW()"
    async with get_db() as db:
        rows = (await db.execute(text(f"""
            SELECT i.token_hash, i.email, i.role_template,
                   i.org_id::text AS org_id, o.name AS org_name,
                   i.expires_at, i.consumed_at, i.created_at, i.notes
              FROM analytics.invites i
              LEFT JOIN analytics.orgs o ON o.id = i.org_id
              {where}
             ORDER BY i.created_at DESC
             LIMIT 200
        """))).fetchall()
    return [{
        "token_hash": r.token_hash,
        "email": r.email,
        "role_template": r.role_template,
        "org_id": r.org_id,
        "org_name": r.org_name,
        "expires_at": r.expires_at.isoformat() if r.expires_at else None,
        "consumed_at": r.consumed_at.isoformat() if r.consumed_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "notes": r.notes,
    } for r in rows]
