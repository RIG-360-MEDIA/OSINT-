"""Wayback Machine adapter — earliest archive snapshot lookup.

CDX API: http://web.archive.org/cdx/search/cdx?url=<u>&output=json&limit=...
For domains/usernames we look up archives of likely profile URLs.
Free, no key. Cached 24h.
"""

from __future__ import annotations

import logging

import httpx

from backend.adapters.base import AdapterContext, AdapterSpec, Finding
from backend.dossier.cache import cached

log = logging.getLogger(__name__)

_CDX = "http://web.archive.org/cdx/search/cdx"


async def fetch(ctx: AdapterContext) -> list[Finding]:
    targets = _candidate_urls(ctx)
    if not targets:
        return []

    findings: list[Finding] = []
    async with httpx.AsyncClient(timeout=ctx.timeout_s) as client:
        for u in targets:
            snap = await _earliest(client, u, ctx)
            if snap:
                ts, archived = snap
                findings.append(
                    Finding(
                        source="wayback",
                        field="earliest_archive",
                        value={"url": u, "first_seen": ts},
                        source_url=archived,
                        confidence=0.7,
                    )
                )
    return findings


def _candidate_urls(ctx: AdapterContext) -> list[str]:
    if ctx.target_type == "domain":
        return [f"http://{ctx.target}", f"https://{ctx.target}"]
    if ctx.target_type == "username":
        u = ctx.target.lstrip("@")
        return [
            f"https://twitter.com/{u}",
            f"https://github.com/{u}",
            f"https://reddit.com/user/{u}",
        ]
    return []


async def _earliest(
    client: httpx.AsyncClient, url: str, ctx: AdapterContext
) -> tuple[str, str] | None:
    async def _do_fetch() -> list:
        try:
            r = await client.get(
                _CDX,
                params={"url": url, "output": "json", "limit": "1", "filter": "statuscode:200"},
            )
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as e:
            log.debug("wayback cdx miss for %s: %s", url, e)
            return []

    data = await cached(
        source="wayback",
        target=url,
        target_type=ctx.target_type,
        ttl_hours=24,
        fetch_fn=_do_fetch,
    )
    if not isinstance(data, list) or len(data) < 2:
        return None
    row = data[1]
    if len(row) < 3:
        return None
    timestamp, original = row[1], row[2]
    return (timestamp, f"https://web.archive.org/web/{timestamp}/{original}")


SPEC = AdapterSpec(
    name="wayback",
    supported_types=("domain", "username"),
    fetch=fetch,
    sensitive=False,
)
