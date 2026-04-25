"""GDELT 2.0 DOC adapter — free global news mention search.

Endpoint: https://api.gdeltproject.org/api/v2/doc/doc?query=<q>&mode=ArtList&format=json
No key. Cached 6h.
"""

from __future__ import annotations

import logging
import os

import httpx

from backend.adapters.base import AdapterContext, AdapterSpec, Finding
from backend.dossier.cache import cached

log = logging.getLogger(__name__)

_API = "https://api.gdeltproject.org/api/v2/doc/doc"
_MAX_RESULTS = 8


def _gdelt_timeout(ctx_timeout_s: float) -> float:
    """GDELT is slow — allow per-adapter override via DOSSIER_GDELT_TIMEOUT_S."""
    raw = os.environ.get("DOSSIER_GDELT_TIMEOUT_S", "").strip()
    try:
        if raw:
            return max(float(raw), ctx_timeout_s)
    except ValueError:
        log.warning("invalid DOSSIER_GDELT_TIMEOUT_S=%r, falling back", raw)
    return max(ctx_timeout_s, 25.0)


async def fetch(ctx: AdapterContext) -> list[Finding]:
    if ctx.target_type not in ("name", "domain", "username"):
        return []

    query = f'"{ctx.target}"' if " " in ctx.target else ctx.target
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": str(_MAX_RESULTS),
        "sort": "DateDesc",
    }
    timeout_s = _gdelt_timeout(ctx.timeout_s)

    async def _do_fetch() -> dict:
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                r = await client.get(_API, params=params)
                r.raise_for_status()
                return r.json()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("gdelt fetch failed for %s: %s", ctx.target, e)
            return {}

    data = await cached(
        source="gdelt",
        target=ctx.target,
        target_type=ctx.target_type,
        ttl_hours=6,
        fetch_fn=_do_fetch,
    )

    if not data or not isinstance(data, dict):
        return []

    articles = data.get("articles") or []
    findings: list[Finding] = []
    for a in articles[:_MAX_RESULTS]:
        if not isinstance(a, dict):
            continue
        url = a.get("url")
        if not url:
            continue
        findings.append(
            Finding(
                source="gdelt",
                field="news_mention",
                value={
                    "title": a.get("title"),
                    "domain": a.get("domain"),
                    "language": a.get("language"),
                    "seendate": a.get("seendate"),
                    "tone": a.get("tone"),
                },
                source_url=url,
                confidence=0.65,
            )
        )
    return findings


SPEC = AdapterSpec(
    name="gdelt",
    supported_types=("name", "domain", "username"),
    fetch=fetch,
    sensitive=False,
)
