"""Unit tests for the box-native free-transcript provider pool.

Pure logic (no network): the content guard that rejects HTML/bot pages, and the
pool failover. The guard exists because a naive length check let an Invidious
'are you a bot' page pass as a transcript — these tests pin that it can't recur.

    pytest backend/tests/test_free_transcript.py -v
"""
from __future__ import annotations

import backend.collectors.youtube_v2.free_transcript as ft
from backend.collectors.youtube_v2.free_transcript import (
    FreeTranscript,
    _looks_like_transcript,
    _strip_caption_markup,
    fetch_free_transcript,
)


# ── caption markup stripping (Piped TTML / VTT) ──────────────────────────────

def test_strip_ttml():
    ttml = '<tt xml:lang="en"><body><div><p begin="0s">Hello&#39;s world</p>' \
           '<p begin="2s">second line</p></div></body></tt>'
    out = _strip_caption_markup(ttml)
    assert "Hello's world" in out and "second line" in out
    assert "<" not in out


def test_strip_vtt_drops_timing():
    vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nOperation Sindoor\n\n" \
          "00:00:04.000 --> 00:00:06.000\nwas launched"
    out = _strip_caption_markup(vtt)
    assert "Operation Sindoor was launched" in out
    assert "-->" not in out and "WEBVTT" not in out


# ── content guard ────────────────────────────────────────────────────────────

def test_guard_accepts_real_transcript():
    assert _looks_like_transcript("Operation Sindoor was launched on May 6 " * 5)


def test_guard_rejects_html_page():
    assert not _looks_like_transcript("<!DOCTYPE html>\n<html><head>...</head>")


def test_guard_rejects_bot_challenge():
    assert not _looks_like_transcript("Just a moment... checking your browser " * 5)
    assert not _looks_like_transcript("Making sure you're not a bot! " * 5)


def test_guard_rejects_too_short_and_empty():
    assert not _looks_like_transcript("hi")
    assert not _looks_like_transcript("")
    assert not _looks_like_transcript(None)


# ── pool failover ────────────────────────────────────────────────────────────

def _stub_pool(monkeypatch, providers):
    monkeypatch.setattr(ft, "_PROVIDERS", providers)


def test_returns_first_valid_provider(monkeypatch):
    _stub_pool(monkeypatch, [("good", lambda v: ("Real transcript text " * 10, False))])
    r = fetch_free_transcript("vid1")
    assert isinstance(r, FreeTranscript)
    assert r.provider == "good" and r.chars > 80


def test_fails_over_past_broken_and_html_providers(monkeypatch):
    def boom(v): raise RuntimeError("down")
    def htmlpage(v): return ("<!DOCTYPE html> bot wall", False)
    def good(v): return ("Actual spoken transcript content here " * 5, True)
    _stub_pool(monkeypatch, [("boom", boom), ("html", htmlpage), ("good", good)])
    r = fetch_free_transcript("vid2")
    assert r is not None and r.provider == "good"
    assert r.truncated is True          # hasMore propagated


def test_returns_none_when_all_fail(monkeypatch):
    _stub_pool(monkeypatch, [("html", lambda v: ("<html>nope</html>", False)),
                             ("none", lambda v: None)])
    assert fetch_free_transcript("vid3") is None


def test_empty_video_id_is_none():
    assert fetch_free_transcript("") is None
