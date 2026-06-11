"""Immutable DTOs for the clustering pipeline.

All boundary objects are frozen dataclasses so a result returned from one
stage cannot be mutated by the next. Keeps the pipeline easy to reason
about and to test in isolation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


# Cosine-distance thresholds. Calibrated against the 100-article eval
# (sample.json) — SAME pairs had distance 0.19-0.50, DIFFERENT pairs had
# distance 0.12-0.50. So the unambiguous zones are roughly:
#   distance < 0.18  → very likely SAME (skip LLM)
#   distance > 0.55  → very likely DIFFERENT (skip LLM)
# Everything in between is the ambiguity zone the LLM judge handles.
HARD_MATCH_MAX_DISTANCE: float = 0.18
HARD_REJECT_MIN_DISTANCE: float = 0.55
CANDIDATE_TOP_K: int = 5
WINDOW_DAYS: int = 14


@dataclass(frozen=True)
class Article:
    """Read-only article view used by the clustering pipeline."""

    id: str
    title: str
    primary_subject: str | None
    summary_executive: str | None
    language_detected: str | None
    source_id: str
    source_name: str
    collected_at: datetime
    embedding: list[float]  # 768-dim labse_embedding


@dataclass(frozen=True)
class CandidateThread:
    """One candidate thread, returned by the kNN search."""

    thread_id: str
    title: str
    primary_entities: tuple[str, ...]
    article_count: int
    source_count: int
    seed_article_id: str | None
    seed_title: str | None
    seed_summary: str | None
    distance: float  # cosine distance — lower = closer


@dataclass(frozen=True)
class JudgeVerdict:
    """LLM judge's verdict over the article + candidates."""

    matched_thread_id: str | None  # None → spawn new thread
    confidence: float  # 0.0 - 1.0
    reasoning: str


@dataclass(frozen=True)
class AssignmentResult:
    """Outcome of cluster_article — what happened to this article."""

    article_id: str
    thread_id: str
    spawned_new: bool
    skipped_llm: bool  # True if hit fast-path threshold
    confidence: float
    distance_to_seed: float
