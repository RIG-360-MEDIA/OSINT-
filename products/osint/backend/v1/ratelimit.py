"""Per-key rate limiting (token bucket) + monthly quota enforcement.

The token bucket is in-process. osint-backend runs a single uvicorn process
(no --workers), so one in-memory bucket per key is correct. If the deployment
ever scales to multiple workers, swap the bucket store for Redis — the public
surface (``enforce_limits``) stays the same.

Quota is enforced from the cheap analytics.api_usage_counters rollup: we read
the current period's count and reject at/over the limit. The increment happens
off the critical path in the metering writer, so served-request counting stays
eventually-consistent (a tiny over-count under burst is acceptable).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi import Depends, Request
from sqlalchemy import text

from db import get_db

from .auth import ApiPrincipal, get_api_principal
from .errors import quota_exceeded, rate_limited


@dataclass
class _Bucket:
    capacity: float
    refill_per_sec: float
    tokens: float
    updated: float = field(default_factory=time.monotonic)


# key_id -> bucket. Bounded by the number of live keys (small).
_buckets: dict[str, _Bucket] = {}


def _allow(key_id: str, rate_per_min: int) -> tuple[bool, int, int]:
    """Try to spend one token. Returns (allowed, remaining, retry_after_seconds).

    Single-event-loop access — no lock needed (the asyncio loop serialises it).
    """
    rate_per_min = max(1, int(rate_per_min))
    now = time.monotonic()
    refill = rate_per_min / 60.0
    b = _buckets.get(key_id)
    if b is None or b.capacity != rate_per_min:
        # New key, or its limit changed — (re)initialise full.
        b = _Bucket(capacity=float(rate_per_min), refill_per_sec=refill, tokens=float(rate_per_min), updated=now)
        _buckets[key_id] = b
    else:
        elapsed = max(0.0, now - b.updated)
        b.tokens = min(b.capacity, b.tokens + elapsed * b.refill_per_sec)
        b.updated = now

    if b.tokens >= 1.0:
        b.tokens -= 1.0
        return True, int(b.tokens), 0
    # Seconds until one token is available.
    deficit = 1.0 - b.tokens
    retry_after = max(1, int(deficit / b.refill_per_sec) + 1)
    return False, 0, retry_after


def _period_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


async def _quota_remaining_ok(key_id: str, quota: int | None) -> bool:
    """True if the key is under its monthly quota (or has none)."""
    if quota is None:
        return True
    try:
        async with get_db() as db:
            row = (await db.execute(text("""
                SELECT request_count FROM analytics.api_usage_counters
                 WHERE key_id = CAST(:k AS uuid) AND period = :p
            """), {"k": key_id, "p": _period_now()})).fetchone()
    except Exception:
        # On a counter-read failure, fail OPEN for availability — never block a
        # paying client because the meter hiccuped. Rate limiting still applies.
        return True
    used = int(row.request_count) if row else 0
    return used < quota


async def enforce_limits(
    request: Request,
    principal: ApiPrincipal = Depends(get_api_principal),
) -> ApiPrincipal:
    """Gate every /v1 data request: token-bucket rate limit, then quota.

    Records the rate-limit headers on request.state so the metering middleware
    can attach X-RateLimit-* to the response.
    """
    allowed, remaining, retry_after = _allow(principal.key_id, principal.rate_limit_per_min)
    request.state.rl_limit = principal.rate_limit_per_min
    request.state.rl_remaining = remaining
    request.state.rl_reset = int(time.time()) + 60
    if not allowed:
        raise rate_limited(retry_after)

    if not await _quota_remaining_ok(principal.key_id, principal.monthly_quota):
        raise quota_exceeded()
    return principal
