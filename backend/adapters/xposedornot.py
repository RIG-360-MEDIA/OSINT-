"""XposedOrNot adapter — free breach lookup by email. No API key required.

Public API: https://api.xposedornot.com/v1/check-email/<email>
Returns list of breach names; we expand to one Finding per breach.
"""

from __future__ import annotations

import logging
import re

import httpx

from backend.adapters.base import AdapterContext, AdapterSpec, Finding

log = logging.getLogger(__name__)

_API = "https://api.xposedornot.com/v1/check-email"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


async def fetch(ctx: AdapterContext) -> list[Finding]:
    if ctx.target_type != "email":
        return []
    if not _EMAIL_RE.match(ctx.target):
        return []

    try:
        async with httpx.AsyncClient(timeout=ctx.timeout_s) as client:
            r = await client.get(f"{_API}/{ctx.target}")
            if r.status_code == 404:
                return []  # no breaches found is a valid empty result
            r.raise_for_status()
            data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("xposedornot fetch failed for %s: %s", ctx.target, e)
        return []

    breaches = ((data.get("breaches") or [[]])[0]) or []
    findings: list[Finding] = []
    for name in breaches:
        if not isinstance(name, str):
            continue
        findings.append(
            Finding(
                source="xposedornot",
                field="breach",
                value={"breach": name},
                source_url="https://xposedornot.com/",
                confidence=0.85,
            )
        )
    return findings


SPEC = AdapterSpec(
    name="xposedornot",
    supported_types=("email",),
    fetch=fetch,
    sensitive=False,
)
