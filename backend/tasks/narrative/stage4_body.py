"""Stage 4 — body composer.

Takes the lede + a ranked list of SPO claims and writes the article body.
Body length is target 400-700 words, structured into 4-6 paragraphs.

Anti-recap rule: the body must NOT restate the lede in different words.
Each paragraph must introduce new information (a new claim, a new actor,
a new number, a new context fact).
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


BODY_SYS = """You are a senior reporter writing the body of a news article.

Inputs:
- A lede (already written) — the article opener.
- A ranked list of SPO claims (subject, predicate, object).
- An optional context block.

Return STRICT JSON: {"body": "..."}.

RULES:
- 400-700 words total. 4-6 paragraphs. Each paragraph 60-130 words.
- Paragraph 1 expands the lede with the source/timing/who-said-it.
- Each subsequent paragraph introduces NEW information — a new claim,
  a new actor, a new number, a new context fact. NEVER restate the lede.
- Attribute every claim to its claimant or anchor it to a specific source.
- Use the SUBJECT of each claim as a sentence subject — do not bury actors
  in passive voice ("was announced by X").
- Forbidden: "experts say", "sources told", "it has emerged", "it is learnt".
- Numbers: always include unit + reference period ("rose 4.2% year-on-year").
- No prose outside the JSON. No markdown fences. Use \\n\\n for paragraph breaks.
"""


@dataclass(frozen=True)
class BodyOutput:
    body: str
    word_count: int


async def compose_body(
    lede: str,
    claims_ranked: list[dict],
    context: str = "",
) -> BodyOutput | None:
    user = (
        "LEDE:\n" + lede.strip()
        + "\n\nRANKED CLAIMS:\n" + json.dumps(claims_ranked[:12], ensure_ascii=False)
        + (f"\n\nCONTEXT:\n{context[:600]}" if context else "")
        + "\n\nReturn the JSON object."
    )
    try:
        raw = await call_groq(
            system=BODY_SYS,
            user=user,
            model=FAST_MODEL,
            task_type="generation",
            json_response=True,
            max_tokens_override=2200,
        )
    except (GroqCallFailed, GroqQuotaExhausted) as e:
        logger.warning("body composition failed: %s", e)
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    body = (parsed.get("body") or "").strip()
    if not body or len(body.split()) < 200:
        return None
    return BodyOutput(body=body[:6000], word_count=len(body.split()))
