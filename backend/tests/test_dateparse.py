"""Tests for backend.collectors.sources._dateparse.parse_listing_date."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.collectors.sources._dateparse import parse_listing_date


@pytest.mark.parametrize(
    "text, expected",
    [
        # ISO
        ("2024-03-12", datetime(2024, 3, 12, tzinfo=timezone.utc)),
        ("2024-03-12T06:30:00Z", datetime(2024, 3, 12, 6, 30, tzinfo=timezone.utc)),
        ("Published: 2024-03-12 06:30",
         datetime(2024, 3, 12, 6, 30, tzinfo=timezone.utc)),
        # dd-mm-yyyy and friends
        ("12-03-2024", datetime(2024, 3, 12, tzinfo=timezone.utc)),
        ("12/03/2024", datetime(2024, 3, 12, tzinfo=timezone.utc)),
        ("Order dated 12.03.2024", datetime(2024, 3, 12, tzinfo=timezone.utc)),
        # dd Mon yyyy
        ("12 Mar 2024", datetime(2024, 3, 12, tzinfo=timezone.utc)),
        ("12 March 2024", datetime(2024, 3, 12, tzinfo=timezone.utc)),
        ("Notification dated 12 March 2024",
         datetime(2024, 3, 12, tzinfo=timezone.utc)),
        # Mon dd, yyyy
        ("Mar 12, 2024", datetime(2024, 3, 12, tzinfo=timezone.utc)),
        ("March 12 2024", datetime(2024, 3, 12, tzinfo=timezone.utc)),
        # year-only fallback
        ("W.P. (C) 1234/2023", datetime(2023, 1, 1, tzinfo=timezone.utc)),
    ],
)
def test_parses_known_formats(text: str, expected: datetime):
    assert parse_listing_date(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "    ",
        "click here",
        "no date in this string",
        "1899-01-01",   # year too old (before 2000)
    ],
)
def test_returns_none_when_unparseable(text):
    assert parse_listing_date(text) is None


def test_invalid_numeric_date_falls_through_to_year_only():
    """`32-13-2024` is invalid d/m, but 2024 is still a plausible year.
    Year-only fallback returns Jan 1 of the captured year — caller logs
    a debug-level note that the date confidence is low."""
    got = parse_listing_date("Order dated 32-13-2024")
    assert got is not None
    assert got.year == 2024
    assert got.month == 1 and got.day == 1


def test_returns_first_match():
    """When two dates are present, the first wins."""
    text = "Published 12 March 2024, archived 01 January 2020"
    assert parse_listing_date(text) == datetime(
        2024, 3, 12, tzinfo=timezone.utc
    )


def test_iso_with_offset_normalises_to_utc():
    text = "2024-03-12T12:00:00+05:30"
    got = parse_listing_date(text)
    assert got == datetime(2024, 3, 12, 6, 30, tzinfo=timezone.utc)


def test_year_above_max_year_rejected():
    """A 9999 timestamp should not be accepted as a publish date."""
    text = "Order dated 01-01-9999"
    assert parse_listing_date(text) is None
