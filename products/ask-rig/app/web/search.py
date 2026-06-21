"""SearXNG JSON search client — graceful-degrade.

rig-searxng already runs in the deployment. We never let a web outage break the
corpus path: any failure returns ([], reason) and the caller proceeds corpus-only.
"""
from __future__ import annotations

import httpx

from app.config import Settings
from app.schemas_account import WebResult


def _parse(results: list[dict], k: int) -> list[WebResult]:
    out: list[WebResult] = []
    for item in results[:k]:
        url = item.get("url") or ""
        if not url:
            continue
        out.append(
            WebResult(
                title=(item.get("title") or "").strip() or url,
                url=url,
                snippet=(item.get("content") or None),
                engine=item.get("engine") or None,
            )
        )
    return out


async def search_web(settings: Settings, query: str, k: int | None = None) -> tuple[list[WebResult], str | None]:
    """Return (results, error). error is None on success, else a short reason."""
    if not settings.web_enabled:
        return [], "web disabled"
    k = k or settings.web_max_results
    url = settings.searxng_url.rstrip("/") + "/search"
    params = {"q": query, "format": "json", "safesearch": "0"}
    try:
        async with httpx.AsyncClient(timeout=settings.web_fetch_timeout) as client:
            resp = await client.get(url, params=params, headers={"Accept": "application/json"})
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001 - any web failure must degrade, not crash
        return [], f"web search unavailable: {type(exc).__name__}"
    return _parse(data.get("results") or [], k), None
