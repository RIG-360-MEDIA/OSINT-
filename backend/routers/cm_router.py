"""
CM Page (Chief Minister political situation room) — `/api/cm/*` router.

Architecture: zero LLM calls at request time. Heavy work runs in
`backend/tasks/cm/*` Celery tasks and lands in dedicated `cm_*` tables;
this router is a fast read + assembly layer with an in-process TTL
cache (see `backend/nlp/cm/cache.py`).

State scoping: the `state` query param wins; otherwise the user's
`user_profiles.geo_primary` is resolved into a code (TG / AP / None).

Schemas live in `cm_schemas.py`; SQL helpers live in `cm_queries.py`.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from backend.auth.auth_middleware import get_current_principal, get_current_user, require_page
from backend.nlp.cm import cache as cm_cache
from backend.routers import cm_queries as q
from backend.routers.cm_schemas import (
    CMDashboardResponse,
    CounterNarrativeBullet,
    CounterNarrativeCard,
    CounterNarrativesResponse,
    DissentMember,
    DissentResponse,
    DissentSignal,
    DivergenceResponse,
    DivergenceRow,
    HeatmapCell,
    HeatmapResponse,
    IssueCard,
    IssuesResponse,
    PromiseRow,
    PromisesResponse,
    PulseResponse,
    QuoteRef,
    QuoteRow,
    QuotesResponse,
    RegionPulse,
    RiskEvent,
    RiskWindowResponse,
    SilenceItem,
    SilenceResponse,
    SpokespersonRow,
    SpokespersonsResponse,
    StanceTriad,
    TopicPulse,
    TrajectoryPoint,
    TrajectoryResponse,
    VoiceShareResponse,
    VoiceShareRow,
)

logger = logging.getLogger(__name__)

# D-11 fix: gate every CM endpoint behind the worldmonitor page allowlist.
# Previously the router only required `get_current_user` per endpoint, so any
# logged-in user — including ones whose `user_page_access` lacked
# 'worldmonitor' — could read political-intelligence rows by hitting
# /api/cm/* directly, bypassing the frontend middleware page guard.
cm_router = APIRouter(
    prefix="/api/cm",
    tags=["cm"],
    dependencies=[Depends(require_page("worldmonitor"))],
)

WINDOWS = {"24h", "7d", "30d"}


def _window(window: str) -> str:
    return window if window in WINDOWS else "24h"


# ── I — Pulse ───────────────────────────────────────────────────────────

@cm_router.get("/pulse", response_model=PulseResponse)
async def get_pulse(
    state: str | None = Query(default=None),
    window: str = Query(default="24h"),
    user: dict = Depends(get_current_principal),
) -> PulseResponse:
    state_code = await q.resolve_state(user["id"], state)
    window = _window(window)
    key = (user["id"], state_code or "", window)
    cached = cm_cache.get("pulse", key)
    if cached is not None:
        cached.cache_hit = True
        return cached

    raw = await q.fetch_pulse(state_code, window)
    overall_dict = raw["overall"]
    resp = PulseResponse(
        state=state_code,
        window=window,
        overall=TopicPulse(**overall_dict),
        by_topic=[TopicPulse(**t) for t in raw["by_topic"]],
        by_region=[RegionPulse(**r) for r in raw["by_region"]],
        sample_size=raw["sample_size"],
        computed_at=raw["computed_at"],
        cache_hit=False,
    )
    cm_cache.put("pulse", key, resp)
    return resp


# ── II — Issues ─────────────────────────────────────────────────────────

@cm_router.get("/issues", response_model=IssuesResponse)
async def get_issues(
    state: str | None = Query(default=None),
    limit: int = Query(default=8, ge=1, le=20),
    user: dict = Depends(get_current_principal),
) -> IssuesResponse:
    state_code = await q.resolve_state(user["id"], state)
    key = (user["id"], state_code or "", limit)
    cached = cm_cache.get("issues", key)
    if cached is not None:
        cached.cache_hit = True
        return cached

    rows = await q.fetch_issues(state_code, limit=limit)
    issues: list[IssueCard] = []
    for r in rows:
        triad = r["stances"]
        issues.append(
            IssueCard(
                id=r["id"],
                label=r["label"],
                slug=r["slug"],
                intensity=r["intensity"],
                intensity_delta_24h=r["intensity_delta_24h"],
                last_mention_at=r["last_mention_at"],
                ruling_summary=r["ruling_summary"],
                opposition_summary=r["opposition_summary"],
                neutral_summary=r["neutral_summary"],
                stances=StanceTriad(**triad),
                party_stances=[],
                top_quotes=[QuoteRef(**qref) for qref in r["top_quotes"]],
                evidence_count=r["evidence_count"],
                trajectory=r.get("trajectory") or "unknown",
            )
        )
    resp = IssuesResponse(
        state=state_code,
        issues=issues,
        generated_at=datetime.utcnow(),
        cache_hit=False,
    )
    cm_cache.put("issues", key, resp)
    return resp


# ── III — Silence ───────────────────────────────────────────────────────

@cm_router.get("/silence", response_model=SilenceResponse)
async def get_silence(
    state: str | None = Query(default=None),
    limit: int = Query(default=5, ge=1, le=20),
    user: dict = Depends(get_current_principal),
) -> SilenceResponse:
    state_code = await q.resolve_state(user["id"], state)
    key = (user["id"], state_code or "", limit)
    cached = cm_cache.get("silence", key)
    if cached is not None:
        cached.cache_hit = True
        return cached

    rows = await q.fetch_silence(state_code, limit=limit)
    items = [SilenceItem(**r) for r in rows]
    resp = SilenceResponse(
        state=state_code,
        items=items,
        generated_at=datetime.utcnow(),
        cache_hit=False,
    )
    cm_cache.put("silence", key, resp)
    return resp


# ── IV — Spokespersons ──────────────────────────────────────────────────

@cm_router.get("/spokespersons", response_model=SpokespersonsResponse)
async def get_spokespersons(
    state: str | None = Query(default=None),
    mode: str = Query(default="attackers", pattern="^(attackers|on-message)$"),
    limit: int = Query(default=8, ge=1, le=20),
    user: dict = Depends(get_current_principal),
) -> SpokespersonsResponse:
    state_code = await q.resolve_state(user["id"], state)
    key = (user["id"], state_code or "", mode, limit)
    cached = cm_cache.get("spokespersons", key)
    if cached is not None:
        cached.cache_hit = True
        return cached

    rows = await q.fetch_spokespersons(state_code, mode=mode, limit=limit)
    resp = SpokespersonsResponse(
        state=state_code,
        mode=mode,
        rows=[SpokespersonRow(**r) for r in rows],
        generated_at=datetime.utcnow(),
        cache_hit=False,
    )
    cm_cache.put("spokespersons", key, resp)
    return resp


@cm_router.get("/cabinet-onmessage", response_model=SpokespersonsResponse)
async def get_cabinet_onmessage(
    state: str | None = Query(default=None),
    limit: int = Query(default=8, ge=1, le=20),
    user: dict = Depends(get_current_principal),
) -> SpokespersonsResponse:
    state_code = await q.resolve_state(user["id"], state)
    key = (user["id"], state_code or "", "on-message", limit)
    cached = cm_cache.get("cabinet_onmessage", key)
    if cached is not None:
        cached.cache_hit = True
        return cached
    rows = await q.fetch_spokespersons(state_code, mode="on-message", limit=limit)
    resp = SpokespersonsResponse(
        state=state_code,
        mode="on-message",
        rows=[SpokespersonRow(**r) for r in rows],
        generated_at=datetime.utcnow(),
        cache_hit=False,
    )
    cm_cache.put("cabinet_onmessage", key, resp)
    return resp


# ── V — Dissent ────────────────────────────────────────────────────────

@cm_router.get("/dissent", response_model=DissentResponse)
async def get_dissent(
    state: str | None = Query(default=None),
    confidence: float = Query(default=0.7, ge=0.0, le=1.0),
    user: dict = Depends(get_current_principal),
) -> DissentResponse:
    state_code = await q.resolve_state(user["id"], state)
    key = (user["id"], state_code or "", round(confidence, 2))
    cached = cm_cache.get("dissent", key)
    if cached is not None:
        cached.cache_hit = True
        return cached

    by_coalition = await q.fetch_dissent(state_code, confidence_floor=confidence)

    def _build(rows: list[dict]) -> list[DissentSignal]:
        return [
            DissentSignal(
                id=r["id"],
                coalition=r["coalition"],
                party=r["party"],
                faction=r["faction"],
                headline=r["headline"],
                severity=r["severity"],
                confidence=r["confidence"],
                members=[
                    DissentMember(
                        speaker=m["speaker"],
                        party=m["party"],
                        quote=QuoteRef(**m["quote"]),
                    )
                    for m in r["members"]
                ],
                issue_id=r["issue_id"],
                evidence_urls=r["evidence_urls"],
                detected_at=r["detected_at"],
            )
            for r in rows
        ]

    resp = DissentResponse(
        state=state_code,
        ruling=_build(by_coalition.get("ruling", [])),
        opposition=_build(by_coalition.get("opposition", [])),
        generated_at=datetime.utcnow(),
        cache_hit=False,
    )
    cm_cache.put("dissent", key, resp)
    return resp


# ── VI — Trajectory ─────────────────────────────────────────────────────

@cm_router.get("/trajectory", response_model=TrajectoryResponse)
async def get_trajectory(
    state: str | None = Query(default=None),
    days: int = Query(default=7, ge=3, le=30),
    user: dict = Depends(get_current_principal),
) -> TrajectoryResponse:
    state_code = await q.resolve_state(user["id"], state)
    key = (user["id"], state_code or "", days)
    cached = cm_cache.get("trajectory", key)
    if cached is not None:
        cached.cache_hit = True
        return cached

    rows = await q.fetch_trajectory(state_code, days=days)
    resp = TrajectoryResponse(
        state=state_code,
        rows=[TrajectoryPoint(**r) for r in rows],
        days=days,
        generated_at=datetime.utcnow(),
        cache_hit=False,
    )
    cm_cache.put("trajectory", key, resp)
    return resp


# ── VII — Heatmap ───────────────────────────────────────────────────────

@cm_router.get("/heatmap", response_model=HeatmapResponse)
async def get_heatmap(
    state: str | None = Query(default=None),
    user: dict = Depends(get_current_principal),
) -> HeatmapResponse:
    state_code = await q.resolve_state(user["id"], state)
    key = (user["id"], state_code or "")
    cached = cm_cache.get("heatmap", key)
    if cached is not None:
        cached.cache_hit = True
        return cached
    rows = await q.fetch_heatmap(state_code)
    resp = HeatmapResponse(
        state=state_code,
        cells=[HeatmapCell(**r) for r in rows],
        generated_at=datetime.utcnow(),
        cache_hit=False,
    )
    cm_cache.put("heatmap", key, resp)
    return resp


# ── VIII — Promises ─────────────────────────────────────────────────────

@cm_router.get("/promises", response_model=PromisesResponse)
async def get_promises(
    state: str | None = Query(default=None),
    limit: int = Query(default=12, ge=1, le=50),
    user: dict = Depends(get_current_principal),
) -> PromisesResponse:
    state_code = await q.resolve_state(user["id"], state)
    key = (user["id"], state_code or "", limit)
    cached = cm_cache.get("promises", key)
    if cached is not None:
        cached.cache_hit = True
        return cached
    rows = await q.fetch_promises(state_code, limit=limit)
    resp = PromisesResponse(
        state=state_code,
        rows=[PromiseRow(**r) for r in rows],
        generated_at=datetime.utcnow(),
        cache_hit=False,
    )
    cm_cache.put("promises", key, resp)
    return resp


# ── IX — Counter-narratives ─────────────────────────────────────────────

@cm_router.get("/counter-narratives", response_model=CounterNarrativesResponse)
async def get_counter_narratives(
    state: str | None = Query(default=None),
    limit: int = Query(default=3, ge=1, le=10),
    user: dict = Depends(get_current_principal),
) -> CounterNarrativesResponse:
    state_code = await q.resolve_state(user["id"], state)
    key = (user["id"], state_code or "", limit)
    cached = cm_cache.get("counter_narratives", key)
    if cached is not None:
        cached.cache_hit = True
        return cached
    rows = await q.fetch_counter_narratives(state_code, limit=limit)
    cards = [
        CounterNarrativeCard(
            issue_id=r["issue_id"],
            issue_label=r["issue_label"],
            talking_points=[CounterNarrativeBullet(**tp) for tp in r["talking_points"]],
            grounding_doc_ids=r["grounding_doc_ids"],
            grounding_kinds=r["grounding_kinds"],
            generated_at=r["generated_at"],
            model=r["model"],
            is_draft=True,
        )
        for r in rows
    ]
    resp = CounterNarrativesResponse(
        state=state_code,
        cards=cards,
        generated_at=datetime.utcnow(),
        cache_hit=False,
    )
    cm_cache.put("counter_narratives", key, resp)
    return resp


# ── X — Risk window ─────────────────────────────────────────────────────

@cm_router.get("/risk-window", response_model=RiskWindowResponse)
async def get_risk_window(
    state: str | None = Query(default=None),
    days: int = Query(default=7, ge=1, le=30),
    user: dict = Depends(get_current_principal),
) -> RiskWindowResponse:
    state_code = await q.resolve_state(user["id"], state)
    key = (user["id"], state_code or "", days)
    cached = cm_cache.get("risk_window", key)
    if cached is not None:
        cached.cache_hit = True
        return cached
    rows = await q.fetch_risk_window(state_code, days=days)
    resp = RiskWindowResponse(
        state=state_code,
        days=days,
        events=[RiskEvent(**r) for r in rows],
        generated_at=datetime.utcnow(),
        cache_hit=False,
    )
    cm_cache.put("risk_window", key, resp)
    return resp


# ── XI — Quotes ─────────────────────────────────────────────────────────

@cm_router.get("/quotes", response_model=QuotesResponse)
async def get_quotes(
    state: str | None = Query(default=None),
    limit: int = Query(default=9, ge=1, le=30),
    user: dict = Depends(get_current_principal),
) -> QuotesResponse:
    state_code = await q.resolve_state(user["id"], state)
    key = (user["id"], state_code or "", limit)
    cached = cm_cache.get("quotes", key)
    if cached is not None:
        cached.cache_hit = True
        return cached
    rows = await q.fetch_quotes(state_code, limit=limit)
    resp = QuotesResponse(
        state=state_code,
        rows=[QuoteRow(**r) for r in rows],
        generated_at=datetime.utcnow(),
        cache_hit=False,
    )
    cm_cache.put("quotes", key, resp)
    return resp


# ── XII — Voice share ──────────────────────────────────────────────────

@cm_router.get("/voice-share", response_model=VoiceShareResponse)
async def get_voice_share(
    state: str | None = Query(default=None),
    limit: int = Query(default=8, ge=1, le=20),
    user: dict = Depends(get_current_principal),
) -> VoiceShareResponse:
    state_code = await q.resolve_state(user["id"], state)
    key = (user["id"], state_code or "", limit)
    cached = cm_cache.get("voice_share", key)
    if cached is not None:
        cached.cache_hit = True
        return cached
    rows = await q.fetch_voice_share(state_code, limit=limit)
    resp = VoiceShareResponse(
        state=state_code,
        rows=[VoiceShareRow(**r) for r in rows],
        generated_at=datetime.utcnow(),
        cache_hit=False,
    )
    cm_cache.put("voice_share", key, resp)
    return resp


# ── XIII — Language divergence ─────────────────────────────────────────

@cm_router.get("/divergence/language", response_model=DivergenceResponse)
async def get_language_divergence(
    state: str | None = Query(default=None),
    user: dict = Depends(get_current_principal),
) -> DivergenceResponse:
    state_code = await q.resolve_state(user["id"], state)
    key = (user["id"], state_code or "", "language")
    cached = cm_cache.get("language_divergence", key)
    if cached is not None:
        cached.cache_hit = True
        return cached
    rows = await q.fetch_language_divergence(state_code)
    resp = DivergenceResponse(
        state=state_code,
        kind="language",
        rows=[DivergenceRow(**r) for r in rows],
        generated_at=datetime.utcnow(),
        cache_hit=False,
    )
    cm_cache.put("language_divergence", key, resp)
    return resp


# ── XIV — Medium divergence ────────────────────────────────────────────

@cm_router.get("/divergence/medium", response_model=DivergenceResponse)
async def get_medium_divergence(
    state: str | None = Query(default=None),
    user: dict = Depends(get_current_principal),
) -> DivergenceResponse:
    state_code = await q.resolve_state(user["id"], state)
    key = (user["id"], state_code or "", "medium")
    cached = cm_cache.get("medium_divergence", key)
    if cached is not None:
        cached.cache_hit = True
        return cached
    rows = await q.fetch_medium_divergence(state_code)
    resp = DivergenceResponse(
        state=state_code,
        kind="medium",
        rows=[DivergenceRow(**r) for r in rows],
        generated_at=datetime.utcnow(),
        cache_hit=False,
    )
    cm_cache.put("medium_divergence", key, resp)
    return resp


# ── Aggregator ────────────────────────────────────────────────────────

@cm_router.get("/dashboard", response_model=CMDashboardResponse)
async def get_dashboard(
    state: str | None = Query(default=None),
    window: str = Query(default="24h"),
    user: dict = Depends(get_current_principal),
) -> CMDashboardResponse:
    """Aggregator. Fans out to every section in parallel; one section's
    failure becomes a `section_errors[name] = "..."` entry rather than a
    500 — the CM Page must never blank end-to-end."""
    state_code = await q.resolve_state(user["id"], state)
    key = (user["id"], state_code or "", _window(window))
    cached = cm_cache.get("dashboard", key)
    if cached is not None:
        cached.cache_hit = True
        return cached

    section_errors: dict[str, str] = {}

    async def _safe(name: str, coro):
        try:
            return name, await coro
        except Exception as exc:  # noqa: BLE001 — section isolation is intentional
            logger.exception("cm dashboard section %s failed", name)
            section_errors[name] = str(exc)[:200]
            return name, None

    # Every Query() default must be passed explicitly when calling these
    # handlers Python-side — Query objects only resolve to their default
    # values inside the FastAPI request lifecycle, not on direct call.
    sections = await asyncio.gather(
        _safe("pulse",               get_pulse(state=state_code, window=window, user=user)),
        _safe("issues",              get_issues(state=state_code, limit=8, user=user)),
        _safe("silence",             get_silence(state=state_code, limit=5, user=user)),
        _safe("spokespersons",       get_spokespersons(state=state_code, mode="attackers", limit=8, user=user)),
        _safe("cabinet_onmessage",   get_cabinet_onmessage(state=state_code, limit=8, user=user)),
        _safe("dissent",             get_dissent(state=state_code, confidence=0.7, user=user)),
        _safe("trajectory",          get_trajectory(state=state_code, days=7, user=user)),
        _safe("heatmap",             get_heatmap(state=state_code, user=user)),
        _safe("promises",            get_promises(state=state_code, limit=12, user=user)),
        _safe("counter_narratives",  get_counter_narratives(state=state_code, limit=3, user=user)),
        _safe("risk_window",         get_risk_window(state=state_code, days=7, user=user)),
        _safe("quotes",              get_quotes(state=state_code, limit=9, user=user)),
        _safe("voice_share",         get_voice_share(state=state_code, limit=8, user=user)),
        _safe("language_divergence", get_language_divergence(state=state_code, user=user)),
        _safe("medium_divergence",   get_medium_divergence(state=state_code, user=user)),
    )
    by_section: dict[str, Any] = {name: payload for name, payload in sections}

    resp = CMDashboardResponse(
        state=state_code,
        pulse=by_section.get("pulse"),
        issues=by_section.get("issues"),
        silence=by_section.get("silence"),
        spokespersons=by_section.get("spokespersons"),
        cabinet_onmessage=by_section.get("cabinet_onmessage"),
        dissent=by_section.get("dissent"),
        trajectory=by_section.get("trajectory"),
        heatmap=by_section.get("heatmap"),
        promises=by_section.get("promises"),
        counter_narratives=by_section.get("counter_narratives"),
        risk_window=by_section.get("risk_window"),
        quotes=by_section.get("quotes"),
        voice_share=by_section.get("voice_share"),
        language_divergence=by_section.get("language_divergence"),
        medium_divergence=by_section.get("medium_divergence"),
        section_errors=section_errors,
        generated_at=datetime.utcnow(),
        cache_hit=False,
    )
    cm_cache.put("dashboard", key, resp)
    return resp
