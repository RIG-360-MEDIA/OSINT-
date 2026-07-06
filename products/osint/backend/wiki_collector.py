"""Wikipedia collector — encyclopedic profile for any notable entity.

Given a query (person, org, place, thing), returns the Wikipedia REST summary:
title, one-line description, first-paragraph extract, thumbnail, the Wikidata
QID (wikibase_item) and the canonical page URL. Free, no API key, no auth.
This is the Tasking-brain 'encyclopedia' source made live for notable keywords.
"""
from __future__ import annotations

from typing import Any

import httpx

_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
_HEADERS = {"User-Agent": "RIG-OSINT/1.0", "Accept": "application/json"}
# 'standard' pages carry a real article; these carry no usable profile.
_NON_ARTICLE = {"disambiguation", "no-extract", "internal error"}


def _to_title(q: str) -> str:
    """Wikipedia page titles use underscores for spaces; keep the rest verbatim."""
    return (q or "").strip().replace(" ", "_")


async def wiki_lookup(q: str) -> dict[str, Any]:
    """Encyclopedic profile for a notable entity. Returns partial data on any failure."""
    query = (q or "").strip()
    if not query:
        return {"query": query, "error": "empty query (wiki needs an entity name, e.g. Narendra Modi)"}

    out: dict[str, Any] = {"query": query, "found": False, "profile": None}
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        try:
            r = await client.get(_SUMMARY + _to_title(query), headers=_HEADERS)
        except Exception as exc:  # network / timeout — never raise
            out["error"] = type(exc).__name__
            return out

        if r.status_code == 404:
            out["status"] = 404
            out["summary"] = {"found": False, "reason": "no matching Wikipedia article"}
            return out
        if r.status_code != 200:
            out["status"] = r.status_code
            out["summary"] = {"found": False, "reason": f"unexpected status {r.status_code}"}
            return out

        try:
            d = r.json()
        except Exception as exc:
            out["error"] = f"bad json ({type(exc).__name__})"
            return out

    page_type = (d.get("type") or "").lower()
    qid = d.get("wikibase_item")
    urls = (d.get("content_urls") or {}).get("desktop") or {}
    profile = {
        "title": d.get("title"),
        "description": d.get("description"),
        "extract": d.get("extract"),
        "thumbnail": (d.get("thumbnail") or {}).get("source"),
        "wikibase_item": qid,
        "page_url": urls.get("page"),
        "type": d.get("type"),
        "lang": d.get("lang"),
    }
    is_article = page_type not in _NON_ARTICLE and bool(d.get("extract"))
    out["found"] = is_article
    out["profile"] = profile

    # a small derived signal: is this a resolvable, structured entity?
    desc = profile["description"] or (profile["extract"] or "")[:120] or None
    out["summary"] = {
        "found": is_article,
        "one_line": desc,
        "has_wikidata_qid": bool(qid),
        "wikidata_qid": qid,
        "ambiguous": page_type == "disambiguation",
    }
    return out
