"""Client-facing /v1 API gateway for the OSINT backend.

A sealed, key-authenticated, per-org-scoped read API that external clients
use to pull their own slice of intelligence. Isolated from the JWT dashboard
surface: it never touches Supabase JWTs or impersonation, and every data path
is forced through one central scope gate (see ``scope.py``) so leak-safety is
enforced in a single auditable place.

``install_v1(app)`` wires the router, the metering middleware, and the error
handler onto the existing FastAPI app with one call from ``main.py``.
"""
from __future__ import annotations

from fastapi import FastAPI


def install_v1(app: FastAPI) -> None:
    """Mount the /v1 gateway onto an existing app (idempotent-ish; call once)."""
    # Lazy imports keep package import cheap and avoid import cycles at module load.
    from .errors import GatewayError, gateway_error_handler
    from .metering import MeteringMiddleware
    from .router import router

    app.add_exception_handler(GatewayError, gateway_error_handler)
    app.add_middleware(MeteringMiddleware)
    app.include_router(router)
