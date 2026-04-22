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
from backend.routers.clips_router import clips_router
from backend.routers.documents_router import documents_router
from backend.routers.thread_router import thread_router

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
app.include_router(clips_router)
app.include_router(documents_router)
app.include_router(thread_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def warmup_labse() -> None:
    """Pre-load LaBSE at boot to eliminate 29-second cold start on first analyst query."""
    import logging as _logging
    _logger = _logging.getLogger(__name__)
    try:
        from backend.nlp.nlp_embedding import get_labse_model
        model = get_labse_model()
        model.encode(["Telangana intelligence warmup"], show_progress_bar=False)
        _logger.info("LaBSE model warmed at startup — first query will be fast")
    except Exception as exc:
        _logger.warning(f"LaBSE warmup failed: {exc} — first query may be slow")


@app.get("/debug/groq-status")
async def groq_status() -> dict:
    """Shows Groq key pool health. Used by debug dashboard in P08."""
    from backend.nlp.groq_client import groq_manager
    return {"groq_status": groq_manager.status}


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
