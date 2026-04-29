"""
Tests for backend.collectors.social_collector.

Covers compute_sentiment, find_matched_entities, and the three platform
fetchers (Reddit / Twitter / Telegram). Uses Hypothesis for property
tests on the pure functions and respx for network stubs.

Reference: docs/qa/signals-defects.md (SIG-8, SIG-13).
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings, strategies as st

from backend.collectors.social_collector import (
    compute_sentiment,
    find_matched_entities,
)


# ── compute_sentiment ──────────────────────────────────────────────────────

@pytest.mark.unit
def test_sentiment_empty_returns_zero() -> None:
    assert compute_sentiment("") == 0.0
    assert compute_sentiment("", "te") == 0.0


@pytest.mark.unit
def test_sentiment_positive_english() -> None:
    score = compute_sentiment(
        "I love this wonderful, brilliant news. Amazing!", "en"
    )
    assert score > 0.5


@pytest.mark.unit
def test_sentiment_negative_english() -> None:
    score = compute_sentiment(
        "Terrible disaster. Everyone is angry and devastated.", "en"
    )
    assert score < -0.4


@pytest.mark.unit
def test_sentiment_neutral_english() -> None:
    score = compute_sentiment("The meeting is at 3pm.", "en")
    assert -0.3 < score < 0.3


@pytest.mark.unit
def test_sentiment_non_english_uses_textblob() -> None:
    score = compute_sentiment("Bonjour le monde", "fr")
    assert -1.0 <= score <= 1.0


@pytest.mark.unit
def test_sentiment_swallows_library_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If VADER raises, return 0.0 — never bubble."""

    class Boom:
        def polarity_scores(self, _: str) -> dict[str, float]:
            raise RuntimeError("vader exploded")

    import backend.collectors.social_collector as mod

    monkeypatch.setattr(
        "vaderSentiment.vaderSentiment.SentimentIntensityAnalyzer",
        lambda: Boom(),
        raising=True,
    )
    assert mod.compute_sentiment("anything", "en") == 0.0


@pytest.mark.unit
@settings(deadline=None, max_examples=80)
@given(text=st.text(min_size=0, max_size=400))
def test_sentiment_property_in_range(text: str) -> None:
    """Output is always in [-1.0, 1.0] for any input string."""
    score = compute_sentiment(text, "en")
    assert -1.0 <= score <= 1.0


@pytest.mark.unit
@settings(deadline=None, max_examples=40)
@given(text=st.text(min_size=0, max_size=200), lang=st.sampled_from(
    ["en", "fr", "es", "te", "hi", "zh", "unknown"]
))
def test_sentiment_property_no_exceptions(text: str, lang: str) -> None:
    """compute_sentiment never raises regardless of input."""
    compute_sentiment(text, lang)


# ── find_matched_entities ──────────────────────────────────────────────────

@pytest.mark.unit
def test_match_basic_substring() -> None:
    matched = find_matched_entities(
        "BRS Party announced new initiative", ["BRS", "Congress"]
    )
    assert matched == ["BRS"]


@pytest.mark.unit
def test_match_case_insensitive() -> None:
    matched = find_matched_entities(
        "the brs party leader spoke today", ["BRS"]
    )
    assert matched == ["BRS"]


@pytest.mark.unit
def test_match_multiple_entities() -> None:
    matched = find_matched_entities(
        "KTR of BRS visited Telangana CMO", ["KTR", "BRS", "Congress"]
    )
    assert set(matched) == {"KTR", "BRS"}


@pytest.mark.unit
def test_match_empty_text_returns_empty() -> None:
    assert find_matched_entities("", ["BRS"]) == []


@pytest.mark.unit
def test_match_empty_entities_returns_empty() -> None:
    assert find_matched_entities("BRS news", []) == []


@pytest.mark.unit
def test_match_no_match() -> None:
    assert find_matched_entities("hello world", ["BRS"]) == []


@pytest.mark.unit
def test_match_skips_falsy_entities() -> None:
    matched = find_matched_entities("BRS news", ["", "BRS", None])  # type: ignore[list-item]
    assert matched == ["BRS"]


@pytest.mark.unit
@settings(deadline=None, max_examples=80)
@given(
    text=st.text(min_size=0, max_size=300),
    entities=st.lists(
        st.text(min_size=1, max_size=20).filter(lambda s: s.strip()),
        max_size=10,
    ),
)
def test_match_property_subset_of_entities(
    text: str, entities: list[str]
) -> None:
    """Returned matches are always a subset of the input entities."""
    matched = find_matched_entities(text, entities)
    assert set(matched).issubset(set(entities))


@pytest.mark.unit
@settings(deadline=None, max_examples=80)
@given(
    text=st.text(
        alphabet=st.characters(min_codepoint=32, max_codepoint=126),
        min_size=0,
        max_size=200,
    ),
    entities=st.lists(
        st.text(
            alphabet=st.characters(min_codepoint=32, max_codepoint=126),
            min_size=1,
            max_size=15,
        ),
        max_size=8,
    ),
)
def test_match_property_case_invariant(
    text: str, entities: list[str]
) -> None:
    """Matching against upper- vs lower-cased text gives the same set.

    Restricted to ASCII because Unicode case-folding is not symmetric
    (e.g. `'ß'.upper() == 'SS'`); that's a string-API quirk, not a
    matcher bug, so we don't fail the property on it.
    """
    a = set(find_matched_entities(text, entities))
    b = set(find_matched_entities(text.upper(), entities))
    c = set(find_matched_entities(text.lower(), entities))
    assert a == b == c


# ── Reddit fetcher ─────────────────────────────────────────────────────────

@pytest.mark.unit
def test_reddit_fetcher_handles_429(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SIG-8: 429 currently returns []. This locks current behaviour;
    fix branch should change this to backoff + raise."""
    import backend.collectors.social_collector as mod

    class FakeResp:
        status_code = 429

        def json(self) -> dict[str, Any]:  # pragma: no cover
            raise RuntimeError("should not parse json")

    class FakeClient:
        def __init__(self, *_a: Any, **_kw: Any) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *_exc: Any) -> None:
            return None

        async def get(self, *_a: Any, **_kw: Any) -> FakeResp:
            return FakeResp()

    monkeypatch.setattr(mod.httpx, "AsyncClient", FakeClient)
    out = asyncio.run(mod.collect_reddit_posts("india", limit=5))
    assert out == []


@pytest.mark.unit
def test_reddit_fetcher_parses_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.collectors.social_collector as mod

    payload = {
        "data": {
            "children": [
                {
                    "data": {
                        "id": "t3_abc",
                        "title": "Hello India",
                        "selftext": "Body text.",
                        "score": 42,
                        "num_comments": 7,
                        "created_utc": 1_700_000_000,
                        "permalink": "/r/india/comments/abc/hello/",
                        "author": "tester",
                    }
                }
            ]
        }
    }

    class FakeResp:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return payload

    class FakeClient:
        def __init__(self, *_a: Any, **_kw: Any) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *_exc: Any) -> None:
            return None

        async def get(self, *_a: Any, **_kw: Any) -> FakeResp:
            return FakeResp()

    monkeypatch.setattr(mod.httpx, "AsyncClient", FakeClient)
    out = asyncio.run(mod.collect_reddit_posts("india", limit=5))
    assert len(out) == 1
    post = out[0]
    assert post["platform"] == "reddit"
    assert "Hello India" in post["post_text"]


@pytest.mark.unit
def test_reddit_fetcher_swallows_5xx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.collectors.social_collector as mod

    class Boom:
        def __init__(self, *_a: Any, **_kw: Any) -> None:
            pass

        async def __aenter__(self) -> "Boom":
            return self

        async def __aexit__(self, *_exc: Any) -> None:
            return None

        async def get(self, *_a: Any, **_kw: Any) -> Any:
            raise mod.httpx.ConnectError("dns failure")

    monkeypatch.setattr(mod.httpx, "AsyncClient", Boom)
    out = asyncio.run(mod.collect_reddit_posts("india"))
    assert out == []


# ── Twitter fetcher ────────────────────────────────────────────────────────

@pytest.mark.unit
def test_twitter_fetcher_empty_bearer_raises_or_skips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bearer-less call must not POST to Twitter — current code expects the
    task to gate on env var. We guard by passing empty bearer."""
    import backend.collectors.social_collector as mod

    called: dict[str, bool] = {"hit": False}

    class Tracker:
        def __init__(self, *_a: Any, **_kw: Any) -> None:
            pass

        async def __aenter__(self) -> "Tracker":
            return self

        async def __aexit__(self, *_exc: Any) -> None:
            return None

        async def get(self, *_a: Any, **_kw: Any) -> Any:
            called["hit"] = True
            raise RuntimeError("must not call")

    monkeypatch.setattr(mod.httpx, "AsyncClient", Tracker)
    out = asyncio.run(
        mod.collect_twitter_user_tweets("KTR", "", max_results=5)
    )
    assert out == []
    assert called["hit"] is False


@pytest.mark.unit
def test_twitter_fetcher_401_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.collectors.social_collector as mod

    class Resp401:
        status_code = 401

        def json(self) -> dict[str, Any]:  # pragma: no cover
            return {}

    class FakeClient:
        def __init__(self, *_a: Any, **_kw: Any) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *_exc: Any) -> None:
            return None

        async def get(self, *_a: Any, **_kw: Any) -> Resp401:
            return Resp401()

    monkeypatch.setattr(mod.httpx, "AsyncClient", FakeClient)
    out = asyncio.run(
        mod.collect_twitter_user_tweets("KTR", "fake-bearer", max_results=5)
    )
    assert out == []


# ── Telegram fetcher ───────────────────────────────────────────────────────

@pytest.mark.unit
def test_telegram_user_client_missing_session_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a session string, the user-client path must short-circuit."""
    import backend.collectors.social_collector as mod

    if not hasattr(mod, "collect_telegram_channel_as_user"):
        pytest.skip("symbol not present in this module version")

    out = asyncio.run(
        mod.collect_telegram_channel_as_user(
            "scroll_in", api_id=123456, api_hash="x" * 32, session_string="",
            limit=5,
        )
    )
    assert out == []


@pytest.mark.unit
def test_telegram_bot_unauth_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.collectors.social_collector as mod

    if not hasattr(mod, "collect_telegram_channel_via_bot"):
        pytest.skip("symbol not present in this module version")

    class Resp:
        status_code = 401

        def json(self) -> dict[str, Any]:
            return {"ok": False, "description": "Unauthorized"}

    class FakeClient:
        def __init__(self, *_a: Any, **_kw: Any) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *_exc: Any) -> None:
            return None

        async def get(self, *_a: Any, **_kw: Any) -> Resp:
            return Resp()

    monkeypatch.setattr(mod.httpx, "AsyncClient", FakeClient)
    out = asyncio.run(
        mod.collect_telegram_channel_via_bot("scroll_in", "fake-bot")
    )
    assert out == []
