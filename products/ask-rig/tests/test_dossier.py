"""Unit tests for dossier request parsing + prompt building (DB gather is integration)."""
from __future__ import annotations

import json

from app.dossier import Dossier, build_dossier_prompt, parse_dossier_request
from app.enumerate import ListItem


class _LLM:
    def __init__(self, out):
        self._out = out

    def complete(self, system, user):
        return self._out

    def chat(self, messages, tools=None):
        return None

    def stream_messages(self, messages):
        yield ""


def test_parses_dossier():
    r = parse_dossier_request(_LLM(json.dumps({"is_dossier": True, "entity": "Revanth Reddy", "days": None})),
                              "give me a full dossier on Revanth Reddy")
    assert r == ("Revanth Reddy", 30)  # default window


def test_parses_custom_window_clamped():
    r = parse_dossier_request(_LLM(json.dumps({"is_dossier": True, "entity": "X", "days": 400})), "everything on X")
    assert r[1] == 90  # clamped to max


def test_not_a_dossier():
    assert parse_dossier_request(_LLM(json.dumps({"is_dossier": False})), "what's the latest on X") is None


def test_dossier_without_entity_none():
    assert parse_dossier_request(_LLM(json.dumps({"is_dossier": True, "entity": None})), "dossier") is None


def test_degrades_on_error():
    class _Bad:
        def complete(self, s, u):
            raise RuntimeError("boom")
    assert parse_dossier_request(_Bad(), "dossier on X") is None


def _item(title):
    from datetime import datetime
    return ListItem(id="a1", title=title, url=None, published_at=datetime(2026, 6, 24),
                    language="en", source_id="s", snippet=None)


def test_prompt_includes_all_sections_data():
    d = Dossier(subject="Revanth Reddy", days=30, total=1101, prev_total=900,
                recent=[_item("Metro update")], quotes=['We will deliver.'],
                co_mentions=[("BRS", 209)], languages=[("te", 712), ("en", 300)])
    p = build_dossier_prompt(d)
    assert "Revanth Reddy" in p and "1101" in p and "change +201" in p
    assert "[S1]" in p and "Metro update" in p          # recent headline cited
    assert "We will deliver." in p                       # quote
    assert "BRS (209)" in p                              # co-mention
    assert "TE=712" in p                                 # language spread
