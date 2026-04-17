"""
Async SQLAlchemy engine and session factory.

Used by the NLP processor and any other async pipeline tasks.
DATABASE_URL env var must use postgresql+asyncpg scheme for async support.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://rig:rigpassword@rig-postgres:5432/rig",
)

engine = create_async_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()


@asynccontextmanager
async def get_db():
    """Yield an async SQLAlchemy session, rolling back on error."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
