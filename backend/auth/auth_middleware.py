from __future__ import annotations

import base64
import json
import logging
import os
import time
from typing import Optional
from uuid import UUID

from fastapi import Cookie, Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text

from backend.database import get_db

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)

_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
_ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()

# Cookie name set by the admin "view as" flow.
IMPERSONATION_COOKIE = "rig_impersonate"

# All known page slugs (kept in sync with migration 021 + frontend middleware).
KNOWN_PAGES: frozenset[str] = frozenset({
    "coverage",
    "clips",
    "cuttings",
    "threads",
    "signals",
    "documents",
    "brief",
    "analyst",
    "worldmonitor",
})


# ── JWT decoding ──────────────────────────────────────────────────────────────

def _decode_unverified(token: str) -> dict:
    """Decode JWT payload without verifying the signature.

    Used as a fallback in dev when SUPABASE_JWT_SECRET is not set, and by tests
    that mint unsigned tokens.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Not a JWT")
        payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Malformed token: {exc}") from exc


def _decode_and_verify(token: str) -> dict:
    """Decode and (when configured) cryptographically verify the JWT.

    If SUPABASE_JWT_SECRET is set, verifies with HS256 — Supabase's default.
    Otherwise falls back to unverified decode (dev/test only). When ENVIRONMENT
    is "production" and no secret is configured, refuses to authenticate.
    """
    if _JWT_SECRET:
        try:
            from jose import jwt, JWTError
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


# ── Core dependencies ─────────────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """FastAPI dependency. Returns the *real* (non-impersonated) authenticated user.

    Returned dict shape:
        {"id": str, "email": str}

    For role/impersonation-aware code, use `get_current_principal` instead.
    """
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

    return {"id": user_id, "email": email}


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict | None:
    """Returns None if not authenticated. Used for optional-auth endpoints."""
    if not credentials:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


# ── Role + impersonation aware principal ──────────────────────────────────────

def _is_valid_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


async def _resolve_role(user_id: str) -> str:
    """Read users.role for a given id. Returns 'user' if row missing."""
    async with get_db() as db:
        result = await db.execute(
            text("SELECT role FROM users WHERE id = :uid"),
            {"uid": user_id},
        )
        row = result.fetchone()
        return (row.role if row and row.role else "user")


async def _resolve_impersonation(
    cookie_value: str,
    admin_id: str,
) -> Optional[dict]:
    """Validate an impersonation cookie. Returns target user info or None.

    The cookie holds an impersonation_sessions UUID. Only the admin who opened
    the session can use it. Closed (ended_at IS NOT NULL) sessions are ignored.
    """
    if not _is_valid_uuid(cookie_value):
        return None

    async with get_db() as db:
        result = await db.execute(
            text("""
                SELECT s.id, s.target_user_id, u.email AS target_email
                FROM impersonation_sessions s
                JOIN users u ON u.id = s.target_user_id
                WHERE s.id = :sid
                  AND s.admin_id = :admin_id
                  AND s.ended_at IS NULL
            """),
            {"sid": cookie_value, "admin_id": admin_id},
        )
        row = result.fetchone()
        if not row:
            return None
        return {
            "session_id": str(row.id),
            "target_user_id": str(row.target_user_id),
            "target_email": row.target_email or "",
        }


async def get_current_principal(
    request: Request,
    user: dict = Depends(get_current_user),
    impersonation_cookie: Optional[str] = Cookie(default=None, alias=IMPERSONATION_COOKIE),
) -> dict:
    """Returns the effective principal, honoring super-admin impersonation.

    Returned dict shape:
        {
            "id": effective_user_id,
            "email": effective_email,
            "role": "user" | "super_admin",
            "is_impersonating": bool,
            "real_id": str,            # the authenticated user (admin) id
            "real_email": str,
            "impersonation_session_id": str | None,
            "target_email": str | None,
        }

    Impersonation rules:
      - Only super_admins can impersonate.
      - The cookie must reference a non-closed session opened by *this* admin.
      - Otherwise the cookie is ignored (no error) and the admin acts as themself.
    """
    real_id = user["id"]
    real_email = user["email"]
    role = await _resolve_role(real_id)

    is_impersonating = False
    effective_id = real_id
    effective_email = real_email
    session_id: Optional[str] = None
    target_email: Optional[str] = None

    if role == "super_admin" and impersonation_cookie:
        imp = await _resolve_impersonation(impersonation_cookie, real_id)
        if imp:
            is_impersonating = True
            effective_id = imp["target_user_id"]
            effective_email = imp["target_email"]
            session_id = imp["session_id"]
            target_email = imp["target_email"]

    return {
        "id": effective_id,
        "email": effective_email,
        "role": role,
        "is_impersonating": is_impersonating,
        "real_id": real_id,
        "real_email": real_email,
        "impersonation_session_id": session_id,
        "target_email": target_email,
    }


# ── Page-access + role gates ──────────────────────────────────────────────────

async def _user_has_page(user_id: str, page_slug: str) -> bool:
    async with get_db() as db:
        result = await db.execute(
            text("""
                SELECT 1 FROM user_page_access
                WHERE user_id = :uid AND page_slug = :slug
            """),
            {"uid": user_id, "slug": page_slug},
        )
        return result.fetchone() is not None


def require_page(page_slug: str):
    """Build a FastAPI dependency that gates a router on page-access.

    Super_admins always pass. Otherwise the user must have a row in
    user_page_access for `page_slug`. Unknown slugs raise immediately at
    dependency-build time so typos surface in dev.
    """
    if page_slug not in KNOWN_PAGES:
        raise ValueError(f"require_page: unknown slug '{page_slug}'")

    async def _dep(
        principal: dict = Depends(get_current_principal),
    ) -> dict:
        if principal["role"] == "super_admin":
            return principal
        # Use the *real* admin id when impersonating? No — impersonation by a
        # super_admin already short-circuits above. For a normal user, check
        # the real id (which equals effective id since they cannot impersonate).
        if not await _user_has_page(principal["id"], page_slug):
            raise HTTPException(
                status_code=403,
                detail={"error": "page_forbidden", "page": page_slug},
            )
        return principal

    return _dep


async def require_super_admin(
    principal: dict = Depends(get_current_principal),
) -> dict:
    """Dependency: 403 unless caller is super_admin (in their *real* identity)."""
    if principal["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="super_admin required")
    return principal
