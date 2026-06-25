"""Enumerate mode — the agentic 'give me ALL articles matching X' path.

Unlike RAG synthesis (retrieve ~14 → write one answer), enumerate returns the FULL
filtered set as a list the UI can render as cards and expand per-item. It runs a
structured query over the corpus, not a vector search:

  filters: entity (resolved) and/or keyword (FTS) · time window · language · limit

Recency is correct by construction here (a hard ``published_at`` window), which also
sidesteps the 'no recency boost' weakness of the RAG path. Read-only SELECT.

Sentiment-filtered enumeration ('all NEGATIVE about X') is deliberately NOT a flag
lookup — the stance table is too sparse/free-text — so that lives in a separate
on-the-fly classifier (Phase 1b), fed by the candidate set this module returns.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.llm import LLMProvider

logger = logging.getLogger("ask-rig.enumerate")

_MAX_LIMIT = 100  # hard cap — 50K articles/day means broad filters must stay bounded
_LANG_MAP = {"english": "en", "telugu": "te", "hindi": "hi", "tamil": "ta",
             "kannada": "kn", "malayalam": "ml", "marathi": "mr", "bengali": "bn"}


@dataclass(frozen=True)
class ListRequest:
    """A parsed 'give me all X' request. ``entity_term`` is resolved to an id by the
    caller; ``sentiment`` is applied by the on-the-fly classifier (Phase 1b)."""

    entity_term: str | None = None
    keyword: str | None = None
    since_hours: int | None = None
    languages: tuple[str, ...] | None = None
    sentiment: str | None = None  # 'negative' | 'positive' | None
    recent: bool = False          # 'the latest/newest article(s)' — pure recency, no filter needed
    limit: int = 50


_PARSE_SYSTEM = (
    "You decide whether a user's message is an ENUMERATE request — asking to LIST or get "
    "ALL/every article matching some filter — versus a normal question to be answered in prose. "
    "Output ONLY a JSON object, no prose.\n"
    "Enumerate triggers: 'give me all', 'list all', 'show me every', 'all the articles', "
    "'all negative news about', 'every story on'. ALSO enumerate (set \"recent\":true): asking "
    "for THE LATEST / MOST RECENT / NEWEST article(s) — they want the actual newest items, "
    "sorted by time. But a normal 'what is happening' / 'who is' / 'why' / 'summarise', or "
    "'what's the latest IN/ON <place>' (wants a summary, not a list), is NOT enumerate.\n"
    "Schema: {\"is_list\": bool, \"recent\": bool (true ONLY for 'latest/most recent/newest "
    "article' style — newest-first), \"entity\": string|null (person/org/place to filter by), "
    "\"keyword\": string|null (topic phrase if there's no clear entity), "
    "\"since_hours\": int|null (today/last 24h=24, last 48h=48, this week/7 days=168, last "
    "hour=1, this month=720; null if unspecified), \"sentiment\": \"negative\"|\"positive\"|null, "
    "\"languages\": string[]|null (e.g. [\"te\"] if they ask for Telugu only), \"limit\": int|null}.\n"
    "Examples:\n"
    "'give me all negative articles about the Telangana govt in the last 24 hours' -> "
    "{\"is_list\":true,\"recent\":false,\"entity\":\"Telangana government\",\"keyword\":null,"
    "\"since_hours\":24,\"sentiment\":\"negative\",\"languages\":null,\"limit\":null}\n"
    "'what is the most recent article' / 'show me the latest articles' -> "
    "{\"is_list\":true,\"recent\":true,\"entity\":null,\"keyword\":null,\"since_hours\":null,"
    "\"sentiment\":null,\"languages\":null,\"limit\":null}\n"
    "'the newest articles on the Hyderabad metro' -> {\"is_list\":true,\"recent\":true,"
    "\"entity\":null,\"keyword\":\"Hyderabad metro\",\"since_hours\":null,\"sentiment\":null,"
    "\"languages\":null,\"limit\":null}\n"
    "'what is the latest in Telangana' -> {\"is_list\":false}"
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


def parse_list_request(llm: LLMProvider, query: str) -> ListRequest | None:
    """Detect + parse an enumerate request. Returns None for normal questions or on any
    failure (caller falls through to RAG synthesis). Pure/blocking — run off-loop."""
    query = (query or "").strip()
    if not query:
        return None
    try:
        raw = llm.complete(_PARSE_SYSTEM, f"Message: {query}\n\nJSON:")
    except Exception as exc:  # noqa: BLE001 - never block the turn on parsing
        logger.debug("list parse llm failed: %s", exc)
        return None
    data = _extract_json(raw)
    if not isinstance(data, dict) or not data.get("is_list"):
        return None
    recent = bool(data.get("recent"))
    entity = (str(data.get("entity")).strip() if data.get("entity") else None) or None
    keyword = (str(data.get("keyword")).strip() if data.get("keyword") else None) or None
    if not entity and not keyword and not recent:
        return None  # a list of nothing — fall through to normal answer
    sent = data.get("sentiment")
    sent = sent if sent in ("negative", "positive") else None
    raw_langs = data.get("languages") or []
    langs = tuple(_LANG_MAP.get(str(x).lower(), str(x).lower()) for x in raw_langs if str(x).strip()) or None
    try:
        hours = int(data["since_hours"]) if data.get("since_hours") else None
    except (ValueError, TypeError):
        hours = None
    try:
        limit = int(data["limit"]) if data.get("limit") else (10 if recent else 50)
    except (ValueError, TypeError):
        limit = 10 if recent else 50
    return ListRequest(
        entity_term=entity, keyword=keyword, since_hours=hours,
        languages=langs, sentiment=sent, recent=recent, limit=limit,
    )


@dataclass(frozen=True)
class ListItem:
    """One row in an enumerate result — enough to render a card + drill down later."""

    id: str
    title: str
    url: str | None
    published_at: datetime | None
    language: str | None
    source_id: str | None
    snippet: str | None


# Entity path: the 1.33M-row mentions matview joined to articles. Time window + lang
# are optional AND-clauses. The same WHERE drives the COUNT so we can say 'N of M'.
_ENTITY_WHERE = (
    "FROM article_entity_mentions m JOIN articles a ON a.id = m.article_id "
    "WHERE m.entity_id = :eid AND a.substrate_status = 'ok' AND NOT a.is_duplicate"
    "{since}{lang}"
)
# Keyword path: full-text over the article fts when there's no resolvable entity.
_KEYWORD_WHERE = (
    "FROM articles a "
    "WHERE a.substrate_status = 'ok' AND NOT a.is_duplicate "
    "AND a.fts @@ websearch_to_tsquery(:cfg, :kw){since}{lang}"
)

_SELECT = (
    "SELECT a.id::text AS id, a.title, a.lead_text_translated AS snippet, a.url, "
    "a.published_at, a.source_id::text AS source_id, a.language_detected AS language "
)


_CLASSIFY_SYSTEM = (
    "You label each news headline's stance toward its main subject as exactly one of: "
    "negative, positive, neutral. negative = criticism, failure, scandal, attack, "
    "controversy, protest, loss, allegation. positive = praise, success, achievement, "
    "approval, gain. Everything else = neutral. Output ONLY a JSON array of lowercase "
    "labels, one per item in the SAME order, e.g. [\"negative\",\"neutral\",\"positive\"]."
)


def classify_list_sentiment(
    llm: LLMProvider, items: list["ListItem"], want: str
) -> tuple[list["ListItem"], bool]:
    """Filter ``items`` to those whose stance matches ``want`` ('negative'/'positive')
    via ONE LLM call over the headlines+snippets. Returns (filtered, applied). On any
    failure returns (items, False) so the caller can show the full list with a caveat —
    NEVER silently drop everything. Operates on the candidate page, not the whole match
    set (honest sample when total > page)."""
    if not items or want not in ("negative", "positive"):
        return items, False
    listing = "\n".join(
        f"{i + 1}. {it.title} — {(it.snippet or '')[:120]}" for i, it in enumerate(items)
    )
    try:
        raw = llm.complete(
            _CLASSIFY_SYSTEM, f"Items:\n{listing}\n\nJSON array of {len(items)} labels:"
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("sentiment classify failed: %s", exc)
        return items, False
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if not m:
        return items, False
    try:
        labels = json.loads(m.group(0))
    except json.JSONDecodeError:
        return items, False
    if not isinstance(labels, list) or len(labels) < len(items):
        return items, False
    prefix = want[:3]  # 'neg' / 'pos'
    kept = [it for it, lab in zip(items, labels) if str(lab).strip().lower().startswith(prefix)]
    return kept, True


def _clauses(since_hours: int | None, languages: Sequence[str] | None) -> tuple[str, str]:
    since = " AND a.published_at > now() - make_interval(hours => :hours)" if since_hours else ""
    lang = " AND a.language_detected = ANY(:langs)" if languages else ""
    return since, lang


async def list_articles(
    conn: AsyncConnection,
    settings: Settings,
    *,
    entity_id: str | None = None,
    keyword: str | None = None,
    since_hours: int | None = None,
    languages: Sequence[str] | None = None,
    limit: int = 50,
) -> tuple[list[ListItem], int]:
    """Return (items, total_matched). ``total`` may exceed ``len(items)`` when the
    match set is larger than the cap — the UI shows 'showing N of M'. Entity path is
    preferred (precise); keyword path (FTS) is the fallback when no entity resolves."""
    limit = max(1, min(limit, _MAX_LIMIT))
    since, lang = _clauses(since_hours, languages)
    params: dict = {"limit": limit}
    if since_hours:
        params["hours"] = int(since_hours)
    if languages:
        params["langs"] = list(languages)

    if entity_id:
        where = _ENTITY_WHERE.format(since=since, lang=lang)
        params["eid"] = entity_id
    elif keyword:
        where = _KEYWORD_WHERE.format(since=since, lang=lang)
        params["kw"] = keyword
        params["cfg"] = settings.fts_config
    else:
        # Recency-only ('the latest/most recent article'): newest surfaceable overall.
        # published_at <= now() guards against future-dated feeds topping the list.
        where = ("FROM articles a WHERE a.substrate_status = 'ok' AND NOT a.is_duplicate "
                 "AND a.published_at <= now()" + since + lang)

    total = (await conn.execute(text(f"SELECT count(*) {where}"), params)).scalar() or 0
    rows = (
        await conn.execute(
            text(f"{_SELECT}{where} ORDER BY a.published_at DESC NULLS LAST LIMIT :limit"),
            params,
        )
    ).mappings().all()
    items = [
        ListItem(
            id=r["id"], title=r["title"], url=r["url"], published_at=r["published_at"],
            language=r["language"], source_id=r["source_id"],
            snippet=(r["snippet"] or "")[:240] or None,
        )
        for r in rows
        if (r["title"] or "").strip()
    ]
    return items, int(total)
