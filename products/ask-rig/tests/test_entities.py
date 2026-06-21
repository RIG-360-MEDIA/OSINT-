"""Unit tests for entity helpers (pure functions — no DB)."""
from __future__ import annotations

from app.entities import clean_entity_query, is_uuid, normalize_entity


def test_clean_extracts_name_from_sentence():
    assert clean_entity_query("Tell me top news about revanth reddy") == "revanth reddy"
    assert clean_entity_query("latest on KCR") == "kcr"
    assert clean_entity_query("show me news about Rythu Bharosa") == "rythu bharosa"


def test_clean_passes_through_plain_names():
    assert clean_entity_query("Narendra Modi") == "narendra modi"
    assert clean_entity_query("Modi government") == "modi government"


def test_clean_falls_back_when_all_filler():
    # all-filler input shouldn't collapse to empty
    assert clean_entity_query("latest news") != ""


def test_normalize_lowercases_and_trims() -> None:
    assert normalize_entity("  Narendra Modi  ") == "narendra modi"


def test_normalize_collapses_internal_whitespace() -> None:
    assert normalize_entity("K   Chandrashekar\tRao") == "k chandrashekar rao"


def test_normalize_already_clean() -> None:
    assert normalize_entity("revanth reddy") == "revanth reddy"


def test_is_uuid_accepts_valid() -> None:
    assert is_uuid("123e4567-e89b-12d3-a456-426614174000") is True


def test_is_uuid_rejects_garbage() -> None:
    assert is_uuid("not-a-uuid") is False
    assert is_uuid("") is False
    assert is_uuid("12345") is False


def test_is_uuid_rejects_sql_injection_attempt() -> None:
    # The endpoint relies on this to reject non-UUID path params before any query.
    assert is_uuid("'; DROP TABLE articles; --") is False
