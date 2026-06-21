"""Async, READ-ONLY connection to the RIG corpus database.

Connects as ``analytics_user`` (read-only on ``public.*``) and additionally pins
every session to ``default_transaction_read_only = on`` as belt-and-suspenders.
This module exposes **no** write path by design — the corpus is a frozen source
of truth and this product must never mutate it.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.config import Settings

_engine: AsyncEngine | None = None


def get_engine(settings: Settings) -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.db_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,
            future=True,
            # Enforce read-only at the session level regardless of role grants.
            connect_args={"server_settings": {"default_transaction_read_only": "on"}},
        )
    return _engine


@asynccontextmanager
async def connect(settings: Settings) -> AsyncIterator[AsyncConnection]:
    """Yield a read-only connection; auto-closed on exit."""
    async with get_engine(settings).connect() as conn:
        yield conn


async def ping(settings: Settings) -> bool:
    async with connect(settings) as conn:
        result = await conn.execute(text("SELECT 1"))
        return result.scalar_one() == 1


async def dispose_engine() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
