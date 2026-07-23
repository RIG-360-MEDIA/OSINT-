"""draftsmith.models — THE contract.

Frozen dataclasses shared by every draftsmith stage and by the API layer.
The CMS zod schema (rig-news/src/lib/dispatch/types.ts) mirrors these shapes;
this file is the single source of truth. Keep the two in lock-step — a drift
here is the project's #1 named risk.

Pure data + (de)serialisation only. No I/O, no business logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Literal, Mapping, Optional, Sequence

# --- enumerations (kept as Literals so they serialise to plain strings) ------

JobState = Literal[
    "queued", "planning", "gathering", "ranking", "drafting",
    "verifying", "repairing", "images", "ready",
    "failed", "cancelled", "published",
]

SourceType = Literal[
    "corpus_article", "story_fact", "youtube_clip", "web", "wikipedia",
    "twitter", "reddit", "tiktok", "telegram", "instagram", "wechat",
]

TrustTier = Literal[1, 2, 3]  # 1 primary/verified, 2 corroboration-wanted, 3 lead/colour only

BeatVerdict = Literal["green", "amber", "red"]
Severity = Literal["red", "amber"]
VersionKind = Literal["model", "repair", "editor"]
ImageOrigin = Literal["corpus", "wikimedia", "web"]

# --- dials (editor-set at generation time; sweepable in eval) ----------------

@dataclass(frozen=True)
class Dials:
    creativity: int = 5        # 0-10 ladder → also maps to temperature
    moxy: int = 3              # 0-10 personality ladder
    length_target: int = 1200  # editor-set word target (soft; never padded)
    spot_check: bool = True    # run the adversarial second-verify pass

    def clamp(self) -> "Dials":
        return Dials(
            creativity=max(0, min(10, self.creativity)),
            moxy=max(0, min(10, self.moxy)),
            length_target=max(300, min(4000, self.length_target)),
            spot_check=self.spot_check,
        )

    @staticmethod
    def from_json(d: Optional[Mapping[str, Any]]) -> "Dials":
        d = d or {}
        return Dials(
            creativity=int(d.get("creativity", 5)),
            moxy=int(d.get("moxy", 3)),
            length_target=int(d.get("length_target", 1200)),
            spot_check=bool(d.get("spot_check", True)),
        ).clamp()

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


# --- stage 1: query plan -----------------------------------------------------

@dataclass(frozen=True)
class PlanEntity:
    name: str
    type: Literal["person", "org", "place", "event", "other"]
    disambiguation: str = ""
    aliases: Sequence[str] = field(default_factory=tuple)
    alternates: Sequence[str] = field(default_factory=tuple)  # rejected readings


@dataclass(frozen=True)
class Directives:
    """Extracted verbatim from a long editorial brief; flows into the BRIEF as
    BINDING instructions. Empty when the input is a bare topic line."""
    angle: Optional[str] = None
    must_include: Sequence[str] = field(default_factory=tuple)
    must_avoid: Sequence[str] = field(default_factory=tuple)
    tone_notes: Optional[str] = None
    length_hint: Optional[int] = None
    other_constraints: Sequence[str] = field(default_factory=tuple)

    @property
    def is_empty(self) -> bool:
        return not (self.angle or self.must_include or self.must_avoid
                    or self.tone_notes or self.other_constraints)


@dataclass(frozen=True)
class TimeWindow:
    from_days_ago: int
    to_days_ago: Optional[int]
    rationale: str = ""


@dataclass(frozen=True)
class SourceQueries:
    """Search-shaped keyword strings per source (≤3 each). Empty list = skip
    that source for this topic."""
    warehouse_fts: Sequence[str] = field(default_factory=tuple)
    warehouse_vector_seed: str = ""     # one dense neutral paragraph for embedding
    facts_cluster_hint: str = ""
    web: Sequence[str] = field(default_factory=tuple)
    youtube: Sequence[str] = field(default_factory=tuple)
    twitter: Sequence[str] = field(default_factory=tuple)
    reddit: Sequence[str] = field(default_factory=tuple)
    tiktok: Sequence[str] = field(default_factory=tuple)
    telegram: Sequence[str] = field(default_factory=tuple)
    instagram: Sequence[str] = field(default_factory=tuple)
    wechat: Sequence[str] = field(default_factory=tuple)
    wikipedia_titles: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class QueryPlan:
    topic_summary: str
    entities: Sequence[PlanEntity]
    directives: Directives
    time_window: TimeWindow
    queries: SourceQueries
    geo_hints: Sequence[str] = field(default_factory=tuple)
    language_hints: Sequence[str] = field(default_factory=tuple)


# --- stage 2/3: evidence -----------------------------------------------------

@dataclass(frozen=True)
class EvidenceItem:
    """One normalised, citable unit. `text` is the frozen snapshot the writer
    may quote; `source_id` is its citation handle."""
    source_id: str
    source_type: SourceType
    trust_tier: TrustTier
    text: str
    title: Optional[str] = None
    url: Optional[str] = None
    outlet: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    relevance: float = 0.0
    # source-type-specific extras: cites[] (facts), embed_url+timestamps (yt),
    # verified (tw), engine (web) …
    extra: Mapping[str, Any] = field(default_factory=dict)


# --- stage 4/5: draft + verify -----------------------------------------------

@dataclass(frozen=True)
class DraftBeat:
    subhead: str
    text: str                 # markdown; the ONLY structural break is the subhead
    source_ids: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class KeyFact:
    fact: str
    source_ids: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class PullQuote:
    text: str
    speaker: str = ""
    source_id: str = ""


@dataclass(frozen=True)
class Draft:
    """The article as generated/edited. `beats` carry beat-level citations."""
    headline: str
    dek: str
    beats: Sequence[DraftBeat]
    key_facts: Sequence[KeyFact] = field(default_factory=tuple)
    pull_quote: Optional[PullQuote] = None
    unsourced_gaps: Sequence[str] = field(default_factory=tuple)

    @property
    def word_count(self) -> int:
        return sum(len(b.text.split()) for b in self.beats)


@dataclass(frozen=True)
class Violation:
    span: str
    why: str
    severity: Severity
    expected_source_ids: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class BeatVerdictReport:
    index: int
    verdict: BeatVerdict
    violations: Sequence[Violation] = field(default_factory=tuple)


@dataclass(frozen=True)
class VerifyReport:
    verdict: Literal["pass", "fail"]
    beats: Sequence[BeatVerdictReport]

    @property
    def has_red(self) -> bool:
        return any(b.verdict == "red" for b in self.beats)


@dataclass(frozen=True)
class DraftVersion:
    version: int
    kind: VersionKind
    draft: Draft
    verify_report: Optional[VerifyReport]
    created_by: str            # 'model' | editor id
    created_at: Optional[datetime] = None


# --- flags + images ----------------------------------------------------------

@dataclass(frozen=True)
class Flag:
    id: str
    beat_index: int
    span: str
    severity: Severity
    reason: str
    source_ids: Sequence[str] = field(default_factory=tuple)
    status: Literal["open", "dismissed", "fixed"] = "open"
    resolved_by: Optional[str] = None
    resolution_note: Optional[str] = None


@dataclass(frozen=True)
class ImageCandidate:
    id: str
    slot: int                  # 1-6
    origin: ImageOrigin
    url: str
    thumb_url: Optional[str] = None
    license: Optional[str] = None
    license_url: Optional[str] = None
    attribution: Optional[str] = None
    needs_license_review: bool = False   # always True for origin='web'
    selected: bool = False


# --- publish handoff payload (box → CMS at finalize) -------------------------

@dataclass(frozen=True)
class PublishPayload:
    """What the box returns from /finalize; the CMS maps this onto
    createManualStory() and writes ONE row to Neon manual_stories."""
    job_id: str
    version: int
    headline: str
    dek: str
    body_markdown: str         # beats rendered "## subhead\n\ntext", + plain "## Sources" tail
    topic: str
    country: Optional[str]
    image_url: Optional[str]
    importance_suggested: float
    flags_summary: Mapping[str, int]  # {resolved, red, amber}
