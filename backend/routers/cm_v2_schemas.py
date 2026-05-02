"""
Pydantic response models for CM Page v2 endpoints.

Kept in a separate module from ``cm_schemas.py`` so the legacy CM
situation-room endpoints stay untouched. All v2 responses inherit
``CmV2Base`` which carries ``state``, ``computed_at`` and
``cache_hit`` for consistency.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CmV2Base(BaseModel):
    """Shared envelope fields on every v2 response."""

    state: str | None = None
    computed_at: datetime
    cache_hit: bool = False


# ── Lead ─────────────────────────────────────────────────────────────────


class LeadHeadline(BaseModel):
    rank: int
    eyebrow: str
    headline: str
    cite_ids: list[str] = Field(default_factory=list)
    generated_at: datetime
    model: str


class LeadResponse(CmV2Base):
    headlines: list[LeadHeadline]


# ── News on Chair ────────────────────────────────────────────────────────


class CmNewsItem(BaseModel):
    id: str
    title: str
    source: str
    age_label: str
    sentiment: float | None = None
    reach: str | None = None
    url: str | None = None
    districts: list[str] = Field(default_factory=list)
    published_at: datetime | None = None


class NewsOnChairResponse(CmV2Base):
    items: list[CmNewsItem]


# ── Opposition Watch ─────────────────────────────────────────────────────


class OppositionItem(BaseModel):
    id: str
    actor: str
    party: str
    channel: str
    age_label: str
    text: str
    reach: str | None = None
    sentiment: float | None = None
    url: str | None = None


class OppositionWatchResponse(CmV2Base):
    items: list[OppositionItem]


# ── Threats ──────────────────────────────────────────────────────────────


class ThreatItem(BaseModel):
    id: str
    text: str
    level: Literal["LOW", "LOW-MED", "MED", "HIGH"]
    posture: str
    source: str            # 'dissent' / 'counter_narrative' / 'risk_calendar'
    cite_ids: list[str] = Field(default_factory=list)


class ThreatsResponse(CmV2Base):
    items: list[ThreatItem]


# ── Outlook ──────────────────────────────────────────────────────────────


class OutlookItem(BaseModel):
    when: str               # display: '4 May · Sun', '5–6 May'
    event_date: datetime | None = None
    text: str
    risk_level: str | None = None
    source_url: str | None = None


class OutlookResponse(CmV2Base):
    items: list[OutlookItem]


# ── Monitor ──────────────────────────────────────────────────────────────


class MonitorItem(BaseModel):
    label: str
    status: str             # display: '↑ +23% this week', '● live now · hour 4'
    delta_pct: float | None = None
    trend: Literal["up", "down", "flat", "live"]


class MonitorResponse(CmV2Base):
    items: list[MonitorItem]


# ── Live Pulse ───────────────────────────────────────────────────────────


class PulseTile(BaseModel):
    label: str              # 'TOTAL MENTIONS · 24H'
    value: str              # '1,247'
    delta: str | None = None
    trend: Literal["up", "down", "flat"] | None = None


class LivePulseResponse(CmV2Base):
    tiles: list[PulseTile]


# ── Actions ──────────────────────────────────────────────────────────────


class CmActionItem(BaseModel):
    id: str
    priority: Literal["P0", "P1", "P2"]
    text: str
    deadline: str | None = None
    source_type: Literal["rule", "llm", "calendar"]
    cite_ids: list[str] = Field(default_factory=list)
    expires_at: datetime


class ActionsResponse(CmV2Base):
    items: list[CmActionItem]


# ── Analysis ─────────────────────────────────────────────────────────────


class AnalysisColumn(BaseModel):
    eyebrow: str
    byline: str
    headline: str
    deck: str | None = None
    paragraphs: list[str]
    pull_quote: str | None = None
    endnote: str | None = None
    cite_ids: list[str] = Field(default_factory=list)
    published_at: datetime
    model: str


class AnalysisResponse(CmV2Base):
    column: AnalysisColumn | None = None


# ── Atlas Layer ──────────────────────────────────────────────────────────


class DistrictValue(BaseModel):
    district_id: str
    value: float
    breakdown: dict[str, float] | None = None


class AtlasLayerResponse(CmV2Base):
    layer_id: str
    label: str
    rows: list[DistrictValue]
    stale: bool = False
    last_source_run_at: datetime | None = None


# ── District focus ───────────────────────────────────────────────────────


class DistrictFacts(BaseModel):
    hq_city: str
    population: str | None = None
    area: str | None = None
    notable: str | None = None


class DistrictBriefResponse(CmV2Base):
    district_id: str
    name: str
    facts: DistrictFacts
    stability_score: int | None = None
    one_liner: str | None = None
    news: list[CmNewsItem]
    acled_count_7d: int
    mandi_top_movers: list[dict]
    welfare_summary: list[dict]
    power_status: dict | None = None
    counter_narrative: dict | None = None


# ── Ticker ───────────────────────────────────────────────────────────────


class TickerEvent(BaseModel):
    time: str               # 'HH:MM' display
    text: str
    source_kind: str
    url: str | None = None


class TickerResponse(CmV2Base):
    events: list[TickerEvent]


__all__ = [
    "ActionsResponse",
    "AnalysisColumn",
    "AnalysisResponse",
    "AtlasLayerResponse",
    "CmActionItem",
    "CmNewsItem",
    "CmV2Base",
    "DistrictBriefResponse",
    "DistrictFacts",
    "DistrictValue",
    "LeadHeadline",
    "LeadResponse",
    "LivePulseResponse",
    "MonitorItem",
    "MonitorResponse",
    "NewsOnChairResponse",
    "OppositionItem",
    "OppositionWatchResponse",
    "OutlookItem",
    "OutlookResponse",
    "PulseTile",
    "ThreatItem",
    "ThreatsResponse",
    "TickerEvent",
    "TickerResponse",
]
