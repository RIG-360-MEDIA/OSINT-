"""Web-search / discovery collector — multi-engine meta-search via SearXNG.

Given a keyword (optionally with dork operators like `site:` / `filetype:`), returns
ranked web results, the distinct source domains covering the topic, any
knowledge-panel infobox, and engine suggestions. Also derives a best-guess
OFFICIAL domain (with a confidence flag) — the bridge that lets an org keyword
feed the infra/archive collectors. Free, no key: SearXNG is in-stack at
`rig-searxng:8080`. Honest: reports which engines were unresponsive, and flags
when the top hit is unlikely to be the entity's own site (ambiguous keyword).
"""
from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlsplit

import httpx

_SEARXNG = os.getenv("SEARXNG_URL", "http://rig-searxng:8080").rstrip("/") + "/search"

# Domains that are never an entity's OWN official site (aggregators/social/ref) —
# skipped when deriving the official domain, but still counted as sources.
_NON_OFFICIAL = {
    "wikipedia.org", "wikidata.org", "wikimedia.org", "youtube.com", "facebook.com",
    "twitter.com", "x.com", "instagram.com", "linkedin.com", "reddit.com", "amazon.com",
    "google.com", "bing.com", "duckduckgo.com", "yandex.com", "pinterest.com",
    "tumblr.com", "britannica.com", "imdb.com", "tripadvisor.com", "quora.com",
    "medium.com", "crunchbase.com", "bloomberg.com", "zaubacorp.com", "tofler.in",
}

# Registrable-domain second-level suffixes (no tldextract dependency on the box).
_TWO_LEVEL = {
    "co.uk", "org.uk", "ac.uk", "gov.uk", "co.in", "net.in", "org.in", "gov.in",
    "ac.in", "edu.in", "com.au", "net.au", "org.au", "gov.au", "co.nz", "co.za",
    "com.br", "com.cn", "com.sg", "com.hk", "co.jp", "or.jp", "com.tr", "com.mx",
}


def _registrable_domain(url: str) -> str | None:
    """eTLD+1 of a URL (windlass.com, example.co.in). Best-effort, never raises."""
    try:
        host = (urlsplit(url).hostname or "").lower()
    except Exception:
        return None
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    if ".".join(parts[-2:]) in _TWO_LEVEL:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _parse_result(x: dict[str, Any]) -> dict[str, Any]:
    """One SearXNG result → the fields we surface. Never raises."""
    url = x.get("url") or ""
    return {
        "title": (x.get("title") or "").strip(),
        "url": url,
        "domain": _registrable_domain(url),
        "snippet": (x.get("content") or "").strip()[:300],
        "engine": x.get("engine"),
        "engines": x.get("engines") or ([x.get("engine")] if x.get("engine") else []),
        "score": x.get("score"),
        "published": x.get("publishedDate"),
        "category": x.get("category"),
    }


def _parse_infobox(boxes: Any) -> dict[str, Any] | None:
    """First knowledge-panel infobox (title/content/attributes/urls), if any."""
    if not isinstance(boxes, list) or not boxes:
        return None
    b = boxes[0] or {}
    attrs = [
        {"label": a.get("label"), "value": a.get("value")}
        for a in (b.get("attributes") or []) if isinstance(a, dict)
    ]
    urls = [
        {"title": u.get("title"), "url": u.get("url")}
        for u in (b.get("urls") or []) if isinstance(u, dict)
    ]
    return {
        "title": b.get("infobox") or b.get("title"),
        "content": (b.get("content") or "").strip()[:600] or None,
        "engine": b.get("engine"),
        "attributes": attrs[:12],
        "urls": urls[:8],
    }


def _official_domain(results: list[dict[str, Any]], q: str) -> dict[str, Any]:
    """Best-guess official domain of the entity + a confidence flag.

    The first result whose domain isn't a known aggregator/social/ref site. HIGH
    confidence only when the domain's core label matches a query token (so an
    ambiguous keyword whose top hit is an unrelated site is flagged LOW, not
    passed off as the entity's site — e.g. 'Tridel' → a Wordle game)."""
    q_toks = {t for t in re.findall(r"[a-z0-9]+", q.lower()) if len(t) >= 3}
    first_nonref: dict[str, Any] | None = None
    for r in results:
        dom = r.get("domain")
        if not dom or dom in _NON_OFFICIAL:
            continue
        label = dom.split(".")[0]
        if label in q_toks or any(
                len(t) >= 4 and (t in label or label in t) for t in q_toks):
            # a domain whose name matches the query = the entity's own site (HIGH),
            # even if it wasn't the first result (an unrelated site can outrank it)
            return {"domain": dom, "confidence": "high", "via_title": r.get("title")}
        if first_nonref is None:
            first_nonref = r
    if first_nonref:   # nothing name-matched → best guess is the top non-ref hit (LOW)
        return {"domain": first_nonref["domain"], "confidence": "low",
                "via_title": first_nonref.get("title")}
    return {"domain": None, "confidence": "none", "via_title": None}


async def web_search(q: str, *, limit: int = 10) -> dict[str, Any]:
    """Meta-search a keyword/dork via SearXNG. Partial on any failure.

    Dork operators (`site:`, `filetype:`, quotes) pass straight through — SearXNG
    parses them natively. Engine support for a given operator varies (reported via
    `unresponsive_engines`)."""
    q = (q or "").strip()
    if not q:
        return {"query": q, "error": "empty query (web search needs a keyword or dork)"}

    out: dict[str, Any] = {
        "query": q, "results": [], "top_sources": [], "infobox": None,
        "suggestions": [], "summary": None,
    }
    params = {"q": q, "format": "json"}
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        try:
            r = await client.get(_SEARXNG, params=params,
                                 headers={"Accept": "application/json"})
            if r.status_code == 200 and r.text.lstrip().startswith("{"):
                data = r.json()
                raw = data.get("results", []) or []
                parsed = [_parse_result(x) for x in raw]
                out["results"] = parsed[:limit]
                out["infobox"] = _parse_infobox(data.get("infoboxes"))
                out["suggestions"] = [s for s in (data.get("suggestions") or [])][:8]
                out["number_of_results"] = data.get("number_of_results")
                out["unresponsive_engines"] = data.get("unresponsive_engines") or []
                out["_parsed_all"] = parsed          # for source/domain derivation
            else:
                out["searxng_status"] = r.status_code
        except Exception as exc:
            out["searxng_error"] = type(exc).__name__

    parsed_all = out.pop("_parsed_all", [])
    # source discovery: which domains cover this, ranked by hit count
    domain_hits: dict[str, int] = {}
    for r in parsed_all:
        if r.get("domain"):
            domain_hits[r["domain"]] = domain_hits.get(r["domain"], 0) + 1
    out["top_sources"] = [
        {"domain": d, "hits": n}
        for d, n in sorted(domain_hits.items(), key=lambda kv: (-kv[1], kv[0]))
    ][:8]

    official = _official_domain(parsed_all, q)
    out["summary"] = {
        "result_count": len(parsed_all),
        "distinct_sources": len(domain_hits),
        "official_domain": official["domain"],
        "official_domain_confidence": official["confidence"],
        "has_infobox": out["infobox"] is not None,
        "engines_unresponsive": len(out.get("unresponsive_engines") or []),
    }
    return out
