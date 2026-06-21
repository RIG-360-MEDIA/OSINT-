"""Unit tests for the cross-encoder reranker — CrossEncoder is mocked."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.schemas import RetrievedDoc


def _doc(doc_id: str, title: str, score: float = 0.5) -> RetrievedDoc:
    return RetrievedDoc(
        id=doc_id,
        title=title,
        snippet="sample snippet text",
        url=None,
        published_at=None,
        source_id="src1",
        language="en",
        score=score,
        vec_rank=None,
        lex_rank=None,
    )


# Each test patches _load so the real bge model is never loaded.

@patch("app.rerank._deep_encoder")
def test_rerank_orders_by_cross_encoder_score(mock_load: MagicMock) -> None:
    mock_load.return_value.predict.return_value = np.array([0.2, 0.9, 0.5])
    from app.rerank import rerank

    docs = [_doc("low", "low relevance"), _doc("high", "high relevance"), _doc("mid", "mid relevance")]
    result = rerank("mock", "query", docs, top_n=3)
    assert [d.id for d in result] == ["high", "mid", "low"]


@patch("app.rerank._deep_encoder")
def test_rerank_respects_top_n(mock_load: MagicMock) -> None:
    mock_load.return_value.predict.return_value = np.array([0.1, 0.8, 0.6, 0.3])
    from app.rerank import rerank

    docs = [_doc(str(i), f"doc {i}") for i in range(4)]
    result = rerank("mock", "query", docs, top_n=2)
    assert len(result) == 2
    assert result[0].id == "1"  # score 0.8 is highest


@patch("app.rerank._deep_encoder")
def test_rerank_updates_score_field(mock_load: MagicMock) -> None:
    mock_load.return_value.predict.return_value = np.array([0.753])
    from app.rerank import rerank

    docs = [_doc("x", "article headline", score=0.3)]
    result = rerank("mock", "q", docs, top_n=1)
    assert result[0].score == pytest.approx(0.753, abs=1e-5)


def test_rerank_empty_input() -> None:
    from app.rerank import rerank
    assert rerank("any-model", "q", [], top_n=5) == []


@patch("app.rerank._deep_encoder")
def test_rerank_top_n_capped_at_doc_count(mock_load: MagicMock) -> None:
    mock_load.return_value.predict.return_value = np.array([0.9, 0.4])
    from app.rerank import rerank

    docs = [_doc("1", "a"), _doc("2", "b")]
    result = rerank("mock", "q", docs, top_n=100)
    assert len(result) == 2


@patch("app.rerank._deep_encoder")
def test_rerank_does_not_mutate_input(mock_load: MagicMock) -> None:
    mock_load.return_value.predict.return_value = np.array([0.9, 0.1])
    from app.rerank import rerank

    docs = [_doc("1", "a", score=0.5), _doc("2", "b", score=0.5)]
    rerank("mock", "q", docs, top_n=2)
    # Input objects are Pydantic models (immutable by default) — verify ids unchanged
    assert docs[0].id == "1"
    assert docs[1].id == "2"
    assert docs[0].score == 0.5  # original score preserved
