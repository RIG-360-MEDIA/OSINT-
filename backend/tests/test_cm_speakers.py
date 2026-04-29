"""Unit tests for backend.nlp.cm.speakers — validation + canonical resolution."""
from __future__ import annotations

from backend.nlp.cm.speakers import _resolve_canonical, _validate


def test_validate_drops_short_quotes() -> None:
    assert _validate({"speaker": "X", "quote": "too short"}) is None


def test_validate_drops_missing_speaker_or_quote() -> None:
    assert _validate({"speaker": "", "quote": "this is a long enough quote here"}) is None
    assert _validate({"speaker": "X Y", "quote": ""}) is None


def test_validate_normalises_invalid_stance() -> None:
    item = {
        "speaker": "Some Leader",
        "quote": "this is a long enough quote yeah",
        "stance": "made_up_label",
    }
    out = _validate(item)
    assert out is not None
    assert out.stance == "unknown"


def test_resolve_canonical_by_alias() -> None:
    edict = {
        "Revanth Reddy": {
            "party": "INC",
            "entity_type": "state",
            "aliases": ["Anumula Revanth Reddy", "Revanth"],
        },
    }
    canonical, party, role = _resolve_canonical("revanth", edict)
    assert canonical == "Revanth Reddy"
    assert party == "INC"
    assert role == "state"


def test_resolve_canonical_returns_none_when_no_match() -> None:
    canonical, party, role = _resolve_canonical("Unknown Speaker", {"X": {"aliases": []}})
    assert canonical is None
    assert party is None
    assert role is None
