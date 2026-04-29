import os
from pathlib import Path

from dotenv import load_dotenv

# Load infrastructure/.env when running locally.
# override=True ensures .env always wins over stale Windows env vars.
_env_path = Path(__file__).resolve().parent.parent / "infrastructure" / ".env"
load_dotenv(_env_path, override=True)

# Fail fast — catch missing required vars before any request is served
_REQUIRED = ["SUPABASE_URL", "SUPABASE_SERVICE_KEY", "GROQ_API_KEYS"]
_missing = [v for v in _REQUIRED if not os.getenv(v)]
if _missing:
    raise RuntimeError(
        f"Missing required env vars: {_missing}. "
        f"Check infrastructure/.env exists at {_env_path}"
    )

import asyncpg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers.admin_router import admin_router
from backend.routers.analyst_router import analyst_router
from backend.routers.brief_router import brief_router
from backend.routers.coverage_router import coverage_router
from backend.routers.debug_router import debug_router
from backend.routers.onboarding_router import onboarding_router
from backend.routers.clippings_router import clippings_router, newspapers_router
from backend.routers.clips_router import clips_router
from backend.routers.documents_router import documents_router
from backend.routers.me_router import me_router
from backend.routers.cm_router import cm_router
from backend.routers.rbac_admin_router import rbac_admin_router
from backend.routers.signals_router import signals_router
from backend.routers.thread_router import thread_router
from backend.routers.worldmonitor_router import worldmonitor_router
from backend.middleware.impersonation_audit import ImpersonationAuditMiddleware
from backend.middleware.request_id import RequestIdMiddleware

app = FastAPI(
    title="RIG SURVEILLANCE",
    version="1.0.0",
    description="Personal Intelligence Platform",
)

app.include_router(admin_router)
app.include_router(analyst_router)
app.include_router(debug_router)
app.include_router(onboarding_router)
app.include_router(brief_router)
app.include_router(coverage_router)
app.include_router(clippings_router)
app.include_router(newspapers_router)
app.include_router(clips_router)
app.include_router(documents_router)
app.include_router(signals_router)
app.include_router(thread_router)
app.include_router(worldmonitor_router)
app.include_router(cm_router)
app.include_router(me_router)
app.include_router(rbac_admin_router)

# Audit logger — must be added AFTER routers are configured. ASGI middleware
# wraps the whole app, so registration order doesn't affect routing.
app.add_middleware(ImpersonationAuditMiddleware)
# Request-Id middleware: stamps every request with an X-Request-Id and
# exposes it via contextvar for log-line correlation.
app.add_middleware(RequestIdMiddleware)

# Dossier feature — entity enrichment over free OSINT sources.
# Gated behind DOSSIER_ENABLED so it stays invisible to existing API surface
# when off. try/except ensures a missing dossier dependency cannot prevent
# the rest of the backend from booting.
if os.getenv("DOSSIER_ENABLED", "false").lower() == "true":
    try:
        from backend.routers.dossier_router import dossier_router as _dossier_router
        app.include_router(_dossier_router)
    except Exception as _dx:
        import logging as _dlog
        _dlog.getLogger(__name__).warning(f"Dossier router failed to load: {_dx}")

# CORS allow-list: comma-separated origins via CORS_ALLOWED_ORIGINS env var.
# Default keeps local dev origins working; production must override.
_cors_origins_raw = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:3001,http://localhost:4000",
)
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
)


@app.on_event("startup")
async def seed_admins_on_boot() -> None:
    """Promote SUPER_ADMIN_EMAILS to role='super_admin' on every boot.

    Idempotent and non-fatal. See backend/auth/super_admin_seed.py for the
    full contract. Replaces the hard-coded UPDATE in migration 030.
    """
    import logging as _logging
    _logger = _logging.getLogger(__name__)
    try:
        from backend.auth.super_admin_seed import seed_super_admins
        await seed_super_admins()
    except Exception as exc:  # noqa: BLE001
        _logger.warning(f"super-admin seed failed at boot: {exc}")


@app.on_event("startup")
async def warmup_labse() -> None:
    """Pre-load LaBSE at boot to eliminate 29-second cold start on first analyst query.

    D-13 fix — schedule the warmup as a background task instead of awaiting
    it inline. Previously this blocked uvicorn's "application startup" phase
    for ~3 minutes after every --reload, leaving /openapi.json (and every
    endpoint) returning Connection refused for the entire window. Now uvicorn
    becomes ready immediately; the first analyst query may still be slow if
    it lands before the warmup finishes, but the rest of the API is up.
    """
    import asyncio as _asyncio
    import logging as _logging
    _logger = _logging.getLogger(__name__)

    def _warm_sync() -> None:
        try:
            from backend.nlp.nlp_embedding import get_labse_model
            model = get_labse_model()
            model.encode(["Telangana intelligence warmup"], show_progress_bar=False)
            _logger.info("LaBSE model warmed in background — first query will be fast")
        except Exception as exc:  # noqa: BLE001
            _logger.warning(f"LaBSE warmup failed: {exc} — first query may be slow")

    # Fire-and-forget on a worker thread so the event loop continues serving.
    _asyncio.create_task(_asyncio.to_thread(_warm_sync))


@app.get("/debug/groq-status")
async def groq_status() -> dict:
    """Shows Groq key pool health. Used by debug dashboard in P08."""
    from backend.nlp.groq_client import groq_manager
    return {"groq_status": groq_manager.status}


@app.get("/api/health/social")
async def social_health() -> dict:
    """Process-local Reddit 429 telemetry for ops dashboards."""
    from backend.collectors.social_collector import reddit_throttle_metrics
    return {
        "reddit": reddit_throttle_metrics(),
        "twitter": {"status": "removed", "since": "2026-04-29"},
    }


@app.get("/health")
async def health_check() -> dict:
    db_connected = False
    db_version = None
    entity_count = None
    source_count = None
    article_count = None
    articles_today = None

    try:
        # DATABASE_URL_SYNC is plain postgresql:// — asyncpg accepts this format
        dsn = os.getenv("DATABASE_URL_SYNC", "").replace(
            "postgresql+asyncpg", "postgresql"
        )
        conn = await asyncpg.connect(dsn)

        row = await conn.fetchrow("SELECT version()")
        db_version = row[0][:50]

        entity_row = await conn.fetchrow("SELECT COUNT(*) FROM entity_dictionary")
        entity_count = entity_row[0]

        source_row = await conn.fetchrow("SELECT COUNT(*) FROM sources")
        source_count = source_row[0]

        article_row = await conn.fetchrow("SELECT COUNT(*) FROM articles")
        article_count = article_row[0]

        articles_today_row = await conn.fetchrow(
            "SELECT COUNT(*) FROM articles WHERE collected_at > NOW() - INTERVAL '24 hours'"
        )
        articles_today = articles_today_row[0]

        await conn.close()
        db_connected = True
    except Exception as e:
        db_version = str(e)[:100]

    return {
        "status": "ok",
        "version": "1.0.0",
        "db_connected": db_connected,
        "db_version": db_version,
        "entity_count": entity_count,
        "source_count": source_count,
        "article_count": article_count,
        "articles_today": articles_today,
        "environment": os.getenv("ENVIRONMENT", "development"),
    }
