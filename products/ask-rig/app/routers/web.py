"""Set 3 endpoints: raw web search + fused deep-research."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.db import connect
from app.deps import get_embedder, settings
from app.llm import get_llm
from app.research import run_research
from app.schemas_account import ResearchRequest, ResearchResponse
from app.web.search import search_web

router = APIRouter(tags=["web"])


@router.get("/web/search")
async def web_search_endpoint(q: str) -> dict:
    if len(q.strip()) < 2:
        raise HTTPException(422, "q must be at least 2 characters")
    results, error = await search_web(settings, q)
    return {"query": q, "results": results, "error": error}


@router.post("/research", response_model=ResearchResponse)
async def research_endpoint(req: ResearchRequest) -> ResearchResponse:
    async with connect(settings) as conn:
        return await run_research(
            conn, settings, get_embedder(), get_llm(settings),
            req.question, req.languages, req.use_web, req.web_k,
        )
