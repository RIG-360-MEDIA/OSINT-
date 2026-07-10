"""Wikipedia collector — encyclopedic profile for any notable entity.

Given a query (person, org, place, thing), returns the Wikipedia REST summary:
title, one-line description, first-paragraph extract, thumbnail, the Wikidata
QID (wikibase_item) and the canonical page URL. Free, no API key, no auth.

Exact-title first (fast path); on a miss, resolve the query via the opensearch API
so loose / abbreviated queries ("PLA navy") still land on the right article
("People's Liberation Army Navy"). The Tasking-brain 'encyclopedia' source, live.
"""
from __future__ import annotations

from typing import Any

import httpx

_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
_API = "https://en.wikipedia.org/w/api.php"
_HEADERS = {"User-Agent": "RIG-OSINT/1.0", "Accept": "application/json"}
# 'standard' pages carry a real article; these carry no usable profile.
_NON_ARTICLE = {"disambiguation", "no-extract", "internal error"}


def _to_title(q: str) -> str:
    """Wikipedia page titles use underscores for spaces; keep the rest verbatim."""
    return (q or "").strip().replace(" ", "_")


def _profile(d: dict[str, Any]) -> dict[str, Any]:
    urls = (d.get("content_urls") or {}).get("desktop") or {}
    return {
        "title": d.get("title"),
        "description": d.get("description"),
        "extract": d.get("extract"),
        "thumbnail": (d.get("thumbnail") or {}).get("source"),
        "wikibase_item": d.get("wikibase_item"),
        "page_url": urls.get("page"),
        "type": d.get("type"),
        "lang": d.get("lang"),
    }


async def _summary(client: httpx.AsyncClient, title: str) -> dict[str, Any] | None:
    """Fetch + parse a REST summary for a title; None on 404/error/non-article."""
    try:
        r = await client.get(_SUMMARY + _to_title(title), headers=_HEADERS)
    except Exception:
        return None
    if r.status_code != 200:
        return None
    try:
        d = r.json()
    except Exception:
        return None
    if (d.get("type") or "").lower() in _NON_ARTICLE or not d.get("extract"):
        return None
    return d


async def _resolve_title(client: httpx.AsyncClient, query: str) -> str | None:
    """Best-matching article title for a loose query (opensearch handles case/abbrev/redirects)."""
    try:
        r = await client.get(_API, headers=_HEADERS, params={
            "action": "opensearch", "search": query, "limit": 1, "namespace": 0, "format": "json"})
        arr = r.json()
        titles = arr[1] if isinstance(arr, list) and len(arr) > 1 else []
        return titles[0] if titles else None
    except Exception:
        return None


async def wiki_lookup(q: str) -> dict[str, Any]:
    """Encyclopedic profile for a notable entity. Returns partial data on any failure."""
    query = (q or "").strip()
    if not query:
        return {"query": query, "error": "empty query (wiki needs an entity name, e.g. Narendra Modi)"}

    out: dict[str, Any] = {"query": query, "found": False, "profile": None}
    resolved_from: str | None = None
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        d = await _summary(client, query)
        if d is None:                                  # loose query → resolve to the real title, retry
            title = await _resolve_title(client, query)
            if title and title.lower() != query.lower():
                resolved_from = title
                d = await _summary(client, title)
        if d is None:
            out["summary"] = {"found": False, "reason": "no matching Wikipedia article"}
            return out

    profile = _profile(d)
    qid = profile["wikibase_item"]
    out["found"] = True
    out["profile"] = profile
    if resolved_from:
        out["resolved_via_search"] = resolved_from
    desc = profile["description"] or (profile["extract"] or "")[:120] or None
    out["summary"] = {
        "found": True,
        "one_line": desc,
        "has_wikidata_qid": bool(qid),
        "wikidata_qid": qid,
        "ambiguous": (d.get("type") or "").lower() == "disambiguation",
        "resolved_via_search": resolved_from,
    }
    return out
