"""GET /api/keywords/search — the Keyword Dossier.

One free-text keyword → unified cross-source intelligence (volume, sentiment,
top articles, cross-platform social, related entities). The flagship search.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from auth.middleware import get_optional_user
from db import get_db
from keyword_dossier import build_keyword_dossier
from keyword_alerts import evaluate_watch
from keyword_tracking import list_alerts, list_tracked, track_keyword, untrack_keyword
from academic_collector import academic_lookup
from archive_collector import web_archive
from company_collector import company_lookup
from gdelt_collector import gdelt_coverage
from geo_collector import geo_lookup
from infra_collector import domain_infra
from perspective import build_perspective
from searxng_collector import web_search
from social_live import social_live
from stats_collector import country_stats
from tasking_brain import build_task_plan
from wiki_collector import wiki_lookup

router = APIRouter(prefix="/api/keywords", tags=["keywords"])


@router.get("/plan")
async def keyword_plan(
    q: str = Query(..., min_length=1, max_length=120, description="keyword/phrase"),
) -> dict[str, Any]:
    """The Tasking brain's decision: classify the keyword + the justified source plan."""
    async with get_db() as db:
        return await build_task_plan(db, q)


@router.get("/search")
async def keyword_search(
    q: str = Query(..., min_length=1, max_length=120, description="keyword/phrase"),
    days: int = Query(default=7, ge=1, le=90),
) -> dict[str, Any]:
    """Cross-source dossier for a keyword over the last `days`.

    The aggregation runs several trigram-indexed scans; raise the statement
    timeout above the 20s request default so wide windows complete. The Tasking
    brain's classification + source plan are merged in so the UI knows what the
    keyword IS and which sources are (or will be) searched.
    """
    async with get_db() as db:
        await db.execute(text("SET statement_timeout='30s'"))
        dossier = await build_keyword_dossier(db, q, days)
        plan = await build_task_plan(db, q)
        dossier["classification"] = plan["classification"]
        dossier["perspective_default"] = plan["perspective_default"]
        dossier["source_plan"] = plan["source_plan"]
        return dossier


@router.get("/websearch")
async def websearch(
    q: str = Query(..., min_length=1, max_length=200, description="keyword or dork (site:/filetype:)"),
    limit: int = Query(default=10, ge=1, le=25),
) -> dict[str, Any]:
    """Web-search source — SearXNG multi-engine meta-search for a keyword/dork.

    Ranked results + source-domain discovery + knowledge-panel infobox, and a
    best-guess official domain (feeds infra/archive). Honestly reports which
    engines were unresponsive."""
    return await web_search(q, limit=limit)


@router.get("/infra")
async def infra(
    domain: str = Query(..., min_length=3, max_length=253, description="a domain, e.g. ril.com"),
) -> dict[str, Any]:
    """Domain/Infra source — registration (RDAP) + live DNS for a domain."""
    return await domain_infra(domain)


# ── Phase-7 non-social OSINT sources (free, no-key; on-demand per keyword) ──

@router.get("/academic")
async def academic(q: str = Query(..., min_length=2, max_length=120)) -> dict[str, Any]:
    """Academic/research footprint via OpenAlex (papers, authors, institutions)."""
    return await academic_lookup(q)


@router.get("/stats")
async def stats(country: str = Query(..., min_length=2, max_length=3, description="ISO2 country code")) -> dict[str, Any]:
    """Country indicators (GDP/population/growth/inflation) via World Bank."""
    return await country_stats(country)


@router.get("/geo")
async def geo(q: str = Query(..., min_length=2, max_length=200)) -> dict[str, Any]:
    """Geolocation of a place via OpenStreetMap Nominatim."""
    return await geo_lookup(q)


@router.get("/archive")
async def archive(domain: str = Query(..., min_length=3, max_length=253)) -> dict[str, Any]:
    """Web history (first-seen + snapshot count) via the Wayback Machine."""
    return await web_archive(domain)


@router.get("/wiki")
async def wiki(q: str = Query(..., min_length=2, max_length=120)) -> dict[str, Any]:
    """Encyclopedic profile + Wikidata ID via Wikipedia."""
    return await wiki_lookup(q)


@router.get("/gdelt")
async def gdelt(q: str = Query(..., min_length=2, max_length=120)) -> dict[str, Any]:
    """Worldwide news coverage volume + tone via GDELT (beyond the India corpus)."""
    return await gdelt_coverage(q)


@router.get("/company")
async def company(q: str = Query(..., min_length=2, max_length=120)) -> dict[str, Any]:
    """Official legal-entity registration via GLEIF (LEI, jurisdiction, status)."""
    return await company_lookup(q)


@router.get("/social-live")
async def social_live_endpoint(
    q: str = Query(..., min_length=2, max_length=120),
    limit: int = Query(default=10, ge=1, le=30),
) -> dict[str, Any]:
    """On-demand keyword-driven social — TikTok + WeChat, fetched live (Phase 3)."""
    return await social_live(q, limit)


@router.get("/perspective")
async def perspective(
    q: str = Query(..., min_length=1, max_length=120),
    days: int = Query(default=7, ge=1, le=90),
) -> dict[str, Any]:
    """Perspective Lens — framing divergence across languages/origins for a keyword."""
    async with get_db() as db:
        await db.execute(text("SET statement_timeout='30s'"))
        return await build_perspective(db, q, days)


@router.post("/track")
async def track(
    q: str = Query(..., min_length=1, max_length=120),
    days: int = Query(default=7, ge=1, le=90),
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    """Track a keyword for the authenticated user → standing watch for alerts."""
    if not user:
        raise HTTPException(status_code=401, detail="auth required to track")
    async with get_db() as db:
        plan = await build_task_plan(db, q)
        wid = await track_keyword(db, user["id"], q, plan["classification"],
                                  plan["perspective_default"], days)
        return {"tracked": True, "watch_id": wid, "keyword": q,
                "classification": plan["classification"]}


@router.delete("/track")
async def untrack(
    q: str = Query(..., min_length=1, max_length=120),
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    if not user:
        raise HTTPException(status_code=401, detail="auth required")
    async with get_db() as db:
        changed = await untrack_keyword(db, user["id"], q)
        return {"untracked": changed, "keyword": q}


@router.get("/tracked")
async def tracked(
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    """List the user's tracked keywords + unseen-alert counts."""
    if not user:
        return {"tracked": []}
    async with get_db() as db:
        return {"tracked": await list_tracked(db, user["id"])}


@router.get("/alerts")
async def alerts(
    unseen: bool = Query(default=False),
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    """Alerts across the user's tracked keywords (newest first)."""
    if not user:
        return {"alerts": []}
    async with get_db() as db:
        return {"alerts": await list_alerts(db, user["id"], unseen)}
