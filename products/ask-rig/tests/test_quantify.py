"""Unit tests for quantify request parsing (LLM mocked)."""
from __future__ import annotations

import json

from app.quantify import CountRequest, parse_count_request


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
    base = {"is_count": True, "entity": "Revanth Reddy", "keyword": None,
            "since_hours": 168, "compare_prev": False, "trend_days": None,
            "sentiment": None, "languages": None}
    base.update(over)
    return json.dumps(base)


def test_parses_count_with_compare():
    r = parse_count_request(_LLM(_obj(compare_prev=True)), "how many about X this week vs last")
    assert isinstance(r, CountRequest)
    assert r.entity_term == "Revanth Reddy" and r.since_hours == 168 and r.compare_prev is True


def test_parses_trend():
    r = parse_count_request(_LLM(_obj(trend_days=30, since_hours=None)), "trend over 30 days")
    assert r.trend_days == 30


def test_parses_sentiment_count():
    r = parse_count_request(_LLM(_obj(sentiment="negative", compare_prev=True)),
                            "how many negative this week vs last")
    assert r.sentiment == "negative" and r.compare_prev is True


def test_not_a_count_returns_none():
    assert parse_count_request(_LLM(json.dumps({"is_count": False})), "what is the latest") is None


def test_no_subject_returns_none():
    assert parse_count_request(_LLM(_obj(entity=None, keyword=None)), "how many") is None


def test_bad_sentiment_dropped():
    r = parse_count_request(_LLM(_obj(sentiment="furious")), "how many furious")
    assert r.sentiment is None


def test_degrades_on_non_json():
    assert parse_count_request(_LLM("about 50 I think"), "how many about X") is None


def test_degrades_on_llm_error():
    class _Bad:
        def complete(self, s, u):
            raise RuntimeError("boom")
    assert parse_count_request(_Bad(), "how many about X") is None
