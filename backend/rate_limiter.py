"""Per-user rate limiting (D-06).

Lightweight in-process rate limiter using a sliding window counter keyed
by Supabase user id (or client IP for unauthenticated calls). Used as a
FastAPI ``Depends(...)`` rather than a decorator, which preserves the
endpoint's signature so FastAPI's body/query introspection works
correctly.

Limits applied (see endpoint dependencies):

* ``/api/onboarding/extract`` — 10/min per user (Groq cost guardrail)
* ``/api/admin/impersonate/*`` — 30/min per admin (abuse guardrail)
* ``/api/brief/generate`` — owned by the brief team; their integration

When a limit is exceeded the dep raises ``HTTPException(429)`` with a
``Retry-After`` header.

Single-process / single-container only. If/when the deployment scales
to multiple backend replicas, swap the dict counter for Redis.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
from collections import deque
from typing import Callable

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


# (key, deadline_ts) tuples per (endpoint_label, key). deque order is
# oldest-first so we can pop expired entries off the left in O(1).
_BUCKETS: dict[tuple[str, str], deque[float]] = {}
_LOCK = asyncio.Lock()


def _key_from_request(request: Request) -> str:
    """User-id from JWT (preferred) or client IP fallback."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth.split(None, 1)[1]
        try:
            parts = token.split(".")
            if len(parts) == 3:
                payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
                payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                sub = payload.get("sub")
                if isinstance(sub, str) and sub:
                    return f"user:{sub}"
        except Exception:  # noqa: BLE001
            pass
    client = request.client
    return f"ip:{client.host}" if client else "ip:unknown"


def rate_limit(
    label: str,
    *,
    max_calls: int,
    window_seconds: int = 60,
) -> Callable[[Request], None]:
    """Build a FastAPI dependency that enforces ``max_calls`` per
    ``window_seconds`` per resolved key (user id or IP).

    Usage::

        @router.post("/extract", dependencies=[
            Depends(rate_limit("onboarding_extract", max_calls=10))
        ])
        async def extract_profile(...): ...

    Disabled when ``RATE_LIMIT_DISABLED=true`` (used by tests). Every
    keyed bucket is a deque; we pop expired timestamps off the left and
    reject when the remaining length is at the limit.
    """

    async def _dep(request: Request) -> None:
        if os.getenv("RATE_LIMIT_DISABLED", "false").lower() == "true":
            return

        key = _key_from_request(request)
        bucket_id = (label, key)
        now = time.monotonic()
        cutoff = now - window_seconds

        async with _LOCK:
            bucket = _BUCKETS.setdefault(bucket_id, deque())
            # Drop expired entries.
            while bucket and bucket[0] < cutoff:
                bucket.popleft()

            if len(bucket) >= max_calls:
                oldest = bucket[0]
                retry_after = max(1, int(window_seconds - (now - oldest)))
                logger.info(
                    "rate-limit hit: label=%s key=%s window=%ds limit=%d retry_after=%ds",
                    label, key, window_seconds, max_calls, retry_after,
                )
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "rate_limited",
                        "label": label,
                        "retry_after_seconds": retry_after,
                    },
                    headers={"Retry-After": str(retry_after)},
                )

            bucket.append(now)

    return _dep


__all__ = ["rate_limit"]
