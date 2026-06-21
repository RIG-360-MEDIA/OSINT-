"""Per-user personalization applied to retrieved docs.

Two stages, both deterministic:
  - apply_mutes:  drop docs by source / language / keyword / entity
  - apply_watch_boost: stable-partition watched-entity docs to the front
The entity rules need a doc_id -> {entity_id} map; fetch_doc_entities reads it
from the corpus for just the returned doc set (cheap — ≤ a few dozen ids).

The pure functions take the user's sets as input so they unit-test with no DB.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.schemas import RetrievedDoc


@dataclass(frozen=True)
class Personalization:
    muted_sources: frozenset[str] = field(default_factory=frozenset)
    muted_languages: frozenset[str] = field(default_factory=frozenset)
    muted_keywords: tuple[str, ...] = ()
    muted_entities: frozenset[str] = field(default_factory=frozenset)
    watched_entities: frozenset[str] = field(default_factory=frozenset)

    @property
    def relevant_entity_ids(self) -> frozenset[str]:
        """Entity ids we must look up per doc (muted + watched)."""
        return self.muted_entities | self.watched_entities

    @property
    def is_noop(self) -> bool:
        return not (
            self.muted_sources
            or self.muted_languages
            or self.muted_keywords
            or self.muted_entities
            or self.watched_entities
        )


def apply_mutes(
    docs: list[RetrievedDoc],
    p: Personalization,
    doc_entities: dict[str, set[str]] | None = None,
) -> list[RetrievedDoc]:
    out: list[RetrievedDoc] = []
    for d in docs:
        if d.source_id and d.source_id in p.muted_sources:
            continue
        if d.language and d.language in p.muted_languages:
            continue
        if p.muted_keywords:
            blob = f"{d.title or ''} {d.snippet or ''}".lower()
            if any(kw in blob for kw in p.muted_keywords):
                continue
        if p.muted_entities and doc_entities:
            if doc_entities.get(d.id, set()) & p.muted_entities:
                continue
        out.append(d)
    return out


def apply_watch_boost(
    docs: list[RetrievedDoc],
    p: Personalization,
    doc_entities: dict[str, set[str]] | None,
) -> list[RetrievedDoc]:
    """Stable-partition: docs mentioning a watched entity move to the front,
    relative order preserved within each group (scale-independent, predictable)."""
    if not p.watched_entities or not doc_entities:
        return docs
    watched: list[RetrievedDoc] = []
    rest: list[RetrievedDoc] = []
    for d in docs:
        (watched if doc_entities.get(d.id, set()) & p.watched_entities else rest).append(d)
    return watched + rest


def personalize(
    docs: list[RetrievedDoc],
    p: Personalization,
    doc_entities: dict[str, set[str]] | None = None,
) -> list[RetrievedDoc]:
    return apply_watch_boost(apply_mutes(docs, p, doc_entities), p, doc_entities)


# uuid[] cast keeps the article_id index usable; both sides become uuid.
_DOC_ENTITIES_SQL = """
SELECT article_id::text AS doc_id, entity_id::text AS entity_id
FROM article_entity_mentions
WHERE article_id = ANY(CAST(:doc_ids AS uuid[]))
  AND entity_id = ANY(CAST(:entity_ids AS uuid[]))
"""


async def fetch_doc_entities(
    conn: AsyncConnection,
    doc_ids: Iterable[str],
    entity_ids: Iterable[str],
) -> dict[str, set[str]]:
    doc_ids = list(doc_ids)
    entity_ids = list(entity_ids)
    if not doc_ids or not entity_ids:
        return {}
    rows = (
        await conn.execute(text(_DOC_ENTITIES_SQL), {"doc_ids": doc_ids, "entity_ids": entity_ids})
    ).mappings().all()
    out: dict[str, set[str]] = {}
    for r in rows:
        out.setdefault(r["doc_id"], set()).add(r["entity_id"])
    return out
