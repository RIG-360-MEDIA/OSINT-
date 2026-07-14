"""Core sentiment scoring: per-entity, two-field (stance + impact), guided JSON.

The single source of truth for the prompt + schema. Both the production backfill
and the quality harness import from here so they can never drift apart.

Calls an OpenAI-compatible endpoint (vLLM / TabbyAPI / Ollama in the pool) with
schema-constrained decoding so every response is valid JSON by construction.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

# --- the schema the decoder is CONSTRAINED to (guarantees valid, closed JSON) ---
SENTIMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "stance": {"type": "string", "enum": ["positive", "negative", "neutral"]},
        "impact": {"type": "string", "enum": ["positive", "negative", "neutral", "not_relevant"]},
        # confidence in the IMPACT call (the hard field). 0..1. Lets us gate/route:
        # surface high-confidence, send low-confidence to review or the 32B.
        "impact_confidence": {"type": "number"},
        "note": {"type": "string"},
    },
    "required": ["stance", "impact"],
    "additionalProperties": False,
}

# impact is ORDINAL on the harm<->benefit axis; not_relevant is OFF-axis (own bucket).
# Used for tolerant scoring: neutral-vs-negative is a near-miss, not a full miss.
IMPACT_ORDINAL = {"negative": -1, "neutral": 0, "positive": 1}


def impact_distance(a: str, b: str) -> int | None:
    """Ordinal gap between two impact labels on the harm<->benefit axis.
    Returns None when either side is not_relevant (off-axis: exact-match only)."""
    if a not in IMPACT_ORDINAL or b not in IMPACT_ORDINAL:
        return None
    return abs(IMPACT_ORDINAL[a] - IMPACT_ORDINAL[b])

SYSTEM_PROMPT = (
    "You are a precise media analyst. Judge the SUBJECT on TWO INDEPENDENT dimensions:\n"
    "- stance: the TONE the article's author takes toward the subject — does the text "
    "PRAISE it, CRITICISE it, or neither? (positive/negative/neutral)\n"
    "- impact: whether the EVENTS described are GOOD or BAD for the subject's real-world "
    "interests, IGNORING tone. (positive/negative/neutral/not_relevant)\n"
    "These often differ: a neutral-toned report of the subject losing a contract is "
    "stance=neutral but impact=negative. Use not_relevant if the subject has no stake."
)

# how the stance/impact map to the legacy article_stances vocabulary, if needed
STANCE_TO_LEGACY = {"positive": "supportive", "negative": "critical", "neutral": "neutral"}

MAX_TEXT_CHARS = 1500  # title+lead is enough and keeps prefill cheap


@dataclass(frozen=True)
class SentimentResult:
    entity: str
    stance: str
    impact: str
    impact_confidence: float = 1.0
    note: str = ""


def build_messages(entity: str, text: str) -> list[dict[str, str]]:
    """Immutable prompt construction — returns a fresh message list every call."""
    if not entity or not text:
        raise ValueError("entity and text are both required")
    user = (
        f"ARTICLE:\n{text[:MAX_TEXT_CHARS]}\n\nSUBJECT: {entity}\n\n"
        "Return stance, impact, and impact_confidence (0.0-1.0, how sure you are of the "
        "impact call) as JSON. Use a LOW confidence when the impact is genuinely borderline "
        "(e.g. neutral vs mildly negative)."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _coerce(label: str, allow_not_relevant: bool) -> str:
    v = str(label).lower()
    if allow_not_relevant and "not" in v:
        return "not_relevant"
    if "pos" in v:
        return "positive"
    if "neg" in v:
        return "negative"
    if "neu" in v:
        return "neutral"
    raise ValueError(f"unparseable label: {label!r}")


def parse_result(entity: str, raw: str) -> SentimentResult:
    """Validate a model response at the boundary. Raises on malformed output."""
    obj = json.loads(raw)  # guided decoding guarantees this succeeds
    conf = obj.get("impact_confidence", 1.0)
    try:
        conf = max(0.0, min(1.0, float(conf)))
    except (TypeError, ValueError):
        conf = 1.0
    return SentimentResult(
        entity=entity,
        stance=_coerce(obj["stance"], allow_not_relevant=False),
        impact=_coerce(obj["impact"], allow_not_relevant=True),
        impact_confidence=conf,
        note=str(obj.get("note", ""))[:120],
    )


def score_entity(client, model: str, entity: str, text: str) -> SentimentResult:
    """Score one (entity, text) via an OpenAI-compatible client with guided JSON.

    `client` is an openai.OpenAI (base_url pointed at a pool endpoint). vLLM and
    TabbyAPI accept the guided-JSON hint via extra_body; the response is therefore
    schema-valid and parse_result cannot fail on well-behaved endpoints.
    """
    resp = client.chat.completions.create(
        model=model,
        messages=build_messages(entity, text),
        temperature=0.0,
        max_tokens=96,
        extra_body={"guided_json": SENTIMENT_SCHEMA},  # vLLM/xgrammar constraint
    )
    return parse_result(entity, resp.choices[0].message.content)
