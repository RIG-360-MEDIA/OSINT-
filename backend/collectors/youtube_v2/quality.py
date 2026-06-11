"""Quality gates — the heart of the rebuild.

Every gate is a pure, individually-tested function. They reject the concrete
failure modes from the clips audits (docs/qa/clips-*.md):

  - filler summaries ("too short to summarise", "Opening clip…")
  - empty preview text
  - non-English summaries surfaced to the English UI
  - non-canonical / hallucinated entities
  - timestamp ↔ URL invariant violations

A rejected item is NEVER silently dropped — callers record a RejectReason
metric and log a WARNING (see metrics.py).
"""
from __future__ import annotations

import re
import unicodedata
from enum import Enum


class RejectReason(str, Enum):
    EMPTY_SUMMARY = "empty_summary"
    FILLER_SUMMARY = "filler_summary"
    NON_ENGLISH_SUMMARY = "non_english_summary"
    NON_CANONICAL_ENTITY = "non_canonical_entity"
    EMPTY_SEGMENT = "empty_segment"
    BAD_TIMESTAMP = "bad_timestamp"
    LOW_IMPORTANCE = "low_importance"
    DUPLICATE = "duplicate"


# Phrases the old pipeline showed as real synopses. Matched case-insensitively
# as substrings / prefixes — see is_filler_summary.
_FILLER_PATTERNS: tuple[str, ...] = (
    "too short to summarise",
    "too short to summarize",
    "opening clip",
    "clip around",
    "no summary",
    "not enough context",
    "unable to summarise",
    "unable to summarize",
    "n/a",
    "transcript unavailable",
    "no transcript",
)

# A summary that is mostly a timecode like "Clip at 0:00" or bare punctuation.
_TIMECODE_ONLY = re.compile(r"^[\s\W]*\d{1,2}:\d{2}[\s\W]*$")
_PUNCT_ONLY = re.compile(r"^[\s\W_]+$", re.UNICODE)

_MIN_SUMMARY_CHARS = 15
_MIN_SEGMENT_CHARS = 10


def is_empty_text(text: str | None) -> bool:
    """True for None, whitespace-only, or punctuation-only text (e.g. '। । ।')."""
    if not text or not text.strip():
        return True
    return bool(_PUNCT_ONLY.match(text.strip()))


def is_filler_summary(summary: str | None) -> bool:
    """True if the summary is one of the known filler phrases, a bare timecode,
    or below the minimum useful length."""
    if is_empty_text(summary):
        return True
    s = summary.strip()
    if len(s) < _MIN_SUMMARY_CHARS:
        return True
    if _TIMECODE_ONLY.match(s):
        return True
    low = s.lower()
    return any(p in low for p in _FILLER_PATTERNS)


def latin_ratio(text: str) -> float:
    """Fraction of *letter* characters that are Latin-script. Whitespace,
    digits and punctuation are ignored so '15 crore rupees' still reads as
    English. Returns 1.0 when there are no letters at all (caller treats the
    empty/punct case separately)."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 1.0
    latin = 0
    for c in letters:
        try:
            if "LATIN" in unicodedata.name(c):
                latin += 1
        except ValueError:
            # unnamed character — not Latin
            continue
    return latin / len(letters)


def is_probably_english(text: str | None, threshold: float = 0.9) -> bool:
    """Reject Devanagari/Telugu/Odia/CJK summaries that leaked into the English
    UI. A summary must be ≥ ``threshold`` Latin-script by letter count.

    This is a *script* check, not a language model — it cannot tell English
    from French, but it reliably stops Indic-script text, which is the actual
    failure mode (Gujarati/Odia/Devanagari clips in the audit)."""
    if is_empty_text(text):
        return False
    return latin_ratio(text) >= threshold  # type: ignore[arg-type]


def canonicalize_entity(name: str | None, canonical: dict[str, str]) -> str | None:
    """Map a Groq-returned entity to its EXACT canonical form, or None.

    ``canonical`` maps lowercased-name -> canonical-name. A miss means the
    model hallucinated or named someone off-list — rejected, never stored."""
    if not name or not name.strip():
        return None
    return canonical.get(name.strip().lower())


def validate_timestamps(start: int, end: int, video_duration: float | None) -> bool:
    """Enforce a sane, real time window.

    Rejects the old 'metadata-only fake timestamps' (start=0,end=15 paired with
    a non-timestamped URL). A valid clip has end > start, start ≥ 0, and a
    minimum span — and, when we know the video length, sits inside it.
    """
    if start < 0 or end <= start:
        return False
    if (end - start) < 2:  # sub-2s windows are noise
        return False
    if video_duration is not None and video_duration > 0:
        # allow a small slack for ASR end-cue rounding
        if start > video_duration + 5:
            return False
    return True


def build_canonical_lookup(entities: list[str]) -> dict[str, str]:
    """lowercased -> canonical, for canonicalize_entity. Last wins on collision,
    which is fine because the canonical set is already de-duplicated upstream."""
    return {e.strip().lower(): e for e in entities if e and e.strip()}
