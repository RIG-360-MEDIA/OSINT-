"""LLM-as-judge for the cluster-assignment ambiguity zone.

Called only when the top candidate's cosine distance falls between
HARD_MATCH_MAX_DISTANCE and HARD_REJECT_MIN_DISTANCE — the gray zone
where embedding similarity alone cannot reliably decide.

Uses the existing unified LLM pool (groq_client.call_groq) which
routes across 24 Groq keys + 27 Cerebras keys + Ollama failover. We
do NOT pick a model — the pool decides; classification task_type
keeps it on a fast model.
"""
from __future__ import annotations

import json
import logging
from typing import Sequence

from backend.nlp.groq_client import (
    GroqCallFailed,
    GroqQuotaExhausted,
    call_groq,
)
from backend.nlp.story_clustering.types import (
    Article,
    CandidateThread,
    JudgeVerdict,
)

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You cluster news articles into stories. Two articles belong to "
    "the SAME story only if they describe the same specific "
    "event/incident/announcement (e.g., two outlets covering one "
    "press conference, one protest, one court hearing, or successive "
    "days of one unfolding crisis). They are DIFFERENT stories if "
    "they share a topic, person, or location but cover distinct "
    "events (two different speeches by the same minister, two "
    "unrelated accidents, the same actor at different events). "
    "When in doubt, return NEW."
)

_USER_TEMPLATE = """ARTICLE
Source: {src} | Lang: {lang}
Title: {title}
Subject: {subject}
Summary: {summary}

CANDIDATE STORIES (numbered 1..N — pick the SAME story or NEW):
{candidates}

Output STRICT JSON: {{"match": <int N or "NEW">, "confidence": <0.0..1.0>, "reason": "<one sentence>"}}"""


def _format_candidate(idx: int, c: CandidateThread) -> str:
    seed_title = (c.seed_title or c.title or "")[:160]
    seed_summary = (c.seed_summary or "")[:380]
    return (
        f"{idx}. {seed_title}\n"
        f"   Articles in story: {c.article_count} from {c.source_count} sources.\n"
        f"   Sample summary: {seed_summary}"
    )


async def is_same_story(
    article: Article,
    candidates: Sequence[CandidateThread],
) -> JudgeVerdict:
    """Ask the LLM to either pick one candidate or say NEW.

    On any LLM failure we fall back to NEW with confidence 0.0 — the
    pipeline interprets that as "spawn a fresh thread." Failing-safe
    here is intentional: a singleton is recoverable on the next
    consolidation sweep, but a wrong merge is not.
    """
    if not candidates:
        return JudgeVerdict(matched_thread_id=None, confidence=0.0, reasoning="no candidates")

    rendered = "\n".join(_format_candidate(i + 1, c) for i, c in enumerate(candidates))
    user = _USER_TEMPLATE.format(
        src=article.source_name,
        lang=article.language_detected or "?",
        title=(article.title or "")[:160],
        subject=(article.primary_subject or "")[:200],
        summary=(article.summary_executive or "")[:600],
        candidates=rendered,
    )

    try:
        raw = await call_groq(
            system=_SYSTEM,
            user=user,
            task_type="classification",
            json_response=True,
            max_tokens_override=200,
        )
    except (GroqQuotaExhausted, GroqCallFailed) as exc:
        logger.warning("LLM judge failed for article %s — spawning new: %s", article.id, exc)
        return JudgeVerdict(matched_thread_id=None, confidence=0.0, reasoning=f"llm-error: {exc}")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("LLM judge non-JSON for article %s: %s", article.id, raw[:200])
        return JudgeVerdict(matched_thread_id=None, confidence=0.0, reasoning="non-json response")

    match = parsed.get("match")
    confidence = float(parsed.get("confidence") or 0.0)
    reason = str(parsed.get("reason") or "")[:300]

    if match == "NEW" or match is None:
        return JudgeVerdict(matched_thread_id=None, confidence=confidence, reasoning=reason)

    try:
        idx = int(match) - 1
    except (TypeError, ValueError):
        return JudgeVerdict(matched_thread_id=None, confidence=0.0, reasoning=f"bad index: {match!r}")

    if idx < 0 or idx >= len(candidates):
        return JudgeVerdict(matched_thread_id=None, confidence=0.0, reasoning=f"index out of range: {idx}")

    return JudgeVerdict(
        matched_thread_id=candidates[idx].thread_id,
        confidence=max(0.0, min(1.0, confidence)),
        reasoning=reason,
    )
