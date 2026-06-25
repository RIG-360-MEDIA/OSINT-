"""Dossier mode — a structured intelligence profile on a person/org/place.

'Everything on [X]' gathers several signals (recent coverage, volume + trend, what
they've said, who they appear alongside) and synthesises a sectioned, cited dossier
the user can export. Multi-step gather → one grounded write. Read-only SELECT.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.enumerate import ListItem, list_articles
from app.llm import LLMProvider
from app.quantify import count_articles

logger = logging.getLogger("ask-rig.dossier")

_RECENT_K = 10
_QUOTES_K = 6
_COMENTION_K = 6
_DEFAULT_DAYS = 30

_QUOTES_SQL = """
SELECT COALESCE(NULLIF(quote_text_en, ''), quote_text) AS quote
FROM article_quotes q JOIN articles a ON a.id = q.article_id
WHERE q.speaker_entity_id = :eid AND COALESCE(quote_text_en, quote_text) IS NOT NULL
ORDER BY a.published_at DESC NULLS LAST
LIMIT :k
"""
_COMENTION_SQL = """
SELECT d.canonical_name, count(*) AS n
FROM article_entity_mentions m1
JOIN article_entity_mentions m2 ON m2.article_id = m1.article_id AND m2.entity_id <> m1.entity_id
JOIN entity_dictionary d ON d.id = m2.entity_id AND d.redirected_to IS NULL
JOIN articles a ON a.id = m1.article_id AND a.published_at > now() - make_interval(days => :days)
WHERE m1.entity_id = :eid
GROUP BY d.canonical_name ORDER BY n DESC LIMIT :k
"""
_LANG_SQL = """
SELECT a.language_detected, count(*) AS n
FROM article_entity_mentions m JOIN articles a ON a.id = m.article_id
WHERE m.entity_id = :eid AND a.substrate_status = 'ok' AND NOT a.is_duplicate
  AND a.published_at > now() - make_interval(days => :days)
GROUP BY 1 ORDER BY 2 DESC
"""


@dataclass(frozen=True)
class Dossier:
    subject: str
    days: int
    total: int
    prev_total: int
    recent: list[ListItem]
    quotes: list[str]
    co_mentions: list[tuple[str, int]]
    languages: list[tuple[str, int]] = field(default_factory=list)


async def gather_dossier(
    conn: AsyncConnection, settings: Settings, entity_id: str, subject: str,
    days: int = _DEFAULT_DAYS,
) -> Dossier:
    hours = days * 24
    recent, total = await list_articles(conn, settings, entity_id=entity_id, since_hours=hours, limit=_RECENT_K)
    prev_total = await count_articles(conn, settings, entity_id=entity_id, since_hours=hours, prev_window=True)
    quotes = [r[0] for r in (await conn.execute(text(_QUOTES_SQL), {"eid": entity_id, "k": _QUOTES_K})).all() if r[0]]
    co = [(r[0], int(r[1])) for r in (await conn.execute(text(_COMENTION_SQL), {"eid": entity_id, "days": days, "k": _COMENTION_K})).all()]
    langs = [(r[0] or "?", int(r[1])) for r in (await conn.execute(text(_LANG_SQL), {"eid": entity_id, "days": days})).all()]
    return Dossier(subject=subject, days=days, total=total, prev_total=prev_total,
                   recent=recent, quotes=quotes, co_mentions=co, languages=langs)


DOSSIER_SYSTEM = (
    "You are RIG, an intelligence analyst. Write a structured DOSSIER on the SUBJECT using ONLY "
    "the facts provided — never invent. Use these markdown sections (omit any with no facts):\n"
    "## Overview — 2-3 sentences: who/what this is and the current coverage picture.\n"
    "## Recent developments — the key things in the news now, as bullets; cite [S#].\n"
    "## In their own words — notable quotes provided (verbatim), if any.\n"
    "## Appears alongside — the co-mentioned people/orgs and what that pattern suggests.\n"
    "## Coverage at a glance — the volume, trend vs the prior period, and language spread.\n"
    "Be specific and faithful; if a section is thin, keep it short."
)


def build_dossier_prompt(d: Dossier) -> str:
    parts = [f"SUBJECT: {d.subject}", f"WINDOW: last {d.days} days"]
    parts.append(f"VOLUME: {d.total} articles (prior {d.days} days: {d.prev_total}, "
                 f"change {d.total - d.prev_total:+d})")
    if d.languages:
        parts.append("LANGUAGES: " + ", ".join(f"{l.upper()}={n}" for l, n in d.languages))
    if d.recent:
        parts.append("RECENT HEADLINES (cite as shown):")
        for i, it in enumerate(d.recent, 1):
            when = it.published_at.isoformat()[:10] if it.published_at else ""
            parts.append(f"  [S{i}] {when} {it.title}")
    if d.quotes:
        parts.append("QUOTES ATTRIBUTED TO SUBJECT:")
        parts += [f'  - "{q}"' for q in d.quotes]
    if d.co_mentions:
        parts.append("FREQUENTLY CO-MENTIONED: " + ", ".join(f"{n_} ({c})" for n_, c in d.co_mentions))
    parts.append("\nWrite the dossier now, grounded only in the above.")
    return "\n".join(parts)


_PARSE_SYSTEM = (
    "You decide whether a message asks for a DOSSIER / full profile on a single named person, "
    "org, or place — 'everything on X', 'dossier on X', 'profile of X', 'tell me all about X', "
    "'full picture on X'. NOT a dossier: 'what is the latest', 'give me all articles' (a list), "
    "'how many' (a count). Output ONLY JSON: {\"is_dossier\": bool, \"entity\": string|null, "
    "\"days\": int|null}.\n"
    "'give me a full dossier on Revanth Reddy' -> {\"is_dossier\":true,\"entity\":\"Revanth Reddy\",\"days\":null}\n"
    "'what's the latest on Revanth Reddy' -> {\"is_dossier\":false}"
)


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


def parse_dossier_request(llm: LLMProvider, query: str) -> tuple[str, int] | None:
    """Return (entity_term, days) for a dossier request, else None."""
    query = (query or "").strip()
    if not query:
        return None
    try:
        raw = llm.complete(_PARSE_SYSTEM, f"Message: {query}\n\nJSON:")
    except Exception as exc:  # noqa: BLE001
        logger.debug("dossier parse failed: %s", exc)
        return None
    data = _extract_json(raw)
    if not isinstance(data, dict) or not data.get("is_dossier"):
        return None
    entity = (str(data.get("entity")).strip() if data.get("entity") else None) or None
    if not entity:
        return None
    try:
        days = int(data["days"]) if data.get("days") else _DEFAULT_DAYS
    except (ValueError, TypeError):
        days = _DEFAULT_DAYS
    return entity, max(7, min(days, 90))
