"""embed_guard.py — Pre-flight validation for LaBSE embedding inputs.

Wraps `generate_embedding()` callers so we don't feed the embedder:
  - Empty strings or strings < 100 chars (would collapse to a default vector)
  - Known boilerplate prefixes (subscribe banners, "click to read more" etc.)
  - Pure title text that's < 50 chars

Returns:
  - None if the input should be SKIPPED (caller should leave labse_embedding=NULL)
  - The cleaned text string otherwise

Why: the audit found 8,815 articles share collapsed/identical embeddings.
Root cause investigation showed many of them had only boilerplate text
passed to LaBSE. This guard prevents the pattern from recurring.
"""
from __future__ import annotations

import re
from typing import Optional

MIN_INPUT_LEN = 100  # match generate_embedding's internal minimum

# Boilerplate fingerprints — if the *first 200 chars* match any of these,
# we either trim them or skip embed entirely.
BOILERPLATE_PREFIXES: tuple[str, ...] = (
    "share this article",
    "click here to read",
    "subscribe to our newsletter",
    "follow us on",
    "support our journalism",
    "this content is for subscribers",
    "you must be logged in",
    "javascript is required",
    "please enable cookies",
    "by continuing to use",
    "we use cookies",
    "your browser is out of date",
)

# Common content-empty patterns: just timestamps, dates, or single-line metadata
_EMPTY_PATTERNS = [
    re.compile(r"^[\s\d:/.\-]+$"),                       # pure dates/times
    re.compile(r"^By\s+[A-Z][\w\s]+\s*$"),                # just a byline
    re.compile(r"^Updated\s+\d", re.IGNORECASE),          # "Updated 5 hours ago"
]


def _strip_boilerplate(text: str) -> str:
    """Trim leading boilerplate prefix if found."""
    lower = text[:200].lower()
    for prefix in BOILERPLATE_PREFIXES:
        idx = lower.find(prefix)
        if idx != -1 and idx < 100:
            # Skip past this boilerplate sentence
            after = text[idx + len(prefix):]
            # Skip the rest of that sentence too
            end = after.find(".")
            if 0 < end < 200:
                return after[end + 1:].strip()
            return after.strip()
    return text.strip()


def safe_embed_input(*candidates: Optional[str]) -> Optional[str]:
    """Pick the first valid embedding input from candidates.

    Pass body fields in priority order, e.g.:
        safe_embed_input(article.lead_text_translated,
                         article.full_text_scraped,
                         article.summary_executive)

    Returns the cleaned text, or None if none of the candidates qualify.
    """
    for raw in candidates:
        if not raw:
            continue
        cleaned = _strip_boilerplate(raw)
        # Reject empty-content patterns
        if any(p.match(cleaned) for p in _EMPTY_PATTERNS):
            continue
        # Reject too-short
        if len(cleaned) < MIN_INPUT_LEN:
            continue
        return cleaned[:5000]  # cap to keep encode batch reasonable
    return None
