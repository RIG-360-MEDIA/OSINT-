"""Unit tests for youtube_v2 quality gates.

These pin the anti-sin behaviour from the clips audits: filler/empty/non-English
summaries, non-canonical entities, and fake timestamps must all be rejected.
"""
import pytest

from backend.collectors.youtube_v2.quality import (
    RejectReason,
    build_canonical_lookup,
    canonicalize_entity,
    is_empty_text,
    is_filler_summary,
    is_probably_english,
    latin_ratio,
    validate_timestamps,
)


# ── empty / filler ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", ["", "   ", None, "। । ।", "...", "—", "_ _"])
def test_empty_text_rejected(text):
    assert is_empty_text(text) is True


@pytest.mark.parametrize("text", ["KCR announced a scheme", "15 crore allocated"])
def test_real_text_not_empty(text):
    assert is_empty_text(text) is False


@pytest.mark.parametrize(
    "summary",
    [
        "too short to summarise",
        "Opening clip…",
        "Clip around KCR at 0:00",
        "0:00",
        "N/A",
        "no transcript",
        "short",          # below min length
        "",
        "। । ।",
    ],
)
def test_filler_summaries_rejected(summary):
    assert is_filler_summary(summary) is True


@pytest.mark.parametrize(
    "summary",
    [
        "KCR announced a new irrigation scheme for the district.",
        "Revanth Reddy criticised the opposition over land allotment.",
    ],
)
def test_real_summaries_pass(summary):
    assert is_filler_summary(summary) is False


# ── English / script ──────────────────────────────────────────────────────────

def test_telugu_summary_rejected():
    telugu = "జిల్లాలో 19.38 ఎకరాల వ్యవసాయ భూములను గుర్తించినట్లు తెలిపారు"
    assert is_probably_english(telugu) is False


def test_devanagari_summary_rejected():
    assert is_probably_english("केसीआर ने एक नई योजना की घोषणा की") is False


def test_english_with_numbers_and_punct_passes():
    assert is_probably_english("KCR allocated 15 crore (₹) for 19.38 acres.") is True


def test_latin_ratio_bounds():
    assert latin_ratio("hello world") == 1.0
    assert latin_ratio("12345 !!!") == 1.0   # no letters → treated as latin
    assert latin_ratio("జిల్లా") == 0.0


# ── canonical entity ──────────────────────────────────────────────────────────

def test_canonicalize_exact_and_case_insensitive():
    lookup = build_canonical_lookup(["K. Chandrashekar Rao", "Revanth Reddy"])
    assert canonicalize_entity("revanth reddy", lookup) == "Revanth Reddy"
    assert canonicalize_entity("K. Chandrashekar Rao", lookup) == "K. Chandrashekar Rao"


def test_hallucinated_entity_rejected():
    lookup = build_canonical_lookup(["Revanth Reddy"])
    assert canonicalize_entity("Some Random Person", lookup) is None
    assert canonicalize_entity("", lookup) is None
    assert canonicalize_entity(None, lookup) is None


# ── timestamps ────────────────────────────────────────────────────────────────

def test_valid_timestamp():
    assert validate_timestamps(120, 150, video_duration=600) is True


@pytest.mark.parametrize(
    "start,end,dur",
    [
        (0, 0, 600),       # zero-length
        (150, 120, 600),   # end before start
        (-5, 30, 600),     # negative start
        (10, 11, 600),     # sub-2s span
        (700, 730, 600),   # beyond video duration
    ],
)
def test_invalid_timestamps_rejected(start, end, dur):
    assert validate_timestamps(start, end, video_duration=dur) is False


def test_reject_reason_enum_complete():
    # guards against accidental renames the metrics layer depends on
    assert RejectReason.NON_CANONICAL_ENTITY.value == "non_canonical_entity"
    assert RejectReason.NON_ENGLISH_SUMMARY.value == "non_english_summary"
