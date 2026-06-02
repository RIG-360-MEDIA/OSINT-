#!/usr/bin/env python3
"""Unit tests for nlp_entities.compute_prominence — the word-boundary + surface-form fix.
Runs as `python test_nlp_entities.py` (PASS/FAIL + exit code) or via pytest."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "nlp"))
sys.path.insert(0, "/tmp")  # box run location
from nlp_entities import compute_prominence  # noqa: E402


# ---- the substring bug must be gone (word boundaries) ----
def test_man_does_not_match_inside_words():
    # "Man" must NOT fire on Rah-man / Mani-pur / wo-man / com-mand (the old substring bug)
    p = compute_prominence(["Man"], "Rahman wins big in Manipur, demands recount",
                           "A woman commented on the command.")
    assert p == 0.0


def test_man_matches_whole_word():
    p = compute_prominence(["Man"], "Man constituency result declared", "")
    assert p >= 0.6


# ---- surface-form scoring: the alias that actually appears must count ----
def test_modi_alias_scores_headline():
    # canonical "Narendra Modi" but headline says "PM Modi" -> the "Modi" surface scores it
    p = compute_prominence(["Narendra Modi", "Modi"], "PM Modi rubbishes the claim", "Modi spoke.")
    assert p >= 0.6


def test_canonical_only_misses_headline_alias():
    # documents the old bug: canonical alone does not substring-match "PM Modi" -> 0
    p = compute_prominence(["Narendra Modi"], "PM Modi rubbishes the claim", "")
    assert p == 0.0


# ---- the US -> United Spirits collision must not score ----
def test_us_two_char_alias_ignored():
    p = compute_prominence(["United Spirits", "US"], "US President weighs Iran deal",
                           "The US said today.")
    assert p == 0.0


def test_short_only_forms_score_zero():
    p = compute_prominence(["US", "IT"], "US and IT news roundup", "")
    assert p == 0.0


# ---- normal salience still works ----
def test_real_subject_scores_high():
    p = compute_prominence(["Iran"], "Talks continue",
                           "Iran said. Iran denied. Iran again. Iran. Iran. Iran.")
    assert p == 1.0  # lede(+2) + body cap(+5) = 7/5 -> capped 1.0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except AssertionError:
            print(f"FAIL  {t.__name__}")
    print(f"\n{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)
