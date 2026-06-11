"""Stage 5 — critic panel (5 parallel critics).

The critics each score the draft 0.0-1.0 on a single dimension and emit
1-3 actionable notes for revision. Run in PARALLEL because they're
independent — total latency is the slowest critic, not the sum.

Critics:
  specificity      — every claim has named actor + time + number? (low = vague)
  rhythm           — sentence-length variation, no two consecutive 25+ word
                     sentences, no two consecutive 8- word sentences. (low = monotone)
  stance           — is the stance toward the subject consistent across body?
                     (low = inadvertent flip-flop or both-sides hedging)
  narrative_gravity — does the piece COMMIT to a thesis? (low = encyclopaedic recap)
  anti_recap       — does each paragraph introduce new info vs restating lede?
                     (low = repetitive)
"""
from __future__ import annotations

import asyncio
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


CRITIC_PROMPTS = {
    "specificity": """You are the SPECIFICITY critic.
Score 0.0-1.0 (1.0 = every claim has a named actor + time + number / source).
Penalise: passive voice without actor, "experts say", "in recent times",
"a number of" instead of an actual count.
Return JSON: {"score": 0.0-1.0, "notes": ["...", "..."]}.""",

    "rhythm": """You are the RHYTHM critic.
Score 0.0-1.0 (1.0 = sentence lengths vary, no two consecutive monsters,
no machine-gun staccato runs).
Count sentences. Flag any run of 2+ sentences over 25 words, or 2+ under 8.
Return JSON: {"score": 0.0-1.0, "notes": ["...", "..."]}.""",

    "stance": """You are the STANCE critic.
Score 0.0-1.0 (1.0 = stance toward subjects is consistent — neutral
throughout, or critical throughout, or supportive throughout).
Penalise: both-sides hedging when one side is verifiably wrong;
inadvertent stance flips between paragraphs.
Return JSON: {"score": 0.0-1.0, "notes": ["...", "..."]}.""",

    "narrative_gravity": """You are the NARRATIVE GRAVITY critic.
Score 0.0-1.0 (1.0 = piece commits to a thesis a reader can disagree with).
Penalise: encyclopaedic recap, "on the other hand" with no resolution,
articles that read like Wikipedia summaries.
Return JSON: {"score": 0.0-1.0, "notes": ["...", "..."]}.""",

    "anti_recap": """You are the ANTI-RECAP critic.
Score 0.0-1.0 (1.0 = each paragraph introduces NEW info; no paragraph
restates the lede).
For each paragraph N (2,3,4,...), check: does it add a new actor, claim,
number, or context fact not in paragraph 1?
Return JSON: {"score": 0.0-1.0, "notes": ["...", "..."]}.""",
}


@dataclass(frozen=True)
class CriticVerdict:
    name: str
    score: float
    notes: tuple[str, ...]


async def _run_one_critic(name: str, sys_prompt: str, draft_text: str) -> CriticVerdict:
    user = f"DRAFT:\n{draft_text[:6000]}\n\nReturn the JSON object."
    try:
        raw = await call_groq(
            system=sys_prompt,
            user=user,
            model=FAST_MODEL,
            task_type="classification",
            json_response=True,
            max_tokens_override=400,
        )
    except (GroqCallFailed, GroqQuotaExhausted) as e:
        logger.warning("critic %s failed: %s", name, e)
        return CriticVerdict(name=name, score=0.5, notes=())
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return CriticVerdict(name=name, score=0.5, notes=())
    score = float(parsed.get("score") or 0.5)
    notes_raw = parsed.get("notes") or []
    notes = tuple(str(n)[:240] for n in notes_raw if isinstance(n, str))[:3]
    return CriticVerdict(name=name, score=max(0.0, min(1.0, score)), notes=notes)


async def run_critic_panel(draft_text: str) -> dict[str, CriticVerdict]:
    """All five critics in parallel. Returns dict keyed by critic name."""
    tasks = [
        _run_one_critic(name, prompt, draft_text)
        for name, prompt in CRITIC_PROMPTS.items()
    ]
    results = await asyncio.gather(*tasks)
    return {v.name: v for v in results}


def needs_revision(panel: dict[str, CriticVerdict], floor: float = 0.6) -> bool:
    """True if any critic scored below the floor."""
    return any(v.score < floor for v in panel.values())
