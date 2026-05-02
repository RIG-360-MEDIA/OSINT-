"""
CM Page v2 — `/api/cm/{lead,news_on_chair,...}` endpoints.

Mounted alongside the legacy ``cm_router`` on ``/api/cm`` (no path
collision — every v2 endpoint name is new). Same TTL-cache pattern as
the legacy router (``cm_cache.get/put``) and same auth gate
(``require_page("worldmonitor")``).

Each endpoint is thin: resolve state → cache lookup → query helper →
Pydantic response. No business logic here.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from backend.auth.auth_middleware import get_current_user, require_page
from backend.nlp.cm import cache as cm_cache
from backend.routers import cm_v2_queries as q
from backend.routers.cm_queries import resolve_state
from backend.routers.cm_v2_schemas import (
    ActionsResponse,
    AnalysisColumn,
    AnalysisResponse,
    AtlasLayerResponse,
    CmActionItem,
    CmNewsItem,
    DistrictBriefResponse,
    DistrictFacts,
    DistrictValue,
    LeadHeadline,
    LeadResponse,
    LivePulseResponse,
    MonitorItem,
    MonitorResponse,
    NewsOnChairResponse,
    OppositionItem,
    OppositionWatchResponse,
    OutlookItem,
    OutlookResponse,
    PulseTile,
    ThreatItem,
    ThreatsResponse,
    TickerEvent,
    TickerResponse,
)

logger = logging.getLogger(__name__)

cm_v2_router = APIRouter(prefix="/api/cm", tags=["cm-v2"])

_LAYER_LABELS: dict[str, str] = {
    "news-hotspot": "News Hotspot",
    "sentiment":    "Sentiment",
    "acled":        "ACLED Events",
    "mandi":        "Mandi Volatility",
    "welfare":      "Welfare Coverage",
    "power":        "Power Stress",
    "stability":    "Stability Index",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── 1. Lead ──────────────────────────────────────────────────────────────


@cm_v2_router.get("/lead", response_model=LeadResponse, dependencies=[Depends(require_page("worldmonitor"))])
async def get_lead(
    state: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
) -> LeadResponse:
    state_code = await resolve_state(user["id"], state)
    cache_key = ("v2_lead", user["id"], state_code or "")
    if (cached := cm_cache.get("v2_lead", cache_key)) is not None:
        cached.cache_hit = True
        return cached
    rows = await q.fetch_lead_headlines(state_code)
    resp = LeadResponse(
        state=state_code,
        computed_at=_now(),
        headlines=[LeadHeadline(**r) for r in rows],
    )
    cm_cache.put("v2_lead", cache_key, resp)
    return resp


# ── 2. News on Chair ─────────────────────────────────────────────────────


@cm_v2_router.get("/news_on_chair", response_model=NewsOnChairResponse, dependencies=[Depends(require_page("worldmonitor"))])
async def get_news_on_chair(
    state: str | None = Query(default=None),
    limit: int = Query(default=4, ge=1, le=12),
    user: dict = Depends(get_current_user),
) -> NewsOnChairResponse:
    state_code = await resolve_state(user["id"], state)
    cache_key = ("v2_news", user["id"], state_code or "", limit)
    if (cached := cm_cache.get("v2_news", cache_key)) is not None:
        cached.cache_hit = True
        return cached
    rows = await q.fetch_news_on_chair(state_code, limit=limit)
    resp = NewsOnChairResponse(
        state=state_code,
        computed_at=_now(),
        items=[CmNewsItem(**r) for r in rows],
    )
    cm_cache.put("v2_news", cache_key, resp)
    return resp


# ── 3. Opposition Watch ──────────────────────────────────────────────────


@cm_v2_router.get("/opposition_watch", response_model=OppositionWatchResponse, dependencies=[Depends(require_page("worldmonitor"))])
async def get_opposition_watch(
    state: str | None = Query(default=None),
    limit: int = Query(default=4, ge=1, le=12),
    user: dict = Depends(get_current_user),
) -> OppositionWatchResponse:
    state_code = await resolve_state(user["id"], state)
    cache_key = ("v2_opp", user["id"], state_code or "", limit)
    if (cached := cm_cache.get("v2_opp", cache_key)) is not None:
        cached.cache_hit = True
        return cached
    rows = await q.fetch_opposition_watch(state_code, limit=limit)
    resp = OppositionWatchResponse(
        state=state_code,
        computed_at=_now(),
        items=[OppositionItem(**r) for r in rows],
    )
    cm_cache.put("v2_opp", cache_key, resp)
    return resp


# ── 4. Threats ───────────────────────────────────────────────────────────


@cm_v2_router.get("/threats", response_model=ThreatsResponse, dependencies=[Depends(require_page("worldmonitor"))])
async def get_threats(
    state: str | None = Query(default=None),
    limit: int = Query(default=4, ge=1, le=10),
    user: dict = Depends(get_current_user),
) -> ThreatsResponse:
    state_code = await resolve_state(user["id"], state)
    cache_key = ("v2_threats", user["id"], state_code or "", limit)
    if (cached := cm_cache.get("v2_threats", cache_key)) is not None:
        cached.cache_hit = True
        return cached
    rows = await q.fetch_threats(state_code, limit=limit)
    resp = ThreatsResponse(
        state=state_code,
        computed_at=_now(),
        items=[ThreatItem(**r) for r in rows],
    )
    cm_cache.put("v2_threats", cache_key, resp)
    return resp


# ── 5. Outlook ───────────────────────────────────────────────────────────


@cm_v2_router.get("/outlook", response_model=OutlookResponse, dependencies=[Depends(require_page("worldmonitor"))])
async def get_outlook(
    state: str | None = Query(default=None),
    limit: int = Query(default=4, ge=1, le=10),
    user: dict = Depends(get_current_user),
) -> OutlookResponse:
    state_code = await resolve_state(user["id"], state)
    cache_key = ("v2_outlook", user["id"], state_code or "", limit)
    if (cached := cm_cache.get("v2_outlook", cache_key)) is not None:
        cached.cache_hit = True
        return cached
    rows = await q.fetch_outlook(state_code, limit=limit)
    resp = OutlookResponse(
        state=state_code,
        computed_at=_now(),
        items=[OutlookItem(**r) for r in rows],
    )
    cm_cache.put("v2_outlook", cache_key, resp)
    return resp


# ── 6. Monitor ───────────────────────────────────────────────────────────


@cm_v2_router.get("/monitor", response_model=MonitorResponse, dependencies=[Depends(require_page("worldmonitor"))])
async def get_monitor(
    state: str | None = Query(default=None),
    limit: int = Query(default=6, ge=1, le=12),
    user: dict = Depends(get_current_user),
) -> MonitorResponse:
    state_code = await resolve_state(user["id"], state)
    cache_key = ("v2_monitor", user["id"], state_code or "", limit)
    if (cached := cm_cache.get("v2_monitor", cache_key)) is not None:
        cached.cache_hit = True
        return cached
    rows = await q.fetch_monitor(state_code, limit=limit)
    resp = MonitorResponse(
        state=state_code,
        computed_at=_now(),
        items=[MonitorItem(**r) for r in rows],
    )
    cm_cache.put("v2_monitor", cache_key, resp)
    return resp


# ── 7. Live Pulse ────────────────────────────────────────────────────────


@cm_v2_router.get("/live_pulse", response_model=LivePulseResponse, dependencies=[Depends(require_page("worldmonitor"))])
async def get_live_pulse(
    state: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
) -> LivePulseResponse:
    state_code = await resolve_state(user["id"], state)
    cache_key = ("v2_pulse", user["id"], state_code or "")
    if (cached := cm_cache.get("v2_pulse", cache_key)) is not None:
        cached.cache_hit = True
        return cached
    tiles_raw = await q.fetch_live_pulse(state_code)
    resp = LivePulseResponse(
        state=state_code,
        computed_at=_now(),
        tiles=[PulseTile(**t) for t in tiles_raw],
    )
    cm_cache.put("v2_pulse", cache_key, resp)
    return resp


# ── 8. Actions ───────────────────────────────────────────────────────────


@cm_v2_router.get("/actions", response_model=ActionsResponse, dependencies=[Depends(require_page("worldmonitor"))])
async def get_actions(
    state: str | None = Query(default=None),
    limit: int = Query(default=5, ge=1, le=15),
    user: dict = Depends(get_current_user),
) -> ActionsResponse:
    state_code = await resolve_state(user["id"], state)
    cache_key = ("v2_actions", user["id"], state_code or "", limit)
    if (cached := cm_cache.get("v2_actions", cache_key)) is not None:
        cached.cache_hit = True
        return cached
    rows = await q.fetch_actions(state_code, limit=limit)
    resp = ActionsResponse(
        state=state_code,
        computed_at=_now(),
        items=[CmActionItem(**r) for r in rows],
    )
    cm_cache.put("v2_actions", cache_key, resp)
    return resp


# ── 9. Analysis ──────────────────────────────────────────────────────────


@cm_v2_router.get("/analysis", response_model=AnalysisResponse, dependencies=[Depends(require_page("worldmonitor"))])
async def get_analysis(
    state: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
) -> AnalysisResponse:
    state_code = await resolve_state(user["id"], state)
    cache_key = ("v2_analysis", user["id"], state_code or "")
    if (cached := cm_cache.get("v2_analysis", cache_key)) is not None:
        cached.cache_hit = True
        return cached
    raw = await q.fetch_analysis(state_code)
    resp = AnalysisResponse(
        state=state_code,
        computed_at=_now(),
        column=AnalysisColumn(**raw) if raw else None,
    )
    cm_cache.put("v2_analysis", cache_key, resp)
    return resp


# ── 10. Atlas Layer ──────────────────────────────────────────────────────


@cm_v2_router.get("/atlas/layer/{layer_id}", response_model=AtlasLayerResponse, dependencies=[Depends(require_page("worldmonitor"))])
async def get_atlas_layer(
    layer_id: str,
    state: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
) -> AtlasLayerResponse:
    state_code = await resolve_state(user["id"], state)
    cache_key = ("v2_layer", user["id"], state_code or "", layer_id)
    if (cached := cm_cache.get("v2_layer", cache_key)) is not None:
        cached.cache_hit = True
        return cached
    raw = await q.fetch_atlas_layer(state_code, layer_id)
    resp = AtlasLayerResponse(
        state=state_code,
        computed_at=_now(),
        layer_id=layer_id,
        label=_LAYER_LABELS.get(layer_id, layer_id),
        rows=[DistrictValue(**row) for row in raw["rows"]],
        stale=raw["stale"],
        last_source_run_at=raw["last_source_run_at"],
    )
    cm_cache.put("v2_layer", cache_key, resp)
    return resp


# ── 11. District Brief ───────────────────────────────────────────────────


@cm_v2_router.get("/district/{district_id}", response_model=DistrictBriefResponse | None, dependencies=[Depends(require_page("worldmonitor"))])
async def get_district_brief(
    district_id: str,
    user: dict = Depends(get_current_user),
) -> DistrictBriefResponse | None:
    cache_key = ("v2_district", user["id"], district_id)
    if (cached := cm_cache.get("v2_district", cache_key)) is not None:
        cached.cache_hit = True
        return cached
    raw = await q.fetch_district_brief(district_id)
    if raw is None:
        return None
    resp = DistrictBriefResponse(
        state=None,
        computed_at=_now(),
        district_id=raw["district_id"],
        name=raw["name"],
        facts=DistrictFacts(**raw["facts"]),
        stability_score=raw.get("stability_score"),
        one_liner=raw.get("one_liner"),
        news=[CmNewsItem(**n) for n in raw["news"]],
        acled_count_7d=raw["acled_count_7d"],
        mandi_top_movers=raw["mandi_top_movers"],
        welfare_summary=raw["welfare_summary"],
        power_status=raw.get("power_status"),
        counter_narrative=raw.get("counter_narrative"),
    )
    cm_cache.put("v2_district", cache_key, resp)
    return resp


# ── 12. Ticker ───────────────────────────────────────────────────────────


@cm_v2_router.get("/ticker", response_model=TickerResponse, dependencies=[Depends(require_page("worldmonitor"))])
async def get_ticker(
    state: str | None = Query(default=None),
    limit: int = Query(default=7, ge=1, le=20),
    user: dict = Depends(get_current_user),
) -> TickerResponse:
    state_code = await resolve_state(user["id"], state)
    cache_key = ("v2_ticker", user["id"], state_code or "", limit)
    if (cached := cm_cache.get("v2_ticker", cache_key)) is not None:
        cached.cache_hit = True
        return cached
    rows = await q.fetch_ticker(state_code, limit=limit)
    resp = TickerResponse(
        state=state_code,
        computed_at=_now(),
        events=[TickerEvent(**r) for r in rows],
    )
    cm_cache.put("v2_ticker", cache_key, resp)
    return resp


__all__ = ["cm_v2_router"]
