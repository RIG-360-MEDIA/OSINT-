"""Agent tools — thin wrappers over existing capabilities, exposed as OpenAI
function specs. Each executor returns a TEXT observation for the model; article-
bearing tools register their results in a SourceBook so the final answer can cite
[S#] over everything gathered."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.embedding import LabseEmbedder
from app.entities import entity_feed, is_uuid, search_entities
from app.intel import connect_entities, entity_stance_profile, who_said
from app.retrieval import retrieve_and_curate
from app.schemas import RetrievedDoc
from app.web.fuse import web_to_doc
from app.web.search import search_web


class SourceBook:
    """Accumulates cited sources across tool calls; assigns stable 1-based S#."""

    def __init__(self) -> None:
        self._by_id: dict[str, int] = {}
        self._docs: list[RetrievedDoc] = []

    def add(self, doc: RetrievedDoc) -> int:
        if doc.id in self._by_id:
            return self._by_id[doc.id]
        n = len(self._docs) + 1
        self._by_id[doc.id] = n
        self._docs.append(doc)
        return n

    @property
    def docs(self) -> list[RetrievedDoc]:
        return list(self._docs)


@dataclass
class AgentContext:
    conn: AsyncConnection
    settings: Settings
    embedder: LabseEmbedder
    sources: SourceBook = field(default_factory=SourceBook)


def _line(n: int, doc: RetrievedDoc) -> str:
    return f"[S{n}] ({(doc.language or '?').upper()}) {doc.title or ''} — {(doc.snippet or '')[:160]}"


# ---- executors -----------------------------------------------------------

async def _corpus_search(ctx: AgentContext, query: str, k: int = 6) -> str:
    qvec = await asyncio.to_thread(ctx.embedder.embed, query)
    docs = await retrieve_and_curate(ctx.conn, ctx.settings, query, qvec, None, top_k=min(k, 10), rerank_enabled=False)
    if not docs:
        return "no corpus results"
    return "\n".join(_line(ctx.sources.add(d), d) for d in docs)


async def _web_search(ctx: AgentContext, query: str) -> str:
    results, err = await search_web(ctx.settings, query)
    if err:
        return f"web unavailable: {err}"
    if not results:
        return "no web results"
    return "\n".join(_line(ctx.sources.add(web_to_doc(w, i)), web_to_doc(w, i)) for i, w in enumerate(results))


async def _resolve_entity(ctx: AgentContext, name: str) -> str:
    cands = await search_entities(ctx.conn, name, 6)
    if not cands:
        return f"no entity matched '{name}'"
    return "\n".join(
        f"{c.entity_id} | {c.canonical_name} ({c.entity_type or '?'}, {c.n_articles} articles)"
        for c in cands
    )


async def _entity_feed(ctx: AgentContext, entity_id: str, k: int = 6) -> str:
    if not is_uuid(entity_id):
        return "entity_id must be a UUID (use resolve_entity first)"
    docs = await entity_feed(ctx.conn, ctx.settings, entity_id, k=min(k, 10))
    if not docs:
        return "no recent articles for this entity"
    return "\n".join(_line(ctx.sources.add(d), d) for d in docs)


async def _entity_stances(ctx: AgentContext, entity_id: str) -> str:
    if not is_uuid(entity_id):
        return "entity_id must be a UUID (use resolve_entity first)"
    prof = await entity_stance_profile(ctx.conn, entity_id)
    b = prof["balance"]
    dist = ", ".join(f"{d['stance']}:{d['n']}" for d in prof["distribution"][:5])
    return f"coverage balance = {b['balance_score']} ({b['label']}); stance distribution: {dist}"


async def _quotes(ctx: AgentContext, speaker_id: str, topic: str | None = None) -> str:
    if not is_uuid(speaker_id):
        return "speaker_id must be a UUID (use resolve_entity first)"
    items = await who_said(ctx.conn, speaker_id, topic, k=6)
    if not items:
        return "no quotes found"
    out = []
    for q in items:
        doc = RetrievedDoc(
            id=q["article_id"], title=q.get("title"), snippet=q.get("quote"), url=q.get("url"),
            published_at=q.get("published_at"), source_id=None, language=q.get("language"),
            score=0.0, vec_rank=None, lex_rank=None,
        )
        n = ctx.sources.add(doc)
        out.append(f'[S{n}] "{(q.get("quote") or "")[:200]}" — {q.get("speaker")}')
    return "\n".join(out)


async def _connect(ctx: AgentContext, a: str, b: str) -> str:
    if not (is_uuid(a) and is_uuid(b)):
        return "both a and b must be entity UUIDs (use resolve_entity first)"
    res = await connect_entities(ctx.conn, a, b, k=6)
    lines = []
    for art in res["shared_articles"]:
        doc = RetrievedDoc(
            id=art["id"], title=art.get("title"), snippet=None, url=art.get("url"),
            published_at=art.get("published_at"), source_id=None, language=art.get("language"),
            score=0.0, vec_rank=None, lex_rank=None,
        )
        lines.append(_line(ctx.sources.add(doc), doc))
    bridges = ", ".join(f"{b['canonical_name']}({b['co_mentions']})" for b in res["bridge_entities"][:6])
    return (f"shared articles:\n" + "\n".join(lines) if lines else "no shared articles") + f"\nbridging entities: {bridges}"


_EXECUTORS = {
    "corpus_search": _corpus_search,
    "web_search": _web_search,
    "resolve_entity": _resolve_entity,
    "entity_feed": _entity_feed,
    "entity_stances": _entity_stances,
    "quotes": _quotes,
    "connect_entities": _connect,
}


async def execute_tool(ctx: AgentContext, name: str, args: dict) -> str:
    fn = _EXECUTORS.get(name)
    if fn is None:
        return f"unknown tool: {name}"
    try:
        return await fn(ctx, **args)
    except TypeError as exc:
        return f"bad arguments for {name}: {exc}"
    except Exception as exc:  # noqa: BLE001 - a tool error must not kill the loop
        return f"tool {name} failed: {type(exc).__name__}: {str(exc)[:120]}"


def _spec(name: str, desc: str, props: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required},
        },
    }


TOOL_SPECS = [
    _spec("corpus_search", "Search the RIG news corpus (354K multilingual articles) for a query. Returns cited [S#] articles.",
          {"query": {"type": "string"}, "k": {"type": "integer", "description": "how many (max 10)"}}, ["query"]),
    _spec("web_search", "Search the live web for fresh/breaking info not in the corpus. Returns cited [S#] web pages.",
          {"query": {"type": "string"}}, ["query"]),
    _spec("resolve_entity", "Resolve a person/org/place NAME to candidate entity_ids (disambiguated). Call before any entity tool.",
          {"name": {"type": "string"}}, ["name"]),
    _spec("entity_feed", "Recent cross-language articles mentioning an entity_id. Returns cited [S#].",
          {"entity_id": {"type": "string"}, "k": {"type": "integer"}}, ["entity_id"]),
    _spec("entity_stances", "How an entity is portrayed: supportive-vs-critical balance + stance distribution.",
          {"entity_id": {"type": "string"}}, ["entity_id"]),
    _spec("quotes", "Verbatim (translated) quotes BY a speaker entity_id, optionally about a topic. Returns cited [S#].",
          {"speaker_id": {"type": "string"}, "topic": {"type": "string"}}, ["speaker_id"]),
    _spec("connect_entities", "How two entity_ids are connected: shared articles + bridging entities.",
          {"a": {"type": "string"}, "b": {"type": "string"}}, ["a", "b"]),
]
