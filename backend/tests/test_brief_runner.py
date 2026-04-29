"""Tests for backend/nlp/brief_runner.py.

Pure-function units only — the I/O-heavy ``run_for_user`` is exercised
via the existing ``test_brief_router.py`` integration suite. Here we
just lock the pieces that have caused regressions before:

* ``_prefer_recent`` (the per-pillar freshness gate).
* ``_parse_geo`` (handles both list and stringified-list shapes).
"""
from __future__ import annotations

from datetime import date, timedelta

from backend.nlp.brief_runner import _parse_geo, _prefer_recent


class TestPreferRecent:
    def test_returns_input_when_below_target(self) -> None:
        items = [{"edition_date": "2026-04-25"}]
        out = _prefer_recent(items, key="edition_date", target_min=3)
        assert out == items

    def test_promotes_fresh_items_to_front(self) -> None:
        today = date.today()
        fresh = [{"edition_date": today.isoformat(), "id": "fresh"}] * 3
        stale = [
            {"edition_date": (today - timedelta(days=4)).isoformat(), "id": "stale"}
        ] * 3
        out = _prefer_recent(
            stale + fresh, key="edition_date", target_min=2, days_window=1,
        )
        # Fresh items must come first.
        assert all(o["id"] == "fresh" for o in out[:3])
        assert all(o["id"] == "stale" for o in out[3:])

    def test_keeps_original_order_when_not_enough_fresh(self) -> None:
        today = date.today()
        items = [
            {"edition_date": (today - timedelta(days=5)).isoformat(), "id": "a"},
            {"edition_date": (today - timedelta(days=4)).isoformat(), "id": "b"},
            {"edition_date": (today - timedelta(days=3)).isoformat(), "id": "c"},
            {"edition_date": today.isoformat(), "id": "d"},
        ]
        out = _prefer_recent(
            items, key="edition_date", target_min=3, days_window=1,
        )
        # Only 1 fresh item, 3 needed → leave order alone.
        assert [o["id"] for o in out] == ["a", "b", "c", "d"]

    def test_handles_unparseable_date_silently(self) -> None:
        items = [
            {"edition_date": "not-a-date", "id": "weird"},
            {"edition_date": date.today().isoformat(), "id": "fresh"},
            {"edition_date": "2020-01-01", "id": "old"},
            {"edition_date": "2020-01-02", "id": "old2"},
        ]
        out = _prefer_recent(
            items, key="edition_date", target_min=1, days_window=1,
        )
        # The single fresh item bubbles up, weird is treated as not-fresh.
        assert out[0]["id"] == "fresh"


class TestParseGeo:
    def test_primary_only(self) -> None:
        assert _parse_geo({"geo_primary": "Telangana"}) == ["Telangana"]

    def test_secondary_as_list(self) -> None:
        out = _parse_geo({
            "geo_primary": "Telangana",
            "geo_secondary": ["Andhra Pradesh", "Karnataka"],
        })
        assert "Andhra Pradesh" in out
        assert "Karnataka" in out

    def test_secondary_as_stringified_list(self) -> None:
        out = _parse_geo({
            "geo_primary": "Telangana",
            "geo_secondary": "['Andhra Pradesh', 'Karnataka']",
        })
        assert "Andhra Pradesh" in out
        assert "Karnataka" in out

    def test_secondary_as_plain_string(self) -> None:
        out = _parse_geo({
            "geo_primary": "Telangana",
            "geo_secondary": "Andhra Pradesh",
        })
        assert "Andhra Pradesh" in out

    def test_empty_profile(self) -> None:
        assert _parse_geo({}) == []
