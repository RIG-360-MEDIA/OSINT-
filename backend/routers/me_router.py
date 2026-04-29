"""
/api/me/* — endpoints describing the *current* principal.

Used by the frontend middleware to decide route gating in one round-trip:
which pages the user can see, whether they finished onboarding, whether
they have any tracked entities, and whether the request is being made
under an active impersonation session.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text

from backend.auth.auth_middleware import get_current_principal
from backend.database import get_db

logger = logging.getLogger(__name__)

me_router = APIRouter(prefix="/api/me", tags=["me"])


@me_router.get("/access")
async def get_my_access(
    principal: dict = Depends(get_current_principal),
) -> dict:
    """Return everything the frontend needs to gate routes for this user.

    Response shape:
        {
            "user_id": str,                # effective id (impersonated when applicable)
            "email": str,
            "role": "user" | "super_admin",
            "allowed_pages": list[str],    # page slugs
            "has_profile": bool,           # user_profiles row with role_type
            "has_entities": bool,          # >=1 user_entities row
            "is_impersonating": bool,
            "real_email": str | None,      # the admin's email when impersonating
            "target_email": str | None,    # the impersonated user's email
        }

    Super_admins are reported with all KNOWN_PAGES regardless of their
    user_page_access rows — the gate logic short-circuits on role.
    """
    effective_id = principal["id"]
    role = principal["role"]

    async with get_db() as db:
        if role == "super_admin":
            # Mirror KNOWN_PAGES from auth_middleware. Hard-coded here to keep
            # this endpoint independent of import-time state.
            allowed = [
                "coverage", "clips", "cuttings", "threads", "signals",
                "documents", "brief", "analyst", "worldmonitor",
            ]
        else:
            pages_result = await db.execute(
                text("""
                    SELECT page_slug
                    FROM user_page_access
                    WHERE user_id = :uid
                    ORDER BY page_slug
                """),
                {"uid": effective_id},
            )
            allowed = [r.page_slug for r in pages_result.fetchall()]

        profile_result = await db.execute(
            text("""
                SELECT 1 FROM user_profiles
                WHERE user_id = :uid AND role_type IS NOT NULL
                LIMIT 1
            """),
            {"uid": effective_id},
        )
        has_profile = profile_result.fetchone() is not None

        entities_result = await db.execute(
            text("""
                SELECT 1 FROM user_entities
                WHERE user_id = :uid
                LIMIT 1
            """),
            {"uid": effective_id},
        )
        has_entities = entities_result.fetchone() is not None

    return {
        "user_id": effective_id,
        "email": principal["email"],
        "role": role,
        "allowed_pages": allowed,
        "has_profile": has_profile,
        "has_entities": has_entities,
        "is_impersonating": principal["is_impersonating"],
        "real_email": principal["real_email"] if principal["is_impersonating"] else None,
        "target_email": principal["target_email"],
    }
