"""Personalized brief — aggregate a user's watched entities + saved searches into
one cited digest. Reuses entity_feed + retrieval + the answer guardrail. NO clusters.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.answer import BRIEF_SYSTEM, answer_with_system
from app.appdb.models import SavedSearch, User, WatchedEntity
from app.config import Settings
from app.embedding import LabseEmbedder
from app.entities import entity_feed
from app.llm import LLMProvider
from app.personalization_store import build_personalization
from app.personalize import fetch_doc_entities, personalize
from app.retrieval import retrieve_and_curate
from app.schemas import RetrievedDoc


async def generate_brief(
    conn: AsyncConnection,
    db: AsyncSession,
    settings: Settings,
    user: User,
    embedder: LabseEmbedder,
    llm: LLMProvider,
    max_docs: int = 12,
) -> dict:
    languages = user.default_languages.split(",") if user.default_languages else None
    watched = (await db.scalars(select(WatchedEntity).where(WatchedEntity.user_id == user.id))).all()
    saved = (await db.scalars(select(SavedSearch).where(SavedSearch.user_id == user.id))).all()

    collected: dict[str, RetrievedDoc] = {}
    contributors: list[dict] = []
    for w in watched:
        for d in await entity_feed(conn, settings, w.entity_id, k=8, languages=languages):
            collected.setdefault(d.id, d)
        contributors.append({"type": "entity", "name": w.canonical_name})
    for ss in saved:
        qvec = await asyncio.to_thread(embedder.embed, ss.query)
        for d in await retrieve_and_curate(
            conn, settings, ss.query, qvec, languages, top_k=8, rerank_enabled=False
        ):
            collected.setdefault(d.id, d)
        contributors.append({"type": "search", "name": ss.name})

    docs = list(collected.values())
    pers = await build_personalization(db, user.id)
    if not pers.is_noop and docs:
        doc_entities = (
            await fetch_doc_entities(conn, [d.id for d in docs], pers.relevant_entity_ids)
            if pers.relevant_entity_ids else {}
        )
        docs = personalize(docs, pers, doc_entities)
    docs = docs[:max_docs]

    if not docs:
        return {
            "digest": None, "faithful": True, "citations": [], "sources": [],
            "contributors": contributors,
            "notes": "no watched entities / saved searches yet, or nothing to show",
        }

    result = await asyncio.to_thread(answer_with_system, llm, BRIEF_SYSTEM, "Today's brief", docs)
    return {
        "digest": result.answer,
        "faithful": result.faithful,
        "citations": result.citations,
        "sources": docs,
        "contributors": contributors,
        "notes": result.notes,
    }
