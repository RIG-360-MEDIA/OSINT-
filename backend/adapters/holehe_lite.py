"""Holehe-style email account discovery — pure HTTP, no holehe library.

Probes a curated set of common services that respond differently to known vs
unknown emails on their public password-recovery / signup endpoints. We only
include sites whose probes are clearly safe (no account state mutation).

This is intentionally a small starter set — the real holehe library covers
~120 sites; we cover ~6 high-signal Indian-relevant ones.
"""

from __future__ import annotations

import asyncio
import logging
import re

import httpx

from backend.adapters.base import AdapterContext, AdapterSpec, Finding

log = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PROBE_TIMEOUT_S = 5.0


# Each probe returns True if account exists, False if not, None if inconclusive.
async def _twitter(client: httpx.AsyncClient, email: str) -> bool | None:
    try:
        r = await client.post(
            "https://api.twitter.com/i/users/email_available.json",
            data={"email": email},
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if r.status_code == 200:
            return not bool(r.json().get("valid", True))
    except (httpx.HTTPError, ValueError):
        pass
    return None


async def _github(client: httpx.AsyncClient, email: str) -> bool | None:
    try:
        r = await client.get(
            f"https://api.github.com/search/users?q={email}+in:email",
            headers={"User-Agent": "RIG-Dossier"},
        )
        if r.status_code == 200:
            return (r.json().get("total_count", 0) or 0) > 0
    except (httpx.HTTPError, ValueError):
        pass
    return None


async def _gravatar(client: httpx.AsyncClient, email: str) -> bool | None:
    import hashlib
    h = hashlib.md5(email.strip().lower().encode()).hexdigest()
    try:
        r = await client.get(f"https://www.gravatar.com/{h}.json")
        if r.status_code == 200:
            return True
        if r.status_code == 404:
            return False
    except httpx.HTTPError:
        pass
    return None


_PROBES = [
    ("twitter", _twitter, "https://twitter.com/"),
    ("github",  _github,  "https://github.com/"),
    ("gravatar", _gravatar, "https://gravatar.com/"),
]


async def fetch(ctx: AdapterContext) -> list[Finding]:
    if ctx.target_type != "email":
        return []
    if not _EMAIL_RE.match(ctx.target):
        return []

    async with httpx.AsyncClient(
        timeout=_PROBE_TIMEOUT_S,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 RIG-Dossier/1.0"},
    ) as client:
        results = await asyncio.gather(
            *(probe(client, ctx.target) for _, probe, _ in _PROBES),
            return_exceptions=False,
        )

    findings: list[Finding] = []
    for (site, _, url), exists in zip(_PROBES, results):
        if exists is None:
            continue
        if not exists:
            continue
        findings.append(
            Finding(
                source="holehe_lite",
                field="email_registered_on_site",
                value={"site": site},
                source_url=url,
                confidence=0.6,
            )
        )
    return findings


SPEC = AdapterSpec(
    name="holehe_lite",
    supported_types=("email",),
    fetch=fetch,
    sensitive=False,
)
