"""Tests for keep-all gating in youtube_v2.extraction._gate_clip.

Watchlist becomes a tag, not a gate: monitored subjects are canonicalised and
flagged is_watchlisted=True; off-watchlist newsworthy subjects are kept and
flagged False (keep_all); legacy mode still drops them.
"""
from __future__ import annotations

from backend.collectors.youtube_v2.extraction import _gate_clip
from backend.collectors.youtube_v2.quality import build_canonical_lookup

_CANON = build_canonical_lookup(["Revanth Reddy"])


class _Metrics:
    def record_reject(self, *a, **k):  # noqa: D401
        pass


def _clip(entity: str) -> dict:
    return {
        "entity": entity,
        "summary": "Revanth Reddy announced a new welfare scheme in Hyderabad today.",
        "start_seconds": 10,
        "end_seconds": 45,
        "importance": "medium",
    }


def test_watchlisted_subject_is_canonical_and_flagged():
    g = _gate_clip(_clip("Revanth Reddy"), _CANON, _Metrics(), keep_all=True)
    assert g is not None
    assert g.is_watchlisted is True
    assert g.entity == "Revanth Reddy"


def test_offlist_subject_kept_when_keep_all():
    g = _gate_clip(_clip("Sachin Tendulkar"), _CANON, _Metrics(), keep_all=True)
    assert g is not None
    assert g.is_watchlisted is False
    assert g.entity == "Sachin Tendulkar"


def test_offlist_subject_dropped_in_legacy_mode():
    g = _gate_clip(_clip("Sachin Tendulkar"), _CANON, _Metrics(), keep_all=False)
    assert g is None


def test_missing_subject_dropped_even_in_keep_all():
    g = _gate_clip(_clip(""), _CANON, _Metrics(), keep_all=True)
    assert g is None
