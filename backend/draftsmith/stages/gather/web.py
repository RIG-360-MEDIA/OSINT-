"""backend.draftsmith.stages.gather.web — Stage 2 (web slice): SearXNG search
+ full-text fetch of the top hits.

    items = await gather_web(plan)

Two hops:
  1. SearXNG JSON search (config.SEARXNG_URL) per plan.queries.web query
     (<=3), collecting distinct URLs across queries.
  2. Full-text fetch of the top config.FETCH_CAPS['web_fetch'] distinct
     URLs, 2 concurrent, each bounded by config.TIMEOUTS['gather_web_fetch'].
     Extraction prefers trafilatura (real boilerplate removal); falls back
     to a plain BeautifulSoup text pull if trafilatura is not importable or
     yields nothing.

A search hit that never gets fetched (beyond the web_fetch cap) or whose
fetch/extraction fails is simply not emitted — a two-line SearXNG snippet is
not a citable primary-source snapshot, and EvidenceItem.text is what the
writer may quote verbatim. Every fetch is isolated in its own try/except so
one dead URL never aborts the others.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx

from backend.draftsmith import config
from backend.draftsmith.models import EvidenceItem, QueryPlan
from backend.draftsmith.stages.gather._shared import (
    clip_text,
    domain_of,
    make_source_id,
    parse_iso_datetime,
)

logger = logging.getLogger(__name__)

_SOURCE_TYPE = "web"
_SOURCE_ID_PREFIX = config.SOURCE_ID_PREFIX[_SOURCE_TYPE]
_SEARXNG_TIMEOUT = httpx.Timeout(float(config.TIMEOUTS["gather_source"]), connect=10.0)
_FETCH_TIMEOUT = httpx.Timeout(float(config.TIMEOUTS["gather_web_fetch"]), connect=10.0)
_FETCH_CONCURRENCY = 2
_MIN_BODY_CHARS = 200  # below this, extraction almost certainly failed silently
_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


async def gather_web(plan: QueryPlan) -> list[EvidenceItem]:
    """Stage 2 (web slice): SearXNG search then full-text fetch of the top
    hits, normalised to EvidenceItem."""
    if plan is None:
        raise ValueError("gather_web: plan is required")

    queries = list(plan.queries.web)[:3]
    if not queries:
        return []

    hits = await _search_all(queries)
    if not hits:
        return []

    fetch_cap = config.FETCH_CAPS["web_fetch"]
    to_fetch = hits[:fetch_cap]

    sem = asyncio.Semaphore(_FETCH_CONCURRENCY)

    async def _one(hit: dict[str, Any]) -> Optional[EvidenceItem]:
        async with sem:
            return await _fetch_evidence(hit)

    fetched = await asyncio.gather(*[_one(h) for h in to_fetch])
    return [item for item in fetched if item is not None]


async def _search_all(queries: list[str]) -> list[dict[str, Any]]:
    """SearXNG JSON search per query; distinct URLs across queries (a
    duplicate hit keeps the earlier query's ranking). Each query is
    isolated in its own try/except so one bad query never drops the rest."""
    per_query_cap = config.FETCH_CAPS["web"]
    seen_urls: set[str] = set()
    hits: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=_SEARXNG_TIMEOUT) as client:
        for query in queries:
            try:
                resp = await client.get(
                    config.SEARXNG_URL.rstrip("/") + "/search",
                    params={"q": query, "format": "json"},
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                logger.exception("gather_web: SearXNG search failed (query=%r)", query)
                continue

            for result in (data.get("results") or [])[:per_query_cap]:
                url = (result.get("url") or "").strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                hits.append(result)
    return hits


async def _fetch_evidence(hit: dict[str, Any]) -> Optional[EvidenceItem]:
    url = (hit.get("url") or "").strip()
    if not url:
        return None

    try:
        async with httpx.AsyncClient(
            timeout=_FETCH_TIMEOUT, follow_redirects=True, headers={"User-Agent": _UA},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception:
        logger.warning("gather_web: fetch failed for %s", url, exc_info=True)
        return None

    body = _extract_text(html, url)
    if not body or len(body) < _MIN_BODY_CHARS:
        return None

    outlet = domain_of(url)
    published_at = parse_iso_datetime(hit.get("publishedDate") or hit.get("published_date"))
    engine = hit.get("engine") or hit.get("engines")

    return EvidenceItem(
        source_id=make_source_id(_SOURCE_ID_PREFIX, url),
        source_type=_SOURCE_TYPE,  # type: ignore[arg-type]
        trust_tier=_tier_for_outlet(outlet),  # type: ignore[arg-type]
        text=clip_text(body),
        title=hit.get("title") or None,
        url=url,
        outlet=outlet,
        author=None,
        published_at=published_at,
        relevance=0.0,
        extra={"engine": engine},
    )


def _tier_for_outlet(outlet: Optional[str]) -> int:
    """Substring match on the (lowercased) host against config.WEB_OUTLET_TIER
    — 'edition.cnn.com' must still match 'cnn.com', so this is deliberately
    substring, not exact-key, lookup."""
    if not outlet:
        return config.WEB_DEFAULT_TIER
    for known_outlet, tier in config.WEB_OUTLET_TIER.items():
        if known_outlet in outlet:
            return tier
    return config.WEB_DEFAULT_TIER


def _extract_text(html: str, url: str) -> str:
    try:
        import trafilatura

        extracted = trafilatura.extract(html, url=url, favor_recall=True)
        if extracted and extracted.strip():
            return extracted.strip()
    except ImportError:
        pass
    except Exception:
        logger.debug("gather_web: trafilatura extraction failed for %s", url, exc_info=True)

    return _bs4_fallback(html)


def _bs4_fallback(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return ""
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)
    except Exception:
        logger.debug("gather_web: bs4 fallback failed for %s", url, exc_info=True)
        return ""
