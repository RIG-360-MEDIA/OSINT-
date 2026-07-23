"""backend.draftsmith.api.auth — Bearer token auth + editor identity.

The token lives in the env var named by config.API_TOKEN_ENV (resolved at
request time — never inlined/hardcoded); compared against the request's
Authorization header with a constant-time comparison so a timing side
channel can't leak it byte by byte. The acting editor's id (a real email —
every write-path in backend.draftsmith.db enforces the '@' shape) comes from
the X-Editor-Id header, forwarded by the CMS layer that sits in front of
this service.
"""
from __future__ import annotations

import hmac
import os

from fastapi import Header
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.draftsmith import config


def _configured_token() -> str:
    token = os.environ.get(config.API_TOKEN_ENV, "")
    if not token:
        raise StarletteHTTPException(
            status_code=503,
            detail={
                "code": "server_misconfigured",
                "message": f"{config.API_TOKEN_ENV} is not set on the server",
            },
        )
    return token


async def require_bearer_token(authorization: str = Header(default="")) -> None:
    """FastAPI dependency: 401s unless `Authorization: Bearer <token>` matches
    the configured token. Mounted app-wide in app.py so every route (except
    /healthz) requires it."""
    expected = _configured_token()
    prefix = "Bearer "
    provided = authorization[len(prefix):] if authorization.startswith(prefix) else ""
    if not provided or not hmac.compare_digest(provided, expected):
        raise StarletteHTTPException(
            status_code=401,
            detail={"code": "unauthorized", "message": "missing or invalid bearer token"},
        )


async def get_editor_id(x_editor_id: str = Header(default="")) -> str:
    """FastAPI dependency: the acting editor's id, forwarded as X-Editor-Id.

    Bare presence is checked here; the real-email shape check ('@' in id) is
    enforced independently by backend.draftsmith.db on every write that needs
    a genuine editor identity (create_job, resolve_flag, record_publish), so
    a caller can never bypass that guarantee by only satisfying this layer.
    """
    editor_id = x_editor_id.strip()
    if not editor_id:
        raise StarletteHTTPException(
            status_code=400,
            detail={"code": "missing_editor_id", "message": "X-Editor-Id header is required"},
        )
    return editor_id
