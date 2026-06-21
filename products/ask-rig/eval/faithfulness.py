"""LLM-judge faithfulness scoring (lightweight Ragas-style, no langchain dep).

Faithfulness = of the atomic factual claims in an answer, what fraction are
*supported by the retrieved context*. Correctness != faithfulness: a model can
state a true fact that the cited source doesn't actually back (SIGIR'25 found up
to 57% post-rationalized citations). Our server-side cite-ID guardrail only checks
that [S#] *resolves* to a doc; this checks whether the doc *supports the claim*.

One judge call per answer: extract claims + verdict in a single structured pass.
Designed to run on a DIFFERENT model than the generator (self-judging is biased).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.llm import LLMProvider
from app.schemas import RetrievedDoc

_JUDGE_SYSTEM = (
    "You are a strict faithfulness auditor for a news RAG system. You are given "
    "numbered SOURCES and an ANSWER. Decompose the ANSWER into atomic factual "
    "claims (ignore filler and hedging). For each claim decide if it is SUPPORTED "
    "— directly stated in or unambiguously inferable from the SOURCES — or NOT. "
    "Judge ONLY against the sources, never outside knowledge. A refusal "
    '("not enough information") counts as fully faithful. '
    'Return ONLY JSON: {"claims":[{"claim":"...","supported":true|false}]}'
)

_REFUSAL_HINT = "doesn't have enough"
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(frozen=True)
class FaithfulnessResult:
    score: float           # supported / total (1.0 if no checkable claims / refusal)
    n_claims: int
    n_supported: int
    parsed: bool           # did the judge return valid JSON?


def _context(docs: list[RetrievedDoc]) -> str:
    lines = []
    for i, d in enumerate(docs, start=1):
        lines.append(f"[S{i}] {d.title or ''}\n    {d.snippet or ''}")
    return "\n".join(lines)


def score_faithfulness(
    judge: LLMProvider, answer: str, docs: list[RetrievedDoc]
) -> FaithfulnessResult:
    if not answer or _REFUSAL_HINT in answer.lower():
        return FaithfulnessResult(1.0, 0, 0, True)

    user = f"SOURCES:\n{_context(docs)}\n\nANSWER:\n{answer}"
    raw = judge.complete(_JUDGE_SYSTEM, user)
    match = _JSON_RE.search(raw)
    if not match:
        return FaithfulnessResult(0.0, 0, 0, False)
    try:
        claims = json.loads(match.group(0)).get("claims", [])
    except (json.JSONDecodeError, AttributeError):
        return FaithfulnessResult(0.0, 0, 0, False)

    total = len(claims)
    if total == 0:
        return FaithfulnessResult(1.0, 0, 0, True)
    supported = sum(1 for c in claims if c.get("supported") is True)
    return FaithfulnessResult(supported / total, total, supported, True)
