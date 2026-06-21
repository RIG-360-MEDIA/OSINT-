"""Unit tests for query rewriting (LLM mocked)."""
from __future__ import annotations

from app.rewrite import rewrite_query


class _LLM:
    def __init__(self, out):
        self._out = out

    def complete(self, system, user):
        return self._out

    def chat(self, messages, tools=None):
        return None


def test_parses_lines():
    llm = _LLM("India semiconductor policy\nIndian AI startup funding\nTelangana IT sector")
    assert rewrite_query(llm, "tech in india") == [
        "India semiconductor policy", "Indian AI startup funding", "Telangana IT sector",
    ]


def test_strips_numbering_and_bullets():
    llm = _LLM("1. India chips\n- AI funding\n* IT jobs")
    assert rewrite_query(llm, "tech") == ["India chips", "AI funding", "IT jobs"]


def test_drops_original_and_dupes():
    llm = _LLM("tech\nIndia tech\nIndia tech\nAI India")
    assert rewrite_query(llm, "tech") == ["India tech", "AI India"]


def test_caps_at_n():
    llm = _LLM("a\nb\nc\nd\ne")
    assert len(rewrite_query(llm, "x", n=3)) == 3


def test_degrades_on_error():
    class _Bad:
        def complete(self, s, u):
            raise RuntimeError("boom")

    assert rewrite_query(_Bad(), "x") == []
