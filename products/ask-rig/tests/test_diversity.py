"""Unit tests for the diversity pipeline — all pure functions, no I/O."""
from __future__ import annotations

from collections import Counter

import pytest

from app.diversity import assemble, facet_quota, mmr_select, semantic_dedup
from app.schemas import RetrievedDoc


def _doc(
    doc_id: str,
    title: str,
    source_id: str = "src1",
    score: float = 1.0,
    snippet: str = "",
) -> RetrievedDoc:
    return RetrievedDoc(
        id=doc_id,
        title=title,
        snippet=snippet,
        url=None,
        published_at=None,
        source_id=source_id,
        language="en",
        score=score,
        vec_rank=None,
        lex_rank=None,
    )


# ---- semantic_dedup -------------------------------------------------------

def test_dedup_removes_near_duplicate() -> None:
    a = _doc("1", "Farmer loan waiver Telangana 2024 scheme")
    b = _doc("2", "Farmer loan waiver Telangana 2024 scheme update")
    result = semantic_dedup([a, b], threshold=0.5)
    assert len(result) == 1
    assert result[0].id == "1"  # higher-scored kept


def test_dedup_keeps_dissimilar() -> None:
    a = _doc("1", "Hyderabad metro rail expansion plan Phase 2")
    b = _doc("2", "Farmer loan waiver Telangana budget announcement")
    assert len(semantic_dedup([a, b], threshold=0.65)) == 2


def test_dedup_empty() -> None:
    assert semantic_dedup([]) == []


def test_dedup_single() -> None:
    doc = _doc("1", "Some headline about politics")
    assert semantic_dedup([doc]) == [doc]


def test_dedup_does_not_mutate_input() -> None:
    docs = [_doc("1", "identical headline"), _doc("2", "identical headline")]
    original = list(docs)
    semantic_dedup(docs, threshold=0.9)
    assert docs == original


# ---- mmr_select -----------------------------------------------------------

def test_mmr_returns_top_n() -> None:
    docs = [_doc(str(i), f"unique headline number {i}", score=1.0 / (i + 1)) for i in range(10)]
    assert len(mmr_select(docs, top_n=5)) == 5


def test_mmr_capped_at_input_length() -> None:
    docs = [_doc("1", "one thing"), _doc("2", "two things")]
    assert len(mmr_select(docs, top_n=10)) == 2


def test_mmr_diversity_promotes_different_doc() -> None:
    # Three near-identical high-score docs + one distinct lower-score doc.
    # With λ=0.5, diversity should pull in the outlier over a 3rd copy.
    identical = [
        _doc(str(i), "Telangana farmer loan waiver government announcement", score=0.9 - i * 0.05)
        for i in range(3)
    ]
    outlier = _doc("99", "Hyderabad metro rail Phase 2 inauguration", score=0.6)
    result = mmr_select(identical + [outlier], top_n=3, lam=0.5)
    assert "99" in [d.id for d in result]


def test_mmr_empty() -> None:
    assert mmr_select([], top_n=5) == []


def test_mmr_preserves_doc_identity() -> None:
    docs = [_doc(str(i), f"article {i}", score=float(i)) for i in range(5)]
    result = mmr_select(docs, top_n=3)
    assert all(d.id in {str(i) for i in range(5)} for d in result)


# ---- facet_quota ----------------------------------------------------------

def test_quota_limits_per_source() -> None:
    docs = [_doc(str(i), f"article {i}", source_id="ndtv") for i in range(5)]
    result = facet_quota(docs, max_per_source=2)
    assert len(result) == 2


def test_quota_multiple_sources() -> None:
    docs = [
        _doc("1", "A1", source_id="hindu"),
        _doc("2", "A2", source_id="hindu"),
        _doc("3", "A3", source_id="hindu"),
        _doc("4", "B1", source_id="ndtv"),
        _doc("5", "B2", source_id="ndtv"),
    ]
    counts = Counter(d.source_id for d in facet_quota(docs, max_per_source=2))
    assert counts["hindu"] == 2
    assert counts["ndtv"] == 2


def test_quota_preserves_order() -> None:
    docs = [_doc(str(i), f"art {i}", source_id="src_a" if i < 3 else "src_b") for i in range(6)]
    result = facet_quota(docs, max_per_source=2)
    assert [d.id for d in result] == ["0", "1", "3", "4"]


# ---- assemble -------------------------------------------------------------

def test_assemble_bookends() -> None:
    docs = [_doc(str(i), f"doc {i}", score=1.0 - i * 0.1) for i in range(5)]
    result = assemble(docs)
    assert result[0].id == "0"   # best first
    assert result[-1].id == "1"  # 2nd-best last


def test_assemble_short_unchanged() -> None:
    docs = [_doc("1", "a"), _doc("2", "b")]
    assert assemble(docs) == docs


def test_assemble_preserves_all() -> None:
    docs = [_doc(str(i), f"doc {i}") for i in range(6)]
    result = assemble(docs)
    assert len(result) == 6
    assert {d.id for d in result} == {d.id for d in docs}
