"""Async SQLAlchemy engine + per-request connection dependency.

The engine connects as `analytics_user` (read-only on public.*, RW on analytics.*).
Postgres enforces the read-only contract — any write attempt against public.*
raises permission denied, even if the application code asks for one.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from config import load_settings

_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        s = load_settings()
        _engine = create_async_engine(
            s.db_url,
            pool_size=s.db_pool_size,
            max_overflow=s.db_max_overflow,
            pool_pre_ping=True,
            future=True,
        )
    return _engine


@asynccontextmanager
async def get_db() -> AsyncIterator[AsyncConnection]:
    """Async connection context manager. Auto-rolls-back on exception."""
    async with get_engine().connect() as conn:
        yield conn


async def dispose_engine() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
