"""Unit tests for enumerate mode (LLM mocked): request parsing + sentiment classify."""
from __future__ import annotations

import json

from app.enumerate import ListRequest, classify_list_sentiment, parse_list_request


class _LLM:
    def __init__(self, out):
        self._out = out

    def complete(self, system, user):
        return self._out

    def chat(self, messages, tools=None):
        return None

    def stream_messages(self, messages):
        yield ""


def _plan(**over):
    base = {"is_list": True, "entity": "Revanth Reddy", "keyword": None,
            "since_hours": 24, "sentiment": None, "languages": None, "limit": None}
    base.update(over)
    return json.dumps(base)


def test_parses_basic_list():
    r = parse_list_request(_LLM(_plan()), "give me all articles about Revanth Reddy in 24h")
    assert isinstance(r, ListRequest)
    assert r.entity_term == "Revanth Reddy" and r.since_hours == 24 and r.sentiment is None


def test_parses_sentiment_and_window():
    r = parse_list_request(_LLM(_plan(entity="Telangana government", sentiment="negative")),
                           "all negative news about the Telangana govt today")
    assert r.entity_term == "Telangana government" and r.sentiment == "negative"


def test_maps_language_names():
    r = parse_list_request(_LLM(_plan(keyword="Hyderabad metro", entity=None, languages=["telugu"])), "x")
    assert r.languages == ("te",) and r.keyword == "Hyderabad metro"


def test_not_a_list_returns_none():
    assert parse_list_request(_LLM(json.dumps({"is_list": False})), "what is the latest") is None


def test_list_without_subject_returns_none():
    # is_list true but no entity AND no keyword -> nothing to list
    assert parse_list_request(_LLM(_plan(entity=None, keyword=None)), "list all") is None


def test_bad_sentiment_dropped():
    r = parse_list_request(_LLM(_plan(sentiment="angry")), "x")
    assert r.sentiment is None  # only negative/positive allowed


def test_degrades_on_non_json():
    assert parse_list_request(_LLM("sure, here you go"), "list all about X") is None


def test_degrades_on_llm_error():
    class _Bad:
        def complete(self, s, u):
            raise RuntimeError("boom")
    assert parse_list_request(_Bad(), "list all about X") is None


# ---- sentiment classifier ----
class _Item:
    def __init__(self, title):
        self.title = title
        self.snippet = ""


def test_classify_keeps_matching():
    items = [_Item("Govt praised for scheme"), _Item("Scandal hits minister"), _Item("Routine update")]
    kept, applied = classify_list_sentiment(
        _LLM('["positive","negative","neutral"]'), items, "negative")
    assert applied is True
    assert [i.title for i in kept] == ["Scandal hits minister"]


def test_classify_degrades_to_all_on_bad_output():
    items = [_Item("a"), _Item("b")]
    kept, applied = classify_list_sentiment(_LLM("not json"), items, "negative")
    assert applied is False and kept == items  # never silently drop everything


def test_classify_noop_without_want():
    items = [_Item("a")]
    kept, applied = classify_list_sentiment(_LLM("[]"), items, "neutral")
    assert applied is False and kept == items
