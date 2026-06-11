"""Unit tests for the story clustering pipeline.

Mocks the DB session and the LLM judge — these tests verify pipeline
WIRING (which branch fires for which distance, etc.), not the LLM's
judgment itself (covered by the offline eval in
scratch/cluster-eval/REVIEW.md).
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from backend.nlp.story_clustering.types import (
    HARD_MATCH_MAX_DISTANCE,
    HARD_REJECT_MIN_DISTANCE,
    Article,
    CandidateThread,
    JudgeVerdict,
)


def _article(aid: str = "a1") -> Article:
    return Article(
        id=aid,
        title="Test article",
        primary_subject="Test subject",
        summary_executive="Test summary",
        language_detected="en",
        source_id="src1",
        source_name="Test Source",
        collected_at=datetime.now(timezone.utc),
        embedding=[0.1] * 768,
    )


def _candidate(thread_id: str, distance: float) -> CandidateThread:
    return CandidateThread(
        thread_id=thread_id,
        title="Test thread",
        primary_entities=(),
        article_count=3,
        source_count=2,
        seed_article_id="seed1",
        seed_title="Seed",
        seed_summary="Seed summary",
        distance=distance,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_hard_match_skips_llm() -> None:
    """Distance below HARD_MATCH_MAX_DISTANCE → auto-assign, no LLM."""
    from backend.nlp.story_clustering import pipeline

    article = _article()
    very_close = HARD_MATCH_MAX_DISTANCE / 2

    with (
        patch.object(pipeline, "_load_article", AsyncMock(return_value=article)),
        patch.object(
            pipeline.candidates,
            "find_top_k",
            AsyncMock(return_value=[_candidate("t1", very_close)]),
        ),
        patch.object(
            pipeline.assignment,
            "assign_to_thread",
            AsyncMock(return_value="ASSIGNED"),
        ) as mock_assign,
        patch.object(pipeline.judge, "is_same_story", AsyncMock()) as mock_judge,
    ):
        result = await pipeline.cluster_article("a1", db=AsyncMock())

    assert result == "ASSIGNED"
    mock_judge.assert_not_called()  # fast path bypassed the LLM
    args, kwargs = mock_assign.call_args
    assert kwargs["skipped_llm"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_hard_reject_spawns_without_llm() -> None:
    """Distance above HARD_REJECT_MIN_DISTANCE → auto-spawn, no LLM."""
    from backend.nlp.story_clustering import pipeline

    article = _article()
    very_far = HARD_REJECT_MIN_DISTANCE + 0.1

    with (
        patch.object(pipeline, "_load_article", AsyncMock(return_value=article)),
        patch.object(
            pipeline.candidates,
            "find_top_k",
            AsyncMock(return_value=[_candidate("t1", very_far)]),
        ),
        patch.object(
            pipeline.assignment,
            "spawn_new_thread",
            AsyncMock(return_value="SPAWNED"),
        ) as mock_spawn,
        patch.object(pipeline.judge, "is_same_story", AsyncMock()) as mock_judge,
    ):
        result = await pipeline.cluster_article("a1", db=AsyncMock())

    assert result == "SPAWNED"
    mock_judge.assert_not_called()
    args, kwargs = mock_spawn.call_args
    assert kwargs["skipped_llm"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ambiguous_zone_calls_llm_and_assigns_on_match() -> None:
    """Distance in the gray zone → LLM judges; on match → assign."""
    from backend.nlp.story_clustering import pipeline

    article = _article()
    grey = (HARD_MATCH_MAX_DISTANCE + HARD_REJECT_MIN_DISTANCE) / 2
    candidates = [_candidate("t1", grey), _candidate("t2", grey + 0.05)]

    with (
        patch.object(pipeline, "_load_article", AsyncMock(return_value=article)),
        patch.object(pipeline.candidates, "find_top_k", AsyncMock(return_value=candidates)),
        patch.object(
            pipeline.judge,
            "is_same_story",
            AsyncMock(
                return_value=JudgeVerdict(
                    matched_thread_id="t2", confidence=0.82, reasoning="same protest"
                )
            ),
        ) as mock_judge,
        patch.object(
            pipeline.assignment,
            "assign_to_thread",
            AsyncMock(return_value="ASSIGNED"),
        ) as mock_assign,
    ):
        result = await pipeline.cluster_article("a1", db=AsyncMock())

    assert result == "ASSIGNED"
    mock_judge.assert_called_once()
    args, kwargs = mock_assign.call_args
    assert kwargs["confidence"] == 0.82
    assert kwargs["skipped_llm"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ambiguous_zone_spawns_on_new_verdict() -> None:
    """Distance in the gray zone, LLM says NEW → spawn."""
    from backend.nlp.story_clustering import pipeline

    article = _article()
    grey = (HARD_MATCH_MAX_DISTANCE + HARD_REJECT_MIN_DISTANCE) / 2

    with (
        patch.object(pipeline, "_load_article", AsyncMock(return_value=article)),
        patch.object(
            pipeline.candidates,
            "find_top_k",
            AsyncMock(return_value=[_candidate("t1", grey)]),
        ),
        patch.object(
            pipeline.judge,
            "is_same_story",
            AsyncMock(
                return_value=JudgeVerdict(
                    matched_thread_id=None, confidence=0.3, reasoning="too vague"
                )
            ),
        ),
        patch.object(
            pipeline.assignment,
            "spawn_new_thread",
            AsyncMock(return_value="SPAWNED"),
        ) as mock_spawn,
    ):
        result = await pipeline.cluster_article("a1", db=AsyncMock())

    assert result == "SPAWNED"
    args, kwargs = mock_spawn.call_args
    assert kwargs["skipped_llm"] is False
    assert kwargs["confidence"] == 0.3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_candidates_spawns_new() -> None:
    """Empty candidate list → spawn a new thread without LLM call."""
    from backend.nlp.story_clustering import pipeline

    article = _article()

    with (
        patch.object(pipeline, "_load_article", AsyncMock(return_value=article)),
        patch.object(pipeline.candidates, "find_top_k", AsyncMock(return_value=[])),
        patch.object(
            pipeline.assignment,
            "spawn_new_thread",
            AsyncMock(return_value="SPAWNED"),
        ) as mock_spawn,
        patch.object(pipeline.judge, "is_same_story", AsyncMock()) as mock_judge,
    ):
        result = await pipeline.cluster_article("a1", db=AsyncMock())

    assert result == "SPAWNED"
    mock_judge.assert_not_called()
    args, kwargs = mock_spawn.call_args
    assert kwargs["skipped_llm"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_missing_article_returns_none() -> None:
    """Article without embedding → returns None, no work done."""
    from backend.nlp.story_clustering import pipeline

    with patch.object(pipeline, "_load_article", AsyncMock(return_value=None)):
        result = await pipeline.cluster_article("missing", db=AsyncMock())

    assert result is None
