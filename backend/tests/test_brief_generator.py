"""
Tests for backend.nlp.brief_generator.generate_brief.

The generator fans out 6 concurrent Groq calls. We monkeypatch backend.nlp
.brief_generator.generate to a stub so we can assert:
  - all 6 sections appear in the rendered markdown,
  - per-section failures degrade gracefully (D-BRIEF-14 surfaced),
  - empty article list is handled,
  - finance section gets the topic-filtered subset.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from backend.nlp import brief_generator as gen_module
from backend.nlp.brief_generator import generate_brief

SECTION_HEADERS = [
    "## SITUATION STATUS",
    "## KEY DEVELOPMENTS",
    "## ENTITIES TODAY",
    "## SIGNALS TO WATCH",
    "## FINANCIAL PULSE",
    "## SOURCE COVERAGE",
]


def _profile() -> dict:
    return {
        "role_context": "Test analyst",
        "geo_primary": "Telangana",
    }


def _article(i: int, topic: str = "POLITICS") -> dict:
    return {
        "id": f"a-{i}",
        "title": f"Headline {i}",
        "lead_text_translated": f"Body {i}",
        "topic_category": topic,
        "geo_primary": "Telangana",
        "source_name": f"Source {i % 3}",
        "score_final": 0.9 - i * 0.01,
    }


# ── Happy path ───────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_returns_dict_with_content_articles_and_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_generate(**_: Any) -> str:
        return "stub section text"
    monkeypatch.setattr(gen_module, "generate", fake_generate)

    result = asyncio.run(generate_brief(
        user_id="u",
        user_profile=_profile(),
        user_entities=[{"canonical_name": "Telangana CM"}],
        articles=[_article(i) for i in range(15)],
    ))

    assert result["articles_used"] == 15
    assert result["content"] is not None
    assert "DAILY INTELLIGENCE BRIEF" in result["content"]
    assert isinstance(result["sections"], dict)
    assert len(result["sections"]) == 6


@pytest.mark.unit
def test_all_six_section_headers_in_output(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_generate(**_: Any) -> str:
        return "section body"
    monkeypatch.setattr(gen_module, "generate", fake_generate)

    result = asyncio.run(generate_brief(
        user_id="u",
        user_profile=_profile(),
        user_entities=[],
        articles=[_article(i) for i in range(10)],
    ))
    for header in SECTION_HEADERS:
        assert header in result["content"], f"Missing header: {header}"


# ── Empty inputs ─────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_empty_articles_returns_error_payload() -> None:
    result = asyncio.run(generate_brief(
        user_id="u",
        user_profile=_profile(),
        user_entities=[],
        articles=[],
    ))
    assert result["content"] is None
    assert result["articles_used"] == 0
    assert "No relevant articles" in result["error"]


# ── Partial failure ──────────────────────────────────────────────────────────

@pytest.mark.unit
def test_one_section_failure_does_not_break_other_five(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If 1 of 6 Groq calls raises, the other 5 still render and a placeholder
    appears for the failing one. Surfaces D-BRIEF-14 (the placeholder leaks)."""

    call_counter = {"n": 0}

    async def flaky_generate(**_: Any) -> str:
        call_counter["n"] += 1
        if call_counter["n"] == 3:  # third concurrent task fails
            raise RuntimeError("groq 503")
        return "ok body"

    monkeypatch.setattr(gen_module, "generate", flaky_generate)

    result = asyncio.run(generate_brief(
        user_id="u",
        user_profile=_profile(),
        user_entities=[],
        articles=[_article(i) for i in range(12)],
    ))

    assert result["content"] is not None
    placeholders = [s for s in result["sections"].values() if "Generation failed" in s]
    assert len(placeholders) == 1
    ok_sections = [s for s in result["sections"].values() if s == "ok body"]
    assert len(ok_sections) == 5


# ── Finance topic filter ─────────────────────────────────────────────────────

@pytest.mark.unit
def test_finance_section_uses_only_finance_business_infra_articles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Capture the user-prompts handed to each section to assert finance gets
    the topic-filtered subset (or all-context fallback when no finance articles)."""
    captured: list[dict] = []

    async def capture_generate(**kwargs: Any) -> str:
        captured.append(kwargs)
        return "x"
    monkeypatch.setattr(gen_module, "generate", capture_generate)

    articles = [
        _article(0, "POLITICS"),
        _article(1, "FINANCE"),
        _article(2, "BUSINESS"),
        _article(3, "INFRASTRUCTURE"),
        _article(4, "POLITICS"),
    ]
    asyncio.run(generate_brief(
        user_id="u",
        user_profile=_profile(),
        user_entities=[],
        articles=articles,
    ))

    finance_call = next(
        c for c in captured if "Financial articles" in (c.get("user") or "")
    )
    body = finance_call["user"]
    assert "Headline 1" in body
    assert "Headline 2" in body
    assert "Headline 3" in body
    assert "Headline 0" not in body  # POLITICS excluded
    assert "Headline 4" not in body


# ── Article context truncation ───────────────────────────────────────────────

@pytest.mark.unit
def test_section_user_prompts_are_truncated_to_caps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SITUATION/SIGNALS use [:2000], DEVELOPMENTS uses [:3000], SOURCES [:1000]."""
    captured: list[str] = []

    async def capture_generate(**kwargs: Any) -> str:
        captured.append(kwargs.get("user", ""))
        return "x"
    monkeypatch.setattr(gen_module, "generate", capture_generate)

    long_articles = [_article(i) for i in range(30)]
    asyncio.run(generate_brief(
        user_id="u",
        user_profile=_profile(),
        user_entities=[{"canonical_name": "X"}],
        articles=long_articles,
    ))

    assert all(len(p) <= 5000 for p in captured), "No prompt should exceed sane bounds"
    assert any("Today's top stories" in p for p in captured)
    assert any("Today's articles" in p for p in captured)


# ── Defect-tracking xfail (D-BRIEF-4: no per-call timeout) ───────────────────

@pytest.mark.unit
@pytest.mark.xfail(
    reason="D-BRIEF-4: generate_brief has no asyncio.wait_for around per-section calls.",
    strict=False,
)
def test_slow_groq_call_is_bounded_by_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If one Groq call hangs, generate_brief should not hang the whole flow."""

    async def slow_generate(**_: Any) -> str:
        await asyncio.sleep(60)  # would block forever-ish
        return "x"
    monkeypatch.setattr(gen_module, "generate", slow_generate)

    async def runner() -> dict:
        return await asyncio.wait_for(
            generate_brief(
                user_id="u",
                user_profile=_profile(),
                user_entities=[],
                articles=[_article(i) for i in range(10)],
            ),
            timeout=2.0,
        )

    result = asyncio.run(runner())
    assert result["content"] is not None  # would fail without internal timeout
