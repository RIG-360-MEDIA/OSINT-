#!/usr/bin/env python3
"""
Unit tests (VERIFY-you, handoff §3) for template_guard.block_edge — BOTH directions:
the rule must BLOCK the v3 date-keyed template negatives, and must STILL MERGE a real
evolving story. Also pins the language-agnostic date-key, the entity-key combination
rule, the same-source-only precondition, and that numeric divergence NEVER splits.

Runs as plain `python test_template_guard.py` (prints PASS/FAIL, exit code) or via pytest.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/tmp")  # box run location
from template_guard import block_edge  # noqa: E402


# ---- MUST BLOCK (v3 date-keyed template negatives) ----
def test_blocks_english_front_pages_diff_day():
    block, _ = block_edge(same_source=True, title_trgm=0.95,
                          a_title="Today's Front pages: Tuesday, May 12, 2026",
                          b_title="Today's Front pages: Friday, May 8, 2026")
    assert block is True


def test_blocks_indic_horoscope_numeric_date():
    # language-agnostic: numeric DD-MM-YYYY date fires on Telugu titles, no Indic training data
    block, _ = block_edge(same_source=True, title_trgm=0.90,
                          a_title="సోమవారం రాశి ఫలాలు (25-05-2026)",
                          b_title="శనివారం రాశిఫలాలు ( 23- 05-2026)")
    assert block is True


def test_blocks_diff_stock_lead_entity():
    # entity-key, valid ONLY because same_source + near-identical title also hold
    block, _ = block_edge(same_source=True, title_trgm=0.88,
                          a_title="Tech Mahindra Share Price Live Updates",
                          b_title="HCL Tech Share Price Live Updates",
                          a_lead_entity="Tech Mahindra", b_lead_entity="HCL Tech")
    assert block is True


# ---- MUST MERGE (the rule must never over-block a real same-event pair) ----
def test_merges_evolving_story_same_day():
    # same source, near-identical LIVE title, same day, different angle -> evolving story, MERGE
    block, _ = block_edge(same_source=True, title_trgm=0.92,
                          a_title="West Bengal CM oath ceremony LIVE: Suvendu sworn in",
                          b_title="West Bengal CM oath ceremony LIVE: Suvendu takes charge")
    assert block is False


def test_numeric_divergence_never_splits():
    # titles carry DIFFERENT numbers (toll 80 vs 95) but no date/entity key -> MUST merge
    block, _ = block_edge(same_source=True, title_trgm=0.93,
                          a_title="Coal mine blast kills 80 in northern China",
                          b_title="Coal mine blast kills 95 in northern China")
    assert block is False


def test_different_source_never_blocks():
    # templates are same-source only; cross-source near-identical titles are real corroboration
    block, _ = block_edge(same_source=False, title_trgm=0.99,
                          a_title="Today's Front pages: May 12",
                          b_title="Today's Front pages: May 8")
    assert block is False


def test_entity_key_requires_near_identical_title():
    # different lead entity but titles NOT near-identical -> guard does not fire (scorer decides)
    block, _ = block_edge(same_source=True, title_trgm=0.40,
                          a_title="Tech Mahindra posts strong Q4, shares jump",
                          b_title="HCL Tech Q4 disappoints as margins slip",
                          a_lead_entity="Tech Mahindra", b_lead_entity="HCL Tech")
    assert block is False


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
