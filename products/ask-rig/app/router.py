"""One-shot turn router — the latency fix.

Before: a turn could fire up to FOUR sequential LLM calls before any answer token —
parse_dossier? + parse_count? + parse_list? + plan_turn. Each is a Groq round-trip,
and the QA timing showed the ~30s/turn is almost all *pre-first-token* setup.

This collapses all of that into ONE call: classify the MODE and extract the fields that
mode needs, in a single JSON response. Best-effort — ``route_turn`` returns None on any
failure, and the caller falls back to plain synthesis (legacy rewrite path), so a router
miss only costs the speedup, never correctness.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from app.llm import LLMProvider

logger = logging.getLogger("ask-rig.router")

_MODES = {"synthesize", "enumerate", "quantify", "dossier"}
_QTYPES = {"broad", "specific", "profile", "comparison", "explainer", "followup"}
_LANG_MAP = {"english": "en", "telugu": "te", "hindi": "hi", "tamil": "ta",
             "kannada": "kn", "malayalam": "ml", "marathi": "mr", "bengali": "bn"}
_HISTORY_TURNS = 3


@dataclass(frozen=True)
class Route:
    mode: str = "synthesize"
    # shared
    entity: str | None = None
    keyword: str | None = None
    since_hours: int | None = None
    languages: tuple[str, ...] | None = None
    # synthesize (plan)
    search_query: str = ""
    query_type: str = "specific"
    needs_web: bool = True
    needs_entity: bool = False
    variants: tuple[str, ...] = ()
    is_followup: bool = False
    # enumerate
    recent: bool = False
    sentiment: str | None = None
    limit: int = 50
    # quantify
    compare_prev: bool = False
    trend_days: int | None = None
    metric: str = "volume"
    breakdown: str | None = None
    chart_kind: str | None = None
    # dossier
    days: int = 30


_SYSTEM = (
    "You are the router for a news-intelligence assistant over an Indian multilingual news corpus. "
    "In ONE JSON object, pick the MODE for the user's message and fill the fields that mode needs. "
    "Output ONLY the JSON, no prose.\n\n"
    "MODES:\n"
    "- enumerate: 'give me all/every X', 'list …', or 'the latest/most recent/newest article(s)'. "
    "Returns a LIST of articles.\n"
    "- quantify: 'how many / count / trend / chart / graph / sentiment chart / X this week vs last / "
    "by language / which outlets'. Returns numbers or a CHART.\n"
    "- dossier: 'everything on / dossier on / profile of X'. A full profile.\n"
    "- synthesize: everything else — a normal question to answer in prose ('what is/who is/why/"
    "what's the latest in <place>/explain/compare ideas').\n\n"
    "Resolve follow-ups using the conversation: rewrite 'what about his metro stance?' into a "
    "standalone search_query like 'Revanth Reddy Hyderabad metro stance'.\n\n"
    "Schema (include only what's relevant; defaults are fine for the rest):\n"
    "{\n"
    '  "mode": "synthesize|enumerate|quantify|dossier",\n'
    '  "entity": string|null,    // person/org/place the query centres on (cleaned name)\n'
    '  "keyword": string|null,   // topic phrase when there is no clear entity\n'
    '  "since_hours": int|null,  // today/24h=24, 48h=48, week=168, month=720, hour=1\n'
    '  "languages": string[]|null,  // e.g. ["te"] for Telugu-only\n'
    '  // synthesize: "search_query": standalone query, "query_type": '
    '"broad|specific|profile|comparison|explainer|followup", "needs_web": bool, '
    '"needs_entity": bool, "variants": string[] (0-3 extra search angles), "is_followup": bool\n'
    '  // enumerate: "recent": bool (latest/newest), "sentiment": "negative|positive|null", "limit": int|null\n'
    '  // quantify: "compare_prev": bool, "trend_days": int|null, "metric": "volume|sentiment", '
    '"breakdown": "language|outlet|null", "chart_kind": "pie|doughnut|bar|line|null"\n'
    '  // dossier: "days": int|null\n'
    "}\n\n"
    "Examples:\n"
    'M: "what is the latest in Telangana" -> {"mode":"synthesize","search_query":"latest Telangana news",'
    '"query_type":"broad","needs_web":true,"needs_entity":false,"variants":["Telangana politics","Telangana governance"]}\n'
    'M: "give me all negative articles about the Telangana govt in 24h" -> {"mode":"enumerate",'
    '"entity":"Telangana government","since_hours":24,"sentiment":"negative"}\n'
    'M: "what is the most recent article" -> {"mode":"enumerate","recent":true}\n'
    'M: "sentiment chart over the last 7 days for the Telangana govt" -> {"mode":"quantify",'
    '"entity":"Telangana government","trend_days":7,"metric":"sentiment"}\n'
    'M: "which outlets cover Revanth Reddy the most" -> {"mode":"quantify","entity":"Revanth Reddy",'
    '"since_hours":168,"breakdown":"outlet"}\n'
    'M: "how many articles on the metro this week vs last" -> {"mode":"quantify","keyword":"Hyderabad metro",'
    '"since_hours":168,"compare_prev":true}\n'
    'M: "give me a full dossier on Revanth Reddy" -> {"mode":"dossier","entity":"Revanth Reddy"}\n'
    'M: "who is Revanth Reddy" -> {"mode":"synthesize","search_query":"Revanth Reddy profile",'
    '"query_type":"profile","needs_web":false,"needs_entity":true,"entity":"Revanth Reddy"}'
)


def _history_block(history) -> str:
    turns = [t for t in (history or []) if t.get("role") in ("user", "assistant") and (t.get("content") or "").strip()]
    if not turns:
        return "(no prior conversation)"
    out = []
    for t in turns[-_HISTORY_TURNS * 2:]:
        who = "User" if t["role"] == "user" else "Assistant"
        out.append(f"{who}: {' '.join((t['content'] or '').split())[:300]}")
    return "\n".join(out)


def _extract_json(raw: str) -> dict | None:
    if not raw:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        raw = m.group(1)
    s = raw.find("{")
    if s == -1:
        return None
    depth = 0
    for i in range(s, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(raw[s : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _str(v):
    return s if (v and (s := str(v).strip())) else None


def _langs(v):
    raw = v or []
    if not isinstance(raw, list):
        return None
    out = tuple(_LANG_MAP.get(str(x).lower(), str(x).lower()) for x in raw if str(x).strip())
    return out or None


def _int(v):
    try:
        return int(v) if v not in (None, "", "null") else None
    except (ValueError, TypeError):
        return None


def route_turn(llm: LLMProvider, query: str, history=None) -> Route | None:
    """ONE LLM call → mode + fields. None on failure (caller falls back to synthesis)."""
    query = (query or "").strip()
    if not query:
        return None
    user = f"Conversation so far:\n{_history_block(history)}\n\nMessage: {query}\n\nJSON:"
    try:
        raw = llm.complete(_SYSTEM, user)
    except Exception as exc:  # noqa: BLE001 - routing must never break a turn
        logger.debug("router llm failed: %s", exc)
        return None
    data = _extract_json(raw)
    if not isinstance(data, dict):
        logger.debug("router non-JSON: %.120r", raw)
        return None
    try:
        return _coerce(data, query)
    except Exception as exc:  # noqa: BLE001
        logger.debug("router coerce failed: %s", exc)
        return None


def _coerce(d: dict, query: str) -> Route:
    mode = str(d.get("mode", "synthesize")).lower()
    if mode not in _MODES:
        mode = "synthesize"
    entity = _str(d.get("entity"))
    keyword = _str(d.get("keyword"))

    qtype = str(d.get("query_type", "specific")).lower()
    if qtype not in _QTYPES:
        qtype = "specific"

    sent = d.get("sentiment")
    sent = sent if sent in ("negative", "positive") else None
    metric = "sentiment" if str(d.get("metric", "")).lower() == "sentiment" else "volume"
    bd = str(d.get("breakdown", "")).lower()
    breakdown = bd if bd in ("language", "outlet") else None
    ck = str(d.get("chart_kind", "")).lower()
    chart_kind = ck if ck in ("pie", "doughnut", "bar", "line") else None
    recent = bool(d.get("recent"))

    raw_vars = d.get("variants") or []
    variants = tuple(s for v in raw_vars if (s := str(v).strip()))[:3] if isinstance(raw_vars, list) else ()
    sq = _str(d.get("search_query")) or query

    return Route(
        mode=mode, entity=entity, keyword=keyword,
        since_hours=_int(d.get("since_hours")), languages=_langs(d.get("languages")),
        search_query=sq, query_type=qtype,
        needs_web=bool(d.get("needs_web", True)),
        needs_entity=bool(d.get("needs_entity")) and entity is not None,
        variants=variants, is_followup=bool(d.get("is_followup")),
        recent=recent, sentiment=sent, limit=_int(d.get("limit")) or 50,
        compare_prev=bool(d.get("compare_prev")), trend_days=_int(d.get("trend_days")),
        metric=metric, breakdown=breakdown, chart_kind=chart_kind,
        days=max(7, min(_int(d.get("days")) or 30, 90)),
    )
