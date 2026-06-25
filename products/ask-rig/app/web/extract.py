"""Fetch + main-text extraction for a web URL, with an SSRF guard.

The guard resolves the host and refuses private / loopback / link-local / reserved
targets so a malicious search result can't make us fetch internal services. Size
and timeout are capped. Extraction (trafilatura) is CPU-bound → run off-loop.
"""
from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from urllib.parse import urlparse

import httpx
import trafilatura

from app.config import Settings
from app.schemas_account import WebResult

_UA = "Mozilla/5.0 (compatible; RIG-Research/1.0; +https://rig360media.com)"

# Navigational / portal junk that SearXNG returns for broad queries — homepages,
# e-papers, govt portals, login walls, "latest headlines" landing pages. These
# carry no article content, just crowd out real sources, so we drop them before
# they reach the writer (titles + URL-shape are far more reliable than content here).
_JUNK_TITLE = re.compile(
    r"\b(e[\-\s]?paper|state portal|web ?portal|govt(?:\.|\s)?\s?services|"
    r"latest .{0,30}headlines|public view|sign\s?in|log\s?in|home\s?page|"
    r"official (?:website|portal)|citizen services)\b",
    re.IGNORECASE,
)
_JUNK_HOST_HINTS = ("epaper", "epaper", "/portal", "highcourt", "hcourt")
_HOMEPAGE_PATHS = {"", "home", "index", "index.html", "index.php"}

# Tiny process-wide URL→text cache so a source seen across turns isn't re-fetched.
# Bounded FIFO (drops the oldest on overflow). None caches a known failure too.
_EXTRACT_CACHE: dict[str, str | None] = {}
_CACHE_MAX = 256


def is_safe_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified
        ):
            return False
    return True


async def fetch_extract(settings: Settings, url: str) -> str | None:
    """Return extracted main text, or None (unsafe / unreachable / no content)."""
    if not is_safe_url(url):
        return None
    try:
        async with httpx.AsyncClient(
            timeout=settings.web_fetch_timeout, follow_redirects=True, max_redirects=2
        ) as client:
            resp = await client.get(url, headers={"User-Agent": _UA})
            if resp.status_code != 200:
                return None
            raw = resp.content[: settings.web_max_bytes]
    except Exception:  # noqa: BLE001 - a bad page must not break research
        return None
    html = raw.decode(resp.encoding or "utf-8", errors="replace")
    text = await asyncio.to_thread(
        trafilatura.extract, html, include_comments=False, include_tables=False
    )
    return (text or "").strip() or None


async def _cached_extract(settings: Settings, url: str) -> str | None:
    if url in _EXTRACT_CACHE:
        return _EXTRACT_CACHE[url]
    text = await fetch_extract(settings, url)
    if len(_EXTRACT_CACHE) >= _CACHE_MAX:
        _EXTRACT_CACHE.pop(next(iter(_EXTRACT_CACHE)), None)
    _EXTRACT_CACHE[url] = text
    return text


async def enrich_web_results(
    settings: Settings, results: list[WebResult], top_n: int
) -> list[WebResult]:
    """Replace the snippet of the top-N web results with their full extracted article
    text (trafilatura), so the writer sees whole pages, not teasers. Bounded (only
    top-N fetched), cached, concurrent, and best-effort — a result whose fetch fails
    or yields nothing keeps its original snippet. Lower-ranked results are untouched."""
    if not settings.web_extract_enabled or top_n <= 0 or not results:
        return results
    head = results[:top_n]
    texts = await asyncio.gather(
        *(_cached_extract(settings, w.url) for w in head), return_exceptions=True
    )
    cap = settings.web_extract_max_chars
    enriched: list[WebResult] = []
    for w, text in zip(head, texts):
        if isinstance(text, str) and len(text) > len(w.snippet or ""):
            enriched.append(WebResult(**{**w.model_dump(), "snippet": text[:cap]}))
        else:  # failure, exception, or not richer than the snippet → leave as-is
            enriched.append(w)
    return enriched + results[top_n:]


def _is_homepage(url: str) -> bool:
    try:
        path = urlparse(url).path.strip("/").lower()
    except Exception:  # noqa: BLE001 - a malformed URL is itself junk
        return True
    return path in _HOMEPAGE_PATHS


def is_low_value_web(w: WebResult, min_snippet: int = 40) -> bool:
    """True if a web result is navigational/portal junk rather than an article —
    a junk title, a bare homepage URL, a portal/e-paper host, or a near-empty
    snippet. These crowd out real sources and should never reach the writer."""
    title = (w.title or "").strip()
    if not title or _JUNK_TITLE.search(title):
        return True
    if _is_homepage(w.url):
        return True
    if any(hint in (w.url or "").lower() for hint in _JUNK_HOST_HINTS):
        return True
    if len((w.snippet or "").strip()) < min_snippet:
        return True
    return False


def filter_web_results(results: list[WebResult], min_snippet: int = 40) -> list[WebResult]:
    """Drop navigational/portal junk, preserving order. Run BEFORE enrichment so we
    don't waste fetches on homepages."""
    return [w for w in results if not is_low_value_web(w, min_snippet)]
