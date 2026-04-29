"""Unit tests for backend.nlp.cm.stance — parsing only, no Groq calls."""
from __future__ import annotations

import pytest

from backend.nlp.cm.stance import VALID_LABELS, _parse


@pytest.mark.parametrize(
    "reply,expected_label,expected_conf",
    [
        ("ruling_supportive 0.92", "ruling_supportive", 0.92),
        ("opposition_attack 0.4", "opposition_attack", 0.4),
        ("neutral_factual", "neutral_factual", 0.6),
        ("MIXED 0.7", "mixed", 0.7),
        ("UNKNOWN 1.0", "unknown", 1.0),
        ("", "unknown", 0.0),
        ("not-a-label", "unknown", 0.0),
        ("opposition_attack 1.5", "opposition_attack", 1.0),
        # Negative confidence is malformed; regex skips it and we fall back to
        # the default 0.6 rather than treat the row as worthless.
        ("opposition_attack -0.3", "opposition_attack", 0.6),
    ],
)
def test_parse_known_replies(reply: str, expected_label: str, expected_conf: float) -> None:
    label, conf = _parse(reply)
    assert label == expected_label
    assert conf == pytest.approx(expected_conf, rel=1e-3)


def test_valid_labels_match_schema() -> None:
    assert VALID_LABELS == {
        "ruling_supportive",
        "opposition_attack",
        "neutral_factual",
        "mixed",
        "unknown",
    }
