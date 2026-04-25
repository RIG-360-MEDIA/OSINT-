"""OpenCorporates adapter — free company / officer search.

Public endpoint (anonymous, low rate limit):
    https://api.opencorporates.com/v0.4/companies/search?q=<q>
    https://api.opencorporates.com/v0.4/officers/search?q=<q>

For 'name' targets we look up officer matches; for 'domain' we infer the
company by stripping the TLD (best-effort). Cached 24h.
"""

from __future__ import annotations

import logging

import httpx

from backend.adapters.base import AdapterContext, AdapterSpec, Finding
from backend.dossier.cache import cached

log = logging.getLogger(__name__)

_BASE = "https://api.opencorporates.com/v0.4"


async def fetch(ctx: AdapterContext) -> list[Finding]:
    if ctx.target_type == "name":
        return await _officers(ctx)
    if ctx.target_type == "domain":
        return await _companies_by_domain(ctx)
    return []


async def _officers(ctx: AdapterContext) -> list[Finding]:
    async def _do_fetch() -> dict:
        try:
            async with httpx.AsyncClient(timeout=ctx.timeout_s) as client:
                r = await client.get(f"{_BASE}/officers/search", params={"q": ctx.target})
                r.raise_for_status()
                return r.json()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("opencorporates officer fetch failed for %s: %s", ctx.target, e)
            return {}

    data = await cached(
        source="opencorporates-officer",
        target=ctx.target,
        target_type="name",
        ttl_hours=24,
        fetch_fn=_do_fetch,
    )
    officers = (((data.get("results") or {}).get("officers")) or []) if isinstance(data, dict) else []

    findings: list[Finding] = []
    for entry in officers[:5]:
        if not isinstance(entry, dict):
            continue
        o = entry.get("officer") or {}
        findings.append(
            Finding(
                source="opencorporates",
                field="corporate_role",
                value={
                    "name": o.get("name"),
                    "position": o.get("position"),
                    "company": (o.get("company") or {}).get("name"),
                    "jurisdiction": o.get("jurisdiction_code"),
                    "start_date": o.get("start_date"),
                    "end_date": o.get("end_date"),
                },
                source_url=o.get("opencorporates_url"),
                confidence=0.75,
            )
        )
    return findings


async def _companies_by_domain(ctx: AdapterContext) -> list[Finding]:
    name_guess = ctx.target.split(".")[0]
    if not name_guess:
        return []

    async def _do_fetch() -> dict:
        try:
            async with httpx.AsyncClient(timeout=ctx.timeout_s) as client:
                r = await client.get(f"{_BASE}/companies/search", params={"q": name_guess})
                r.raise_for_status()
                return r.json()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("opencorporates company fetch failed for %s: %s", ctx.target, e)
            return {}

    data = await cached(
        source="opencorporates-company",
        target=name_guess,
        target_type="domain",
        ttl_hours=24,
        fetch_fn=_do_fetch,
    )
    companies = (((data.get("results") or {}).get("companies")) or []) if isinstance(data, dict) else []

    findings: list[Finding] = []
    for entry in companies[:3]:
        if not isinstance(entry, dict):
            continue
        c = entry.get("company") or {}
        findings.append(
            Finding(
                source="opencorporates",
                field="company_record",
                value={
                    "name": c.get("name"),
                    "company_number": c.get("company_number"),
                    "jurisdiction": c.get("jurisdiction_code"),
                    "status": c.get("current_status"),
                    "incorporation_date": c.get("incorporation_date"),
                },
                source_url=c.get("opencorporates_url"),
                confidence=0.65,
            )
        )
    return findings


SPEC = AdapterSpec(
    name="opencorporates",
    supported_types=("name", "domain"),
    fetch=fetch,
    sensitive=False,
)
