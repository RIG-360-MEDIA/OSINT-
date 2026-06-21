"""Unit tests for the faithfulness scorer — the LLM judge is mocked."""
from __future__ import annotations

import json

from eval.faithfulness import score_faithfulness
from app.schemas import RetrievedDoc


def _doc(doc_id: str = "1", title: str = "headline", snippet: str = "body") -> RetrievedDoc:
    return RetrievedDoc(
        id=doc_id, title=title, snippet=snippet, url=None, published_at=None,
        source_id="s", language="en", score=1.0, vec_rank=None, lex_rank=None,
    )


class _Judge:
    """Stub LLMProvider returning a canned completion."""

    def __init__(self, payload: str) -> None:
        self._payload = payload

    def complete(self, system: str, user: str) -> str:
        return self._payload


def test_all_supported_scores_one() -> None:
    judge = _Judge(json.dumps({"claims": [
        {"claim": "a", "supported": True},
        {"claim": "b", "supported": True},
    ]}))
    r = score_faithfulness(judge, "Some answer [S1].", [_doc()])
    assert r.score == 1.0
    assert r.n_claims == 2 and r.n_supported == 2 and r.parsed


def test_partial_support() -> None:
    judge = _Judge(json.dumps({"claims": [
        {"claim": "a", "supported": True},
        {"claim": "b", "supported": False},
        {"claim": "c", "supported": False},
    ]}))
    r = score_faithfulness(judge, "answer [S1]", [_doc()])
    assert abs(r.score - 1 / 3) < 1e-6
    assert r.n_supported == 1 and r.n_claims == 3


def test_refusal_is_faithful_without_calling_judge() -> None:
    called = {"n": 0}

    class _Counting(_Judge):
        def complete(self, system: str, user: str) -> str:
            called["n"] += 1
            return "{}"

    judge = _Counting("{}")
    r = score_faithfulness(judge, "The corpus doesn't have enough on this yet.", [_doc()])
    assert r.score == 1.0 and r.n_claims == 0
    assert called["n"] == 0  # refusal short-circuits before the judge call


def test_empty_answer_is_faithful() -> None:
    r = score_faithfulness(_Judge("{}"), "", [_doc()])
    assert r.score == 1.0 and r.parsed


def test_unparseable_judge_output_flags_parsed_false() -> None:
    r = score_faithfulness(_Judge("not json at all"), "answer [S1]", [_doc()])
    assert r.parsed is False and r.score == 0.0


def test_judge_json_embedded_in_prose() -> None:
    payload = 'Sure! Here is my verdict: {"claims":[{"claim":"x","supported":true}]} done.'
    r = score_faithfulness(_Judge(payload), "answer [S1]", [_doc()])
    assert r.parsed and r.score == 1.0 and r.n_claims == 1


def test_zero_claims_scores_one() -> None:
    r = score_faithfulness(_Judge(json.dumps({"claims": []})), "answer [S1]", [_doc()])
    assert r.score == 1.0 and r.n_claims == 0
