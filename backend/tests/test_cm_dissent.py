"""Unit tests for backend.nlp.cm.dissent low-confidence behaviour."""
from __future__ import annotations

import json
from typing import Any

import pytest

from backend.nlp.cm import dissent


@pytest.mark.asyncio
async def test_compare_returns_none_for_same_speaker(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**_: Any) -> str:
        raise AssertionError("groq must not be called for same speaker")

    monkeypatch.setattr(dissent, "extract_json", _stub)
    out = await dissent.compare(
        issue_label="x",
        party="INC",
        speaker_a="Same Person",
        quote_a="A",
        speaker_b="same person",
        quote_b="B",
    )
    assert out is None


@pytest.mark.asyncio
async def test_compare_below_floor_marks_no_contradiction(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(*, system: str, user: str) -> str:
        return json.dumps(
            {
                "contradicts": True,
                "confidence": 0.2,  # below floor (0.55)
                "severity": "crack",
                "summary": "looks like disagreement",
            }
        )

    monkeypatch.setattr(dissent, "extract_json", _stub)
    out = await dissent.compare(
        issue_label="bond yields",
        party="INC",
        speaker_a="Leader A",
        quote_a="we will defend the policy",
        speaker_b="Leader B",
        quote_b="the policy needs reconsideration",
    )
    assert out is not None
    assert out.contradicts is False  # downgraded by floor


@pytest.mark.asyncio
async def test_compare_high_confidence_keeps_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(*, system: str, user: str) -> str:
        return json.dumps(
            {
                "contradicts": True,
                "confidence": 0.85,
                "severity": "crack",
                "summary": "open disagreement",
            }
        )

    monkeypatch.setattr(dissent, "extract_json", _stub)
    out = await dissent.compare(
        issue_label="x",
        party="INC",
        speaker_a="A",
        quote_a="x",
        speaker_b="B",
        quote_b="y",
    )
    assert out is not None
    assert out.contradicts is True
    assert out.severity == "crack"
