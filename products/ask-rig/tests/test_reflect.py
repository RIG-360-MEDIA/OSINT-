"""Unit tests for the coverage-reflection step (LLM mocked). Focus: robust JSON
parsing, the sufficient/gaps coercion rules, and graceful degradation to None."""
from __future__ import annotations

import json

from app.reflect import Coverage, assess_coverage

HEADLINES = ["Telangana metro phase II approved", "Revanth Reddy on irrigation"]


class _LLM:
    def __init__(self, out):
        self._out = out

    def complete(self, system, user):
        return self._out

    def chat(self, messages, tools=None):
        return None

    def stream_messages(self, messages):
        yield ""


def _obj(**over):
    base = {"sufficient": False, "gaps": ["Telangana education budget"]}
    base.update(over)
    return json.dumps(base)


def test_parses_insufficient_with_gaps():
    v = assess_coverage(_LLM(_obj()), "latest across metro and education", HEADLINES)
    assert isinstance(v, Coverage)
    assert v.sufficient is False
    assert v.gaps == ["Telangana education budget"]


def test_sufficient_verdict_drops_gaps():
    # Even if the model contradicts itself, a sufficient verdict carries no gaps.
    v = assess_coverage(_LLM(_obj(sufficient=True, gaps=["something"])), "q", HEADLINES)
    assert v.sufficient is True and v.gaps == []


def test_insufficient_without_gaps_becomes_sufficient():
    # Insufficient but nothing actionable -> treat as sufficient (no useless round).
    v = assess_coverage(_LLM(_obj(sufficient=False, gaps=[])), "q", HEADLINES)
    assert v.sufficient is True and v.gaps == []


def test_gaps_capped_at_two():
    v = assess_coverage(_LLM(_obj(gaps=["a", "b", "c", "d"])), "q", HEADLINES)
    assert len(v.gaps) == 2


def test_gaps_deduped():
    v = assess_coverage(_LLM(_obj(gaps=["Same Topic", "same topic"])), "q", HEADLINES)
    assert v.gaps == ["Same Topic"]


def test_strips_markdown_fence():
    v = assess_coverage(_LLM("```json\n" + _obj() + "\n```"), "q", HEADLINES)
    assert v is not None and v.sufficient is False


def test_none_on_non_json():
    assert assess_coverage(_LLM("looks fine to me"), "q", HEADLINES) is None


def test_none_on_llm_error():
    class _Bad:
        def complete(self, s, u):
            raise RuntimeError("boom")

    assert assess_coverage(_Bad(), "q", HEADLINES) is None


def test_none_on_empty_inputs():
    assert assess_coverage(_LLM(_obj()), "q", []) is None
    assert assess_coverage(_LLM(_obj()), "   ", HEADLINES) is None
