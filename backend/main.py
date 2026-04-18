import os

import asyncpg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers.brief_router import brief_router
from backend.routers.debug_router import debug_router
from backend.routers.onboarding_router import onboarding_router

app = FastAPI(
    title="RIG SURVEILLANCE",
    version="1.0.0",
    description="Personal Intelligence Platform",
)

app.include_router(debug_router)
app.include_router(onboarding_router)
app.include_router(brief_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
