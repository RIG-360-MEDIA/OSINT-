"""Tests for per-pillar model routing + cross-model fallback in groq_client.

Pure-logic + monkeypatched-pool tests — no real Groq/Cerebras calls.
"""
from __future__ import annotations

import asyncio

import backend.nlp.groq_client as gc


# ── _resolve_chain (pure) ─────────────────────────────────────────────────────

def test_chain_flag_off_single_model(monkeypatch):
    monkeypatch.setattr(gc, "_MODEL_FALLBACK", False)
    assert gc._resolve_chain(None, "youtube", "generation") == [gc.QUALITY_MODEL]
    assert gc._resolve_chain("pinned", "youtube", "generation") == ["pinned"]


def test_chain_per_pillar_primary(monkeypatch):
    monkeypatch.setattr(gc, "_MODEL_FALLBACK", True)
    assert gc._resolve_chain(None, "articles", "generation")[0] == "qwen/qwen3-32b"
    assert gc._resolve_chain(None, "youtube", "generation")[0] == "llama-3.3-70b-versatile"
    assert gc._resolve_chain(None, "newspapers", "generation")[0] == "openai/gpt-oss-120b"
    # every chain ends on the cheap high-headroom model
    for pillar in ("articles", "youtube", "newspapers"):
        assert gc._resolve_chain(None, pillar, "generation")[-1] == "llama-3.1-8b-instant"


def test_chain_unknown_pillar_and_fast_task(monkeypatch):
    monkeypatch.setattr(gc, "_MODEL_FALLBACK", True)
    assert gc._resolve_chain(None, None, "generation") == gc._DEFAULT_CHAIN
    # fast tasks stay on the single cheap model — no heavy fallback
    assert gc._resolve_chain(None, "articles", "classification") == [gc.FAST_MODEL]


def test_chain_explicit_model_honoured_then_tail(monkeypatch):
    monkeypatch.setattr(gc, "_MODEL_FALLBACK", True)
    ch = gc._resolve_chain("custom-model", "youtube", "generation")
    assert ch[0] == "custom-model"
    assert "custom-model" not in ch[1:]  # no duplicate


# ── call_groq fallback loop (monkeypatched pool) ──────────────────────────────

def _force_unified(monkeypatch):
    monkeypatch.setattr(gc, "_MODEL_FALLBACK", True)
    monkeypatch.setattr(gc, "_PARALLEL_LLM_POOL", True)
    monkeypatch.setattr(gc, "_CEREBRAS_KEYS", ["dummy"])  # ensure unified path


def test_call_groq_falls_through_to_next_model(monkeypatch):
    _force_unified(monkeypatch)
    tried: list[str] = []

    async def fake_pool(messages, model, max_tokens, temperature, json_response):
        tried.append(model)
        if model == "llama-3.3-70b-versatile":   # youtube primary "capped"
            raise gc.GroqQuotaExhausted("capped")
        return f"OK:{model}"

    monkeypatch.setattr(gc, "_call_unified_pool", fake_pool)
    out = asyncio.run(gc.call_groq("sys", "usr", pillar="youtube"))
    assert out == "OK:qwen/qwen3-32b"            # fell through to 2nd in chain
    assert tried == ["llama-3.3-70b-versatile", "qwen/qwen3-32b"]


def test_call_groq_raises_when_whole_chain_exhausted(monkeypatch):
    _force_unified(monkeypatch)

    async def fake_pool(*a, **k):
        raise gc.GroqQuotaExhausted("capped")

    monkeypatch.setattr(gc, "_call_unified_pool", fake_pool)
    try:
        asyncio.run(gc.call_groq("sys", "usr", pillar="articles"))
        assert False, "expected GroqQuotaExhausted"
    except gc.GroqQuotaExhausted:
        pass


def test_call_groq_first_model_wins_no_fallback(monkeypatch):
    _force_unified(monkeypatch)
    tried: list[str] = []

    async def fake_pool(messages, model, *a, **k):
        tried.append(model)
        return f"OK:{model}"

    monkeypatch.setattr(gc, "_call_unified_pool", fake_pool)
    out = asyncio.run(gc.call_groq("sys", "usr", pillar="newspapers"))
    assert out == "OK:openai/gpt-oss-120b"
    assert tried == ["openai/gpt-oss-120b"]      # primary succeeded, no fallback
