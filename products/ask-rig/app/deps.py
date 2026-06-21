"""Shared settings + FastAPI dependencies (app-DB session, current user).

Single source of truth for Settings so the corpus engine, app engine, and routers
all agree. Endpoint tests override ``get_db`` / ``current_user`` via
``app.dependency_overrides`` rather than touching globals.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.appdb.engine import get_sessionmaker
from app.appdb.models import Token, User
from app.auth import hash_token
from app.config import load_settings
from app.embedding import LabseEmbedder

settings = load_settings()


@lru_cache(maxsize=1)
def get_embedder() -> LabseEmbedder:
    """Process-wide LaBSE singleton (heavy — load once, share everywhere)."""
    return LabseEmbedder(settings.embed_model)


async def get_db() -> AsyncIterator[AsyncSession]:
    sessionmaker = get_sessionmaker(settings)
    async with sessionmaker() as session:
        yield session


async def _resolve_user(authorization: str | None, db: AsyncSession) -> User | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    raw = authorization.split(" ", 1)[1].strip()
    token = await db.get(Token, hash_token(raw))
    if token is None:
        return None
    return await db.get(User, token.user_id)


async def current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await _resolve_user(authorization, db)
    if user is None:
        raise HTTPException(401, "missing or invalid bearer token")
    return user


async def optional_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Like current_user but returns None instead of 401 — for endpoints that
    work anonymously and add personalization only when authenticated."""
    return await _resolve_user(authorization, db)
