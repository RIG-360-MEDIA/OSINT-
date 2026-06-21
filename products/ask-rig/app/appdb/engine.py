"""Async engine + session factory for the writable app DB.

One process-wide engine, lazily initialised from Settings. Distinct from the
read-only corpus engine in app/db.py — they must never be confused.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.appdb.models import Base
from app.config import Settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_engine(settings: Settings) -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        _engine = create_async_engine(settings.app_db_url, future=True)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker(settings: Settings) -> async_sessionmaker[AsyncSession]:
    init_engine(settings)
    assert _sessionmaker is not None
    return _sessionmaker


async def create_all(settings: Settings) -> None:
    engine = init_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_app_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
