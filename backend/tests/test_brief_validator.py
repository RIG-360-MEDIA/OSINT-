"""Tests for backend/nlp/brief_validator.py.

fix/brief-prod-readiness P2.7 + audit follow-up. The validator is the
guardrail that catches hallucinated citation IDs before a brief reaches
the user, so its unit coverage matters more than the rest of the
pillar.
"""
from __future__ import annotations

import pytest

from backend.nlp.brief_validator import (
    build_id_allowlist,
    count_words,
    strip_invalid_citations,
    validate_citations,
)


class TestValidateCitations:
    """validate_citations identifies in-range and out-of-range cites."""

    def test_valid_indexes_within_range_pass(self) -> None:
        text = "Item one [1] and item two [2] both confirm the trend."
        result = validate_citations(
            "KEY DEVELOPMENTS", text,
            article_count=5, govt_doc_count=0,
            newspaper_count=0, social_count=0, video_count=0,
        )
        assert result.is_valid
        assert result.invalid_article_indexes == ()
        assert result.article_indexes_seen == (1, 2)

    def test_index_above_article_count_is_flagged(self) -> None:
        text = "See [1], [2], and the spurious [99]."
        result = validate_citations(
            "ENTITIES TODAY", text,
            article_count=3, govt_doc_count=0,
            newspaper_count=0, social_count=0, video_count=0,
        )
        assert not result.is_valid
        assert 99 in result.invalid_article_indexes
        assert any("hallucinated" in i for i in result.issues)

    def test_doc_cite_without_pillar_evidence_is_flagged(self) -> None:
        text = "(Doc: Example Order, p.12) outlines the policy."
        result = validate_citations(
            "FINANCIAL PULSE", text,
            article_count=10, govt_doc_count=0,
            newspaper_count=0, social_count=0, video_count=0,
        )
        assert not result.is_valid
        assert any("(Doc:" in i for i in result.issues)

    def test_doc_cite_with_evidence_passes(self) -> None:
        text = "(Doc: Example Order, p.12) outlines the policy."
        result = validate_citations(
            "FINANCIAL PULSE", text,
            article_count=10, govt_doc_count=2,
            newspaper_count=0, social_count=0, video_count=0,
        )
        assert result.is_valid
        assert result.doc_cite_count == 1

    def test_paper_cite_consistency(self) -> None:
        text = "(Paper: Eenadu 2026-04-28, p.5) confirms."
        bad = validate_citations(
            "KEY DEVELOPMENTS", text,
            article_count=10, govt_doc_count=0,
            newspaper_count=0, social_count=0, video_count=0,
        )
        good = validate_citations(
            "KEY DEVELOPMENTS", text,
            article_count=10, govt_doc_count=0,
            newspaper_count=4, social_count=0, video_count=0,
        )
        assert not bad.is_valid
        assert good.is_valid

    def test_empty_text_reports_issue(self) -> None:
        result = validate_citations(
            "FINANCIAL PULSE", "",
            article_count=10, govt_doc_count=0,
            newspaper_count=0, social_count=0, video_count=0,
        )
        assert "empty section" in result.issues

    def test_total_cites_aggregates_pillars(self) -> None:
        text = (
            "Article [1] (Doc: A, p.1) and (Paper: X 2026-04-28) and "
            "(Social: reddit @ 2026-04-28) and (Video: NDTV @ 1:23)."
        )
        result = validate_citations(
            "KEY DEVELOPMENTS", text,
            article_count=5, govt_doc_count=1,
            newspaper_count=1, social_count=1, video_count=1,
        )
        assert result.is_valid
        assert result.total_cites == 5


class TestStripInvalidCitations:
    """strip_invalid_citations drops sentences with bad article cites."""

    def test_drops_offending_sentence_keeps_rest(self) -> None:
        text = "Good cite [1] is fine. Bad cite [99] should disappear."
        cleaned = strip_invalid_citations(text, article_count=5)
        assert "[1]" in cleaned
        assert "[99]" not in cleaned

    def test_keeps_text_when_no_cites_invalid(self) -> None:
        text = "No cites here. Just prose."
        cleaned = strip_invalid_citations(text, article_count=5)
        assert cleaned == text


class TestCountWords:
    def test_empty(self) -> None:
        assert count_words("") == 0

    def test_punctuation_doesnt_count(self) -> None:
        assert count_words("Hello, world!") == 2

    def test_multiple_spaces(self) -> None:
        assert count_words("one   two\tthree\nfour") == 4


class TestBuildIdAllowlist:
    def test_includes_article_range(self) -> None:
        out = build_id_allowlist(
            article_count=10, govt_doc_count=2,
            newspaper_count=3, social_count=4, video_count=1,
        )
        assert "[1]–[10]" in out
        assert "Govt docs in evidence: 2" in out
        assert "Newspaper clippings: 3" in out
        assert "Social posts: 4" in out
        assert "Video clips: 1" in out

    def test_zero_articles_renders_placeholder(self) -> None:
        out = build_id_allowlist(
            article_count=0, govt_doc_count=0,
            newspaper_count=0, social_count=0, video_count=0,
        )
        assert "(no articles)" in out
