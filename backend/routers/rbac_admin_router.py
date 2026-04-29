"""
Super-admin endpoints for RBAC + impersonation.

Lives alongside the existing dev-only `admin_router` (which handles entity
dictionary). Both share the `/api/admin` prefix but routes do not overlap:
this file owns `/users/*` and `/impersonate/*`. Auth is enforced router-level
via `require_super_admin` — every endpoint requires the caller's *real*
identity to be a super_admin (impersonation cannot be used to grant access).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from backend.auth.auth_middleware import (
    IMPERSONATION_COOKIE,
    KNOWN_PAGES,
    require_super_admin,
)
from backend.database import get_db
from backend.rate_limiter import rate_limit

logger = logging.getLogger(__name__)

rbac_admin_router = APIRouter(
    prefix="/api/admin",
    tags=["admin-rbac"],
    dependencies=[Depends(require_super_admin)],
)


# ── Request models ────────────────────────────────────────────────────────────

class SetPagesRequest(BaseModel):
    """Replaces the user's full page-grant set."""
    pages: list[str] = Field(default_factory=list)


class SetRoleRequest(BaseModel):
    role: str  # 'user' | 'super_admin'


class ImpersonateRequest(BaseModel):
    reason: str | None = None


# ── User listing + management ─────────────────────────────────────────────────

@rbac_admin_router.get("/users")
async def list_users(_p: dict = Depends(require_super_admin)) -> dict:
    """List every user with role, email, page-grant set, and entity count.

    The frontend admin table renders directly from this payload.
    """
    async with get_db() as db:
        rows = (await db.execute(
            text("""
                SELECT
                    u.id,
                    u.email,
                    u.role,
                    u.created_at,
                    COALESCE(
                        (
                            SELECT array_agg(page_slug ORDER BY page_slug)
                            FROM user_page_access upa
                            WHERE upa.user_id = u.id
                        ),
                        ARRAY[]::text[]
                    ) AS allowed_pages,
                    (
                        SELECT COUNT(*)::int FROM user_entities ue
                        WHERE ue.user_id = u.id
                    ) AS entity_count,
                    EXISTS (
                        SELECT 1 FROM user_profiles up
                        WHERE up.user_id = u.id AND up.role_type IS NOT NULL
                    ) AS has_profile
                FROM users u
                ORDER BY u.created_at DESC NULLS LAST, u.email
            """)
        )).fetchall()

    return {
        "users": [
            {
                "id": str(r.id),
                "email": r.email or "",
                "role": r.role or "user",
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "allowed_pages": list(r.allowed_pages or []),
                "entity_count": r.entity_count or 0,
                "has_profile": bool(r.has_profile),
            }
            for r in rows
        ],
        "known_pages": sorted(KNOWN_PAGES),
    }


@rbac_admin_router.put("/users/{user_id}/pages")
async def set_user_pages(
    user_id: str,
    req: SetPagesRequest,
    principal: dict = Depends(require_super_admin),
) -> dict:
    """Replace a user's page-grant set with the supplied list.

    Unknown slugs are rejected with 400. Slugs are deduped and validated
    against KNOWN_PAGES before any write.
    """
    requested = set(req.pages)
    unknown = requested - KNOWN_PAGES
    if unknown:
        raise HTTPException(
            status_code=400,
            detail={"error": "unknown_pages", "pages": sorted(unknown)},
        )

    async with get_db() as db:
        # Confirm target user exists — friendlier 404 than a silent no-op.
        exists_row = (await db.execute(
            text("SELECT 1 FROM users WHERE id = :uid"),
            {"uid": user_id},
        )).fetchone()
        if not exists_row:
            raise HTTPException(status_code=404, detail="user not found")

        # Replace strategy: delete + reinsert. The set is small (<20 rows).
        await db.execute(
            text("DELETE FROM user_page_access WHERE user_id = :uid"),
            {"uid": user_id},
        )
        for slug in sorted(requested):
            await db.execute(
                text("""
                    INSERT INTO user_page_access (user_id, page_slug, granted_by)
                    VALUES (:uid, :slug, :admin_id)
                """),
                {"uid": user_id, "slug": slug, "admin_id": principal["real_id"]},
            )
        await db.commit()

    logger.info(
        "RBAC: admin %s set pages for %s → %s",
        principal["real_email"], user_id, sorted(requested),
    )
    return {"success": True, "user_id": user_id, "pages": sorted(requested)}


@rbac_admin_router.put("/users/{user_id}/role")
async def set_user_role(
    user_id: str,
    req: SetRoleRequest,
    principal: dict = Depends(require_super_admin),
) -> dict:
    """Promote or demote a user. The CHECK constraint on users.role enforces
    the allowed values, but we validate ahead of the write for a clean 400.

    A super_admin may demote themself, but the operation will leave them
    unable to call this endpoint again from the next request — caller's
    responsibility to confirm.
    """
    if req.role not in ("user", "super_admin"):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_role", "got": req.role},
        )

    async with get_db() as db:
        result = await db.execute(
            text("UPDATE users SET role = :role WHERE id = :uid"),
            {"role": req.role, "uid": user_id},
        )
        await db.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="user not found")

    logger.info(
        "RBAC: admin %s set role for %s → %s",
        principal["real_email"], user_id, req.role,
    )
    return {"success": True, "user_id": user_id, "role": req.role}


# ── Impersonation ─────────────────────────────────────────────────────────────
# NOTE: route declaration order matters — the static `/impersonate/end` and
# `/impersonate/sessions` routes MUST be declared before the parametric
# `/impersonate/{target_user_id}` route, otherwise FastAPI will match "end"
# and "sessions" as user IDs.

@rbac_admin_router.post(
    "/impersonate/end",
    dependencies=[Depends(rate_limit("impersonate_end", max_calls=30))],
)
async def end_impersonation(
    response: Response,
    principal: dict = Depends(require_super_admin),
    cookie_value: str | None = Cookie(default=None, alias=IMPERSONATION_COOKIE),
) -> dict:
    """Close the active impersonation session and clear the cookie."""
    closed = 0
    if cookie_value:
        async with get_db() as db:
            result = await db.execute(
                text("""
                    UPDATE impersonation_sessions
                       SET ended_at = NOW()
                     WHERE id = :sid
                       AND admin_id = :admin_id
                       AND ended_at IS NULL
                """),
                {"sid": cookie_value, "admin_id": principal["real_id"]},
            )
            await db.commit()
            closed = result.rowcount or 0

    response.delete_cookie(IMPERSONATION_COOKIE, path="/")

    logger.info(
        "Impersonation ended: admin %s closed %d session(s)",
        principal["real_email"], closed,
    )
    return {"success": True, "closed": closed}


@rbac_admin_router.get("/impersonate/sessions")
async def list_impersonation_sessions(
    limit: int = 100,
    _p: dict = Depends(require_super_admin),
) -> dict:
    """Audit view: most recent impersonation sessions across all admins."""
    limit = max(1, min(500, limit))
    async with get_db() as db:
        rows = (await db.execute(
            text("""
                SELECT
                    s.id,
                    s.started_at,
                    s.ended_at,
                    s.reason,
                    a.email AS admin_email,
                    t.email AS target_email,
                    (
                        SELECT COUNT(*)::int FROM impersonation_actions ia
                        WHERE ia.session_id = s.id
                    ) AS action_count
                FROM impersonation_sessions s
                JOIN users a ON a.id = s.admin_id
                JOIN users t ON t.id = s.target_user_id
                ORDER BY s.started_at DESC
                LIMIT :lim
            """),
            {"lim": limit},
        )).fetchall()

    def _iso(value: datetime | None) -> str | None:
        if not value:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()

    return {
        "sessions": [
            {
                "id": str(r.id),
                "started_at": _iso(r.started_at),
                "ended_at": _iso(r.ended_at),
                "reason": r.reason,
                "admin_email": r.admin_email or "",
                "target_email": r.target_email or "",
                "action_count": r.action_count or 0,
            }
            for r in rows
        ]
    }


@rbac_admin_router.post(
    "/impersonate/{target_user_id}",
    dependencies=[Depends(rate_limit("impersonate_start", max_calls=30))],
)
async def start_impersonation(
    target_user_id: str,
    req: ImpersonateRequest,
    response: Response,
    principal: dict = Depends(require_super_admin),
) -> dict:
    """Open an impersonation session and set the cookie.

    Refuses to impersonate self (no-op) or another super_admin (footgun
    prevention; if you really need it, demote first). Closes any pre-existing
    open sessions for this admin so we don't leak rows.
    """
    if target_user_id == principal["real_id"]:
        raise HTTPException(status_code=400, detail="cannot impersonate self")

    async with get_db() as db:
        target_row = (await db.execute(
            text("SELECT id, email, role FROM users WHERE id = :uid"),
            {"uid": target_user_id},
        )).fetchone()
        if not target_row:
            raise HTTPException(status_code=404, detail="user not found")
        if target_row.role == "super_admin":
            raise HTTPException(
                status_code=400,
                detail="cannot impersonate another super_admin",
            )

        # Close any open sessions for this admin before opening a new one.
        await db.execute(
            text("""
                UPDATE impersonation_sessions
                   SET ended_at = NOW()
                 WHERE admin_id = :admin_id AND ended_at IS NULL
            """),
            {"admin_id": principal["real_id"]},
        )

        new_row = (await db.execute(
            text("""
                INSERT INTO impersonation_sessions
                    (admin_id, target_user_id, reason)
                VALUES (:admin_id, :target, :reason)
                RETURNING id
            """),
            {
                "admin_id": principal["real_id"],
                "target": target_user_id,
                "reason": req.reason,
            },
        )).fetchone()
        session_id = str(new_row.id)
        await db.commit()

    response.set_cookie(
        key=IMPERSONATION_COOKIE,
        value=session_id,
        httponly=True,
        secure=False,  # set True behind HTTPS in production
        samesite="lax",
        max_age=60 * 60 * 8,  # 8h hard cap
        path="/",
    )

    logger.info(
        "Impersonation started: admin %s → target %s (session %s)",
        principal["real_email"], target_row.email, session_id,
    )
    return {
        "success": True,
        "session_id": session_id,
        "target_user_id": target_user_id,
        "target_email": target_row.email or "",
    }
