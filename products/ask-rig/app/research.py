"""Deep-research-lite: corpus retrieve + web search + page extraction → one cited
answer over the fused source set. Reuses the LLM pool and cite-ID guardrail."""
from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncConnection

from app.answer import answer_question
from app.config import Settings
from app.embedding import LabseEmbedder
from app.llm import LLMProvider
from app.retrieval import retrieve_and_curate
from app.schemas_account import ResearchResponse, WebResult
from app.web.extract import fetch_extract
from app.web.fuse import fuse_web_corpus
from app.web.search import search_web


async def run_research(
    conn: AsyncConnection,
    settings: Settings,
    embedder: LabseEmbedder,
    llm: LLMProvider,
    question: str,
    languages: list[str] | None = None,
    use_web: bool = True,
    web_k: int = 6,
) -> ResearchResponse:
    qvec = await asyncio.to_thread(embedder.embed, question)
    corpus = await retrieve_and_curate(
        conn, settings, question, qvec, languages, top_k=8, rerank_enabled=False
    )

    # Deep-read more pages when the user asks for more breadth (cap at 4 to bound latency).
    extract_top = min(max(web_k // 2, 2), 4)
    web_results: list[WebResult] = []
    web_err: str | None = None
    if use_web and web_k > 0:
        web_results, web_err = await search_web(settings, question, k=web_k)
        # Enrich the top pages with real extracted body text (not just SERP snippet).
        enriched: list[WebResult] = []
        for i, w in enumerate(web_results):
            if i < extract_top:
                body = await fetch_extract(settings, w.url)
                enriched.append(
                    WebResult(title=w.title, url=w.url, snippet=(body[:600] if body else w.snippet), engine=w.engine)
                )
            else:
                enriched.append(w)
        web_results = enriched

    fused = fuse_web_corpus(corpus, web_results)[: min(14, 8 + web_k)]
    result = await asyncio.to_thread(answer_question, llm, question, fused)

    notes = result.notes
    if web_err:
        notes = f"{notes} | {web_err}" if notes else web_err
    return ResearchResponse(
        question=question,
        answer=result.answer,
        faithful=result.faithful,
        citations=result.citations,
        sources=fused,  # what the [S#] citations index into
        web_sources=web_results,
        notes=notes,
    )
