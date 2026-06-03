"""F-1 representative-title on-core preference (2026-06-03, audit #5 donkey-on-PSG).

rep_pick must prefer a member whose extracted entities include the cluster core entity, so the
headline is about the subject — but fall back gracefully when no on-core member exists (concept
stories), never returning nothing where the old logic would have returned a title.

story_loader imports psycopg2 + reads MEMBERS/EDGES at module load, so we inject dummy env and
skip if backend deps are absent (the function under test is pure; CI has the deps).
"""
import importlib.util
import os
import pathlib

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


def test_rep_pick_prefers_on_core_member():
    sl = _load()
    arts = [
        {"id": "a", "title": "Therapy donkeys bring comfort to flood victims today", "lang": "en", "src": "s1"},
        {"id": "b", "title": "PSG riots erupt across Paris after the cup final loss", "lang": "en", "src": "s2"},
    ]
    art_ents = {"a": ["donkeys", "therapy"], "b": ["psg", "paris"]}
    rid, rtitle = sl.rep_pick(arts, core_ent="psg", art_ents=art_ents)
    assert rid == "b"  # on-core wins over an off-core but otherwise-valid clean title


def test_rep_pick_falls_back_when_no_on_core():
    sl = _load()
    arts = [{"id": "a", "title": "A clean english headline about the weather this week", "lang": "en", "src": "s1"}]
    art_ents = {"a": ["weather"]}
    rid, rtitle = sl.rep_pick(arts, core_ent="psg", art_ents=art_ents)
    assert rid == "a"  # no on-core candidate -> still returns a sensible title (no regression)


def test_rep_pick_unchanged_without_core_ent():
    sl = _load()
    arts = [{"id": "a", "title": "A clean english headline of a perfectly reasonable length", "lang": "en", "src": "s1"}]
    rid, _ = sl.rep_pick(arts)  # old call signature still works (median-length English)
    assert rid == "a"
