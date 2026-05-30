"""Grounded prose synthesis for brief blocks — faithfulness-gated.

Thin wrapper over the ported multi-key Groq/Cerebras pool (``groq_client.py``).
The pool is imported **lazily inside the call** so a missing-key environment
degrades to the caller's template fallback instead of crashing the service at
import time (``groq_client`` builds its key manager at import and *raises* if
``GROQ_API_KEYS`` is unset).

Contract: ``synthesize_paragraph`` returns a clean one-paragraph string on
success, or ``None`` on ANY failure — no keys, timeout, pool error, empty/short
output, or output failing the faithfulness gate. Callers MUST always have a
deterministic template fallback for the ``None`` case.

Design choices:
  * Numeric faithfulness gate — every multi-digit number in the model output
    must already appear in the source facts. Fabricated figures (₹1,000 cr,
    16 lakh) are the single highest-risk hallucination for an intelligence
    brief; names are far lower risk because we feed the real entity-tagged
    headlines. The gate is deterministic and adds no second LLM call.
  * ``<think>`` stripping — the pool's model (qwen3-32b) is a reasoning model
    that can emit ``<think>…</think>``. We both request ``/no_think`` and strip
    defensively.
"""
from __future__ import annotations

import asyncio
import logging
import re

logger = logging.getLogger("osint-backend.llm_synth")

# qwen3-32b at ~120 words returns in 1-3s; 14s is a generous hard ceiling so the
# endpoint degrades to the template rather than hanging if the pool is slow.
_TIMEOUT_S = 14.0

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_NUM = re.compile(r"\d[\d,\.]*\d|\d")
_WS = re.compile(r"\s+")


def _strip_think(s: str) -> str:
    return _THINK.sub("", s or "").strip()


def _numbers(s: str) -> set[str]:
    """Normalised numeric tokens (separators removed) for containment checks."""
    return {re.sub(r"[,\.]", "", m) for m in _NUM.findall(s or "")}


def _faithful(output: str, source: str) -> bool:
    """Every multi-digit number in *output* must appear in *source*.

    Single digits ("1 of 3", "two") are ignored as ordinary prose; only
    multi-digit figures — the dangerous, specific ones — are policed.
    """
    src = _numbers(source)
    for n in _numbers(output):
        if len(n) <= 1:
            continue
        if n not in src:
            logger.warning("llm_synth: unsupported number %r in output → reject", n)
            return False
    return True


def _clean_paragraph(raw: str) -> str:
    """Collapse a model response into a single trimmed paragraph."""
    text = _strip_think(raw)
    text = _WS.sub(" ", text).strip()
    # Models sometimes wrap the whole answer in quotes — drop a single outer pair.
    if len(text) >= 2 and text[0] in "\"'" and text[-1] in "\"'":
        text = text[1:-1].strip()
    return text


async def synthesize_paragraph(
    *, system: str, facts: str, source_check: str,
    min_words: int = 12, min_chars: int = 40,
) -> str | None:
    """Synthesise one grounded paragraph, or ``None`` to signal use-the-template.

    Args:
        system: system prompt (rules + role). Should forbid invention.
        facts: the user message — the real, labelled facts to synthesise.
        source_check: text the faithfulness gate validates numbers against
            (typically the raw headlines the facts were built from).
    """
    try:
        from groq_client import generate  # lazy: avoid import-time key crash
    except Exception as exc:  # noqa: BLE001 — degrade, never crash the endpoint
        logger.warning("llm_synth: pool unavailable (%s); using template", exc)
        return None

    try:
        raw = await asyncio.wait_for(
            generate(system=system, user=facts, task_type="brief_generation"),
            timeout=_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        logger.warning("llm_synth: timed out after %.0fs; using template", _TIMEOUT_S)
        return None
    except Exception as exc:  # noqa: BLE001 — pool exhaustion / network / SDK
        logger.warning("llm_synth: pool error (%s); using template", exc)
        return None

    text = _clean_paragraph(raw)
    if len(text) < min_chars or len(text.split()) < min_words:
        logger.warning("llm_synth: output too short (%d chars); using template", len(text))
        return None
    if not _faithful(text, source_check):
        return None
    return text
