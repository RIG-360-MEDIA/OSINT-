"""draftsmith.stages.plan — Stage 1: topic/brief -> QueryPlan.

Calls the Cerebras planner with the build_planner_prompt system+user, then
TOLERANTLY parses the model's JSON into the frozen models.QueryPlan shape.
The parse never trusts the model: unknown enum values fall back to safe
defaults, per-source query lists are clamped to the ≤3 contract, and a missing
topic_summary falls back to the input's first line so the plan is always well
formed. Errors surface (never silently swallowed) — a non-object payload or an
empty input raises.

    plan(input_text, dials) -> models.QueryPlan
"""

from __future__ import annotations

from typing import Any, Optional

from backend.draftsmith import config
from backend.draftsmith.llm import cerebras_json
from backend.draftsmith.models import (
    Dials,
    Directives,
    PlanEntity,
    QueryPlan,
    SourceQueries,
    TimeWindow,
)
from backend.draftsmith.prompts import build_planner_prompt

# Per-source query cap — mirrors SourceQueries' "≤3 each" contract.
_MAX_QUERIES_PER_SOURCE = 3
# Fallback recency window (days) when the planner omits or malforms it.
_DEFAULT_FROM_DAYS = 14
_ENTITY_TYPES = frozenset({"person", "org", "place", "event", "other"})


# --- coercion helpers (never trust model output) ----------------------------
def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _as_opt_str(value: Any) -> Optional[str]:
    s = _as_str(value)
    return s or None


def _as_opt_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_str_tuple(value: Any, cap: Optional[int] = None) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    items = [s for s in (_as_str(v) for v in value) if s]
    if cap is not None:
        items = items[:cap]
    return tuple(items)


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


# --- sub-shape builders ------------------------------------------------------
def _to_entity(raw: Any) -> Optional[PlanEntity]:
    if not isinstance(raw, dict):
        return None
    name = _as_str(raw.get("name"))
    if not name:
        return None
    etype = _as_str(raw.get("type"), "other").lower()
    if etype not in _ENTITY_TYPES:
        etype = "other"
    return PlanEntity(
        name=name,
        type=etype,  # type: ignore[arg-type]
        disambiguation=_as_str(raw.get("disambiguation")),
        aliases=_as_str_tuple(raw.get("aliases")),
        alternates=_as_str_tuple(raw.get("alternates")),
    )


def _to_directives(raw: Any) -> Directives:
    d = raw if isinstance(raw, dict) else {}
    return Directives(
        angle=_as_opt_str(d.get("angle")),
        must_include=_as_str_tuple(d.get("must_include")),
        must_avoid=_as_str_tuple(d.get("must_avoid")),
        tone_notes=_as_opt_str(d.get("tone_notes")),
        length_hint=_as_opt_int(d.get("length_hint")),
        other_constraints=_as_str_tuple(d.get("other_constraints")),
    )


def _to_time_window(raw: Any) -> TimeWindow:
    d = raw if isinstance(raw, dict) else {}
    frm = _as_opt_int(d.get("from_days_ago"))
    return TimeWindow(
        from_days_ago=frm if frm is not None else _DEFAULT_FROM_DAYS,
        to_days_ago=_as_opt_int(d.get("to_days_ago")),
        rationale=_as_str(d.get("rationale")),
    )


def _to_queries(raw: Any) -> SourceQueries:
    d = raw if isinstance(raw, dict) else {}

    def capped(field: str) -> tuple[str, ...]:
        return _as_str_tuple(d.get(field), cap=_MAX_QUERIES_PER_SOURCE)

    return SourceQueries(
        warehouse_fts=capped("warehouse_fts"),
        warehouse_vector_seed=_as_str(d.get("warehouse_vector_seed")),
        facts_cluster_hint=_as_str(d.get("facts_cluster_hint")),
        web=capped("web"),
        youtube=capped("youtube"),
        twitter=capped("twitter"),
        reddit=capped("reddit"),
        tiktok=capped("tiktok"),
        telegram=capped("telegram"),
        instagram=capped("instagram"),
        wechat=capped("wechat"),
        wikipedia_titles=capped("wikipedia_titles"),
    )


def _fallback_topic(input_text: str) -> str:
    for line in (input_text or "").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:200]
    return "untitled topic"


def to_query_plan(data: dict[str, Any], input_text: str) -> QueryPlan:
    """Tolerantly assemble a QueryPlan from a raw planner payload.

    Pure and deterministic — exposed for reuse/testing. `input_text` supplies
    the topic_summary fallback so the plan is never emitted with an empty topic.
    """
    entities = tuple(
        e for e in (_to_entity(x) for x in _as_list(data.get("entities"))) if e
    )
    topic = _as_str(data.get("topic_summary")) or _fallback_topic(input_text)
    return QueryPlan(
        topic_summary=topic,
        entities=entities,
        directives=_to_directives(data.get("directives")),
        time_window=_to_time_window(data.get("time_window")),
        queries=_to_queries(data.get("queries")),
        geo_hints=_as_str_tuple(data.get("geo_hints")),
        language_hints=_as_str_tuple(data.get("language_hints")),
    )


async def plan(input_text: str, dials: Dials) -> QueryPlan:
    """Stage 1 — turn an editor topic/brief into a frozen QueryPlan.

    `dials` is accepted for the uniform stage(input, dials) signature; query
    planning is content-shaped and does not consume the voice/length dials
    (those flow into the writer stage). The BRIEF-vs-topic split is derived
    from `input_text` inside build_planner_prompt.
    """
    if not input_text or not input_text.strip():
        raise ValueError("plan: input_text is empty")
    if dials is None:  # explicit boundary check; never assume a caller default
        raise ValueError("plan: dials is required")

    system, user = build_planner_prompt(input_text)
    data = await cerebras_json(system, user, temperature=config.PLANNER_TEMP)
    if not isinstance(data, dict):
        raise ValueError(
            "plan: planner returned a non-object JSON payload (%r)" % type(data)
        )
    return to_query_plan(data, input_text)
