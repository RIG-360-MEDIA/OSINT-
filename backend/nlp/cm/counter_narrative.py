"""
Counter-narrative draft generator for CM Page.

For a given hostile issue, retrieve grounding via the existing RAG engine
and ask Groq QUALITY_MODEL to draft 3-5 talking-point bullets, each citing
at least one [doc_id] from the retrieved set. Hard guardrail: every cite
ID returned must be in the grounding set; if any is unknown, regenerate
once with a stricter prompt; if it still fails, mark the row rejected and
do not surface it.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from backend.nlp.groq_client import GroqCallFailed, GroqQuotaExhausted, generate

logger = logging.getLogger(__name__)

QUALITY_MODEL = "llama-3.3-70b-versatile"

_SYSTEM = (
    "You draft talking points for a Chief Minister's communications desk.\n"
    "You will be given an issue label, two opposition framings, and a numbered\n"
    "list of factual chunks. Produce 3 to 5 bullet talking points. Constraints:\n"
    "  - 1-2 sentences per bullet, neutral or constructive tone.\n"
    "  - EVERY bullet must cite at least one [doc_id] from the chunks list.\n"
    "  - NEVER attack named individuals.\n"
    "  - NEVER invent statistics, quotes, or names.\n"
    "  - If the chunks do not support a useful response, return an empty list.\n"
    "Return STRICT JSON: {\"talking_points\": [{\"text\": \"...\", \"cites\": [int, ...]}]}.\n"
)


@dataclass(frozen=True)
class TalkingPoint:
    text: str
    cites: list[str] = field(default_factory=list)   # UUID strings


@dataclass(frozen=True)
class CounterNarrative:
    talking_points: list[TalkingPoint]
    grounding_doc_ids: list[str]                     # UUID strings
    grounding_kinds: list[str]
    model: str
    retry_count: int
    rejected: bool


def _format_chunks(chunks: list[dict]) -> tuple[str, list[str], list[str]]:
    """chunks: [{'id': str|UUID, 'kind': str, 'text': str}].
    Returns (rendered, ids, kinds). Numeric chunks are stringified — the
    cite-ID guardrail compares strings throughout."""
    lines: list[str] = []
    ids: list[str] = []
    kinds: list[str] = []
    for ch in chunks:
        cid_raw = ch.get("id")
        if cid_raw is None:
            continue
        cid = str(cid_raw)
        body = (ch.get("text") or "").strip().replace("\n", " ")
        if not body:
            continue
        lines.append(f"[{cid}] {body[:600]}")
        ids.append(cid)
        kinds.append(ch.get("kind") or "article")
    return "\n".join(lines), ids, kinds


def _validate_cites(points: list[TalkingPoint], known_ids: set[str]) -> bool:
    if not points:
        return True
    for p in points:
        for cid in p.cites:
            if cid not in known_ids:
                return False
        if not p.cites:
            return False
    return True


async def _ask(prompt_user: str, retry: bool = False) -> tuple[list[TalkingPoint], str]:
    suffix = (
        "\nSTRICT MODE: every cite ID MUST appear verbatim in the chunks list. "
        "Re-check each cite before returning."
        if retry
        else ""
    )
    try:
        raw = await generate(
            system=_SYSTEM + suffix,
            user=prompt_user,
            task_type="generation",
        )
    except (GroqQuotaExhausted, GroqCallFailed) as exc:
        logger.info("counter-narrative generate failed (%s)", exc)
        return ([], "groq-failed")

    text = raw if isinstance(raw, str) else json.dumps(raw)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return ([], QUALITY_MODEL)

    items = payload.get("talking_points") or []
    points: list[TalkingPoint] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        body = (item.get("text") or "").strip()
        cites_raw = item.get("cites") or []
        cites: list[str] = []
        for c in cites_raw:
            if c is None:
                continue
            cites.append(str(c))
        if body:
            points.append(TalkingPoint(text=body, cites=cites))
    return (points, QUALITY_MODEL)


async def generate_for_issue(
    *,
    issue_label: str,
    opposition_quotes: list[str],
    chunks: list[dict],
) -> CounterNarrative:
    chunks_block, ids, kinds = _format_chunks(chunks)
    if not ids:
        return CounterNarrative([], [], [], "no-grounding", 0, True)

    opp_block = "\n".join(f"- \"{q.strip()}\"" for q in (opposition_quotes or [])[:2])

    user_prompt = (
        f"Issue: {issue_label}\n"
        f"Opposition framing:\n{opp_block or '(none captured)'}\n"
        f"\nFactual chunks (cite by [id]):\n{chunks_block}\n"
    )

    known_ids = set(ids)
    points, model = await _ask(user_prompt, retry=False)
    retry_count = 0
    if not _validate_cites(points, known_ids):
        retry_count = 1
        points, model = await _ask(user_prompt, retry=True)
        if not _validate_cites(points, known_ids):
            logger.info("counter-narrative cite-check failed twice; rejecting")
            return CounterNarrative([], ids, kinds, model, retry_count, True)

    return CounterNarrative(points, ids, kinds, model, retry_count, False)
