"""Unit tests for the chat planner (LLM mocked). Focus: robust JSON parsing,
coercion to a safe Plan, and graceful degradation to None."""
from __future__ import annotations

import json

from app.planner import Plan, plan_turn


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
    base = {
        "search_query": "Telangana news",
        "query_type": "broad",
        "is_followup": False,
        "needs_web": True,
        "needs_entity": False,
        "entity": None,
        "variants": ["Telangana politics", "Telangana economy"],
    }
    base.update(over)
    return json.dumps(base)


def test_parses_clean_json():
    p = plan_turn(_LLM(_obj()), "latest in telangana")
    assert isinstance(p, Plan)
    assert p.search_query == "Telangana news"
    assert p.query_type == "broad"
    assert p.needs_web is True
    assert p.variants == ["Telangana politics", "Telangana economy"]


def test_strips_markdown_fence():
    p = plan_turn(_LLM("```json\n" + _obj() + "\n```"), "x")
    assert p is not None and p.search_query == "Telangana news"


def test_ignores_prose_around_json():
    raw = "Sure, here is the plan:\n" + _obj(search_query="India US trade") + "\nHope that helps!"
    p = plan_turn(_LLM(raw), "trade talks")
    assert p is not None and p.search_query == "India US trade"


def test_queries_dedupes_search_query_and_variants():
    raw = _obj(search_query="metro", variants=["metro", "Metro", "metro cost"])
    p = plan_turn(_LLM(raw), "metro")
    assert p.queries == ["metro", "metro cost"]


def test_entity_requires_both_flag_and_name():
    # needs_entity true but no name -> entity dropped, needs_entity false
    p = plan_turn(_LLM(_obj(needs_entity=True, entity=None)), "x")
    assert p.needs_entity is False and p.entity is None
    # both present -> kept
    p2 = plan_turn(_LLM(_obj(needs_entity=True, entity="Revanth Reddy")), "x")
    assert p2.needs_entity is True and p2.entity == "Revanth Reddy"


def test_invalid_query_type_falls_back_to_specific():
    p = plan_turn(_LLM(_obj(query_type="nonsense")), "x")
    assert p.query_type == "specific"


def test_variants_capped_at_three():
    raw = _obj(variants=["a", "b", "c", "d", "e"])
    p = plan_turn(_LLM(raw), "x")
    assert len(p.variants) == 3


def test_empty_search_query_falls_back_to_raw():
    p = plan_turn(_LLM(_obj(search_query="")), "raw question")
    assert p is not None and p.search_query == "raw question"


def test_degrades_on_non_json():
    assert plan_turn(_LLM("I cannot help with that."), "x") is None


def test_degrades_on_llm_error():
    class _Bad:
        def complete(self, s, u):
            raise RuntimeError("boom")

    assert plan_turn(_Bad(), "x") is None


def test_degrades_on_empty_query():
    assert plan_turn(_LLM(_obj()), "   ") is None


def test_followup_history_passed_through():
    # The planner should at least run with history present and resolve a standalone query.
    raw = _obj(search_query="Revanth Reddy metro", is_followup=True, query_type="followup")
    history = [
        {"role": "user", "content": "who is Revanth Reddy"},
        {"role": "assistant", "content": "He is the CM of Telangana."},
    ]
    p = plan_turn(_LLM(raw), "what about the metro?", history)
    assert p.is_followup is True and p.search_query == "Revanth Reddy metro"
