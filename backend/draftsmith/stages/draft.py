"""draftsmith.stages.draft — Stage 4: BRIEF -> models.Draft.

Calls the Cerebras writer with build_draft_prompt(brief, dials) at the
creativity-derived temperature (config.writer_temperature), then TOLERANTLY
parses the model's JSON into the frozen models.Draft shape. Mirrors the live
worldwide_gen_v2 gen() step, but targets the Door B beats schema (per-beat
citations) instead of a single markdown body.

The parse never trusts the model:
  * unknown/malformed fields fall back to safe empties,
  * a legacy single "body" string (or a nested body.body) is split into beats
    on its ## subheads so an off-schema completion still yields a usable Draft,
  * pull_quote accepts the writer prompt's "source_id" or the legacy "source".

    draft(brief, dials) -> models.Draft
"""

from __future__ import annotations

import re
from typing import Any, Optional

from backend.draftsmith import config
from backend.draftsmith.llm import cerebras_json
from backend.draftsmith.models import (
    Dials,
    Draft,
    DraftBeat,
    KeyFact,
    PullQuote,
)
from backend.draftsmith.prompts import build_draft_prompt

# Split a legacy markdown "body" on its ## subheads (multiline, tolerant of
# leading whitespace). Only used on the off-schema fallback path.
_SUBHEAD_SPLIT = re.compile(r"(?m)^\s*##\s+")


# --- coercion helpers (never trust model output) ----------------------------
def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _as_str_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(s for s in (_as_str(v) for v in value) if s)


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _unwrap_body(value: Any, guard: int = 3) -> str:
    """Collapse a body value to a markdown string. Mirrors
    worldwide_gen_v2.extract_body: unwraps a nested {"body": {...}} up to a few
    levels, joins a dict/list into ## sections, passes a plain string through.
    """
    depth = 0
    while isinstance(value, dict) and "body" in value and depth < guard:
        value = value["body"]
        depth += 1
    if isinstance(value, dict):
        return "\n\n".join(
            "## " + str(k).replace("_", " ").title() + "\n" + _as_str(v)
            for k, v in value.items()
        )
    if isinstance(value, list):
        return "\n\n".join(_as_str(x) for x in value)
    return _as_str(value)


def _beats_from_body(body: str) -> tuple[DraftBeat, ...]:
    """Fallback: turn a single markdown body into beats on its ## subheads.

    A body with no ## break becomes one subhead-less beat so no prose is lost.
    """
    text = (body or "").strip()
    if not text:
        return ()
    if "##" not in text:
        return (DraftBeat(subhead="", text=text),)
    beats: list[DraftBeat] = []
    for part in _SUBHEAD_SPLIT.split(text):
        chunk = part.strip()
        if not chunk:
            continue
        head, _, rest = chunk.partition("\n")
        beats.append(DraftBeat(subhead=head.strip(), text=rest.strip()))
    return tuple(beats)


def _to_beat(raw: Any) -> Optional[DraftBeat]:
    if not isinstance(raw, dict):
        return None
    text = _unwrap_body(raw.get("text", raw.get("body")))
    subhead = _as_str(raw.get("subhead"))
    if not text and not subhead:
        return None
    return DraftBeat(
        subhead=subhead,
        text=text,
        source_ids=_as_str_tuple(raw.get("source_ids")),
    )


def _to_key_fact(raw: Any) -> Optional[KeyFact]:
    if isinstance(raw, dict):
        fact = _as_str(raw.get("fact"))
        source_ids = _as_str_tuple(raw.get("source_ids"))
    else:
        fact = _as_str(raw)
        source_ids = ()
    if not fact:
        return None
    return KeyFact(fact=fact, source_ids=source_ids)


def _to_pull_quote(raw: Any) -> Optional[PullQuote]:
    if not isinstance(raw, dict):
        return None
    text = _as_str(raw.get("text"))
    if not text:
        return None
    # writer prompt emits "source_id"; the legacy PROMPT_D emitted "source".
    source_id = _as_str(raw.get("source_id") or raw.get("source"))
    return PullQuote(
        text=text,
        speaker=_as_str(raw.get("speaker")),
        source_id=source_id,
    )


def _coerce_beats(data: dict[str, Any]) -> tuple[DraftBeat, ...]:
    beats = tuple(
        b for b in (_to_beat(x) for x in _as_list(data.get("beats"))) if b
    )
    if beats:
        return beats
    # off-schema completion: reconstruct beats from a single body string.
    return _beats_from_body(_unwrap_body(data.get("body")))


def to_draft(data: dict[str, Any]) -> Draft:
    """Tolerantly assemble a Draft from a raw writer/repair payload.

    Pure and deterministic — exported so the repair stage reuses the exact same
    coercion for its re-drafted output. Raises ValueError only on a payload that
    is not a JSON object at all; every field-level defect degrades to an empty.
    """
    if not isinstance(data, dict):
        raise ValueError("to_draft: expected a JSON object, got %r" % type(data))
    return Draft(
        headline=_as_str(data.get("headline")),
        dek=_as_str(data.get("dek") or data.get("standfirst")),
        beats=_coerce_beats(data),
        key_facts=tuple(
            k for k in (_to_key_fact(x) for x in _as_list(data.get("key_facts"))) if k
        ),
        pull_quote=_to_pull_quote(data.get("pull_quote")),
        unsourced_gaps=_as_str_tuple(data.get("unsourced_gaps")),
    )


async def draft(brief: str, dials: Dials) -> Draft:
    """Stage 4 — write the Door B long-read from a grounded BRIEF.

    Temperature is derived from the creativity dial (config.writer_temperature);
    the moxy/length dials shape the prompt inside build_draft_prompt. The BRIEF
    must be non-empty — the writer never drafts from nothing.
    """
    if not brief or not brief.strip():
        raise ValueError("draft: brief is empty")
    if dials is None:  # explicit boundary check; never assume a caller default
        raise ValueError("draft: dials is required")

    d = dials.clamp()
    system, user = build_draft_prompt(brief, d)
    data = await cerebras_json(
        system, user, temperature=config.writer_temperature(d.creativity),
    )
    if not isinstance(data, dict):
        raise ValueError(
            "draft: writer returned a non-object JSON payload (%r)" % type(data)
        )
    return to_draft(data)
