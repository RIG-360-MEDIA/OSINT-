"""API-key authentication for /v1 — resolves a key to its org principal.

Parallel to auth/middleware.py's JWT path, but deliberately separate:
  * It reads ONLY the API key (Authorization: Bearer … or X-API-Key: …).
  * It NEVER reads X-Impersonate — client keys can never impersonate, so the
    header is structurally ignored (impersonation is impossible on /v1).
  * Auth failures all return an identical terse 401 so a caller cannot probe
    whether a key exists, is revoked, or is expired.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import text

from db import get_db

from . import keys
from .errors import server_error, unauthorized
from .settings import DEFAULT_RATE_LIMIT_PER_MIN, hash_secret

logger = logging.getLogger("osint-v1.auth")


@dataclass(frozen=True)
class ApiPrincipal:
    """The authenticated client: an org plus the key's limits. Immutable."""

    org_id: str
    org_name: str | None
    key_id: str
    is_sandbox: bool
    rate_limit_per_min: int
    monthly_quota: int | None
    can_manage: bool = False


def _extract_key(request: Request) -> str | None:
    """Pull the raw key from Authorization: Bearer or X-API-Key. None if absent."""
    auth = request.headers.get("Authorization", "").strip()
    if auth:
        parts = auth.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
            return parts[1].strip()
    xkey = request.headers.get("X-API-Key", "").strip()
    return xkey or None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_api_principal(request: Request) -> ApiPrincipal:
    """Resolve the request's API key to an ApiPrincipal, or raise 401/500.

    The org is derived entirely from the key. Nothing the client sends (params,
    other headers) can widen or change it.
    """
    raw = _extract_key(request)
    if not raw or not keys.is_well_formed(raw):
        raise unauthorized()

    key_hash = keys.hash_key(raw, hash_secret())
    try:
        async with get_db() as db:
            row = (await db.execute(text("""
                SELECT k.id::text          AS key_id,
                       k.org_id::text      AS org_id,
                       k.is_sandbox        AS is_sandbox,
                       k.rate_limit_per_min AS rate_limit_per_min,
                       k.monthly_quota     AS monthly_quota,
                       k.expires_at        AS expires_at,
                       k.revoked_at        AS revoked_at,
                       COALESCE(k.can_manage, false) AS can_manage,
                       o.name              AS org_name
                  FROM analytics.api_keys k
                  JOIN analytics.orgs o ON o.id = k.org_id
                 WHERE k.key_hash = :h
            """), {"h": key_hash})).fetchone()
    except Exception:
        logger.exception("api_keys lookup failed")
        raise server_error()

    # Identical response for: no match, revoked, expired — no existence oracle.
    if row is None or row.revoked_at is not None:
        raise unauthorized()
    if row.expires_at is not None and row.expires_at <= _utcnow():
        raise unauthorized()

    principal = ApiPrincipal(
        org_id=row.org_id,
        org_name=row.org_name,
        key_id=row.key_id,
        is_sandbox=bool(row.is_sandbox),
        rate_limit_per_min=int(row.rate_limit_per_min or DEFAULT_RATE_LIMIT_PER_MIN),
        monthly_quota=row.monthly_quota,
        can_manage=bool(row.can_manage),
    )

    # Stash for the metering middleware (read off request.state after handler).
    request.state.api_org_id = principal.org_id
    request.state.api_key_id = principal.key_id
    request.state.api_is_sandbox = principal.is_sandbox
    return principal
