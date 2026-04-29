"""Tests for the D-24 sentinel reject + D-25 political-relevance filter.

The audit (docs/qa/worldmonitor-audit-2026-04-28/06_content_quality.md)
found that:

  D-24: the LLM no-extraction sentinel "The article does not mention a
        specific named person" was being persisted as a `speaker` value.
  D-25: top speakers were dominated by cricketers, actors, judges, and
        industry analysts because there was no political-relevance gate.

These tests pin the fixes against regression.
"""
from __future__ import annotations

import pytest

from backend.nlp.cm.speakers import _looks_political, _validate


# ── D-24 ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "speaker",
    [
        "The article does not mention a specific named person",
        "the article does not mention a specific named person",
        "The article does not mention a specific named person.",
        '"The article does not mention a specific named person"',
        "no named speaker",
        "No specific named person",
        "Unknown",
        "Anonymous",
        "Officials",
        "Officials said",
        "Various",
        "N/A",
        "None",
        "Not mentioned",
        "the article author writes",  # any "the article …" prefix is suspect
    ],
)
def test_validate_drops_sentinel_speaker(speaker: str) -> None:
    record = {
        "speaker": speaker,
        "quote": "We will deliver every promise made in the manifesto.",
        "stance": "ruling_supportive",
    }
    assert _validate(record) is None


def test_validate_keeps_real_named_speaker() -> None:
    record = {
        "speaker": "Revanth Reddy",
        "quote": "We will deliver every promise made in the manifesto.",
        "stance": "ruling_supportive",
    }
    out = _validate(record)
    assert out is not None
    assert out.speaker == "Revanth Reddy"


# ── D-25 ──────────────────────────────────────────────────────────────────

def test_looks_political_passes_when_canonical_resolved() -> None:
    """Speakers matched against entity_dict are trusted regardless of role."""
    assert _looks_political({"speaker": "X", "role": "", "party": ""}, canonical="K T Rama Rao")


def test_looks_political_passes_on_political_role_keyword() -> None:
    assert _looks_political({"role": "Chief Minister"}, canonical=None)
    assert _looks_political({"role": "Cabinet Minister"}, canonical=None)
    assert _looks_political({"role": "MLA"}, canonical=None)
    assert _looks_political({"role": "Spokesperson"}, canonical=None)


def test_looks_political_passes_on_known_party_code() -> None:
    assert _looks_political({"party": "INC"}, canonical=None)
    assert _looks_political({"party": "BJP"}, canonical=None)
    assert _looks_political({"party": "BRS"}, canonical=None)
    assert _looks_political({"party": "AIMIM"}, canonical=None)


def test_looks_political_rejects_industry_analyst() -> None:
    """The Vamshi Karangula × 10 logistics-article case from the audit."""
    rec = {
        "speaker": "Vamshi Karangula",
        "role": "Industry Director",
        "party": "",
    }
    assert _looks_political(rec, canonical=None) is False


def test_looks_political_rejects_judge() -> None:
    rec = {"speaker": "Justice Sandeep Mehta", "role": "Judge", "party": ""}
    assert _looks_political(rec, canonical=None) is False


def test_looks_political_rejects_cricketer() -> None:
    rec = {"speaker": "Piyush Chawla", "role": "", "party": ""}
    assert _looks_political(rec, canonical=None) is False


def test_looks_political_rejects_actor() -> None:
    rec = {"speaker": "Sylvester Stallone", "role": "", "party": ""}
    assert _looks_political(rec, canonical=None) is False
