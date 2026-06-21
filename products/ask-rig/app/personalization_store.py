"""Assemble a user's Personalization from the app DB (mutes + watched entities)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.appdb.models import Mute, WatchedEntity
from app.personalize import Personalization


def aware_utc(dt: datetime | None) -> datetime | None:
    """Normalise to tz-aware UTC. SQLite returns naive datetimes; the corpus
    returns aware ones — comparing them directly raises, so coerce here."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def build_personalization(db: AsyncSession, user_id: str) -> Personalization:
    mutes = (await db.scalars(select(Mute).where(Mute.user_id == user_id))).all()
    sources: set[str] = set()
    languages: set[str] = set()
    keywords: list[str] = []
    entities: set[str] = set()
    for m in mutes:
        if m.kind == "source":
            sources.add(m.value)
        elif m.kind == "language":
            languages.add(m.value.lower())
        elif m.kind == "keyword":
            keywords.append(m.value.lower())
        elif m.kind == "entity":
            entities.add(m.value)

    watched = (
        await db.scalars(select(WatchedEntity.entity_id).where(WatchedEntity.user_id == user_id))
    ).all()

    return Personalization(
        muted_sources=frozenset(sources),
        muted_languages=frozenset(languages),
        muted_keywords=tuple(keywords),
        muted_entities=frozenset(entities),
        watched_entities=frozenset(watched),
    )
