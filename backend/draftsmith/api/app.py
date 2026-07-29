"""backend.draftsmith.api.app — the FastAPI app for the Door B service.

Mounts the job/draft/flags/images routers behind require_bearer_token
(app-wide, via the FastAPI() `dependencies=` list — see auth.py), and wraps
every response — success or error — in the {ok, data, error} envelope
(see _envelope.py). Run standalone with:

    python -m uvicorn backend.draftsmith.api.app:app --port <config.API_PORT>

or `python -m backend.draftsmith.api.app` directly.
"""
from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.draftsmith import config
from backend.draftsmith.api._envelope import detail_to_error, err
from backend.draftsmith.api.auth import require_bearer_token
from backend.draftsmith.api.routes_draft import router as draft_router
from backend.draftsmith.api.routes_flags import router as flags_router
from backend.draftsmith.api.routes_images import router as images_router
from backend.draftsmith.api.routes_bundle import router as bundle_router
from backend.draftsmith.api.routes_jobs import router as jobs_router

logger = logging.getLogger(__name__)

app = FastAPI(
    title="draftsmith",
    description="Door B (AI-assisted article generation) — Rig Wire",
    version="0.0.1",
    dependencies=[Depends(require_bearer_token)],
)

app.include_router(jobs_router)
app.include_router(bundle_router)
app.include_router(draft_router)
app.include_router(flags_router)
app.include_router(images_router)


@app.exception_handler(StarletteHTTPException)
async def _on_http_exception(_request: Request, exc: StarletteHTTPException):
    return detail_to_error(exc.status_code, exc.detail)


@app.exception_handler(RequestValidationError)
async def _on_validation_error(_request: Request, exc: RequestValidationError):
    return err("validation_error", str(exc.errors()), status_code=422)


@app.exception_handler(Exception)
async def _on_unhandled_error(_request: Request, exc: Exception):
    logger.exception("draftsmith API: unhandled error")
    return err("internal_error", "an unexpected error occurred", status_code=500)


@app.get("/healthz")
async def healthz() -> dict:
    # NOTE: FastAPI(dependencies=[...]) app-level dependencies apply to every
    # route including this one — a route-level `dependencies=[]` override
    # does NOT remove them. So /healthz also requires the bearer token; fine
    # for a box-internal probe hit by something that already has the token
    # (e.g. the deploy's own healthcheck), not meant as a public liveness URL.
    return {"ok": True, "data": {"status": "up"}, "error": None}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.draftsmith.api.app:app", host="0.0.0.0", port=config.API_PORT)
