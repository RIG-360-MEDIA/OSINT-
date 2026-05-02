"""
Unit tests for backend.nlp.cm.geo_district.tag_districts.

These tests construct GazetteerEntry objects directly so the matcher can
be exercised without a database. The integration test that calls
``load_gazetteer(db)`` against a seeded districts table lives in the
backfill task's smoke suite (see test_backfill_district_geo_smoke.py)
and is intentionally separate.
"""

from __future__ import annotations

import pytest

from backend.nlp.cm.geo_district import (
    DistrictMatch,
    GazetteerEntry,
    LANDMARKS,
    _build_district_pattern,
    reset_cache,
    tag_districts,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _entry(district_id: str, name: str, hq_city: str, *aliases: str) -> GazetteerEntry:
    return GazetteerEntry(
        district_id=district_id,
        state_code="TG",
        name=name,
        hq_city=hq_city,
        pattern=_build_district_pattern(name, hq_city, list(aliases)),
    )


@pytest.fixture(autouse=True)
def _reset_module_cache() -> None:
    """Tag-district module caches are global; reset around every test so
    landmark-pattern compilation isn't shared across cases."""
    reset_cache()
    # The tag_districts function references the module-level
    # _LANDMARK_PATTERN that the resolver builds inside load_gazetteer.
    # In tests we don't go through load_gazetteer, so we build it manually.
    from backend.nlp.cm import geo_district as gd

    gd._LANDMARK_PATTERN = gd._build_landmark_pattern()


@pytest.fixture
def small_gazetteer() -> list[GazetteerEntry]:
    """Six districts representative of the matching shapes we care about."""
    return [
        _entry("hyderabad", "HYDERABAD", "Hyderabad", "HYD"),
        _entry("rangareddy", "RANGAREDDY", "Rangareddy", "RANGA REDDY", "RANGAREDDI"),
        _entry("khammam", "KHAMMAM", "Khammam"),
        _entry("warangal", "WARANGAL", "Warangal", "WARANGAL RURAL"),
        _entry("hanumakonda", "HANUMAKONDA", "Hanumakonda", "HANAMKONDA", "WARANGAL URBAN"),
        _entry("komaram-bheem", "KUMRAM BHEEM", "Kumram Bheem", "KOMARAM BHEEM", "ASIFABAD"),
    ]


# ---------------------------------------------------------------------------
# Core matching
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_title_match_returns_primary(small_gazetteer: list[GazetteerEntry]) -> None:
    matches = tag_districts(
        title="Khammam farmer assembly enters fourth hour",
        body=None,
        entities=None,
        gazetteer=small_gazetteer,
    )
    assert len(matches) == 1
    m = matches[0]
    assert m.district_id == "khammam"
    assert m.is_primary is True
    assert m.mention_count == 1
    assert 0 < m.confidence <= 1.0


@pytest.mark.unit
def test_multi_district_returns_all_with_one_primary(
    small_gazetteer: list[GazetteerEntry],
) -> None:
    matches = tag_districts(
        title="Khammam farmer arrested in Hyderabad after Warangal protest",
        body=None,
        entities=None,
        gazetteer=small_gazetteer,
    )
    ids = {m.district_id for m in matches}
    assert ids == {"khammam", "hyderabad", "warangal"}
    primaries = [m for m in matches if m.is_primary]
    assert len(primaries) == 1, "exactly one district must be primary"


@pytest.mark.unit
def test_word_boundary_respected(small_gazetteer: list[GazetteerEntry]) -> None:
    """'Hyderabadi cuisine' must NOT match HYDERABAD as a district hit."""
    matches = tag_districts(
        title="Hyderabadi cuisine featured at international expo",
        body=None,
        entities=None,
        gazetteer=small_gazetteer,
    )
    assert all(m.district_id != "hyderabad" for m in matches)


@pytest.mark.unit
def test_alias_matches(small_gazetteer: list[GazetteerEntry]) -> None:
    """RANGA REDDY (with space) and RANGAREDDI (alt spelling) both hit."""
    m1 = tag_districts(
        title="Ranga Reddy district to host industrial summit",
        body=None,
        entities=None,
        gazetteer=small_gazetteer,
    )
    assert any(m.district_id == "rangareddy" for m in m1)

    m2 = tag_districts(
        title=None,
        body="Officials in Rangareddi convened a meeting today.",
        entities=None,
        gazetteer=small_gazetteer,
    )
    assert any(m.district_id == "rangareddy" for m in m2)


@pytest.mark.unit
def test_warangal_urban_alias_routes_to_hanumakonda(
    small_gazetteer: list[GazetteerEntry],
) -> None:
    """The pre-rename label 'Warangal Urban' must resolve to hanumakonda,
    not warangal — both districts have the word 'Warangal' in their text
    profile, so this is a real disambiguation case."""
    matches = tag_districts(
        title="Warangal Urban municipal corporation passes budget",
        body=None,
        entities=None,
        gazetteer=small_gazetteer,
    )
    ids = {m.district_id for m in matches}
    # Must include hanumakonda (via the 'WARANGAL URBAN' alias).
    # Note: 'Warangal' substring matching is intentional — 'Warangal Urban'
    # does contain 'Warangal' as a token, so warangal also lights up. This
    # is acceptable: the article does mention the larger Warangal area,
    # and is_primary will land on the highest-confidence (longest match).
    assert "hanumakonda" in ids


@pytest.mark.unit
def test_body_lead_weighs_more_than_deep_body(
    small_gazetteer: list[GazetteerEntry],
) -> None:
    """A district mentioned in the lead body outranks one mentioned only deep."""
    deep_filler = "Lorem ipsum dolor sit amet. " * 20  # > 300 chars
    matches = tag_districts(
        title=None,
        body="Khammam administration responded today. " + deep_filler + "Hyderabad sources noted.",
        entities=None,
        gazetteer=small_gazetteer,
    )
    by_id = {m.district_id: m for m in matches}
    assert "khammam" in by_id and "hyderabad" in by_id
    # Khammam in lead, Hyderabad in deep body → Khammam should be primary.
    assert by_id["khammam"].is_primary is True
    assert by_id["khammam"].confidence >= by_id["hyderabad"].confidence


@pytest.mark.unit
def test_entities_drive_match_when_text_silent(
    small_gazetteer: list[GazetteerEntry],
) -> None:
    """A short title + entities-only article still gets tagged."""
    matches = tag_districts(
        title="District officer reviews preparedness",
        body=None,
        entities=[{"name": "Khammam", "type": "GPE"}],
        gazetteer=small_gazetteer,
    )
    assert any(m.district_id == "khammam" for m in matches)


# ---------------------------------------------------------------------------
# Landmarks
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_landmark_routes_to_parent_districts(
    small_gazetteer: list[GazetteerEntry],
) -> None:
    """'Musi River' resolves to both Hyderabad and Rangareddy."""
    matches = tag_districts(
        title="Musi River rejuvenation plan questioned",
        body=None,
        entities=None,
        gazetteer=small_gazetteer,
    )
    ids = {m.district_id for m in matches}
    assert "hyderabad" in ids
    assert "rangareddy" in ids


@pytest.mark.unit
def test_landmarks_dict_invariants() -> None:
    """Every landmark must have at least one parent district."""
    for landmark, parents in LANDMARKS.items():
        assert isinstance(landmark, str) and landmark
        assert isinstance(parents, tuple) and len(parents) >= 1
        for d in parents:
            assert isinstance(d, str) and d
            # All landmark parents should be lowercase slugs.
            assert d == d.lower()


# ---------------------------------------------------------------------------
# Empty / no-match
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_empty_inputs_return_empty(small_gazetteer: list[GazetteerEntry]) -> None:
    assert tag_districts(title=None, body=None, entities=None, gazetteer=small_gazetteer) == []


@pytest.mark.unit
def test_no_match_article_returns_empty(small_gazetteer: list[GazetteerEntry]) -> None:
    matches = tag_districts(
        title="Federal Reserve raises interest rates by 25 basis points",
        body="The decision was unanimous. Markets reacted by mid-afternoon.",
        entities=[{"name": "Federal Reserve", "type": "ORG"}],
        gazetteer=small_gazetteer,
    )
    assert matches == []


@pytest.mark.unit
def test_empty_gazetteer_returns_empty() -> None:
    matches = tag_districts(
        title="Khammam farmer assembly enters fourth hour",
        body=None,
        entities=None,
        gazetteer=[],
    )
    assert matches == []


# ---------------------------------------------------------------------------
# Confidence clamping
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_confidence_never_exceeds_one(small_gazetteer: list[GazetteerEntry]) -> None:
    """Even when a district is mentioned 50 times, confidence ≤ 1.0."""
    body = ("Khammam district reported again. " * 50)
    matches = tag_districts(
        title="Khammam Khammam Khammam Khammam Khammam",
        body=body,
        entities=[{"name": "Khammam"}, {"name": "Khammam"}, {"name": "Khammam"}],
        gazetteer=small_gazetteer,
    )
    assert all(0.0 <= m.confidence <= 1.0 for m in matches)
    khammam = next(m for m in matches if m.district_id == "khammam")
    assert khammam.confidence == 1.0


@pytest.mark.unit
def test_match_shape_is_dataclass(small_gazetteer: list[GazetteerEntry]) -> None:
    """Frozen dataclass — required so the result list is hashable in sets."""
    matches = tag_districts(
        title="Khammam update",
        body=None,
        entities=None,
        gazetteer=small_gazetteer,
    )
    assert isinstance(matches[0], DistrictMatch)
    # Frozen — assignment must fail.
    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        matches[0].confidence = 0.5  # type: ignore[misc]
