"""
Internal dissent detector for CM Page.

Pairs same-party speakers on the same issue within a 48h window and asks
Groq whether the two quotes contradict each other materially. Below the
SEVERITY thresholds the row is dropped — we don't surface "weak murmurs"
as breaks. The endpoint then enforces an additional confidence floor on
read.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from backend.nlp.groq_client import GroqCallFailed, GroqQuotaExhausted, extract_json

logger = logging.getLogger(__name__)

CONFIDENCE_FLOOR = 0.55

_SYSTEM = (
    "You decide whether two political statements from members of the SAME party\n"
    "materially contradict each other on the SAME issue.\n"
    "Return STRICT JSON:\n"
    "{\n"
    "  \"contradicts\": true|false,\n"
    "  \"confidence\": <float in [0,1]>,\n"
    "  \"severity\": \"murmur\"|\"crack\"|\"break\",\n"
    "  \"summary\": \"one sentence describing the contradiction (or empty if none)\"\n"
    "}\n"
    "Definitions:\n"
    "  murmur — different emphasis, no real disagreement\n"
    "  crack  — clear policy or position disagreement\n"
    "  break  — open public attack between members of the same party\n"
)


@dataclass(frozen=True)
class DissentVerdict:
    contradicts: bool
    confidence: float
    severity: str
    summary: str


async def compare(
    *,
    issue_label: str,
    party: str,
    speaker_a: str,
    quote_a: str,
    speaker_b: str,
    quote_b: str,
) -> DissentVerdict | None:
    """Returns None when LLM call fails or output is unparseable.
    Returns a verdict with contradicts=False when there's no real disagreement."""
    if speaker_a.strip().lower() == speaker_b.strip().lower():
        return None
    user = (
        f"Issue: {issue_label}\n"
        f"Party: {party}\n"
        f"Speaker A ({speaker_a}): \"{quote_a.strip()[:600]}\"\n"
        f"Speaker B ({speaker_b}): \"{quote_b.strip()[:600]}\"\n"
    )
    try:
        raw = await extract_json(system=_SYSTEM, user=user)
    except (GroqQuotaExhausted, GroqCallFailed) as exc:
        logger.info("dissent compare failed (%s)", exc)
        return None

    payload = raw
    if isinstance(raw, str):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None

    contradicts = bool(payload.get("contradicts"))
    try:
        conf = float(payload.get("confidence") or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    severity = (payload.get("severity") or "murmur").strip().lower()
    if severity not in {"murmur", "crack", "break"}:
        severity = "murmur"
    summary = (payload.get("summary") or "").strip()

    if conf < CONFIDENCE_FLOOR:
        return DissentVerdict(False, conf, severity, summary)
    return DissentVerdict(contradicts, conf, severity, summary)
