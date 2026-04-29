"""
Request-ID middleware.

Generates (or honours an inbound) `X-Request-Id` for every HTTP request and
exposes it via a `contextvars.ContextVar` so downstream code can include it
in log lines without threading it through every function signature.

The id is also echoed back on the response so a client error report can
be correlated with server logs.
"""
from __future__ import annotations

import contextvars
import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

_REQUEST_ID_CTX: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


def get_request_id() -> str:
    """Return the request id for the current task, or '-' if outside a request."""
    return _REQUEST_ID_CTX.get()


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a stable request id to every request lifecycle."""

    HEADER = "X-Request-Id"

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        rid = request.headers.get(self.HEADER) or uuid.uuid4().hex[:16]
        token = _REQUEST_ID_CTX.set(rid)
        try:
            response = await call_next(request)
        finally:
            _REQUEST_ID_CTX.reset(token)
        response.headers[self.HEADER] = rid
        return response
