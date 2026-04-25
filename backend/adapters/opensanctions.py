"""OpenSanctions adapter — free PEP / sanctions / watchlist match.

Public endpoint: https://api.opensanctions.org/match/sanctions  (no key needed
for low volume). Cached 24h.
"""

from __future__ import annotations

import logging
import os

import httpx

from backend.adapters.base import AdapterContext, AdapterSpec, Finding
from backend.dossier.cache import cached

log = logging.getLogger(__name__)

_API = "https://api.opensanctions.org/match/default"


def _auth_headers() -> dict[str, str]:
    """Build auth headers if OPENSANCTIONS_API_KEY is set.

    Without a key the public endpoint enforces a strict per-IP daily quota
    and 401s on most requests; with a key we get the free dev tier.
    """
    key = os.environ.get("OPENSANCTIONS_API_KEY", "").strip()
    headers = {"Accept": "application/json"}
    if key:
        headers["Authorization"] = f"ApiKey {key}"
    return headers


async def fetch(ctx: AdapterContext) -> list[Finding]:
    if ctx.target_type != "name":
        return []

    payload = {
        "queries": {
            "q1": {"schema": "Person", "properties": {"name": [ctx.target]}}
        }
    }
    headers = _auth_headers()

    async def _do_fetch() -> dict:
        try:
            async with httpx.AsyncClient(timeout=ctx.timeout_s, headers=headers) as client:
                r = await client.post(_API, json=payload)
                r.raise_for_status()
                return r.json()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("opensanctions fetch failed for %s: %s", ctx.target, e)
            return {}

    data = await cached(
        source="opensanctions",
        target=ctx.target,
        target_type="name",
        ttl_hours=24,
        fetch_fn=_do_fetch,
    )

    if not data or not isinstance(data, dict):
        return []

    matches = (((data.get("responses") or {}).get("q1") or {}).get("results")) or []
    findings: list[Finding] = []
    for m in matches[:5]:
        if not isinstance(m, dict):
            continue
        score = m.get("score") or m.get("match")
        if isinstance(score, (int, float)) and score < 0.5:
            continue
        props = m.get("properties") or {}
        findings.append(
            Finding(
                source="opensanctions",
                field="sanctions_or_pep_match",
                value={
                    "id": m.get("id"),
                    "name": (props.get("name") or [None])[0],
                    "topics": props.get("topics") or [],
                    "country": props.get("country") or [],
                    "score": score,
                },
                source_url=f"https://www.opensanctions.org/entities/{m.get('id')}/" if m.get("id") else None,
                confidence=0.85,
            )
        )
    return findings


SPEC = AdapterSpec(
    name="opensanctions",
    supported_types=("name",),
    fetch=fetch,
    sensitive=False,
)
