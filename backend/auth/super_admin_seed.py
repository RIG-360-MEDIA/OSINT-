"""Super-admin bootstrap.

Reads ``SUPER_ADMIN_EMAILS`` from ``infrastructure/.env``, resolves each
email to its Supabase Auth user id via the admin API, and idempotently
upserts a row in ``public.users`` with ``role='super_admin'``.

Replaces the hard-coded ``UPDATE users SET role = 'super_admin' WHERE
email = 'pranavsinghpuri09@gmail.com'`` block in migration 030. Any
operator can now bootstrap their own super-admin account by setting:

    SUPER_ADMIN_EMAILS=ops@example.com,backup@example.com

…signing up with each email at /signup, and restarting the backend.

Design notes:

* The hook is **idempotent** — re-running on every boot is safe. It uses
  ``INSERT ... ON CONFLICT (id) DO UPDATE`` so an existing row is bumped
  to ``super_admin`` if it isn't already.
* The hook is **non-fatal** — Supabase outage or missing env var logs a
  warning and continues. The backend boots without super-admin access
  rather than refusing to start.
* The hook **never creates Supabase auth accounts**. The operator must
  sign up at ``/signup`` first; only then will this hook find the user
  via ``GET /auth/v1/admin/users?email=...`` and flip the role.
"""
from __future__ import annotations

import logging
import os
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import text

from backend.config import settings
from backend.database import get_db

logger = logging.getLogger(__name__)


async def _lookup_supabase_user_id(
    email: str,
    *,
    supabase_url: str,
    service_key: str,
    client: httpx.AsyncClient,
) -> str | None:
    """Look up a Supabase auth.users id by email via the admin API.

    Returns None if the user doesn't exist yet (operator hasn't signed up),
    or if Supabase returns a non-200 / unparseable response. Never raises.
    """
    try:
        resp = await client.get(
            f"{supabase_url}/auth/v1/admin/users",
            params={"email": email},
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
            },
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        logger.warning(
            "super-admin seed: Supabase admin API unreachable for %s: %s",
            email,
            exc,
        )
        return None

    if resp.status_code != 200:
        logger.warning(
            "super-admin seed: Supabase admin API returned %d for %s — %s",
            resp.status_code,
            email,
            resp.text[:200],
        )
        return None

    try:
        body: Any = resp.json()
    except ValueError:
        logger.warning("super-admin seed: non-JSON Supabase response for %s", email)
        return None

    # The admin endpoint returns either {"users": [...]} or a list directly,
    # depending on auth-js version. Normalize both.
    users = body.get("users") if isinstance(body, dict) else body
    if not isinstance(users, list):
        return None

    target = email.lower()
    for u in users:
        if not isinstance(u, dict):
            continue
        if str(u.get("email", "")).lower() == target:
            user_id = u.get("id")
            if isinstance(user_id, str) and _is_valid_uuid(user_id):
                return user_id
    return None


def _is_valid_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


async def _promote_user(user_id: str, email: str) -> bool:
    """Upsert ``public.users`` row with role='super_admin'. Returns True on
    a state change (insert or role flip), False if already super_admin."""
    async with get_db() as db:
        existing = (
            await db.execute(
                text("SELECT role FROM users WHERE id = :uid"),
                {"uid": user_id},
            )
        ).fetchone()

        already_admin = existing is not None and existing.role == "super_admin"

        await db.execute(
            text(
                """
                INSERT INTO users (id, email, role)
                VALUES (:uid, :email, 'super_admin')
                ON CONFLICT (id) DO UPDATE
                  SET role  = 'super_admin',
                      email = EXCLUDED.email
                """
            ),
            {"uid": user_id, "email": email},
        )
        await db.commit()
        return not already_admin


async def seed_super_admins() -> dict[str, int]:
    """Run the super-admin bootstrap. Safe to call on every boot.

    Returns a small summary dict: ``{requested, promoted, missing, skipped}``
    so the boot logs show exactly what happened.
    """
    emails = settings.super_admin_emails_list
    summary = {
        "requested": len(emails),
        "promoted": 0,  # actual state change
        "already_admin": 0,
        "missing": 0,  # email not found in Supabase yet
        "skipped": 0,  # config error
    }

    if not emails:
        logger.info(
            "super-admin seed: SUPER_ADMIN_EMAILS unset — no admins promoted "
            "(set the env var and restart to bootstrap)."
        )
        return summary

    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    service_key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not supabase_url or not service_key:
        logger.warning(
            "super-admin seed: SUPABASE_URL or SUPABASE_SERVICE_KEY missing — "
            "cannot resolve admin emails."
        )
        summary["skipped"] = len(emails)
        return summary

    async with httpx.AsyncClient() as client:
        for email in emails:
            user_id = await _lookup_supabase_user_id(
                email,
                supabase_url=supabase_url,
                service_key=service_key,
                client=client,
            )
            if not user_id:
                logger.info(
                    "super-admin seed: %s not in Supabase yet — sign up at /signup first.",
                    email,
                )
                summary["missing"] += 1
                continue

            try:
                changed = await _promote_user(user_id, email)
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "super-admin seed: DB error promoting %s: %s", email, exc
                )
                summary["skipped"] += 1
                continue

            if changed:
                logger.info("super-admin seed: promoted %s (%s) to super_admin", email, user_id)
                summary["promoted"] += 1
            else:
                summary["already_admin"] += 1

    logger.info("super-admin seed summary: %s", summary)
    return summary


__all__ = ["seed_super_admins"]
