"""The chat planner — one fast LLM pass that decides HOW to answer before we search.

The old pipeline ran the same shape every turn: rewrite → corpus + web + maybe-entity
→ synthesize. That wastes work (web on a definitional follow-up) and retrieves badly
on follow-ups ("what about his metro stance?" embeds the pronoun, not the subject).

The planner replaces the blind front of the pipeline with a decision:

  - resolve a follow-up into a STANDALONE search query (pronouns → the real subject,
    using the conversation so far),
  - classify the question shape (broad roundup / specific / profile / comparison / explainer),
  - decide whether the LIVE WEB is actually needed,
  - name the ENTITY to pull a feed for (precise, vs the old loose ILIKE guard),
  - emit a few complementary search variants (RAG-Fusion, but intent-aware).

It is BEST-EFFORT. ``plan_turn`` returns ``None`` on any failure (bad JSON, LLM down,
empty), and the caller falls back to the exact legacy path. Never let planning block
or break a turn.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Sequence

from app.llm import LLMProvider

logger = logging.getLogger("ask-rig.planner")

_QUERY_TYPES = {"broad", "specific", "profile", "comparison", "explainer", "followup"}
_MAX_VARIANTS = 3
_PLANNER_HISTORY_TURNS = 3  # prior turns the planner sees to resolve a follow-up


@dataclass(frozen=True)
class Plan:
    """The decided shape of one chat turn. ``search_query`` is always standalone
    (safe to embed on its own); ``variants`` are extra retrieval angles."""

    search_query: str
    query_type: str = "specific"
    is_followup: bool = False
    needs_web: bool = True
    needs_entity: bool = False
    entity: str | None = None
    variants: list[str] = field(default_factory=list)

    @property
    def queries(self) -> list[str]:
        """All search strings (standalone query first, then de-duped variants)."""
        out = [self.search_query]
        seen = {self.search_query.strip().lower()}
        for v in self.variants:
            key = v.strip().lower()
            if v.strip() and key not in seen:
                seen.add(key)
                out.append(v.strip())
        return out


_PLANNER_SYSTEM = (
    "You are the planning step of a news-intelligence assistant. The corpus is Indian "
    "multilingual NEWS (English, Telugu, Hindi, Tamil) plus a live web search. Given the "
    "user's NEW message and the conversation so far, output a JSON plan for how to retrieve. "
    "Think, then output ONLY a single JSON object — no prose, no markdown fences.\n\n"
    "Schema:\n"
    "{\n"
    '  "search_query": string,   // a STANDALONE search query. If the new message is a '
    "follow-up that uses pronouns or omits the subject (\"what about his stance?\", \"and the "
    "cost?\"), REWRITE it into a full query using the conversation (\"Revanth Reddy Hyderabad "
    "metro stance\"). Otherwise lightly clean the user's query. Keep it under 12 words.\n"
    '  "query_type": one of "broad" | "specific" | "profile" | "comparison" | "explainer" | "followup",\n'
    '  "is_followup": boolean,   // true if it depends on the previous turns\n'
    '  "needs_web": boolean,     // true for anything time-sensitive, breaking, "latest", '
    "prices/scores, or topics the news corpus may lag on. false for a pure definitional/"
    "explainer or a follow-up answerable from what was already retrieved.\n"
    '  "needs_entity": boolean,  // true if the question centres on ONE named person, org, '
    "or place we should pull a dedicated recent-coverage feed for.\n"
    '  "entity": string|null,    // the canonical name to look up when needs_entity is true, else null\n'
    '  "variants": string[]      // 0-3 complementary search angles on the SAME intent. For a '
    "BROAD roundup give coverage angles (major developments, politics, key people). For a "
    "SPECIFIC question give sharper rephrasings. Do NOT invent narrow verticals (weather, "
    "sports, crime) unless asked. Each under 9 words.\n"
    "}\n\n"
    "Examples:\n"
    'New: "latest in Telangana"  ->  {"search_query":"latest Telangana news","query_type":"broad",'
    '"is_followup":false,"needs_web":true,"needs_entity":false,"entity":null,'
    '"variants":["Telangana government policy developments","Telangana major political events"]}\n'
    'New: "who is Revanth Reddy"  ->  {"search_query":"Revanth Reddy profile","query_type":"profile",'
    '"is_followup":false,"needs_web":false,"needs_entity":true,"entity":"Revanth Reddy","variants":[]}\n'
    'Prev user: "who is Revanth Reddy"  New: "what has he said about the metro?"  ->  '
    '{"search_query":"Revanth Reddy Hyderabad metro statements","query_type":"followup",'
    '"is_followup":true,"needs_web":false,"needs_entity":true,"entity":"Revanth Reddy","variants":[]}'
)


def _history_block(history: Sequence[dict]) -> str:
    turns = [t for t in history if t.get("role") in ("user", "assistant") and (t.get("content") or "").strip()]
    if not turns:
        return "(no prior conversation)"
    lines = []
    for t in turns[-_PLANNER_HISTORY_TURNS * 2:]:
        who = "User" if t["role"] == "user" else "Assistant"
        text = " ".join((t["content"] or "").split())[:400]
        lines.append(f"{who}: {text}")
    return "\n".join(lines)


def _extract_json(raw: str) -> dict | None:
    """Pull the first balanced JSON object out of an LLM response."""
    if not raw:
        return None
    raw = raw.strip()
    # Strip a ```json fence if the model added one despite instructions.
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1)
    start = raw.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(raw)):
        c = raw[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(raw[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _coerce(data: dict, fallback_query: str) -> Plan | None:
    sq = str(data.get("search_query") or "").strip() or fallback_query.strip()
    if not sq:
        return None

    qtype = str(data.get("query_type") or "specific").strip().lower()
    if qtype not in _QUERY_TYPES:
        qtype = "specific"

    raw_variants = data.get("variants") or []
    variants: list[str] = []
    if isinstance(raw_variants, list):
        for v in raw_variants:
            s = str(v).strip()
            if s and s.lower() != sq.lower():
                variants.append(s)
            if len(variants) >= _MAX_VARIANTS:
                break

    entity = data.get("entity")
    entity = str(entity).strip() if entity not in (None, "", "null") else None
    needs_entity = bool(data.get("needs_entity")) and entity is not None

    return Plan(
        search_query=sq,
        query_type=qtype,
        is_followup=bool(data.get("is_followup")),
        needs_web=bool(data.get("needs_web", True)),
        needs_entity=needs_entity,
        entity=entity if needs_entity else None,
        variants=variants,
    )


def plan_turn(llm: LLMProvider, query: str, history: Sequence[dict] | None = None) -> Plan | None:
    """Decide the retrieval shape for one turn. Returns ``None`` on any failure so the
    caller can fall back to the legacy pipeline. Pure/blocking — run off the event loop."""
    query = (query or "").strip()
    if not query:
        return None
    user = f"Conversation so far:\n{_history_block(history or [])}\n\nNew message: {query}\n\nJSON plan:"
    try:
        raw = llm.complete(_PLANNER_SYSTEM, user)
    except Exception as exc:  # noqa: BLE001 - planning must never break a turn
        logger.debug("planner LLM failed: %s", exc)
        return None
    data = _extract_json(raw)
    if not isinstance(data, dict):
        logger.debug("planner returned non-JSON: %.120r", raw)
        return None
    try:
        return _coerce(data, query)
    except Exception as exc:  # noqa: BLE001 - any shape surprise → legacy path
        logger.debug("planner coerce failed: %s", exc)
        return None
