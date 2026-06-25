"""Unit tests for the one-shot turn router (LLM mocked)."""
from __future__ import annotations

import json

from app.router import Route, route_turn


class _LLM:
    def __init__(self, out):
        self._out = out

    def complete(self, system, user):
        return self._out

    def chat(self, messages, tools=None):
        return None

    def stream_messages(self, messages):
        yield ""


def _r(d):
    return route_turn(_LLM(json.dumps(d)), "q", [])


def test_synthesize_default():
    r = _r({"mode": "synthesize", "search_query": "latest Telangana", "query_type": "broad", "needs_web": True})
    assert r.mode == "synthesize" and r.search_query == "latest Telangana" and r.query_type == "broad"


def test_enumerate_fields():
    r = _r({"mode": "enumerate", "entity": "Telangana government", "since_hours": 24, "sentiment": "negative"})
    assert r.mode == "enumerate" and r.entity == "Telangana government" and r.since_hours == 24 and r.sentiment == "negative"


def test_enumerate_recent():
    r = _r({"mode": "enumerate", "recent": True})
    assert r.mode == "enumerate" and r.recent is True


def test_quantify_sentiment_trend():
    r = _r({"mode": "quantify", "entity": "X", "trend_days": 7, "metric": "sentiment"})
    assert r.mode == "quantify" and r.trend_days == 7 and r.metric == "sentiment"


def test_quantify_breakdown_and_chartkind():
    r = _r({"mode": "quantify", "entity": "X", "breakdown": "outlet", "chart_kind": "pie"})
    assert r.breakdown == "outlet" and r.chart_kind == "pie"


def test_dossier_days_clamped():
    r = _r({"mode": "dossier", "entity": "X", "days": 500})
    assert r.mode == "dossier" and r.days == 90


def test_bad_mode_falls_back_to_synthesize():
    r = _r({"mode": "nonsense"})
    assert r.mode == "synthesize"


def test_search_query_defaults_to_raw():
    r = route_turn(_LLM(json.dumps({"mode": "synthesize"})), "raw question", [])
    assert r.search_query == "raw question"


def test_languages_mapped():
    r = _r({"mode": "enumerate", "keyword": "metro", "languages": ["Telugu"]})
    assert r.languages == ("te",)


def test_needs_entity_requires_entity():
    r = _r({"mode": "synthesize", "needs_entity": True, "entity": None})
    assert r.needs_entity is False


def test_none_on_non_json():
    assert route_turn(_LLM("I think it's a list"), "q", []) is None


def test_none_on_llm_error():
    class _Bad:
        def complete(self, s, u):
            raise RuntimeError("boom")
    assert route_turn(_Bad(), "q", []) is None
