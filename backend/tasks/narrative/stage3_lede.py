"""Stage 3 — lede constructor.

Builds the opening 1-3 sentences of the piece. The lede must:
  - Lead with the single most consequential SPO claim
  - Avoid the AI-cliché "In a [adjective] development..." opener
  - Name the subject in the FIRST 5 words
  - Be falsifiable (no vague "experts say" type lines)

Operates on a cluster + the top-ranked claims from Stage 2A (or the top
interrogated claim from Stage 2B for singletons).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from backend.nlp.groq_client import (
    FAST_MODEL,
    GroqCallFailed,
    GroqQuotaExhausted,
    call_groq,
)

logger = logging.getLogger(__name__)


LEDE_SYS = """You are a senior newsroom editor writing the opening of a news article.

You will receive 1-5 SPO (subject, predicate, object) claims and a brief
context. Return STRICT JSON: {"headline": "...", "lede": "..."}.

RULES:
- Lede is 1-3 sentences, max 60 words total.
- The SUBJECT of the most consequential claim must appear in the first 5 words.
- Forbidden openings: "In a [adjective] development", "In what could be",
  "A new report reveals", "Sources say", "It has been reported".
- Forbidden hedges: "appears to", "is said to", "is believed to" — replace
  with the actual subject + predicate, or omit the claim.
- The headline is 6-12 words, declarative, no clickbait, no colon-stack.
- No prose outside the JSON. No markdown fences.
"""


@dataclass(frozen=True)
class LedeOutput:
    headline: str
    lede: str


async def build_lede(
    primary_claim: dict,
    supporting_claims: list[dict],
    context: str = "",
) -> LedeOutput | None:
    """primary_claim and supporting_claims each look like
    {"subject": "...", "predicate": "...", "object": "...", "text": "..."}.
    """
    user = (
        "PRIMARY CLAIM:\n" + json.dumps(primary_claim, ensure_ascii=False)
        + "\n\nSUPPORTING CLAIMS:\n" + json.dumps(supporting_claims, ensure_ascii=False)
        + (f"\n\nCONTEXT (optional):\n{context[:400]}" if context else "")
        + "\n\nReturn the JSON object."
    )
    try:
        raw = await call_groq(
            system=LEDE_SYS,
            user=user,
            model=FAST_MODEL,
            task_type="generation",
            json_response=True,
            max_tokens_override=400,
        )
    except (GroqCallFailed, GroqQuotaExhausted) as e:
        logger.warning("lede generation failed: %s", e)
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    headline = (parsed.get("headline") or "").strip()
    lede = (parsed.get("lede") or "").strip()
    if not headline or not lede:
        return None
    return LedeOutput(headline=headline[:200], lede=lede[:600])
