"""
Shared listing-page date parser for govt source adapters.

The government-document collection pipeline ships every row with
``published_at`` so downstream ranking, recency filters, and the
``since_days`` gate can do their job. Until this helper landed, every
adapter wrote ``published_at = None`` (defect D-22), which made the
feed silently rank by ``collected_at`` instead.

Recognised formats (case-insensitive):

  - ISO 8601           ``2024-03-12``, ``2024-03-12T06:30:00Z``
  - dd-mm-yyyy         ``12-03-2024``  (and / . separators)
  - dd Mon yyyy        ``12 Mar 2024``, ``12 March 2024``
  - Mon dd, yyyy       ``Mar 12, 2024``, ``March 12 2024``
  - yyyy-mm-dd hh:mm   ``2024-03-12 06:30``
  - dated-X variants   ``Order dated 12.03.2024``,
                       ``Notification dated 12 March 2024``,
                       ``W.P. (C) 1234/2024``  (year only — January 1 fallback)

Returns timezone-aware UTC datetimes. Year-only matches default to
``Jan 1 00:00:00 UTC`` of that year and log at DEBUG so the gap is
visible.

Anything that fails to parse returns ``None`` — adapters then write
``published_at=None`` and the orchestrator logs a WARNING with the
adapter name so selector drift / new portal layouts surface.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Final

logger = logging.getLogger(__name__)


# Order matters: first match wins. Tighter / less-ambiguous patterns first.
_PATTERNS: Final[list[tuple[re.Pattern[str], str]]] = [
    # ISO 8601 with optional time and Z/offset
    (
        re.compile(
            r"\b(\d{4}-\d{2}-\d{2})"
            r"(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+\-]\d{2}:?\d{2})?)?\b"
        ),
        "iso",
    ),
    # dd Mon yyyy (1-2 digit day, full or short month, 4-digit year)
    (
        re.compile(
            r"\b(\d{1,2})\s+"
            r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
            r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|"
            r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
            r"[,\s]+(\d{4})\b",
            re.IGNORECASE,
        ),
        "dmy_named",
    ),
    # Mon dd, yyyy (named month first)
    (
        re.compile(
            r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
            r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|"
            r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+"
            r"(\d{1,2})[,\s]+(\d{4})\b",
            re.IGNORECASE,
        ),
        "mdy_named",
    ),
    # dd-mm-yyyy / dd/mm/yyyy / dd.mm.yyyy
    (
        re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b"),
        "dmy_numeric",
    ),
    # bare 4-digit year — last-ditch fallback only
    (re.compile(r"\b(20\d{2})\b"), "year_only"),
]

_MONTHS: Final[dict[str, int]] = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_MIN_YEAR: Final[int] = 2000
_MAX_YEAR: Final[int] = datetime.now(timezone.utc).year + 1


def parse_listing_date(text: str | None) -> datetime | None:
    """Best-effort parse of a date out of unstructured listing text.

    Returns a timezone-aware UTC datetime, or ``None`` if no plausible
    date is found. Year-only matches return ``Jan 1`` of that year; the
    caller should log a WARNING so the gap is visible.
    """
    if not text:
        return None
    haystack = text.strip()
    if not haystack:
        return None

    for pattern, kind in _PATTERNS:
        m = pattern.search(haystack)
        if not m:
            continue
        try:
            dt = _build(kind, m)
        except (ValueError, KeyError):
            continue
        if dt is None:
            continue
        if not (_MIN_YEAR <= dt.year <= _MAX_YEAR):
            continue
        return dt
    return None


def _build(kind: str, m: re.Match[str]) -> datetime | None:
    if kind == "iso":
        dt = datetime.fromisoformat(m.group(0).replace("Z", "+00:00"))
        # `astimezone` on a naive datetime does a local-time conversion
        # that fails with OSError on some Windows builds. Treat naive
        # ISO strings as already-UTC to avoid that path entirely.
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    if kind == "dmy_named":
        d, mon_str, y = m.group(1), m.group(2).lower(), m.group(3)
        return datetime(int(y), _MONTHS[mon_str], int(d), tzinfo=timezone.utc)

    if kind == "mdy_named":
        mon_str, d, y = m.group(1).lower(), m.group(2), m.group(3)
        return datetime(int(y), _MONTHS[mon_str], int(d), tzinfo=timezone.utc)

    if kind == "dmy_numeric":
        d, mo, y = m.group(1), m.group(2), m.group(3)
        # Reject impossible combos rather than swap day/month silently.
        di, moi, yi = int(d), int(mo), int(y)
        if not (1 <= di <= 31 and 1 <= moi <= 12):
            return None
        return datetime(yi, moi, di, tzinfo=timezone.utc)

    if kind == "year_only":
        y = int(m.group(1))
        logger.debug("date parser fell through to year-only on %r", m.string)
        return datetime(y, 1, 1, tzinfo=timezone.utc)

    return None
