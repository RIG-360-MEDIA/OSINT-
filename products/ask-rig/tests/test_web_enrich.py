"""Unit tests for web full-text enrichment (network mocked). Focus: only top-N
fetched, failures keep the snippet, cap applied, caching, and the kill switch."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.web.extract as ex
from app.schemas_account import WebResult


def _settings(enabled=True, cap=1600):
    return SimpleNamespace(web_extract_enabled=enabled, web_extract_max_chars=cap)


def _results(n):
    return [WebResult(title=f"t{i}", url=f"https://ex.com/{i}", snippet="short") for i in range(n)]


@pytest.fixture(autouse=True)
def _clear_cache(monkeypatch):
    ex._EXTRACT_CACHE.clear()
    yield
    ex._EXTRACT_CACHE.clear()


async def _run(settings, results, top_n, fake):
    import app.web.extract as mod

    async def fake_fetch(_s, url):
        return fake(url)

    # patch the underlying fetch; _cached_extract wraps it
    orig = mod.fetch_extract
    mod.fetch_extract = fake_fetch
    try:
        return await mod.enrich_web_results(settings, results, top_n)
    finally:
        mod.fetch_extract = orig


@pytest.mark.asyncio
async def test_only_top_n_enriched():
    out = await _run(_settings(), _results(5), 2, lambda u: "FULL ARTICLE TEXT " * 5)
    assert out[0].snippet.startswith("FULL ARTICLE TEXT")  # enriched
    assert out[1].snippet.startswith("FULL ARTICLE TEXT")
    assert out[2].snippet == "short"  # beyond top-N, untouched
    assert out[4].snippet == "short"
    assert len(out) == 5


@pytest.mark.asyncio
async def test_failure_keeps_snippet():
    out = await _run(_settings(), _results(2), 2, lambda u: None)
    assert all(r.snippet == "short" for r in out)


@pytest.mark.asyncio
async def test_not_richer_keeps_snippet():
    # extracted text no longer than the snippet -> not worth swapping
    out = await _run(_settings(), _results(1), 1, lambda u: "tiny")
    assert out[0].snippet == "short"


@pytest.mark.asyncio
async def test_cap_applied():
    out = await _run(_settings(cap=50), _results(1), 1, lambda u: "X" * 500)
    assert len(out[0].snippet) == 50


@pytest.mark.asyncio
async def test_kill_switch_returns_unchanged():
    same = _results(2)
    out = await _run(_settings(enabled=False), same, 2, lambda u: "FULL " * 20)
    assert out is same  # short-circuits, no fetch


@pytest.mark.asyncio
async def test_cache_avoids_refetch():
    calls = {"n": 0}

    def fake(url):
        calls["n"] += 1
        return "FULL ARTICLE BODY " * 4

    await _run(_settings(), _results(1), 1, fake)
    await _run(_settings(), _results(1), 1, fake)  # same URL -> served from cache
    assert calls["n"] == 1
