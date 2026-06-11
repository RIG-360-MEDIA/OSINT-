"""Supabase JWT auth + role-aware principal resolution for osint-backend.

Modelled on rig-backend/backend/auth/auth_middleware.py — same library
(python-jose) and same HS256 + SUPABASE_JWT_SECRET pattern. Differences:

  - We resolve users from `analytics.users` (not public.users) — keeps the
    osint product self-contained.
  - Role model is org-template based: `is_super_admin` boolean + the org's
    `role_template` (govt / pr / journalist / academic / corporate).
  - No impersonation flow yet (defer — rig-backend's `impersonation_sessions`
    is out of scope for the brief product right now).
"""
from __future__ import annotations

import base64
import json
import logging
import os
import time
from typing import Any

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text

from db import get_db

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)

_JWT_SECRET = os.getenv("OSINT_SUPABASE_JWT_SECRET", "") or os.getenv("SUPABASE_JWT_SECRET", "")
_ENVIRONMENT = os.getenv("OSINT_ENVIRONMENT", os.getenv("ENVIRONMENT", "development")).lower()


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

async def get_current_principal(
    user: dict[str, str] = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the effective principal — JWT identity + DB row from analytics.users.

    Shape:
        {
            "id":              uuid str,
            "email":           str,
            "full_name":       str | None,
            "designation":     str | None,
            "is_super_admin":  bool,
            "org_id":          uuid str | None,
            "org_name":        str | None,
            "role_template":   str | None,
            "onboarded":       bool,
        }

    If the user is in Supabase but not yet in analytics.users (first login
    after invite acceptance), returns a "stub" principal — callers can use the
    `onboarded` flag to gate access to the wizard.
    """
    async with get_db() as db:
        row = (await db.execute(text("""
            SELECT u.id, u.email, u.full_name, u.designation, u.is_super_admin,
                   u.org_id, u.onboarded_at,
                   o.name AS org_name, o.role_template
              FROM analytics.users u
              LEFT JOIN analytics.orgs o ON o.id = u.org_id
             WHERE u.id = CAST(:uid AS uuid)
        """), {"uid": user["id"]})).fetchone()

    if row is None:
        return {
            "id": user["id"],
            "email": user["email"],
            "full_name": None,
            "designation": None,
            "is_super_admin": False,
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
        "org_id": str(row.org_id) if row.org_id else None,
        "org_name": row.org_name,
        "role_template": row.role_template,
        "onboarded": row.onboarded_at is not None,
    }


async def require_super_admin(
    principal: dict[str, Any] = Depends(get_current_principal),
) -> dict[str, Any]:
    """403 unless caller is super_admin in analytics.users."""
    if not principal["is_super_admin"]:
        raise HTTPException(status_code=403, detail="super_admin required")
    return principal


async def require_onboarded(
    principal: dict[str, Any] = Depends(get_current_principal),
) -> dict[str, Any]:
    """403 unless caller has finished the onboarding wizard."""
    if not principal["onboarded"]:
        raise HTTPException(status_code=403, detail="onboarding required")
    return principal
