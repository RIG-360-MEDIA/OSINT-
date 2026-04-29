"""
Pydantic response schemas for the CM Page (`/api/cm/*`).

Schemas are the locked contract between the FastAPI router and the
frontend `frontend/src/app/brief/cm/types.ts` interfaces. Adding a field
is non-breaking; renaming or removing one requires a coordinated frontend
change.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


# ── Shared ──────────────────────────────────────────────────────────────

Stance = Literal["ruling_supportive", "opposition_attack", "neutral_factual", "mixed", "unknown"]
PartyKind = Literal["ruling", "opposition", "neutral"]
Trajectory = Literal["intensifying", "steady", "fading", "unknown"]
PromiseStatus = Literal["kept", "in_progress", "stalled", "broken", "unknown"]
RiskKind = Literal["court", "parliament", "festival", "by_election", "anniversary", "deadline", "protest", "session"]
RiskLevel = Literal["low", "med", "high"]
DissentSeverity = Literal["murmur", "crack", "break"]
SilenceSeverity = Literal["watch", "warn", "critical"]


class QuoteRef(BaseModel):
    speaker: str
    party: str | None = None
    role: str | None = None
    quote: str
    source_url: str | None = None
    source_kind: str | None = None
    captured_at: datetime | None = None


class StanceTriad(BaseModel):
    ruling: float = Field(..., description="weighted-mean stance for ruling-tagged sources, [-1,+1]")
    opposition: float
    neutral: float
    n_ruling: int
    n_opposition: int
    n_neutral: int


# ── I — Pulse ───────────────────────────────────────────────────────────

class TopicPulse(BaseModel):
    topic: str
    score: float
    delta_7d: float
    n: int


class RegionPulse(BaseModel):
    region: str
    score: float
    delta_7d: float
    n: int


class PulseResponse(BaseModel):
    state: str | None
    window: str
    overall: TopicPulse
    by_topic: list[TopicPulse]
    by_region: list[RegionPulse]
    sample_size: int
    computed_at: datetime
    cache_hit: bool = False


# ── II — Issues ─────────────────────────────────────────────────────────

class PartyStance(BaseModel):
    party: str
    stance: Literal["defend", "attack", "silent", "ambiguous"]
    confidence: float


class IssueCard(BaseModel):
    id: int
    label: str
    slug: str
    intensity: float
    intensity_delta_24h: float
    last_mention_at: datetime | None = None
    ruling_summary: str | None = None
    opposition_summary: str | None = None
    neutral_summary: str | None = None
    stances: StanceTriad
    party_stances: list[PartyStance] = Field(default_factory=list)
    top_quotes: list[QuoteRef] = Field(default_factory=list)
    evidence_count: int = 0
    trajectory: Trajectory = "unknown"


class IssuesResponse(BaseModel):
    state: str | None
    issues: list[IssueCard]
    generated_at: datetime
    cache_hit: bool = False


# ── III — Silence ───────────────────────────────────────────────────────

class SilenceItem(BaseModel):
    issue_id: int | None = None
    label: str
    started_at: datetime | None = None
    age_hours: float
    public_volume_7d: int
    govt_mentions_7d: int
    days_since_govt_statement: float | None = None
    ministers_named: list[str] = Field(default_factory=list)
    severity: SilenceSeverity
    sample_evidence: list[QuoteRef] = Field(default_factory=list)


class SilenceResponse(BaseModel):
    state: str | None
    items: list[SilenceItem]
    generated_at: datetime
    cache_hit: bool = False


# ── IV — Spokespersons ──────────────────────────────────────────────────

class SpokespersonRow(BaseModel):
    speaker: str
    party: str | None = None
    role: str | None = None
    score: float
    mentions_24h: int
    mentions_7d: int
    delta_pct: float
    avg_sentiment: float
    on_message_rate: float | None = None
    top_topics: list[str] = Field(default_factory=list)
    latest_quote: QuoteRef | None = None


class SpokespersonsResponse(BaseModel):
    state: str | None
    mode: Literal["attackers", "on-message"]
    rows: list[SpokespersonRow]
    generated_at: datetime
    cache_hit: bool = False


# ── V — Internal Dissent ───────────────────────────────────────────────

class DissentMember(BaseModel):
    speaker: str
    party: str
    quote: QuoteRef


class DissentSignal(BaseModel):
    id: int
    coalition: PartyKind
    party: str
    faction: str | None = None
    headline: str
    severity: DissentSeverity
    confidence: float
    members: list[DissentMember] = Field(default_factory=list)
    issue_id: int | None = None
    evidence_urls: list[str] = Field(default_factory=list)
    detected_at: datetime


class DissentResponse(BaseModel):
    state: str | None
    ruling: list[DissentSignal]
    opposition: list[DissentSignal]
    generated_at: datetime
    cache_hit: bool = False


# ── VI — Trajectory ─────────────────────────────────────────────────────

class TrajectoryPoint(BaseModel):
    issue_id: int
    label: str
    series_volume: list[int]
    series_sentiment: list[float]
    classification: Trajectory
    slope: float
    delta_24h: float


class TrajectoryResponse(BaseModel):
    state: str | None
    rows: list[TrajectoryPoint]
    days: int
    generated_at: datetime
    cache_hit: bool = False


# ── VII — Heatmap ───────────────────────────────────────────────────────

class HeatmapCell(BaseModel):
    constituency_code: str
    constituency_name: str
    state: str
    score: float
    volume: int
    top_issue_ids: list[int] = Field(default_factory=list)


class HeatmapResponse(BaseModel):
    state: str | None
    cells: list[HeatmapCell]
    generated_at: datetime
    cache_hit: bool = False


# ── VIII — Promises ─────────────────────────────────────────────────────

class PromiseRow(BaseModel):
    id: int
    pledge_text: str
    pledge_short: str | None = None
    owner_party: str
    deadline: date | None = None
    status: PromiseStatus
    status_confidence: float | None = None
    last_status_change: datetime
    exploitation_index: float
    source_url: str | None = None
    last_evidence_url: str | None = None


class PromisesResponse(BaseModel):
    state: str | None
    rows: list[PromiseRow]
    generated_at: datetime
    cache_hit: bool = False


# ── IX — Counter-narratives ─────────────────────────────────────────────

class CounterNarrativeBullet(BaseModel):
    text: str
    cites: list[str]                                # UUIDs of grounding articles


class CounterNarrativeCard(BaseModel):
    issue_id: int
    issue_label: str
    talking_points: list[CounterNarrativeBullet]
    grounding_doc_ids: list[str]                    # UUIDs
    grounding_kinds: list[str]
    generated_at: datetime
    model: str
    is_draft: bool = True


class CounterNarrativesResponse(BaseModel):
    state: str | None
    cards: list[CounterNarrativeCard]
    generated_at: datetime
    cache_hit: bool = False


# ── X — Risk window ─────────────────────────────────────────────────────

class RiskEvent(BaseModel):
    id: int
    event_date: date
    state: str | None = None
    kind: RiskKind
    title: str
    description: str | None = None
    risk_summary: str | None = None
    risk_level: RiskLevel
    source_url: str | None = None


class RiskWindowResponse(BaseModel):
    state: str | None
    days: int
    events: list[RiskEvent]
    generated_at: datetime
    cache_hit: bool = False


# ── XI — Quotes (Verbatim) ──────────────────────────────────────────────

class QuoteRow(BaseModel):
    id: int | None = None
    speaker: str
    party: str | None = None
    role: str | None = None
    quote: str
    quote_lang: str | None = None
    issue_id: int | None = None
    sentiment: float | None = None
    stance: Stance | None = None
    source_url: str | None = None
    source_kind: str | None = None
    captured_at: datetime | None = None


class QuotesResponse(BaseModel):
    state: str | None
    rows: list[QuoteRow]
    generated_at: datetime
    cache_hit: bool = False


# ── XII — Voice share delta ────────────────────────────────────────────

class VoiceShareRow(BaseModel):
    speaker: str
    party: str | None = None
    share_24h_pct: float
    share_7d_pct: float
    delta_pct: float
    mentions_24h: int
    mentions_7d: int


class VoiceShareResponse(BaseModel):
    state: str | None
    rows: list[VoiceShareRow]
    generated_at: datetime
    cache_hit: bool = False


# ── XIII / XIV — Divergence ────────────────────────────────────────────

class DivergenceRow(BaseModel):
    topic: str
    side_a_label: str
    side_b_label: str
    score_a: float
    score_b: float
    delta: float
    flagged: bool
    sample_a: list[QuoteRef] = Field(default_factory=list)
    sample_b: list[QuoteRef] = Field(default_factory=list)


class DivergenceResponse(BaseModel):
    state: str | None
    kind: Literal["language", "medium"]
    rows: list[DivergenceRow]
    generated_at: datetime
    cache_hit: bool = False


# ── Dashboard aggregator ───────────────────────────────────────────────

class CMDashboardResponse(BaseModel):
    state: str | None
    pulse: PulseResponse | None = None
    issues: IssuesResponse | None = None
    silence: SilenceResponse | None = None
    spokespersons: SpokespersonsResponse | None = None
    cabinet_onmessage: SpokespersonsResponse | None = None
    dissent: DissentResponse | None = None
    trajectory: TrajectoryResponse | None = None
    heatmap: HeatmapResponse | None = None
    promises: PromisesResponse | None = None
    counter_narratives: CounterNarrativesResponse | None = None
    risk_window: RiskWindowResponse | None = None
    quotes: QuotesResponse | None = None
    voice_share: VoiceShareResponse | None = None
    language_divergence: DivergenceResponse | None = None
    medium_divergence: DivergenceResponse | None = None
    section_errors: dict[str, str] = Field(default_factory=dict)
    generated_at: datetime
    cache_hit: bool = False
