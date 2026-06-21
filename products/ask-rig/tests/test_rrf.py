import pytest

from app.retrieval import reciprocal_rank_fusion

pytestmark = pytest.mark.unit


def test_rrf_rewards_top_ranks():
    scores = reciprocal_rank_fusion([["a", "b", "c"]], k=60)
    assert scores["a"] > scores["b"] > scores["c"]


def test_rrf_symmetric_lists_tie():
    scores = reciprocal_rank_fusion([["a", "b"], ["b", "a"]], k=60)
    assert round(scores["a"], 9) == round(scores["b"], 9)


def test_rrf_consensus_beats_single_list():
    # 'a' is rank-1 in both lists; 'x' and 'y' each appear once.
    scores = reciprocal_rank_fusion([["a", "x"], ["a", "y"]], k=60)
    assert scores["a"] > scores["x"]
    assert scores["a"] > scores["y"]


def test_rrf_empty_input():
    assert reciprocal_rank_fusion([]) == {}
