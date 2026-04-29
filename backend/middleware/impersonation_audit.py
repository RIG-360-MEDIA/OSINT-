"""
ASGI middleware that logs every request to `impersonation_actions` when the
caller has an active impersonation cookie.

This is the *only* file that runs on every request, so it must be:
  - Cheap when there is no cookie (one dict lookup, no DB call)
  - Resilient — never fail-closed; a logging error must not break the response
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable
from uuid import UUID

from fastapi import Request, Response
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

from backend.auth.auth_middleware import IMPERSONATION_COOKIE
from backend.database import get_db

logger = logging.getLogger(__name__)


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


class ImpersonationAuditMiddleware(BaseHTTPMiddleware):
    """Log (method, path, status) for every request bearing an impersonation cookie.

    The cookie is set only after a super_admin opens a session via
    `POST /api/admin/impersonate/{id}`, so a stray cookie cannot fabricate
    audit rows — the FK to `impersonation_sessions(id)` makes a bogus value
    fail the insert.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)

        cookie_value = request.cookies.get(IMPERSONATION_COOKIE)
        if not cookie_value or not _is_uuid(cookie_value):
            return response

        # Don't log the impersonation lifecycle endpoints themselves —
        # otherwise "view as" produces a self-referential row.
        path = request.url.path
        if path.startswith("/api/admin/impersonate"):
            return response

        try:
            async with get_db() as db:
                await db.execute(
                    text("""
                        INSERT INTO impersonation_actions
                            (session_id, method, path, status_code)
                        VALUES (:sid, :method, :path, :status)
                    """),
                    {
                        "sid": cookie_value,
                        "method": request.method,
                        "path": path[:512],  # keep TEXT column compact
                        "status": response.status_code,
                    },
                )
                await db.commit()
        except Exception as exc:
            # FK violation (cookie pointed at a deleted/closed session) is the
            # most common path — log at debug, not warning.
            logger.debug("Impersonation audit insert skipped: %s", exc)

        return response
