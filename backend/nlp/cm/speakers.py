"""
Speaker NER for CM Page.

Extracts attributed political quotes from article / clipping bodies using
Groq extract_json with a strict schema. Resolves each speaker against
entity_dictionary aliases — when a match is found we override party / role
with the verified canonical values, never trusting the model on those.

Per backend/nlp/cm/__init__.py contract: never invent. If the model emits
quotes without a clear attribution, those rows are dropped here, not stored.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from backend.nlp.groq_client import (
    GroqCallFailed,
    GroqQuotaExhausted,
    extract_json,
)

logger = logging.getLogger(__name__)

_BODY_CAP = 4000

# D-24 fix — sentinel strings the LLM returns when it cannot find a real
# speaker. These were being persisted as `speaker` values, surfacing on the
# CM page as fake spokespersons. Reject them in `_validate`.
_SPEAKER_SENTINELS: frozenset[str] = frozenset({
    "the article does not mention a specific named person",
    "no named speaker",
    "no specific named person",
    "no speaker",
    "n/a",
    "na",
    "none",
    "not specified",
    "not mentioned",
    "anonymous",
    "anonymous source",
    "sources said",
    "the article",
    "unknown",
    "unknown speaker",
    "various",
    "observers",
    "officials",
    "officials said",
    "spokesperson",
})

# D-25 fix — accept a quote only when at least one of these is true:
#   1. speaker_canonical resolves via entity_dict (verified politician), OR
#   2. role contains a political keyword (Minister, MLA, MP, CM, etc.), OR
#   3. party is set to a known Indian party code.
# Without this, the speakers task was treating cricketers, actors, justices,
# logistics analysts, and corporate execs as political voices.
_POLITICAL_ROLE_KEYWORDS: frozenset[str] = frozenset({
    "minister", "cm", "chief minister", "deputy cm", "mla", "mp",
    "lok sabha", "rajya sabha", "spokesperson", "party",
    "leader of opposition", "lop", "speaker of the assembly",
    "governor", "mayor", "corporator", "councillor", "mlc",
    "sarpanch", "panchayat", "zilla parishad", "block president",
    "general secretary", "national president", "state president",
    "working president",
})
_POLITICAL_PARTIES: frozenset[str] = frozenset({
    "INC", "BJP", "BRS", "TDP", "YSRCP", "JSP", "AIMIM", "AAP",
    "CPI", "CPI(M)", "CPM", "DMK", "AIADMK", "TMC", "SP", "BSP",
    "JD(U)", "JDU", "JD(S)", "JDS", "RJD", "SS", "NCP", "BJD",
    "SAD", "INLD", "NPP", "MNF", "SDF", "NPF", "SKM", "NPEP",
})


def _looks_political(record: dict[str, Any], canonical: str | None) -> bool:
    """D-25: return True only when the quote has a credible political signal."""
    if canonical:
        # Resolved against entity_dict — trust the curated record.
        return True
    role = (record.get("role") or "").strip().lower()
    if role and any(kw in role for kw in _POLITICAL_ROLE_KEYWORDS):
        return True
    party = (record.get("party") or "").strip().upper()
    if party in _POLITICAL_PARTIES:
        return True
    return False

_SYSTEM = (
    "You extract attributed political quotes from an Indian state-politics text.\n"
    "Return ONLY a JSON object with a single key 'quotes' whose value is an array.\n"
    "Each quote object MUST have these fields:\n"
    "  speaker      — the named person who said it (no anonymous 'sources said')\n"
    "  party        — party code if obvious, else null\n"
    "  role         — minister title, MLA, MP, spokesperson, or null\n"
    "  quote        — verbatim 8 to 40 words, no paraphrase\n"
    "  stance       — one of ruling_supportive, opposition_attack, neutral_factual, mixed, unknown\n"
    "  issue_hint   — short topic phrase, max 6 words, lowercase\n"
    "Rules:\n"
    "  - Direct or clearly-attributed indirect speech only.\n"
    "  - Skip if no named human speaker.\n"
    "  - Do NOT fabricate. Do NOT include the article author.\n"
    "  - If no qualifying quote exists, return {\"quotes\": []}.\n"
)


@dataclass(frozen=True)
class ExtractedQuote:
    speaker: str
    party: str | None
    role: str | None
    quote: str
    stance: str
    issue_hint: str | None
    speaker_canonical: str | None = None


@dataclass(frozen=True)
class SpeakerExtractionResult:
    quotes: list[ExtractedQuote] = field(default_factory=list)
    model: str = ""


def _resolve_canonical(
    speaker: str,
    entity_dict: dict[str, dict[str, Any]] | None,
) -> tuple[str | None, str | None, str | None]:
    """Look up speaker in entity_dictionary by canonical name OR alias.
    Returns (canonical_name, party, role) — None where unresolved."""
    if not entity_dict or not speaker:
        return (None, None, None)
    needle = speaker.strip().lower()
    for canonical, meta in entity_dict.items():
        if canonical.lower() == needle:
            return (canonical, meta.get("party"), meta.get("entity_type"))
        aliases = meta.get("aliases") or []
        if any((a or "").lower() == needle for a in aliases):
            return (canonical, meta.get("party"), meta.get("entity_type"))
    return (None, None, None)


def _validate(record: dict[str, Any]) -> ExtractedQuote | None:
    speaker = (record.get("speaker") or "").strip()
    quote = (record.get("quote") or "").strip()
    if not speaker or not quote:
        return None
    if len(quote.split()) < 4:
        return None
    # D-24: drop LLM no-extraction sentinels (case-insensitive, punctuation-stripped).
    speaker_norm = speaker.lower().strip(" .'\"`")
    if speaker_norm in _SPEAKER_SENTINELS:
        return None
    # Also reject obvious non-name fragments ("the article", "officials", etc.).
    if speaker_norm.startswith("the article"):
        return None
    stance = (record.get("stance") or "unknown").strip().lower()
    if stance not in {
        "ruling_supportive",
        "opposition_attack",
        "neutral_factual",
        "mixed",
        "unknown",
    }:
        stance = "unknown"
    return ExtractedQuote(
        speaker=speaker,
        party=(record.get("party") or None) or None,
        role=(record.get("role") or None) or None,
        quote=quote,
        stance=stance,
        issue_hint=(record.get("issue_hint") or None) or None,
    )


async def extract(
    *,
    title: str,
    body: str,
    entity_dict: dict[str, dict[str, Any]] | None = None,
) -> SpeakerExtractionResult:
    """Extract attributed quotes from a single article/clipping. Returns an
    empty list (not raises) on quota / API / JSON failure so the task can
    advance the watermark and try again later."""
    body_text = (body or "").strip()
    if len(body_text) < 80:
        return SpeakerExtractionResult([], "skipped-too-short")

    user_prompt = (
        f"Title: {title or '(untitled)'}\n\nBody:\n{body_text[:_BODY_CAP]}"
    )

    try:
        raw = await extract_json(
            system=_SYSTEM,
            user=user_prompt,
        )
    except (GroqQuotaExhausted, GroqCallFailed) as exc:
        logger.info("speakers extract failed (%s)", exc)
        return SpeakerExtractionResult([], "groq-failed")

    payload: Any
    if isinstance(raw, str):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.info("speakers extract returned non-JSON; dropping")
            return SpeakerExtractionResult([], "non-json")
    else:
        payload = raw

    items = (payload or {}).get("quotes") or []
    out: list[ExtractedQuote] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        validated = _validate(item)
        if validated is None:
            continue
        canonical, dict_party, dict_role = _resolve_canonical(validated.speaker, entity_dict)
        # D-25: drop quotes that aren't credibly political. Resolved-against-
        # entity_dict speakers always pass; otherwise require a political role
        # or party code on the LLM record itself.
        if not _looks_political(item, canonical):
            continue
        if canonical is not None:
            validated = ExtractedQuote(
                speaker=validated.speaker,
                party=dict_party or validated.party,
                role=dict_role or validated.role,
                quote=validated.quote,
                stance=validated.stance,
                issue_hint=validated.issue_hint,
                speaker_canonical=canonical,
            )
        out.append(validated)

    return SpeakerExtractionResult(out, "llama-3.1-8b-instant")
