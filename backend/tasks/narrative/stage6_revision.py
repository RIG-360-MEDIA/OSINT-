"""Stage 6 — revision pass.

Takes the critic-panel feedback and rewrites the draft. Each critic note
becomes a constraint the model must address. Output is a new lede + body.

The pipeline runs Stage 5 → Stage 6 in a loop up to N times (default 2);
if no critic is below the floor (0.6 default), we exit early with the
current draft.
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
from backend.tasks.narrative.stage5_critic import CriticVerdict

logger = logging.getLogger(__name__)


REVISION_SYS = """You are revising a news article based on critic feedback.

Inputs:
- The current draft (headline, lede, body).
- A list of critic notes — each is an actionable change request.

Return STRICT JSON: {"headline": "...", "lede": "...", "body": "..."}.

RULES:
- Address EVERY critic note in the new draft. If a note conflicts with
  another, prefer the higher-impact one (specificity > narrative_gravity > rhythm).
- Do not invent facts. Reuse the SAME SPO claims that the original body used.
- Keep word counts: lede 25-60 words, body 400-700 words.
- No prose outside the JSON. No markdown fences.
"""


@dataclass(frozen=True)
class RevisedDraft:
    headline: str
    lede: str
    body: str


async def revise_draft(
    headline: str,
    lede: str,
    body: str,
    critic_notes: dict[str, CriticVerdict],
) -> RevisedDraft | None:
    """Apply critic feedback. Returns a new draft or None on failure."""
    notes_payload = {
        name: {"score": v.score, "notes": list(v.notes)}
        for name, v in critic_notes.items()
        if v.notes  # ignore critics that had nothing to say
    }
    if not notes_payload:
        return RevisedDraft(headline=headline, lede=lede, body=body)
    user = (
        "CURRENT DRAFT:\n"
        + json.dumps({"headline": headline, "lede": lede, "body": body}, ensure_ascii=False)
        + "\n\nCRITIC NOTES:\n"
        + json.dumps(notes_payload, ensure_ascii=False)
        + "\n\nReturn the JSON object."
    )
    try:
        raw = await call_groq(
            system=REVISION_SYS,
            user=user,
            model=FAST_MODEL,
            task_type="generation",
            json_response=True,
            max_tokens_override=2500,
        )
    except (GroqCallFailed, GroqQuotaExhausted) as e:
        logger.warning("revision failed: %s", e)
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    new_headline = (parsed.get("headline") or "").strip() or headline
    new_lede = (parsed.get("lede") or "").strip()
    new_body = (parsed.get("body") or "").strip()
    if not new_lede or not new_body or len(new_body.split()) < 200:
        return None
    return RevisedDraft(
        headline=new_headline[:200],
        lede=new_lede[:600],
        body=new_body[:6000],
    )
