"""Unit tests for personalization logic (pure — no DB, no corpus)."""
from __future__ import annotations

from app.personalize import Personalization, apply_mutes, apply_watch_boost, personalize
from app.schemas import RetrievedDoc


def _doc(doc_id, title="t", source_id="src", language="en", snippet="body"):
    return RetrievedDoc(
        id=doc_id, title=title, snippet=snippet, url=None, published_at=None,
        source_id=source_id, language=language, score=1.0, vec_rank=None, lex_rank=None,
    )


def test_mute_by_source():
    docs = [_doc("1", source_id="spam"), _doc("2", source_id="good")]
    p = Personalization(muted_sources=frozenset({"spam"}))
    out = apply_mutes(docs, p)
    assert [d.id for d in out] == ["2"]


def test_mute_by_language():
    docs = [_doc("1", language="ta"), _doc("2", language="en")]
    p = Personalization(muted_languages=frozenset({"ta"}))
    assert [d.id for d in apply_mutes(docs, p)] == ["2"]


def test_mute_by_keyword():
    docs = [_doc("1", title="Cricket score update"), _doc("2", title="Budget policy")]
    p = Personalization(muted_keywords=("cricket",))
    assert [d.id for d in apply_mutes(docs, p)] == ["2"]


def test_mute_by_entity():
    docs = [_doc("1"), _doc("2")]
    p = Personalization(muted_entities=frozenset({"e1"}))
    doc_entities = {"1": {"e1"}, "2": {"e9"}}
    assert [d.id for d in apply_mutes(docs, p, doc_entities)] == ["2"]


def test_watch_boost_partitions_to_front():
    docs = [_doc("1"), _doc("2"), _doc("3")]
    p = Personalization(watched_entities=frozenset({"ew"}))
    doc_entities = {"3": {"ew"}}  # only doc 3 mentions the watched entity
    out = apply_watch_boost(docs, p, doc_entities)
    assert out[0].id == "3"  # watched moves to front
    assert [d.id for d in out] == ["3", "1", "2"]  # rest order preserved


def test_watch_boost_noop_without_watch():
    docs = [_doc("1"), _doc("2")]
    p = Personalization()
    assert apply_watch_boost(docs, p, {"1": {"x"}}) == docs


def test_personalize_composes_mute_then_boost():
    docs = [_doc("1", source_id="spam"), _doc("2"), _doc("3")]
    p = Personalization(muted_sources=frozenset({"spam"}), watched_entities=frozenset({"ew"}))
    doc_entities = {"3": {"ew"}}
    out = personalize(docs, p, doc_entities)
    assert [d.id for d in out] == ["3", "2"]  # spam muted, watched(3) to front


def test_is_noop_and_relevant_entity_ids():
    assert Personalization().is_noop is True
    p = Personalization(muted_entities=frozenset({"a"}), watched_entities=frozenset({"b"}))
    assert p.is_noop is False
    assert p.relevant_entity_ids == frozenset({"a", "b"})


def test_mutes_do_not_mutate_input():
    docs = [_doc("1", source_id="spam"), _doc("2")]
    original = list(docs)
    apply_mutes(docs, Personalization(muted_sources=frozenset({"spam"})))
    assert docs == original
