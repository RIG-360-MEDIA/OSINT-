"""Google News RSS collector — free, NO key, reliable from a datacenter IP.

`news.google.com/rss/search` returns fresh, relevance+recency-ranked news for any keyword
as an RSS feed. Unlike scraping search engines (Google/Brave/Mojeek 429/403-block server
IPs), the RSS endpoint is bot-tolerant and fast — ~100 items in <1s, verified from the box.
This is the reliable "latest content on a keyword" source. Multilingual via hl/gl/ceid.
"""
from __future__ import annotations

import html
import re
import urllib.parse
from typing import Any

import httpx

_RSS = "https://news.google.com/rss/search"
_BING = "https://www.bing.com/news/search"
_HEADERS = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124 Safari/537.36")}


def _tag(block: str, tag: str) -> str | None:
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S)
    return html.unescape(m.group(1).strip()) if m else None


def _clean(s: str | None) -> str | None:
    if not s:
        return None
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip() or None


async def news_search(q: str, *, limit: int = 15, lang: str = "en-US", country: str = "US") -> dict[str, Any]:
    """Fresh news for a keyword via Google News RSS. Returns partial data on any failure."""
    query = (q or "").strip()
    if not query:
        return {"query": query, "articles": [], "count": 0, "error": "empty query"}
    ceid = f"{country}:{lang.split('-')[0]}"
    url = (f"{_RSS}?q={urllib.parse.quote(query)}"
           f"&hl={lang}&gl={country}&ceid={urllib.parse.quote(ceid)}")
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url, headers=_HEADERS)
            body = r.text
    except Exception as exc:                              # network/timeout — never raise
        return {"query": query, "articles": [], "count": 0, "error": f"{type(exc).__name__}: {exc}"[:110]}

    items = re.findall(r"<item>(.*?)</item>", body, re.S)
    articles: list[dict[str, Any]] = []
    for it in items[:limit]:
        title = _tag(it, "title")
        src_m = re.search(r'<source url="([^"]*)">(.*?)</source>', it, re.S)
        source = html.unescape(src_m.group(2)) if src_m else None
        source_url = src_m.group(1) if src_m else None
        if title and source and title.endswith(f" - {source}"):   # RSS titles are "Headline - Source"
            title = title[: -(len(source) + 3)].strip()
        articles.append({
            "title": title,
            "url": _tag(it, "link"),                       # Google redirect link (opens the article)
            "source": source,
            "source_url": source_url,
            "published": _tag(it, "pubDate"),              # already newest-first from Google
            "snippet": _clean(_tag(it, "description")),
        })
    return {
        "query": query,
        "articles": articles,
        "count": len(articles),
        "summary": {
            "total_available": len(items),
            "returned": len(articles),
            "sources": sorted({a["source"] for a in articles if a["source"]})[:14],
        },
    }


async def bing_news_search(q: str, *, limit: int = 15) -> dict[str, Any]:
    """Bing News RSS — independent no-key news feed; redundancy so news never depends on
    one provider. Bing gives the REAL article URL (not a redirect). Partial data on failure."""
    query = (q or "").strip()
    if not query:
        return {"query": query, "articles": [], "count": 0, "error": "empty query"}
    url = f"{_BING}?q={urllib.parse.quote(query)}&format=rss&count={min(limit, 50)}"
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url, headers=_HEADERS)
            body = r.text
    except Exception as exc:
        return {"query": query, "articles": [], "count": 0, "error": f"{type(exc).__name__}: {exc}"[:110]}
    items = re.findall(r"<item>(.*?)</item>", body, re.S)
    articles = [{
        "title": _tag(it, "title"),
        "url": _tag(it, "link"),                          # Bing gives the direct article URL
        "source": None,
        "published": _tag(it, "pubDate"),
        "snippet": _clean(_tag(it, "description")),
    } for it in items[:limit]]
    return {"query": query, "articles": articles, "count": len(articles),
            "summary": {"total_available": len(items), "returned": len(articles)}}
