"""Hudson Rock Cavalier adapter — free infostealer breach lookup.

Public endpoints (no key for the free tier):
    https://api.hudsonrock.com/json/v2/osint-tools/search-by-email?email=
    https://api.hudsonrock.com/json/v2/osint-tools/search-by-domain?domain=

Returns whether the target appears in stealer logs and approx counts.
Cached 12h.
"""

from __future__ import annotations

import logging

import httpx

from backend.adapters.base import AdapterContext, AdapterSpec, Finding
from backend.dossier.cache import cached

log = logging.getLogger(__name__)

_BASE = "https://api.hudsonrock.com/json/v2/osint-tools"


async def fetch(ctx: AdapterContext) -> list[Finding]:
    if ctx.target_type not in ("email", "domain"):
        return []

    endpoint = "search-by-email" if ctx.target_type == "email" else "search-by-domain"
    param = "email" if ctx.target_type == "email" else "domain"

    async def _do_fetch() -> dict:
        try:
            async with httpx.AsyncClient(timeout=ctx.timeout_s) as client:
                r = await client.get(f"{_BASE}/{endpoint}", params={param: ctx.target})
                r.raise_for_status()
                return r.json()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("hudsonrock fetch failed for %s: %s", ctx.target, e)
            return {}

    data = await cached(
        source="hudsonrock",
        target=ctx.target,
        target_type=ctx.target_type,
        ttl_hours=12,
        fetch_fn=_do_fetch,
    )

    if not data or not isinstance(data, dict):
        return []

    findings: list[Finding] = []
    message = data.get("message")
    stealers = data.get("stealers") or []
    total = data.get("total") if isinstance(data.get("total"), int) else len(stealers)

    if isinstance(stealers, list) and stealers:
        findings.append(
            Finding(
                source="hudsonrock",
                field="infostealer_compromise",
                value={"total": total, "summary": str(message)[:300]},
                source_url="https://www.hudsonrock.com/free-tools",
                confidence=0.9,
            )
        )
        for s in stealers[:5]:
            if not isinstance(s, dict):
                continue
            findings.append(
                Finding(
                    source="hudsonrock",
                    field="stealer_log",
                    value={
                        "computer_name": s.get("computer_name"),
                        "operating_system": s.get("operating_system"),
                        "date_compromised": s.get("date_compromised"),
                        "stealer_family": s.get("stealer_family"),
                        "ip": s.get("ip"),
                    },
                    source_url="https://www.hudsonrock.com/free-tools",
                    confidence=0.9,
                )
            )
    return findings


SPEC = AdapterSpec(
    name="hudsonrock",
    supported_types=("email", "domain"),
    fetch=fetch,
    sensitive=False,
)
