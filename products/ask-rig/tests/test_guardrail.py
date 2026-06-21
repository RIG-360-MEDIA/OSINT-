import pytest

from app.answer import (
    strip_invalid_markers,
    to_citations,
    used_markers,
    validate_citations,
)
from app.schemas import RetrievedDoc

pytestmark = pytest.mark.unit


def _docs(n: int) -> list[RetrievedDoc]:
    return [
        RetrievedDoc(
            id=str(i),
            title=f"title {i}",
            snippet="snippet",
            url=f"http://example/{i}",
            published_at=None,
            source_id=None,
            language="en",
            score=1.0,
            vec_rank=i,
            lex_rank=None,
        )
        for i in range(1, n + 1)
    ]


def test_used_markers_dedup_and_sort():
    assert used_markers("Foo [S2]. Bar [S1][S2].") == [1, 2]


def test_valid_citations_pass():
    faithful, invalid = validate_citations("X [S1]. Y [S2].", 3)
    assert faithful and invalid == []


def test_out_of_range_citation_flagged():
    faithful, invalid = validate_citations("Claim [S5].", 3)
    assert not faithful and invalid == [5]


def test_no_citation_is_unfaithful():
    faithful, invalid = validate_citations("A confident claim with no source.", 3)
    assert not faithful and invalid == []


def test_explicit_refusal_is_faithful():
    faithful, _ = validate_citations("The corpus doesn't have enough on this yet.", 3)
    assert faithful


def test_strip_invalid_markers_removes_only_bad():
    assert strip_invalid_markers("A [S1] B [S9] C", 3) == "A [S1] B  C"


def test_to_citations_maps_to_docs():
    cites = to_citations("Answer [S2].", _docs(3))
    assert len(cites) == 1
    assert cites[0].doc_id == "2" and cites[0].marker == "S2"
