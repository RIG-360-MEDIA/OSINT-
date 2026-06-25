"""Quantify mode — counts, trends, and comparisons over the corpus.

Answers 'how many articles about X this week', 'X this week vs last', and 'trend of X
over 30 days'. Volume counts are clean structured queries (article_entity_mentions +
published_at). Sentiment counts ('how many NEGATIVE…') are estimated from a bounded
sample classified on the fly — the stored stance flag is too sparse — and ALWAYS
reported as an estimate, never as exact truth. Read-only SELECT.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.llm import LLMProvider

logger = logging.getLogger("ask-rig.quantify")

_TREND_MAX_DAYS = 90
_LANG_MAP = {"english": "en", "telugu": "te", "hindi": "hi", "tamil": "ta",
             "kannada": "kn", "malayalam": "ml", "marathi": "mr", "bengali": "bn"}


@dataclass(frozen=True)
class CountRequest:
    entity_term: str | None = None
    keyword: str | None = None
    since_hours: int | None = None
    compare_prev: bool = False     # 'this week vs last week'
    trend_days: int | None = None  # 'trend over 30 days' → daily series
    sentiment: str | None = None   # negative/positive (sampled estimate)
    languages: tuple[str, ...] | None = None


_COUNT_ENTITY = (
    "SELECT count(*) FROM article_entity_mentions m JOIN articles a ON a.id = m.article_id "
    "WHERE m.entity_id = :eid AND a.substrate_status = 'ok' AND NOT a.is_duplicate{since}{prev}{lang}"
)
_COUNT_KEYWORD = (
    "SELECT count(*) FROM articles a WHERE a.substrate_status = 'ok' AND NOT a.is_duplicate "
    "AND a.fts @@ websearch_to_tsquery(:cfg, :kw){since}{prev}{lang}"
)
_TREND_SQL = (
    "SELECT date_trunc('day', a.published_at)::date AS d, count(*) AS n "
    "FROM article_entity_mentions m JOIN articles a ON a.id = m.article_id "
    "WHERE m.entity_id = :eid AND a.substrate_status = 'ok' AND NOT a.is_duplicate "
    "AND a.published_at > now() - make_interval(days => :days) "
    "GROUP BY 1 ORDER BY 1"
)


async def count_articles(
    conn: AsyncConnection,
    settings: Settings,
    *,
    entity_id: str | None = None,
    keyword: str | None = None,
    since_hours: int | None = None,
    prev_window: bool = False,
    languages: Sequence[str] | None = None,
) -> int:
    """Count matches. ``prev_window`` shifts the window back by one length (the period
    BEFORE the current one) for 'vs last' comparisons."""
    since = lang = prev = ""
    params: dict = {}
    if since_hours and not prev_window:
        since = " AND a.published_at > now() - make_interval(hours => :hours)"
        params["hours"] = int(since_hours)
    elif since_hours and prev_window:
        prev = (" AND a.published_at > now() - make_interval(hours => :h2)"
                " AND a.published_at <= now() - make_interval(hours => :h1)")
        params["h1"] = int(since_hours)
        params["h2"] = int(since_hours) * 2
    if languages:
        lang = " AND a.language_detected = ANY(:langs)"
        params["langs"] = list(languages)
    if entity_id:
        sql = _COUNT_ENTITY.format(since=since, prev=prev, lang=lang)
        params["eid"] = entity_id
    elif keyword:
        sql = _COUNT_KEYWORD.format(since=since, prev=prev, lang=lang)
        params["kw"] = keyword
        params["cfg"] = settings.fts_config
    else:
        return 0
    return int((await conn.execute(text(sql), params)).scalar() or 0)


async def count_by_day(conn: AsyncConnection, entity_id: str, days: int) -> list[tuple[str, int]]:
    """Daily article counts for an entity over the last ``days`` (for trend lines)."""
    days = max(2, min(days, _TREND_MAX_DAYS))
    rows = (await conn.execute(text(_TREND_SQL), {"eid": entity_id, "days": days})).all()
    return [(str(r[0]), int(r[1])) for r in rows]


_PARSE_SYSTEM = (
    "You decide whether a message is a QUANTIFY request — asking HOW MANY / a COUNT / a "
    "TREND / a comparison over time — vs a normal question. Output ONLY JSON.\n"
    "Triggers: 'how many', 'count', 'how much coverage', 'trend', 'over the last N days', "
    "'this week vs last'. NOT quantify: 'what is', 'who is', 'give me all' (that's a list).\n"
    "Schema: {\"is_count\": bool, \"entity\": string|null, \"keyword\": string|null, "
    "\"since_hours\": int|null (today/24h=24, this week=168, this month=720), "
    "\"compare_prev\": bool (true for 'vs last week/previous'), \"trend_days\": int|null "
    "(set for 'trend over N days' / 'over the last month'=30), \"sentiment\": "
    "\"negative\"|\"positive\"|null, \"languages\": string[]|null}.\n"
    "Examples:\n"
    "'how many negative articles about the govt this week vs last' -> {\"is_count\":true,"
    "\"entity\":\"Telangana government\",\"keyword\":null,\"since_hours\":168,\"compare_prev\":true,"
    "\"trend_days\":null,\"sentiment\":\"negative\",\"languages\":null}\n"
    "'sentiment of Revanth Reddy over the last 30 days' -> {\"is_count\":true,\"entity\":"
    "\"Revanth Reddy\",\"keyword\":null,\"since_hours\":null,\"compare_prev\":false,"
    "\"trend_days\":30,\"sentiment\":null,\"languages\":null}\n"
    "'what is the latest in Telangana' -> {\"is_count\":false}"
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


def parse_count_request(llm: LLMProvider, query: str) -> CountRequest | None:
    """Detect + parse a quantify request. None for non-count questions or any failure."""
    query = (query or "").strip()
    if not query:
        return None
    try:
        raw = llm.complete(_PARSE_SYSTEM, f"Message: {query}\n\nJSON:")
    except Exception as exc:  # noqa: BLE001
        logger.debug("count parse failed: %s", exc)
        return None
    data = _extract_json(raw)
    if not isinstance(data, dict) or not data.get("is_count"):
        return None
    entity = (str(data.get("entity")).strip() if data.get("entity") else None) or None
    keyword = (str(data.get("keyword")).strip() if data.get("keyword") else None) or None
    if not entity and not keyword:
        return None
    sent = data.get("sentiment")
    sent = sent if sent in ("negative", "positive") else None
    raw_langs = data.get("languages") or []
    langs = tuple(_LANG_MAP.get(str(x).lower(), str(x).lower()) for x in raw_langs if str(x).strip()) or None
    try:
        hours = int(data["since_hours"]) if data.get("since_hours") else None
    except (ValueError, TypeError):
        hours = None
    try:
        trend = int(data["trend_days"]) if data.get("trend_days") else None
    except (ValueError, TypeError):
        trend = None
    return CountRequest(
        entity_term=entity, keyword=keyword, since_hours=hours,
        compare_prev=bool(data.get("compare_prev")), trend_days=trend,
        sentiment=sent, languages=langs,
    )
