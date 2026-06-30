"""Consistent error + response envelopes for the /v1 gateway.

The client contract (per the API docs) is:
    success: {"data": ..., "meta": {...}?}
    error:   {"error": {"code": str, "message": str, "status": int}}

``GatewayError`` is raised only by /v1 code; the registered handler renders the
error envelope. Because no other router raises it, installing the handler
app-wide does not affect the JWT dashboard surface.

Error messages are deliberately terse and generic for auth/scope failures —
they never reveal whether a key exists, whether an object exists out of scope,
or any internal detail.
"""
from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class GatewayError(Exception):
    """A client-facing /v1 error with a stable code + HTTP status."""

    def __init__(self, status: int, code: str, message: str, *, headers: dict[str, str] | None = None) -> None:
        self.status = status
        self.code = code
        self.message = message
        self.headers = headers or {}
        super().__init__(message)


# ── Canonical errors (factories keep messages uniform + leak-free) ──────────

def unauthorized(message: str = "Invalid or missing API key") -> GatewayError:
    return GatewayError(401, "unauthorized", message, headers={"WWW-Authenticate": "Bearer"})


def forbidden(message: str = "Not permitted") -> GatewayError:
    return GatewayError(403, "forbidden", message)


def not_found(message: str = "Resource not found") -> GatewayError:
    # Used for both genuinely-missing and out-of-scope objects — identical
    # response so a client cannot probe existence outside their scope.
    return GatewayError(404, "not_found", message)


def bad_request(message: str) -> GatewayError:
    return GatewayError(400, "bad_request", message)


def rate_limited(retry_after: int) -> GatewayError:
    err = GatewayError(429, "rate_limited", "Too many requests",
                       headers={"Retry-After": str(max(1, int(retry_after)))})
    return err


def quota_exceeded() -> GatewayError:
    return GatewayError(429, "quota_exceeded", "Monthly quota exceeded")


def server_error(message: str = "Internal error") -> GatewayError:
    return GatewayError(500, "server_error", message)


async def gateway_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Render a GatewayError as the client error envelope."""
    if not isinstance(exc, GatewayError):  # defensive; handler is registered for GatewayError
        return JSONResponse(status_code=500, content={
            "error": {"code": "server_error", "message": "Internal error", "status": 500}})
    body = {"error": {"code": exc.code, "message": exc.message, "status": exc.status}}
    if exc.status == 429 and "retry_after" not in body["error"]:
        ra = exc.headers.get("Retry-After")
        if ra:
            body["error"]["retry_after"] = int(ra)
    return JSONResponse(status_code=exc.status, content=body, headers=exc.headers)


# ── Success envelopes ───────────────────────────────────────────────────────

def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Wrap a payload in the success envelope."""
    out: dict[str, Any] = {"data": data}
    if meta is not None:
        out["meta"] = meta
    return out
