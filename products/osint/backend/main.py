"""osint-backend — FastAPI service for the RIG OSINT Morning Brief.

Read-only API over the rig-postgres data engine. Connects as `analytics_user`
(Postgres-enforced read-only on public.*). Lives at port OSINT_PORT (default
8000 inside container, mapped to 8002 on host per kickoff).

Endpoints (all under /api/brief):
  GET /kpi       — KPI tiles (articles parsed, outlets, languages, sentiment)
  GET /entities  — 4 Watched Entity cards
  GET /emerging  — top-N surging entities (default 5)
  GET /stories   — Defining Stories from event_clusters (default 5)
  GET /health    — liveness probe (no DB call)
  GET /ready     — readiness probe (round-trips DB)
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from config import load_settings
from db import dispose_engine, get_db, get_engine
from routers import admin, climbing, cm_perspective, entities, emerging, executive, export, horizon, intel, kpi, me, mood, onboarding, posture, stories, textual, top_articles, voices

settings = load_settings()

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("osint-backend")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("osint-backend starting; pool_size=%d", settings.db_pool_size)
    get_engine()  # eager init so a bad DB URL fails fast
    yield
    await dispose_engine()
    logger.info("osint-backend stopped cleanly")


app = FastAPI(
    title="RIG OSINT Brief",
    description="Read-only API powering the Morning Brief frontend.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    # POST/PUT/DELETE are required for signup-accept, issue-invite, and
    # complete-onboarding. The old GET/OPTIONS-only list made every POST
    # fail the browser's preflight (400) while server-side tests passed.
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(kpi.router)
app.include_router(entities.router)
app.include_router(emerging.router)
app.include_router(stories.router)
app.include_router(top_articles.router)
app.include_router(executive.router)
app.include_router(cm_perspective.router)
app.include_router(posture.router)
app.include_router(textual.router)
app.include_router(export.router)
app.include_router(intel.router)
app.include_router(voices.router)
app.include_router(climbing.router)
app.include_router(horizon.router)
app.include_router(mood.router)
app.include_router(me.router)
app.include_router(admin.router)
app.include_router(onboarding.router)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["meta"])
async def ready() -> dict[str, str]:
    async with get_db() as db:
        row = (await db.execute(text("SELECT 1 AS one"))).fetchone()
    return {"status": "ready" if row and row.one == 1 else "degraded"}
