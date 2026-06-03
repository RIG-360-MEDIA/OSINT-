"""F-3 subject_country by event location (2026-06-03, audit #3).

_subject_country derives subject_country from article_locations (the EVENT location), margin-guarded
(top located country must beat the runner-up >=2x) and ISO-mapped, falling back to the source-country
mode otherwise. Pins: clear-plurality overrides, near-ties keep the fallback (kills the
mentioned-not-subject tail), unmappable names keep the fallback (surface-when-unsure).

story_loader imports psycopg2 + reads MEMBERS/EDGES at module load -> dummy env + skip if deps absent.
"""
import importlib.util
import os
import pathlib
from collections import Counter

import pytest

os.environ.setdefault("MEMBERS", "x")
os.environ.setdefault("EDGES", "x")

_LOADER = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "story_loader.py"


def _load():
    spec = importlib.util.spec_from_file_location("story_loader", _LOADER)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:  # pragma: no cover - env-dependent
        pytest.skip(f"story_loader not importable here ({e})")
    return mod


def test_clear_plurality_overrides():
    sl = _load()
    # cruise: Spain 159 vs Cape Verde 38 -> 4.2x -> override IN->ES
    assert sl._subject_country(Counter({"Spain": 159, "Cape Verde": 38}), "IN") == "ES"


def test_near_tie_keeps_fallback():
    sl = _load()
    # Putin BRICS in New Delhi: China 12 vs India 11 -> 1.09x -> keep IN (mentioned-not-subject tail)
    assert sl._subject_country(Counter({"China": 12, "India": 11}), "IN") == "IN"
    # Modi Nordic investment in India: Norway 18 vs India 12 -> 1.5x -> keep IN
    assert sl._subject_country(Counter({"Norway": 18, "India": 12}), "IN") == "IN"


def test_single_country_overrides():
    sl = _load()
    assert sl._subject_country(Counter({"Mexico": 38}), "XX") == "MX"


def test_unmappable_keeps_fallback():
    sl = _load()
    # surface-when-unsure: a name not in the verified map must NOT guess an ISO
    assert sl._subject_country(Counter({"Atlantis": 50}), "IN") == "IN"


def test_below_min_support_keeps_fallback():
    sl = _load()
    assert sl._subject_country(Counter({"Spain": 1}), "IN") == "IN"  # c1<2 -> no override


def test_empty_keeps_fallback():
    sl = _load()
    assert sl._subject_country(Counter(), "IN") == "IN"


def test_case_insensitive_lookup():
    sl = _load()
    assert sl._subject_country(Counter({"spain": 159}), "IN") == "ES"
