"""Unit tests for the Phase-2 landing adapter (pure — no DB).

Verifies each platform's collector fields are promoted onto the shared typed
columns (channel / full_content / source) before the DB upsert, and that the
adapter never mutates the collector's original dict.

    pytest backend/tests/test_land.py -v
"""
from __future__ import annotations

from backend.collectors.cheap_stack.land import _SOURCE, _adapt


def test_adapt_reddit_channel_from_subreddit():
    p = _adapt({"platform": "reddit", "subreddit": "worldnews"}, "reddit")
    assert p["channel"] == "worldnews"
    assert p["source"] == _SOURCE["reddit"]


def test_adapt_youtube_channel_from_author():
    p = _adapt({"platform": "youtube", "author_username": "Zee News"}, "youtube")
    assert p["channel"] == "Zee News"


def test_adapt_wechat_promotes_body_to_full_content():
    p = _adapt({"platform": "wechat", "account": "CCTV", "content": "长文正文"}, "wechat")
    assert p["channel"] == "CCTV"
    assert p["full_content"] == "长文正文"
    assert "content" not in p            # popped so it isn't duplicated into raw


def test_adapt_telegram_channel_preserved():
    p = _adapt({"platform": "telegram", "channel": "rybar"}, "telegram")
    assert p["channel"] == "rybar"


def test_adapt_keeps_explicit_source():
    p = _adapt({"platform": "tiktok", "source": "custom"}, "tiktok")
    assert p["source"] == "custom"       # setdefault: don't override


def test_adapt_is_non_mutating():
    orig = {"platform": "reddit", "subreddit": "x"}
    _adapt(orig, "reddit")
    assert "channel" not in orig and "source" not in orig
