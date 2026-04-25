"""SearXNG adapter — metasearch across DuckDuckGo, Brave, Mojeek, Yandex,
Qwant, Startpage, Wikipedia, Reddit, GitHub, and friends. All free, no keys.

Reads SEARXNG_URL from env. Returns first ~10 hits as Findings, one per result.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from backend.adapters.base import AdapterContext, AdapterSpec, Finding

log = logging.getLogger(__name__)

_SEARXNG_URL = os.getenv("SEARXNG_URL", "http://rig-searxng:8080").rstrip("/")
_MAX_RESULTS = 10


async def fetch(ctx: AdapterContext) -> list[Finding]:
    if ctx.target_type not in ("name", "email", "phone", "username", "domain"):
        return []

    query = _build_query(ctx)
    params = {
        "q": query,
        "format": "json",
        "safesearch": "0",
        "language": "en",
    }

    try:
        async with httpx.AsyncClient(timeout=ctx.timeout_s) as client:
            resp = await client.get(f"{_SEARXNG_URL}/search", params=params)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("searxng fetch failed for %s: %s", ctx.target, e)
        return []

    results = data.get("results") or []
    findings: list[Finding] = []
    for r in results[:_MAX_RESULTS]:
        url = r.get("url")
        title = r.get("title")
        if not url or not title:
            continue
        findings.append(
            Finding(
                source="searxng",
                field="web_mention",
                value={
                    "title": title,
                    "snippet": (r.get("content") or "")[:400],
                    "engine": r.get("engine"),
                },
                source_url=url,
                confidence=0.6,
            )
        )
    return findings


def _build_query(ctx: AdapterContext) -> str:
    if ctx.target_type == "email":
        return f'"{ctx.target}"'
    if ctx.target_type == "phone":
        return f'"{ctx.target}"'
    if ctx.target_type == "username":
        return f'"{ctx.target}" site:twitter.com OR site:github.com OR site:reddit.com'
    return ctx.target


SPEC = AdapterSpec(
    name="searxng",
    supported_types=("name", "email", "phone", "username", "domain"),
    fetch=fetch,
    sensitive=False,
)
