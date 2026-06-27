"""Supabase JWT auth + role-aware principal resolution for osint-backend.

Modelled on rig-backend/backend/auth/auth_middleware.py — same library
(python-jose) and same HS256 + SUPABASE_JWT_SECRET pattern. Differences:

  - We resolve users from `analytics.users` (not public.users) — keeps the
    osint product self-contained.
  - Role model: `role` column (super_user | admin | client) + legacy
    `is_super_admin` boolean kept for backward compat.
  - Impersonation: super_user callers can include `X-Impersonate: <uuid>`
    header to act as another user — middleware transparently substitutes
    that user's principal so all data endpoints scope to their org/prefs.
  - OSINT_SUPER_USER_EMAILS: comma-separated list of emails that are
    auto-promoted to super_user on first login (no Supabase admin required).
"""
from __future__ import annotations

import base64
import json
import logging
import os
import time
from typing import Any

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text

from db import get_db

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)

_JWT_SECRET = os.getenv("OSINT_SUPABASE_JWT_SECRET", "") or os.getenv("SUPABASE_JWT_SECRET", "")
_ENVIRONMENT = os.getenv("OSINT_ENVIRONMENT", os.getenv("ENVIRONMENT", "development")).lower()

# Comma-separated emails auto-promoted to super_user on first login.
# e.g. OSINT_SUPER_USER_EMAILS=sycek@rig360media.com,rohit@rig360media.com
_SUPER_USER_EMAILS: frozenset[str] = frozenset(
    e.strip().lower()
    for e in os.getenv("OSINT_SUPER_USER_EMAILS", "sycek@rig360media.com,rohit@rig360media.com").split(",")
    if e.strip()
)


# ─────────────────────────────────────────────────────────────────────────────
# JWT decode
# ─────────────────────────────────────────────────────────────────────────────

def _decode_unverified(token: str) -> dict[str, Any]:
    """Decode payload without verifying signature. Dev/test fallback only."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Not a JWT")
        payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Malformed token: {exc}") from exc


def _decode_and_verify(token: str) -> dict[str, Any]:
    """Decode + verify the JWT. Production refuses if no secret configured."""
    if _JWT_SECRET:
        try:
            from jose import jwt, JWTError  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover
            raise HTTPException(status_code=500, detail=f"JWT lib missing: {exc}") from exc
        try:
            return jwt.decode(
                token,
                _JWT_SECRET,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
        except JWTError as exc:
            raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc

    if _ENVIRONMENT == "production":
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_JWT_SECRET not configured — refusing to skip signature verification in production",
        )
    return _decode_unverified(token)


# ─────────────────────────────────────────────────────────────────────────────
# Core FastAPI dependencies
# ─────────────────────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, str]:
    """Return {id, email} from a valid Supabase JWT. 401 otherwise."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    payload = _decode_and_verify(credentials.credentials)

    exp = payload.get("exp", 0)
    if exp and time.time() > exp:
        raise HTTPException(status_code=401, detail="Token expired — please log in again")

    user_id = payload.get("sub")
    email = payload.get("email", "")

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token: missing sub claim")

    return {"id": str(user_id), "email": str(email)}


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, str] | None:
    """Return user if authenticated, None otherwise (no 401)."""
    if not credentials:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Role-aware principal (joins JWT identity with analytics.users + analytics.orgs)
# ─────────────────────────────────────────────────────────────────────────────

async def _load_principal_row(uid: str) -> dict[str, Any]:
    """Fetch one user row from analytics.users + orgs. Returns stub if not found."""
    async with get_db() as db:
        row = (await db.execute(text("""
            SELECT u.id, u.email, u.full_name, u.designation,
                   u.is_super_admin, u.role,
                   u.org_id, u.onboarded_at,
                   o.name AS org_name, o.role_template
              FROM analytics.users u
              LEFT JOIN analytics.orgs o ON o.id = u.org_id
             WHERE u.id = CAST(:uid AS uuid)
        """), {"uid": uid})).fetchone()

    if row is None:
        return {
            "id": uid,
            "email": "",
            "full_name": None,
            "designation": None,
            "is_super_admin": False,
            "role": "client",
            "org_id": None,
            "org_name": None,
            "role_template": None,
            "onboarded": False,
        }

    return {
        "id": str(row.id),
        "email": row.email,
        "full_name": row.full_name,
        "designation": row.designation,
        "is_super_admin": bool(row.is_super_admin),
        "role": row.role or "client",
        "org_id": str(row.org_id) if row.org_id else None,
        "org_name": row.org_name,
        "role_template": row.role_template,
        "onboarded": row.onboarded_at is not None,
    }


async def _ensure_super_user_row(uid: str, email: str) -> None:
    """Upsert a super_user row for emails in OSINT_SUPER_USER_EMAILS."""
    async with get_db() as db:
        async with db.begin():
            # ensure internal org exists
            org = (await db.execute(text("""
                SELECT id::text AS id FROM analytics.orgs
                 WHERE name = 'RIG 360 Media (internal)' LIMIT 1
            """))).fetchone()
            if org is None:
                org = (await db.execute(text("""
                    INSERT INTO analytics.orgs (name, role_template, notes)
                    VALUES ('RIG 360 Media (internal)', 'corporate', 'Auto-created for super_user seed')
                    RETURNING id::text AS id
                """))).fetchone()
            org_id = org.id

            await db.execute(text("""
                INSERT INTO analytics.users
                    (id, org_id, email, full_name, is_super_admin, role, onboarded_at)
                VALUES
                    (CAST(:uid AS uuid), CAST(:org AS uuid), :em,
                     :em, TRUE, 'super_user', NOW())
                ON CONFLICT (id) DO UPDATE
                  SET is_super_admin = TRUE,
                      role = 'super_user',
                      org_id = COALESCE(analytics.users.org_id, EXCLUDED.org_id)
            """), {"uid": uid, "org": org_id, "em": email})


async def get_current_principal(
    request: Request,
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the effective principal — JWT identity + analytics.users row.

    Shape returned:
        id, email, full_name, designation, is_super_admin, role,
        org_id, org_name, role_template, onboarded,
        impersonating (uuid str | None)

    If caller is super_user AND sends `X-Impersonate: <uuid>` header,
    returns the impersonated user's principal (with impersonating set).
    All data endpoints transparently scope to the impersonated user's org.

    If the email is in OSINT_SUPER_USER_EMAILS, the user is auto-promoted
    to super_user and upserted into analytics.users on first call.
    """
    # Auto-seed super_users by email (idempotent upsert)
    if user["email"].strip().lower() in _SUPER_USER_EMAILS:
        try:
            await _ensure_super_user_row(user["id"], user["email"])
        except Exception:
            logger.exception("_ensure_super_user_row failed for %s", user.get("email"))

    own = await _load_principal_row(user["id"])
    own["email"] = own["email"] or user["email"]
    own["impersonating"] = None

    # Impersonation: super_user only, via X-Impersonate header
    if own["role"] == "super_user":
        target_id = request.headers.get("X-Impersonate", "").strip()
        if target_id:
            impersonated = await _load_principal_row(target_id)
            if not impersonated["onboarded"] and impersonated["email"] == "":
                raise HTTPException(status_code=404, detail="Impersonation target not found")
            impersonated["impersonating"] = target_id
            return impersonated

    return own


async def require_super_admin(
    principal: dict[str, Any] = Depends(get_current_principal),
) -> dict[str, Any]:
    """403 unless caller's own role is super_user."""
    if not principal.get("is_super_admin") and principal.get("role") != "super_user":
        raise HTTPException(status_code=403, detail="super_user required")
    return principal


async def require_admin(
    principal: dict[str, Any] = Depends(get_current_principal),
) -> dict[str, Any]:
    """403 unless caller has admin or super_user role."""
    if principal.get("role") not in ("super_user", "admin"):
        raise HTTPException(status_code=403, detail="admin role required")
    return principal


async def require_onboarded(
    principal: dict[str, Any] = Depends(get_current_principal),
) -> dict[str, Any]:
    """403 unless caller has finished the onboarding wizard."""
    if not principal["onboarded"]:
        raise HTTPException(status_code=403, detail="onboarding required")
    return principal
