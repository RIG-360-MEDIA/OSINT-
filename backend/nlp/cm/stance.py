"""
Stance classifier for CM Page.

Uses Groq FAST_MODEL (llama-3.1-8b-instant) for cheap per-item classification.
Returns one of:
    ruling_supportive | opposition_attack | neutral_factual | mixed | unknown

Confidence is parsed from the model's stated certainty when present; defaults
to 0.6 when the label is given without one. Anything we cannot parse maps to
('unknown', 0.0) so the row is still upserted but does not bias aggregates.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from backend.nlp.cm import coalitions
from backend.nlp.groq_client import (
    GroqCallFailed,
    GroqQuotaExhausted,
    classify,
)

logger = logging.getLogger(__name__)

VALID_LABELS = {
    "ruling_supportive",
    "opposition_attack",
    "neutral_factual",
    "mixed",
    "unknown",
}

_TEXT_CAP = 1500


@dataclass(frozen=True)
class StanceResult:
    stance: str
    party_kind: str
    confidence: float
    model: str


def _build_system(state: str | None, ruling: list[str], opposition: list[str]) -> str:
    state_label = state or "the state"
    ruling_str = ", ".join(ruling) if ruling else "(unknown)"
    opp_str = ", ".join(opposition) if opposition else "(unknown)"
    return (
        "You classify the political stance of an Indian state-politics text.\n"
        f"State: {state_label}.\n"
        f"Ruling coalition parties: {ruling_str}.\n"
        f"Opposition parties: {opp_str}.\n"
        "Return EXACTLY one label and nothing else, on a single line. Choose from:\n"
        "  ruling_supportive   — defends or praises ruling parties / govt actions\n"
        "  opposition_attack   — criticises ruling parties / govt; or amplifies opposition framing\n"
        "  neutral_factual     — reports facts without taking sides\n"
        "  mixed               — substantive content from both sides, no dominant frame\n"
        "  unknown             — too short / unclear / not political\n"
        "After the label, output one space and a confidence number in [0,1].\n"
        "Format: <label> <confidence>"
    )


def _build_user(text: str, party: str | None, role: str | None) -> str:
    party_line = f"Speaker party: {party}\n" if party else ""
    role_line = f"Speaker role: {role}\n" if role else ""
    body = (text or "").strip().replace("", "")[:_TEXT_CAP]
    return f"{party_line}{role_line}Text:\n{body}"


_LABEL_RE = re.compile(
    r"^\s*(ruling_supportive|opposition_attack|neutral_factual|mixed|unknown)\b"
    r"(?:\s+([01](?:\.\d+)?))?",
    re.IGNORECASE,
)


def _parse(reply: str) -> tuple[str, float]:
    if not reply:
        return ("unknown", 0.0)
    m = _LABEL_RE.match(reply.strip())
    if not m:
        return ("unknown", 0.0)
    label = m.group(1).lower()
    conf_raw = m.group(2)
    try:
        conf = float(conf_raw) if conf_raw else 0.6
    except ValueError:
        conf = 0.6
    if label not in VALID_LABELS:
        return ("unknown", 0.0)
    return (label, max(0.0, min(1.0, conf)))


async def score(
    *,
    text: str,
    state: str | None,
    party: str | None = None,
    role: str | None = None,
) -> StanceResult:
    """Classify a single piece of text. Never raises — quota / API failures
    return ('unknown', 0.0) so the upserter can still record the attempt."""
    if not text or len(text.strip()) < 12:
        return StanceResult("unknown", "neutral", 0.0, "skipped-too-short")

    ruling = await coalitions.parties_for(state, "ruling") if state else []
    opposition = await coalitions.parties_for(state, "opposition") if state else []
    party_kind = await coalitions.party_kind(state, party) if party else "neutral"

    sys_prompt = _build_system(state, ruling, opposition)
    user_prompt = _build_user(text, party, role)

    try:
        reply = await classify(sys_prompt, user_prompt)
    except (GroqQuotaExhausted, GroqCallFailed) as exc:
        logger.info("stance classify failed (%s) — recording unknown", exc)
        return StanceResult("unknown", party_kind, 0.0, "groq-failed")

    label, conf = _parse(reply)
    return StanceResult(label, party_kind, conf, "llama-3.1-8b-instant")
