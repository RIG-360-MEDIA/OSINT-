"""Unit tests for the pure intelligence scorers (no DB)."""
from __future__ import annotations

from app.intel import balance_from_stances, find_contested


def _s(stance, intensity=0.8):
    return {"stance": stance, "intensity": intensity}


def _row(eid, stance, aid, actor="X"):
    return {"actor_entity_id": eid, "actor": actor, "stance": stance,
            "article_id": aid, "title": f"t{aid}", "url": f"http://{aid}", "language": "en"}


def test_contested_target_returned():
    rows = [_row("e1", "supportive", "a1"), _row("e1", "critical", "a2")]
    c = find_contested(rows)
    assert len(c) == 1 and c[0]["actor_entity_id"] == "e1"
    assert c[0]["supportive_count"] == 1 and c[0]["critical_count"] == 1


def test_one_sided_target_not_contested():
    rows = [_row("e1", "supportive", "a1"), _row("e1", "supportive", "a2")]
    assert find_contested(rows) == []


def test_even_split_scores_one():
    rows = [_row("e1", "supportive", "a1"), _row("e1", "critical", "a2")]
    assert find_contested(rows)[0]["contested_score"] == 1.0


def test_lopsided_split_scores_low():
    rows = [_row("e1", "supportive", f"a{i}") for i in range(9)] + [_row("e1", "critical", "ax")]
    # 1 critical of 10 → min/total*2 = 0.2
    assert find_contested(rows)[0]["contested_score"] == 0.2


def test_examples_dedup_by_article():
    rows = [_row("e1", "supportive", "a1"), _row("e1", "supportive", "a1"),
            _row("e1", "critical", "a2")]
    c = find_contested(rows)[0]
    assert len(c["supportive_examples"]) == 1  # a1 only once


def test_rows_without_entity_ignored():
    rows = [{"actor_entity_id": None, "actor": "x", "stance": "supportive", "article_id": "a1"},
            {"actor_entity_id": None, "actor": "x", "stance": "critical", "article_id": "a2"}]
    assert find_contested(rows) == []


def test_sorted_by_total_volume():
    rows = ([_row("e1", "supportive", "a1"), _row("e1", "critical", "a2")]
            + [_row("e2", "supportive", f"b{i}") for i in range(5)]
            + [_row("e2", "critical", f"c{i}") for i in range(5)])
    out = find_contested(rows)
    assert out[0]["actor_entity_id"] == "e2"  # 10 stances > 2


def test_all_supportive_is_plus_one():
    r = balance_from_stances([_s("supportive"), _s("supportive"), _s("admiration")])
    assert r["balance_score"] == 1.0
    assert r["label"] == "leans supportive"


def test_all_critical_is_minus_one():
    r = balance_from_stances([_s("critical"), _s("mocking")])
    assert r["balance_score"] == -1.0
    assert r["label"] == "leans critical"


def test_even_split_is_balanced():
    r = balance_from_stances([_s("supportive", 1.0), _s("critical", 1.0)])
    assert r["balance_score"] == 0.0
    assert r["label"] == "balanced"


def test_intensity_weighting():
    # strong support (1.0) vs weak criticism (0.2) → leans supportive
    r = balance_from_stances([_s("supportive", 1.0), _s("critical", 0.2)])
    assert r["balance_score"] > 0.5
    assert r["label"] == "leans supportive"


def test_neutral_counted_separately_not_in_score():
    r = balance_from_stances([_s("supportive", 1.0), _s("neutral", 1.0), _s("analytical", 1.0)])
    assert r["neutral_count"] == 2
    assert r["balance_score"] == 1.0  # only the supportive counts toward polarity


def test_empty_is_zero():
    r = balance_from_stances([])
    assert r["balance_score"] == 0.0 and r["n_stances"] == 0 and r["label"] == "balanced"


def test_mild_lean_under_threshold_is_balanced():
    # 0.55 vs 0.45 → score 0.1 < 0.2 → balanced
    r = balance_from_stances([_s("supportive", 0.55), _s("critical", 0.45)])
    assert abs(r["balance_score"]) < 0.2 and r["label"] == "balanced"


def test_counts_and_weights_reported():
    r = balance_from_stances([_s("supportive", 0.8), _s("critical", 0.4), _s("neutral", 0.5)])
    assert r["supportive_weight"] == 0.8
    assert r["critical_weight"] == 0.4
    assert r["n_stances"] == 3
