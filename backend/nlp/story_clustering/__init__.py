"""Story clustering v2.

Replaces the broken thread_engine.py matcher. Architecture:

    article (with labse_embedding)
        │
        ▼
    candidates.find_top_k(...)        ← cheap kNN over active v2 seeds
        │
        ▼
    fast-path threshold check?         ← skip LLM in the unambiguous zones
        │  yes → auto-assign / auto-spawn
        │  no  → continue
        ▼
    judge.is_same_story(...)           ← LLM-as-judge on top-3 candidates
        │
        ▼
    assignment.assign_or_spawn(...)    ← persist
        │
        ▼
    aggregates.refresh(thread_id)      ← recompute source_count,
                                         primary_entities, momentum
                                         every time the thread changes

Public entry points:
    pipeline.cluster_article(article_id, db)
    pipeline.consolidate(db)
"""
from __future__ import annotations

from backend.nlp.story_clustering.pipeline import cluster_article, consolidate
from backend.nlp.story_clustering.types import (
    Article,
    CandidateThread,
    JudgeVerdict,
    AssignmentResult,
)

__all__ = [
    "cluster_article",
    "consolidate",
    "Article",
    "CandidateThread",
    "JudgeVerdict",
    "AssignmentResult",
]
