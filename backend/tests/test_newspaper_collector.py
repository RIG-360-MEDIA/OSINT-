"""
Tests for backend.collectors.newspaper_collector pure-function helpers.

These tests cover the date-variant matching and Drive ID extraction
that decide whether a paper produces a PDF for the day. They never
touch the network or PDF parsing; those paths require fixtures of
real PDFs which live in QA artefacts, not unit tests.
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.collectors.newspaper_collector import (
    _GDRIVE_FILE_ID_RE,
    _date_variants,
    _find_gdrive_id_near_date,
    _gdrive_direct_url,
)


@pytest.mark.unit
def test_date_variants_covers_all_observed_formats() -> None:
    d = date(2026, 4, 23)
    variants = _date_variants(d)
    expected_substrings = [
        "23 April 2026",
        "23-04-2026",
        "23/04/2026",
        "April 23, 2026",
        "April 23 2026",
        "2026-04-23",
    ]
    for expected in expected_substrings:
        assert expected in variants, f"missing variant {expected!r}"


@pytest.mark.unit
def test_date_variants_zero_pad_and_unpadded_both_present() -> None:
    d = date(2026, 4, 5)
    variants = _date_variants(d)
    assert "05 April 2026" in variants
    assert "5 April 2026" in variants
    assert "5-04-2026" in variants


@pytest.mark.unit
def test_gdrive_regex_accepts_20_plus_char_id() -> None:
    html = (
        '<a href="https://drive.google.com/file/d/'
        '1AbCdEfGhIjKlMnOpQrSt/view">'
    )
    m = _GDRIVE_FILE_ID_RE.search(html)
    assert m is not None
    assert m.group(1) == "1AbCdEfGhIjKlMnOpQrSt"


@pytest.mark.unit
def test_gdrive_regex_rejects_short_ids() -> None:
    html = '<a href="https://drive.google.com/file/d/short123/view">'
    assert _GDRIVE_FILE_ID_RE.search(html) is None


@pytest.mark.unit
def test_gdrive_regex_ignores_non_drive_links() -> None:
    html = (
        '<a href="https://example.com/file/d/'
        '1AbCdEfGhIjKlMnOpQrSt/view">'
    )
    assert _GDRIVE_FILE_ID_RE.search(html) is None


@pytest.mark.unit
def test_find_gdrive_id_near_date_today_match() -> None:
    target = date(2026, 4, 23)
    fid = "1AbCdEfGhIjKlMnOpQrSt"
    html = (
        f"<p>23 April 2026: "
        f'<a href="https://drive.google.com/file/d/{fid}/view">PDF</a></p>'
    )
    assert _find_gdrive_id_near_date(html, target) == fid


@pytest.mark.unit
def test_find_gdrive_id_near_date_picks_dated_link_not_first() -> None:
    """When the page lists older editions before today's, the function
    must skip the irrelevant ones and lock on the dated section."""
    target = date(2026, 4, 23)
    older_id = "OLDOLDOLDOLDOLDOLDOL"
    today_id = "TODAYTODAYTODAYTODAY"
    html = (
        f'<a href="https://drive.google.com/file/d/{older_id}/view">old</a>'
        f"<p>22 April 2026 yesterday's edition</p>"
        f"<p>23 April 2026: "
        f'<a href="https://drive.google.com/file/d/{today_id}/view">today</a></p>'
    )
    assert _find_gdrive_id_near_date(html, target) == today_id


@pytest.mark.unit
def test_find_gdrive_id_near_date_no_match() -> None:
    """Date string absent → returns None."""
    target = date(2026, 4, 23)
    html = "<p>some unrelated content</p>"
    assert _find_gdrive_id_near_date(html, target) is None


@pytest.mark.unit
def test_find_gdrive_id_near_date_dd_mm_format() -> None:
    target = date(2026, 4, 23)
    fid = "DDMMDDMMDDMMDDMMDDMM"
    html = (
        f"<tr><td>23-04-2026</td>"
        f'<td><a href="https://drive.google.com/file/d/{fid}/view">x</a></td></tr>'
    )
    assert _find_gdrive_id_near_date(html, target) == fid


@pytest.mark.unit
def test_find_gdrive_id_near_date_iso_format() -> None:
    target = date(2026, 4, 23)
    fid = "ISOISOISOISOISOISOIS"
    html = (
        f"<p>2026-04-23 — "
        f'<a href="https://drive.google.com/file/d/{fid}/view">link</a></p>'
    )
    assert _find_gdrive_id_near_date(html, target) == fid


@pytest.mark.unit
def test_find_gdrive_id_window_does_not_cross_unrelated_link() -> None:
    """If the date appears far away from any Drive link (>2500 chars),
    the function must NOT return an unrelated link as a false match."""
    target = date(2026, 4, 23)
    far_id = "FAR1234567890ABCDEFG"
    filler = "x" * 3000
    html = (
        f"<p>23 April 2026 was a Tuesday.</p>{filler}"
        f'<a href="https://drive.google.com/file/d/{far_id}/view">unrelated</a>'
    )
    assert _find_gdrive_id_near_date(html, target) is None


@pytest.mark.unit
def test_gdrive_direct_url_format() -> None:
    fid = "1AbCdEfGhIjKlMnOpQrSt"
    assert _gdrive_direct_url(fid) == (
        f"https://drive.google.com/uc?export=download&id={fid}"
    )


# ── Relevance scorer ─────────────────────────────────────────────────────────

import asyncio

from backend.collectors.newspaper_collector import is_relevant_to_user


def _score(headline: str, text: str, entities: list[str], geo: str = "telangana"):
    return asyncio.run(is_relevant_to_user(headline, text, entities, geo))


@pytest.mark.unit
def test_relevance_entity_match_alone_is_relevant() -> None:
    is_rel, score, reason = _score(
        "Revanth Reddy announces scheme",
        "The Chief Minister said the new initiative …",
        ["Revanth Reddy"],
    )
    assert is_rel is True
    assert score >= 0.4
    assert "Revanth Reddy" in reason


@pytest.mark.unit
def test_relevance_geo_alone_below_threshold_when_no_entity_or_political() -> None:
    """Geography alone scores 0.3 — exactly at threshold, but with no
    entity match this is borderline and should still pass."""
    is_rel, score, _ = _score(
        "Hyderabad weather report",
        "Light rain expected in the city",
        [],  # no user entities
        "hyderabad",
    )
    assert score >= 0.3
    assert is_rel is True


@pytest.mark.unit
def test_relevance_unrelated_content_rejected() -> None:
    is_rel, score, _ = _score(
        "Lakers beat Warriors",
        "NBA basketball game went into overtime in Los Angeles.",
        ["Revanth Reddy"],
        "telangana",
    )
    assert score < 0.3
    assert is_rel is False


@pytest.mark.unit
def test_relevance_political_term_only_below_threshold() -> None:
    """A bare political term contributes 0.1 — should NOT clear 0.3 alone."""
    is_rel, score, _ = _score(
        "Government spending in faraway state",
        "The minister announced a budget overhaul. Parliament debated.",
        [],
        "kerala",  # not in the alias map; falls through to literal check
    )
    assert score < 0.3
    assert is_rel is False


@pytest.mark.unit
def test_relevance_telugu_geo_alias_matches() -> None:
    is_rel, score, _ = _score(
        "తెలంగాణలో నూతన పథకం",  # "New scheme in Telangana"
        "ముఖ్యమంత్రి ప్రకటన.",
        [],
        "telangana",
    )
    assert is_rel is True
    assert score >= 0.3


@pytest.mark.unit
def test_relevance_handles_empty_inputs() -> None:
    is_rel, score, _ = _score("", "", [], "telangana")
    assert is_rel is False
    assert score == 0.0
