"""F-2 display junk-entity stoplist (2026-06-03).

DISPLAY_STOP de-junks primary_entities (audit #4) but MUST NOT touch _core — the §2b and
size x core gates read entity_core_cov, and the §B measurement proved de-junking does not move
core. These tests pin that separation: _core excludes only STOP_ENT (wire services), never the
display JUNK_ENT, so F-2 has provably zero gate impact.
"""
import importlib.util
import pathlib

_RESCUE = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "story_rescue.py"


def _load():
    spec = importlib.util.spec_from_file_location("story_rescue", _RESCUE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sr = _load()


def test_display_stop_is_superset_of_stop_ent():
    assert sr.STOP_ENT <= sr.DISPLAY_STOP
    assert "passengers" in sr.DISPLAY_STOP
    assert "passengers" not in sr.STOP_ENT  # junk is display-only, not a core stop


def test_core_still_counts_display_junk():
    # _core excludes STOP_ENT ONLY — a JUNK_ENT term can still be the core entity, so removing it
    # from the display rollup cannot change entity_core_cov (the gate-feeding signal).
    members = ["a", "b", "c"]
    art_ents = {"a": ["passengers"], "b": ["passengers"], "c": ["passengers"]}
    cov, ent = sr._core(members, art_ents)
    assert cov == 1.0 and ent == "passengers"


def test_core_excludes_wire_stop_ent():
    members = ["a", "b"]
    art_ents = {"a": ["reuters"], "b": ["reuters"]}
    cov, _ = sr._core(members, art_ents)
    assert cov == 0.0  # wire service is excluded from core


def test_atlantic_council_not_globally_stoplisted():
    # real org; only 1 of its 2 surfaced uses is the cruise Atlantic-Ocean mis-tag -> NER workstream
    assert "atlantic council" not in sr.DISPLAY_STOP
