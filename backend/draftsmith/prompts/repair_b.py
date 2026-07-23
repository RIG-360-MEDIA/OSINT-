"""draftsmith.prompts.repair_b — Door B repair prompt.

Adapts worldwide_gen_v2 REPAIR to the beats schema: rewrite ONLY the spans
verification flagged, introduce no new facts or sources, and keep the beat
structure (same beats, same subheads) intact. Output matches models.Draft.

`REPAIR_B_SYSTEM` is the system string; `build_repair_prompt(brief, draft,
violations)` assembles the (system, user) pair.
"""

from __future__ import annotations

REPAIR_B_SYSTEM = (
    "You are editing a Rig Wire article to remove UNSUPPORTED content while "
    "keeping its voice, length, and BEAT STRUCTURE. You receive the BRIEF, the "
    "DRAFT (an array of beats), and VIOLATIONS (per-beat spans that failed "
    "verification). Rewrite ONLY the offending spans: for each violation, remove "
    "or rewrite the span so nothing outside the brief remains — for an invented or "
    "computed date make it vague using ONLY the brief's stated ordering; for a "
    "fact resting only on a Tier-3 source either attribute it in-text as "
    "unverified or cut it. Replace removed material by developing a fact that IS "
    "in the brief and citing its [id]. Introduce NO new facts and NO new sources.\n\n"

    "Preserve the structure: keep every beat's subhead, keep the SAME number of "
    "beats in the SAME order, and keep untouched spans EXACTLY as they were. After "
    "editing a beat, update its \"source_ids\" so they match the beat's final "
    "text. Leave a fact the brief cannot support out entirely and, if the editor's "
    "directives asked for it, note it in \"unsourced_gaps\" — never re-invent it.\n\n"

    "OUTPUT strict JSON only, the SAME schema as the draft: "
    '{"headline":"","dek":"","beats":[{"subhead":"","text":"","source_ids":[]}],'
    '"key_facts":[{"fact":"","source_ids":[]}],'
    '"pull_quote":{"text":"","speaker":"","source_id":""},"unsourced_gaps":[]}'
)


def build_repair_prompt(
    brief: str, draft_json: str, violations_json: str
) -> tuple[str, str]:
    """Build (system, user) for the repair call.

    `draft_json` is the current draft serialised as JSON; `violations_json` is
    the verifier's per-beat violations serialised as JSON.
    """
    user = (
        "BRIEF:\n"
        + (brief or "")
        + "\n\nDRAFT JSON:\n"
        + (draft_json or "")
        + "\n\nVIOLATIONS:\n"
        + (violations_json or "")
    )
    return REPAIR_B_SYSTEM, user
