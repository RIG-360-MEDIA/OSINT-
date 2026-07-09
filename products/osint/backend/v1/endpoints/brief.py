"""Briefing endpoints — the scope digest.

A structured "what's happening in your world" digest: the top surfaceable stories
in the caller's scope, grouped into topic sections. Reuses the same scope +
surfaceable logic as /stories, so the brief is always consistent with the feed.
(A prose LLM-narrated summary is a future enhancement; v1 gives a structured digest
with a count summary — honest, fast, no generation cost.)
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request

from db import get_db

from .. import queries
from ..errors import bad_request, ok
from ..scope import ApiContext, get_context

router = APIRouter(prefix="/v1", tags=["briefings"])


async def _digest(ctx: ApiContext, limit: int, order_by: str, kind: str) -> dict:
    async with get_db() as db:
        rows, _ = await queries.list_scoped_stories(
            db,
            entity_ids=list(ctx.scope.entity_ids),
            all_entities=ctx.scope.all_entities,
            regions=ctx.scope.regions,
            country=None,
            cursor=None,
            limit=limit,
            order_by=order_by,
            mute_terms=ctx.scope.mute_terms,
        )
    sections: dict[str, list] = {}
    for r in rows:
        topic = r.get("topic") or "OTHER"
        sections.setdefault(topic, []).append({
            "story_id": r.get("id"),
            "title": r.get("title"),
            "outlets": r.get("outlets"),
            "article_count": r.get("article_count"),
            "subject_country": r.get("subject_country"),
            "representative_article_id": r.get("representative_article_id"),
        })
    ordered = sorted(sections.items(), key=lambda kv: -sum((s["outlets"] or 0) for s in kv[1]))
    out_sections = [{"title": t, "stories": s} for t, s in ordered]
    return {
        "kind": kind,
        "ordering": order_by,  # 'importance' (today/daily) vs 'recent' (situation)
        "date": datetime.now(timezone.utc).date().isoformat(),
        "summary": f"{len(rows)} developments across your scope, in {len(out_sections)} topics.",
        "sections": out_sections,
    }


@router.get("/brief/today", summary="Today's digest — top stories in your scope, grouped by topic")
async def brief_today(
    request: Request,
    limit: int = Query(30, ge=1, le=100),
    ctx: ApiContext = Depends(get_context),
) -> dict:
    d = await _digest(ctx, limit, order_by="importance", kind="today")
    request.state.result_count = sum(len(s["stories"]) for s in d["sections"])
    return ok(d)


@router.get("/brief/situation", summary="Rolling situation summary across your scope")
async def brief_situation(
    request: Request,
    limit: int = Query(30, ge=1, le=100),
    ctx: ApiContext = Depends(get_context),
) -> dict:
    d = await _digest(ctx, limit, order_by="recent", kind="situation")
    request.state.result_count = sum(len(s["stories"]) for s in d["sections"])
    return ok(d)


@router.get("/brief/daily", summary="The digest for a given day (defaults to current)")
async def brief_daily(
    request: Request,
    date: str | None = Query(None, description="ISO date YYYY-MM-DD (v1 returns the current scope digest)"),
    limit: int = Query(30, ge=1, le=100),
    ctx: ApiContext = Depends(get_context),
) -> dict:
    if date:
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise bad_request("'date' must be an ISO date (YYYY-MM-DD)")
    d = await _digest(ctx, limit, order_by="importance", kind="daily")
    if date:
        d["requested_date"] = date
        d["note"] = "historical daily briefs are not yet stored; showing the current scope digest"
    request.state.result_count = sum(len(s["stories"]) for s in d["sections"])
    return ok(d)
