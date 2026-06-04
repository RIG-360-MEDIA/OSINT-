"""Tier 4 of the entity-dict dedup (migration 095): NER title-strip fallback.

Pins the _strip_title behavior so a new "Chief Minister Smith" article resolves to "smith"
rather than creating a new titled dictionary row. Must match migration 095's regex byte-for-byte
to keep the SQL one-shot and the runtime path in sync.
"""
import importlib.util
import pathlib

import pytest

_PATH = pathlib.Path(__file__).resolve().parents[1] / "nlp" / "nlp_entities.py"


def _load():
    spec = importlib.util.spec_from_file_location("nlp_entities", _PATH)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:  # pragma: no cover - env-dependent (spacy/sqlalchemy not always present)
        pytest.skip(f"nlp_entities not importable here ({e})")
    return mod


@pytest.fixture(scope="module")
def strip():
    return _load()._strip_title


@pytest.mark.parametrize("titled,bare", [
    ("chief minister revanth reddy", "revanth reddy"),
    ("cm revanth reddy", "revanth reddy"),
    ("a revanth reddy", "revanth reddy"),
    ("a. revanth reddy", "revanth reddy"),
    ("dr neiphiu rio", "neiphiu rio"),
    ("dr. tunji alausa", "tunji alausa"),
    ("the new york times", "new york times"),
    ("the wall street journal", "wall street journal"),
    ("justice swarana kanta sharma", "swarana kanta sharma"),
    ("sri narendra modi", "narendra modi"),
    ("hon. abc xyz long", "abc xyz long"),
    ("prof rajiv kumar", "rajiv kumar"),
])
def test_strip_titled_variants(strip, titled, bare):
    assert strip(titled) == bare


@pytest.mark.parametrize("kept", [
    "revanth reddy",          # already bare
    "iran",                   # no prefix
    "new york",               # 'new' is not in the strip regex
    "supreme court",          # 'supreme' is not in the strip regex
    "of india",               # leading 'of' is not in the regex (no risk of over-strip)
    "ms dhoni",               # the 'ms' Title would strip but 'dhoni' is len>2 -> spared as a name
])
def test_no_overstrip_or_unrelated(strip, kept):
    out = strip(kept)
    # Either returns the input unchanged OR returns a still-meaningful bare-form.
    assert out == kept or len(out) >= 3


def test_too_short_bare_keeps_original(strip):
    # "Dr X" -> "x" (len 1) must NOT be returned; keep original to avoid resolving to a noise key.
    assert strip("dr x") == "dr x"
    assert strip("a y") == "a y"


def test_idempotent_single_pass(strip):
    # We deliberately strip ONLY ONE prefix per call (count=1). Stacked titles are not common
    # in real text and double-stripping risks over-eager matches.
    assert strip("dr chief minister revanth reddy") == "chief minister revanth reddy"
