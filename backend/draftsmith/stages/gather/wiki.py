"""backend.draftsmith.stages.gather.wiki — Stage 2 (background slice):
Wikipedia REST summary/intro for each planner-supplied title.

    items = await gather_wiki(plan)

One REST `page/summary` call per plan.queries.wikipedia_titles entry
(<=config.FETCH_CAPS['wikipedia'], already <=5 by the SourceQueries
contract), sent with config.WIKI_USER_AGENT. Always trust_tier == 1
(config.BASE_TRUST_TIER['wikipedia']) — background/context only; it is the
prompt layer that actually enforces "context, never a primary citation",
this adapter just fetches and normalises. Each title is isolated in its own
try/except so one bad/missing/disambiguation title never drops the rest.

Wikimedia IMAGES are a separate stage (7, images) — not fetched here.
"""
from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import quote

import httpx

from backend.draftsmith import config
from backend.draftsmith.models import EvidenceItem, QueryPlan
from backend.draftsmith.stages.gather._shared import clip_text, make_source_id, parse_iso_datetime

logger = logging.getLogger(__name__)

_SOURCE_TYPE = "wikipedia"
_SOURCE_ID_PREFIX = config.SOURCE_ID_PREFIX[_SOURCE_TYPE]
_TRUST_TIER = 1
_TIMEOUT = httpx.Timeout(float(config.TIMEOUTS["gather_source"]), connect=10.0)
_DEFAULT_LANG = "en"
_LANG_HINT_RE = re.compile(r"^[a-z]{2,3}$")


async def gather_wiki(plan: QueryPlan) -> list[EvidenceItem]:
    """Stage 2 (background slice): Wikipedia summary/intro per planner
    title, normalised to EvidenceItem."""
    if plan is None:
        raise ValueError("gather_wiki: plan is required")

    titles = list(plan.queries.wikipedia_titles)[: config.FETCH_CAPS["wikipedia"]]
    if not titles:
        return []

    lang = _wiki_lang(plan)
    headers = {"User-Agent": config.WIKI_USER_AGENT, "Accept": "application/json"}

    items: list[EvidenceItem] = []
    async with httpx.AsyncClient(
        timeout=_TIMEOUT, headers=headers, follow_redirects=True,
    ) as client:
        for title in titles:
            item = await _fetch_one(client, lang, title)
            if item is not None:
                items.append(item)
    return items


def _wiki_lang(plan: QueryPlan) -> str:
    """Best-effort REST subdomain from the planner's language_hints; falls
    back to English. The plan contract has no per-title language field, so
    this is a whole-plan approximation, not a per-title lookup."""
    for hint in plan.language_hints:
        candidate = (hint or "").strip().lower()
        if _LANG_HINT_RE.match(candidate):
            return candidate
    return _DEFAULT_LANG


async def _fetch_one(client: httpx.AsyncClient, lang: str, title: str) -> Optional[EvidenceItem]:
    clean_title = (title or "").strip()
    if not clean_title:
        return None

    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{_encode_title(clean_title)}"
    try:
        resp = await client.get(url)
    except Exception:
        logger.warning("gather_wiki: request failed for title=%r", clean_title, exc_info=True)
        return None

    if resp.status_code == 404:
        logger.info("gather_wiki: no page for title=%r (lang=%s)", clean_title, lang)
        return None

    try:
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        logger.warning("gather_wiki: bad response for title=%r", clean_title, exc_info=True)
        return None

    if data.get("type") == "disambiguation":
        logger.info("gather_wiki: %r is a disambiguation page, skipping", clean_title)
        return None

    extract = (data.get("extract") or "").strip()
    if not extract:
        return None

    resolved_title = data.get("title") or clean_title
    page_url = (
        (data.get("content_urls") or {}).get("desktop", {}).get("page")
        or f"https://{lang}.wikipedia.org/wiki/{_encode_title(resolved_title)}"
    )
    published_at = parse_iso_datetime(data.get("timestamp"))

    return EvidenceItem(
        source_id=make_source_id(_SOURCE_ID_PREFIX, f"{lang}:{resolved_title}"),
        source_type=_SOURCE_TYPE,  # type: ignore[arg-type]
        trust_tier=_TRUST_TIER,  # type: ignore[arg-type]
        text=clip_text(extract),
        title=resolved_title,
        url=page_url,
        outlet="wikipedia",
        author=None,
        published_at=published_at,
        relevance=0.0,
        extra={"lang": lang, "description": data.get("description")},
    )


def _encode_title(title: str) -> str:
    return quote(title.replace(" ", "_"), safe="")
