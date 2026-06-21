"""The coverage-reflection step — the chat's one agentic escalation.

After the first retrieval pass, a hard multi-part question ("compare X and Y on
A, B and C", "what's the latest across infra, education AND politics") is often
under-covered: the fan-out found plenty on one part and nothing on another. A
single pass can't tell — so we reflect.

``assess_coverage`` shows the LLM the question and the HEADLINES we retrieved and
asks one thing: does every distinct part of the question have support, and if not,
what focused searches would fill the gaps? The orchestrator then runs a bounded
second retrieval for those gaps and synthesises over the enriched context.

This only fires on complex query types (the planner's classification), runs at most
once, and returns at most ``_MAX_GAPS`` gap queries. Best-effort: returns ``None``
on any failure so the turn proceeds on the single-pass context.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Sequence

from app.llm import LLMProvider

logger = logging.getLogger("ask-rig.reflect")

_MAX_GAPS = 2          # never spawn more than this many follow-up searches
_MAX_HEADLINES = 16    # headlines shown to the assessor (keep the prompt cheap)


@dataclass(frozen=True)
class Coverage:
    """The reflection verdict. ``gaps`` is non-empty only when ``sufficient`` is False."""

    sufficient: bool
    gaps: list[str]


_ASSESS_SYSTEM = (
    "You are the coverage check in a news-retrieval pipeline. You are given a user's "
    "QUESTION and the HEADLINES of the sources retrieved so far. Decide whether those "
    "headlines, taken together, can support a COMPLETE answer to EVERY distinct part of "
    "the question.\n"
    "- If the question has multiple parts / sub-topics / named things and one of them has "
    "NO supporting headline, it is NOT sufficient: return a focused search query that would "
    "find that missing part.\n"
    "- If coverage is already good, say so — do NOT invent gaps to look thorough.\n"
    "- Return at most 2 gap queries, each a short standalone search string (under 9 words).\n"
    "Output ONLY a single JSON object, no prose, no markdown fences:\n"
    '{"sufficient": boolean, "gaps": string[]}'
)


def _extract_json(raw: str) -> dict | None:
    """First balanced JSON object in an LLM response (tolerates fences / prose)."""
    if not raw:
        return None
    raw = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1)
    start = raw.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(raw[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _coerce(data: dict) -> Coverage:
    sufficient = bool(data.get("sufficient", True))
    raw_gaps = data.get("gaps") or []
    gaps: list[str] = []
    if isinstance(raw_gaps, list):
        seen: set[str] = set()
        for g in raw_gaps:
            s = str(g).strip()
            key = s.lower()
            if s and key not in seen:
                seen.add(key)
                gaps.append(s)
            if len(gaps) >= _MAX_GAPS:
                break
    # A "sufficient" verdict never carries gaps; an "insufficient" verdict with no
    # gaps is useless (nothing actionable) — treat it as sufficient.
    if sufficient or not gaps:
        return Coverage(sufficient=True, gaps=[])
    return Coverage(sufficient=False, gaps=gaps)


def assess_coverage(
    llm: LLMProvider, query: str, headlines: Sequence[str]
) -> Coverage | None:
    """Judge whether ``headlines`` cover every part of ``query``. Returns ``None`` on
    any failure (caller proceeds on the single-pass context). Blocking — run off-loop."""
    titles = [h.strip() for h in headlines if h and h.strip()][:_MAX_HEADLINES]
    if not query.strip() or not titles:
        return None
    listing = "\n".join(f"- {t}" for t in titles)
    user = f"QUESTION: {query}\n\nHEADLINES:\n{listing}\n\nJSON verdict:"
    try:
        raw = llm.complete(_ASSESS_SYSTEM, user)
    except Exception as exc:  # noqa: BLE001 - reflection must never break a turn
        logger.debug("coverage LLM failed: %s", exc)
        return None
    data = _extract_json(raw)
    if not isinstance(data, dict):
        logger.debug("coverage returned non-JSON: %.120r", raw)
        return None
    try:
        return _coerce(data)
    except Exception as exc:  # noqa: BLE001
        logger.debug("coverage coerce failed: %s", exc)
        return None
