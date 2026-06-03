"""Conformance test for the size x core surfacing gate (ship-blocker fix 2026-06-03).

Pins the reference predicate's truth table (story_rescue.size_core_suppress) AND guards that
the EXECUTABLE SQL copies — scripts/migrations/093_low_core_surfacing_gate.sql and the
post-INSERT step in scripts/maintenance/story_loader.py — still carry the gate's clauses, so
the three copies cannot silently drift apart.

Root cause it fixes: §2b only evaluates clusters with independent_source_count >= 25; 69/71
surfaced low-core stories escaped purely by being under that floor, and 2 were genuinely
incoherent mid-size grab-bags (NASA n=19/core 0.16, exam n=52/core 0.21) that reached users.
The gate suppresses those two classes while sparing tiny real stories and vernacular NER-zeros.
"""
import importlib.util
import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_RESCUE = _ROOT / "scripts" / "maintenance" / "story_rescue.py"
_LOADER = _ROOT / "scripts" / "maintenance" / "story_loader.py"
_MIGRATION = _ROOT / "scripts" / "migrations" / "093_low_core_surfacing_gate.sql"


def _load_rescue():
    spec = importlib.util.spec_from_file_location("story_rescue", _RESCUE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


size_core_suppress = _load_rescue().size_core_suppress


# label, core, n, surfaced, en_count, total_lang, expected_suppress
CASES = [
    ("NASA grab-bag -> CAUGHT",                 0.16, 19, True,  19,  19, True),
    ("exam pile -> CAUGHT",                     0.21, 52, True,  52,  52, True),
    ("Maldives divers -> spare (size n=12)",    0.17, 12, True,  12,  12, False),
    ("JPMorgan -> spare (core 0.37)",           0.37, 330, True, 330, 330, False),
    ("Philippine lawmaker -> spare (core 0.42)", 0.42, 62, True, 62,  62, False),
    ("legit small low-core -> spare (size n=3)", 0.20, 3, True,   3,   3, False),
    ("vernacular core~0 -> spare (carve-out)",  0.00, 20, True,   1,  20, False),
    ("non-surfaced isc<3 -> spare (scope)",     0.16, 19, False, 19,  19, False),
]


@pytest.mark.parametrize("label,core,n,surfaced,en,total,expected", CASES)
def test_truth_table(label, core, n, surfaced, en, total, expected):
    assert size_core_suppress(core, n, surfaced, en, total) is expected, label


def test_size_floor_boundary():
    # N_mid=15: the largest legit-small was n=14; NASA at n=19. Below 15 is never suppressed.
    assert size_core_suppress(0.16, 14, True, 14, 14) is False
    assert size_core_suppress(0.16, 15, True, 15, 15) is True


def test_core_ceiling_boundary():
    # C_low=0.25 is a strict ceiling: 0.25 spared, 0.24 caught (exam 0.21 in; JPMorgan 0.37 out).
    assert size_core_suppress(0.25, 20, True, 20, 20) is False
    assert size_core_suppress(0.24, 20, True, 20, 20) is True


def test_carveout_only_for_core_near_zero():
    # A vernacular-dominant cluster with core ABOVE the carve-out cutoff is still suppressed —
    # the carve-out protects NER-zero (core~0), not all low-core vernacular.
    assert size_core_suppress(0.10, 20, True, 1, 20) is True
    assert size_core_suppress(0.04, 20, True, 1, 20) is False


@pytest.mark.parametrize("path", [_LOADER, _MIGRATION])
def test_sql_copies_carry_the_gate(path):
    """Drift guard: the runtime SQL must still encode every arm of the gate."""
    sql = path.read_text(encoding="utf-8")
    assert "size-core-gate" in sql, f"{path.name}: missing reason tag"
    assert "entity_core_cov" in sql and "article_count" in sql, f"{path.name}: missing size/core test"
    assert "jsonb_each_text(languages)" in sql, f"{path.name}: missing vernacular carve-out"
    assert "independent_source_count" in sql, f"{path.name}: missing surfaced scope"
