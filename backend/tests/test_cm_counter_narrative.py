"""Unit tests for backend.nlp.cm.counter_narrative cite-ID guardrail."""
from __future__ import annotations

from backend.nlp.cm.counter_narrative import (
    TalkingPoint,
    _format_chunks,
    _validate_cites,
)


def test_format_chunks_stringifies_uuid_ids() -> None:
    rendered, ids, kinds = _format_chunks(
        [
            {"id": "11111111-1111-1111-1111-111111111111", "kind": "article", "text": "First fact"},
            {"id": None, "kind": "article", "text": "skipped because no id"},
            {"id": "22222222-2222-2222-2222-222222222222", "kind": "govt_document", "text": "Second fact"},
        ]
    )
    assert ids == [
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
    ]
    assert kinds == ["article", "govt_document"]
    assert "[11111111-1111-1111-1111-111111111111]" in rendered
    assert "skipped" not in rendered


def test_validate_cites_rejects_unknown_id() -> None:
    points = [TalkingPoint("First", ["uuid-a", "uuid-b"]), TalkingPoint("Second", ["uuid-c"])]
    assert _validate_cites(points, {"uuid-a", "uuid-b"}) is False
    assert _validate_cites(points, {"uuid-a", "uuid-b", "uuid-c"}) is True


def test_validate_cites_rejects_empty_cites() -> None:
    points = [TalkingPoint("Has no cite", [])]
    assert _validate_cites(points, {"uuid-a"}) is False


def test_validate_cites_accepts_no_points() -> None:
    assert _validate_cites([], {"uuid-a"}) is True
