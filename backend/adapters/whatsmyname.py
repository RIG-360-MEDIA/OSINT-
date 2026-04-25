"""WhatsMyName adapter — username enumeration across ~600 sites.

Uses the public WMN data file (JSON list of site checks) and probes a curated
subset of high-signal sites concurrently. Free, no key. Cached 24h per username.
"""

from __future__ import annotations

import asyncio
import logging
import re

import httpx

from backend.adapters.base import AdapterContext, AdapterSpec, Finding
from backend.dossier.cache import cached

log = logging.getLogger(__name__)

_WMN_URL = "https://raw.githubusercontent.com/WebBreacher/WhatsMyName/main/wmn-data.json"
_TARGET_SITES = {
    "GitHub", "GitLab", "Twitter", "Reddit", "Instagram", "TikTok",
    "YouTube", "Pinterest", "Medium", "Telegram", "Twitch", "Steam",
    "HackerNews", "Keybase", "Pastebin", "DevTo", "ProductHunt",
    "AboutMe", "Quora", "Vimeo", "SoundCloud", "Spotify", "Patreon",
}
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{2,40}$")
_FETCH_CONCURRENCY = 8
_PROBE_TIMEOUT_S = 4.0


async def fetch(ctx: AdapterContext) -> list[Finding]:
    if ctx.target_type != "username":
        return []
    if not _USERNAME_RE.match(ctx.target):
        return []

    sites = await _load_sites()
    if not sites:
        return []

    sem = asyncio.Semaphore(_FETCH_CONCURRENCY)
    async with httpx.AsyncClient(
        timeout=_PROBE_TIMEOUT_S,
        follow_redirects=False,
        headers={"User-Agent": "Mozilla/5.0 RIG-Dossier/1.0"},
    ) as client:
        results = await asyncio.gather(
            *(_probe(client, sem, site, ctx.target) for site in sites),
            return_exceptions=False,
        )

    findings: list[Finding] = []
    for site, hit_url in zip(sites, results):
        if not hit_url:
            continue
        findings.append(
            Finding(
                source="whatsmyname",
                field="linked_account",
                value={"site": site["name"], "category": site.get("cat", "social")},
                source_url=hit_url,
                confidence=0.7,
            )
        )
    return findings


async def _load_sites() -> list[dict]:
    async def _do_fetch() -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.get(_WMN_URL)
                r.raise_for_status()
                data = r.json()
            return [s for s in (data.get("sites") or []) if s.get("name") in _TARGET_SITES]
        except (httpx.HTTPError, ValueError) as e:
            log.warning("whatsmyname site list fetch failed: %s", e)
            return []

    return await cached(
        source="whatsmyname-sitelist",
        target="all",
        target_type="meta",
        ttl_hours=24 * 7,
        fetch_fn=_do_fetch,
    )


async def _probe(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    site: dict,
    username: str,
) -> str | None:
    uri_check = (site.get("uri_check") or "").replace("{account}", username)
    if not uri_check:
        return None
    e_code = site.get("e_code", 200)
    e_string = site.get("e_string") or ""

    async with sem:
        try:
            r = await client.get(uri_check)
        except httpx.HTTPError:
            return None

    if r.status_code != e_code:
        return None
    if e_string and e_string not in r.text:
        return None
    return uri_check


SPEC = AdapterSpec(
    name="whatsmyname",
    supported_types=("username",),
    fetch=fetch,
    sensitive=False,
)
