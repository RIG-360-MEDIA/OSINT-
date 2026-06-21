"""Bucket-1 intelligence endpoints: stance profile, bias-balance, who-said-it,
connect-entities, district-sentiment. All read-only over existing corpus data."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from app.answer import DEBATE_SYSTEM, SIGNIFICANCE_SYSTEM, answer_with_system
from app.db import connect
from app.deps import get_embedder, settings
from app.entities import is_uuid
from app.intel import (
    balance_from_stances,
    connect_entities,
    disagreements,
    district_sentiment,
    entity_stance_profile,
    stances_for_articles,
    who_said,
)
from app.llm import get_llm
from app.retrieval import retrieve_and_curate

router = APIRouter(tags=["intel"], prefix="/intel")


async def _docs_for(q: str, top_k: int):
    qvec = await asyncio.to_thread(get_embedder().embed, q)
    async with connect(settings) as conn:
        return await retrieve_and_curate(conn, settings, q, qvec, None, top_k=top_k, rerank_enabled=False)


@router.get("/entity/{entity_id}/stances")
async def entity_stances(entity_id: str) -> dict:
    """How an entity is portrayed: stance distribution + intensity-weighted balance."""
    if not is_uuid(entity_id):
        raise HTTPException(422, "entity_id must be a UUID")
    async with connect(settings) as conn:
        return await entity_stance_profile(conn, entity_id)


@router.get("/bias")
async def bias_meter(q: str, top_k: int = 20) -> dict:
    """Bias-balance of the coverage behind a query — how one-sided are the sources."""
    if len(q.strip()) < 2:
        raise HTTPException(422, "q must be at least 2 characters")
    qvec = await asyncio.to_thread(get_embedder().embed, q)
    async with connect(settings) as conn:
        docs = await retrieve_and_curate(conn, settings, q, qvec, None, top_k=top_k, rerank_enabled=False)
        rows = await stances_for_articles(conn, [d.id for d in docs])
    return {"query": q, "n_articles": len(docs), **balance_from_stances(rows)}


@router.get("/disagree")
async def disagree(q: str, top_k: int = 30) -> dict:
    """Where sources disagree — targets that get both supportive and critical
    coverage in the same result set (no clusters; scoped to the query's articles)."""
    if len(q.strip()) < 2:
        raise HTTPException(422, "q must be at least 2 characters")
    qvec = await asyncio.to_thread(get_embedder().embed, q)
    async with connect(settings) as conn:
        docs = await retrieve_and_curate(conn, settings, q, qvec, None, top_k=top_k, rerank_enabled=False)
        contested = await disagreements(conn, [d.id for d in docs])
    return {"query": q, "n_articles": len(docs), "contested": contested}


@router.get("/debate")
async def debate(q: str, top_k: int = 8) -> dict:
    """For-and-against on a topic, argued only from sourced evidence (cited)."""
    if len(q.strip()) < 2:
        raise HTTPException(422, "q must be at least 2 characters")
    docs = await _docs_for(q, top_k)
    result = await asyncio.to_thread(answer_with_system, get_llm(settings), DEBATE_SYSTEM, q, docs)
    return {"query": q, "debate": result.answer, "faithful": result.faithful,
            "citations": result.citations, "sources": docs, "notes": result.notes}


@router.get("/significance")
async def significance(q: str, top_k: int = 8) -> dict:
    """"So what" — why this matters, grounded only in the sources (cited)."""
    if len(q.strip()) < 2:
        raise HTTPException(422, "q must be at least 2 characters")
    docs = await _docs_for(q, top_k)
    result = await asyncio.to_thread(answer_with_system, get_llm(settings), SIGNIFICANCE_SYSTEM, q, docs)
    return {"query": q, "significance": result.answer, "faithful": result.faithful,
            "citations": result.citations, "sources": docs, "notes": result.notes}


@router.get("/quotes")
async def quotes(speaker_id: str, topic: str | None = None, k: int = 20) -> dict:
    """Verbatim (translated) quotes by a speaker, optionally filtered to a topic."""
    if not is_uuid(speaker_id):
        raise HTTPException(422, "speaker_id must be a UUID")
    async with connect(settings) as conn:
        items = await who_said(conn, speaker_id, topic, min(max(k, 1), 50))
    return {"speaker_id": speaker_id, "topic": topic, "quotes": items}


@router.get("/connect")
async def connect_endpoint(a: str, b: str, k: int = 10) -> dict:
    """How two entities are connected: shared coverage + bridging entities."""
    if not (is_uuid(a) and is_uuid(b)):
        raise HTTPException(422, "a and b must be UUIDs")
    if a == b:
        raise HTTPException(422, "a and b must differ")
    async with connect(settings) as conn:
        return await connect_entities(conn, a, b, min(max(k, 1), 25))


@router.get("/district-sentiment")
async def district_sentiment_endpoint(entity_id: str | None = None, k: int = 40) -> dict:
    """Per-district supportive-vs-critical balance, optionally toward one entity."""
    if entity_id and not is_uuid(entity_id):
        raise HTTPException(422, "entity_id must be a UUID")
    async with connect(settings) as conn:
        rows = await district_sentiment(conn, entity_id, min(max(k, 1), 100))
    return {"entity_id": entity_id, "districts": rows}
