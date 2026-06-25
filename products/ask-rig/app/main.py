"""Ask-RIG FastAPI service: cited, cross-lingual answers over the RIG corpus."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.answer import DETAILED_SYSTEM, answer_question, answer_with_system
from app.appdb.engine import create_all, dispose_app_engine
from app.appdb.models import QueryHistory, User
from app.chat import chat_stream
from app.db import connect, dispose_engine, ping
from app.deps import get_db, get_embedder, optional_user, settings
from app.entities import entity_feed, is_uuid, search_entities
from app.llm import get_llm
from app.personalization_store import build_personalization
from app.personalize import fetch_doc_entities, personalize
from app.retrieval import multi_retrieve_and_curate, retrieve_and_curate
from app.rewrite import rewrite_query
from app.routers import account, intel, users
from app.routers import agent as agent_router
from app.routers import brief as brief_router
from app.routers import web as web_router
from app.schemas import AskRequest, AskResponse, ChatRequest
from app.similar import find_similar
from app.web.fuse import fuse_web_corpus
from app.web.search import search_web

_INDEX_HTML = Path(__file__).resolve().parent / "static" / "index.html"

logging.basicConfig(level=settings.log_level)
log = logging.getLogger("ask-rig")

app = FastAPI(title="Ask-RIG", version="0.2.0")
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(users.router)
app.include_router(account.router)
app.include_router(web_router.router)
app.include_router(intel.router)
app.include_router(brief_router.router)
app.include_router(agent_router.router)


@app.on_event("startup")
async def _startup() -> None:
    await create_all(settings)  # idempotent — creates the app-DB schema if absent


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    # Read per-request so edits to the page show on refresh (no server restart).
    return _INDEX_HTML.read_text(encoding="utf-8")


@app.get("/health")
async def health() -> dict:
    try:
        ok = await ping(settings)
    except Exception as exc:  # noqa: BLE001 - surface any DB failure as 503
        raise HTTPException(503, f"db unavailable: {exc}") from exc
    return {"status": "ok" if ok else "degraded", "read_only": True}


# Live corpus size for the header badge. Cached so a header badge never fires a
# count(*) on a ~300K-row filtered set on every page load.
_STATS_CACHE: dict = {"value": None, "ts": 0.0}
_STATS_TTL = 300.0  # seconds


@app.get("/stats")
async def stats() -> dict:
    """Live 'surfaceable' corpus count (substrate_status='ok' AND NOT is_duplicate)
    — what the chat can actually retrieve. Cached for a few minutes; degrades to the
    last good value (or a 503) so the badge never breaks the page."""
    now = time.monotonic()
    cached = _STATS_CACHE["value"]
    if cached is not None and (now - _STATS_CACHE["ts"]) < _STATS_TTL:
        return cached
    try:
        async with connect(settings) as conn:
            result = await conn.execute(
                text(
                    "SELECT count(*) FROM articles "
                    "WHERE substrate_status = 'ok' AND NOT is_duplicate"
                )
            )
            surfaceable = int(result.scalar() or 0)
        payload = {"surfaceable": surfaceable, "languages": 4}
        _STATS_CACHE.update(value=payload, ts=now)
        return payload
    except Exception as exc:  # noqa: BLE001 - a badge must never take the page down
        if cached is not None:
            return cached
        raise HTTPException(503, f"stats unavailable: {exc}") from exc


def _sse(event: dict) -> str:
    """Serialize one event as a Server-Sent-Events frame."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@app.post("/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    """Unified chat: one streaming endpoint that fans out over corpus + web +
    (on-demand) entities and streams a grounded, detailed answer. Anonymous."""
    history = [t.model_dump() for t in req.history]

    async def event_stream():
        try:
            async for event in chat_stream(
                settings, get_llm(settings), get_embedder(), req.query, history,
                article_id=req.article_id,
            ):
                yield _sse(event)
        except Exception as exc:  # noqa: BLE001 - last-resort: tell the client, don't hang
            log.warning("chat stream failed: %s", exc)
            yield _sse({"type": "error", "text": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy buffering so tokens flush live
        },
    )


@app.post("/ask", response_model=AskResponse)
async def ask(
    req: AskRequest,
    user: User | None = Depends(optional_user),
    db: AsyncSession = Depends(get_db),
) -> AskResponse:
    try:
        # Embedding is CPU-bound and blocking — run off the event loop so the
        # server stays responsive to concurrent requests.
        qvec = await asyncio.to_thread(get_embedder().embed, req.query)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - model load/encode failure
        raise HTTPException(503, f"embedding failed: {exc}") from exc

    # Apply the user's default languages when the request doesn't specify any.
    languages = req.languages
    if user and not languages and user.default_languages:
        languages = user.default_languages.split(",")

    # RAG-Fusion: expand a (possibly vague) query into sharper variants. Only worth
    # the extra LLM call when we're going to write an answer.
    rewritten: list[str] = []
    if req.rewrite and req.answer and settings.answer_enabled:
        try:
            rewritten = await asyncio.to_thread(rewrite_query, get_llm(settings), req.query)
        except Exception:  # noqa: BLE001 - rewriting must never block the search
            rewritten = []

    personalized = False
    web_used = False
    async with connect(settings) as conn:
        if rewritten:
            queries = [req.query, *rewritten]
            qvecs = [qvec]
            for variant in rewritten:
                qvecs.append(await asyncio.to_thread(get_embedder().embed, variant))
            docs = await multi_retrieve_and_curate(
                conn, settings, queries, qvecs, languages, req.top_k, req.rerank
            )
        else:
            docs = await retrieve_and_curate(
                conn, settings, req.query, qvec, languages, req.top_k, req.rerank
            )
        if user:
            pers = await build_personalization(db, user.id)
            if not pers.is_noop:
                doc_entities: dict = {}
                if pers.relevant_entity_ids:
                    doc_entities = await fetch_doc_entities(
                        conn, [d.id for d in docs], pers.relevant_entity_ids
                    )
                docs = personalize(docs, pers, doc_entities)
                personalized = True
        if req.web:
            web_results, _ = await search_web(settings, req.query)
            if web_results:
                docs = fuse_web_corpus(docs, web_results)[:12]
                web_used = True

    answer: str | None = None
    faithful = True
    citations: list = []
    notes: str | None = None
    if req.answer and settings.answer_enabled:
        try:
            # LLM call is a blocking HTTP request — keep it off the event loop.
            # Detailed (signature) style by default; terse cited mode on request.
            if req.detailed:
                result = await asyncio.to_thread(
                    answer_with_system, get_llm(settings), DETAILED_SYSTEM, req.query, docs
                )
            else:
                result = await asyncio.to_thread(answer_question, get_llm(settings), req.query, docs)
            answer, faithful = result.answer, result.faithful
            citations, notes = result.citations, result.notes
        except Exception as exc:  # noqa: BLE001 - never let answer failure kill retrieval
            notes = f"answer skipped: {exc}"
            log.warning(notes)

    if user:
        db.add(
            QueryHistory(
                user_id=user.id,
                query=req.query,
                languages=",".join(languages) if languages else None,
                n_results=len(docs),
                used_web=1 if web_used else 0,
            )
        )
        await db.commit()

    return AskResponse(
        query=req.query,
        answer=answer,
        faithful=faithful,
        citations=citations,
        retrieved=docs,
        notes=notes,
        personalized=personalized,
        web_used=web_used,
        rewritten=rewritten,
    )


def _langs(languages: str | None) -> list[str] | None:
    return [x.strip() for x in languages.split(",") if x.strip()] if languages else None


@app.get("/similar/{article_id}")
async def similar(article_id: str, k: int = 8, languages: str | None = None) -> dict:
    """Feature 2 — articles most similar to ``article_id`` (cross-lingual)."""
    if not is_uuid(article_id):
        raise HTTPException(422, "article_id must be a UUID")
    async with connect(settings) as conn:
        docs = await find_similar(conn, settings, article_id, min(max(k, 1), 25), _langs(languages))
    if docs is None:
        raise HTTPException(404, "article not found or has no v4 embedding")
    return {"article_id": article_id, "similar": docs}


@app.get("/entities/search")
async def entities_search(q: str, limit: int = 10) -> dict:
    """Feature 3a — resolve a term to canonical entity candidates (disambiguation)."""
    if len(q.strip()) < 2:
        raise HTTPException(422, "q must be at least 2 characters")
    async with connect(settings) as conn:
        candidates = await search_entities(conn, q, min(max(limit, 1), 25))
    return {"query": q, "candidates": candidates}


@app.get("/entities/{entity_id}/feed")
async def entities_feed(entity_id: str, k: int = 20, languages: str | None = None) -> dict:
    """Feature 3b — recent cross-language articles mentioning ``entity_id``."""
    if not is_uuid(entity_id):
        raise HTTPException(422, "entity_id must be a UUID")
    async with connect(settings) as conn:
        docs = await entity_feed(conn, settings, entity_id, min(max(k, 1), 50), _langs(languages))
    return {"entity_id": entity_id, "feed": docs}


@app.on_event("shutdown")
async def _shutdown() -> None:
    await dispose_engine()
    await dispose_app_engine()
