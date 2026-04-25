"""Dossier cache — read-through wrapper backed by the dossier_cache table.

Adapters call `cached(source, target, ttl_h, fetch_fn)` and we either return
the stored payload (if fresh) or invoke fetch_fn and store the result.

Cache failures NEVER block the adapter — on any DB error we fall through to
the live fetch.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable

from sqlalchemy import text

from backend.database import get_db

log = logging.getLogger(__name__)


def _key(source: str, target: str, target_type: str) -> tuple[str, str]:
    target_hash = hashlib.sha256(f"{target_type}:{target.lower().strip()}".encode()).hexdigest()
    return (f"{source}:{target_hash}", target_hash)


async def cached(
    *,
    source: str,
    target: str,
    target_type: str,
    ttl_hours: int,
    fetch_fn: Callable[[], Awaitable[Any]],
) -> Any:
    cache_key, target_hash = _key(source, target, target_type)

    try:
        async with get_db() as db:
            result = await db.execute(
                text(
                    """
                    SELECT payload FROM dossier_cache
                    WHERE cache_key = :k AND expires_at > NOW()
                    """
                ),
                {"k": cache_key},
            )
            row = result.first()
            if row:
                payload = row[0]
                return payload if not isinstance(payload, str) else json.loads(payload)
    except Exception as e:
        log.debug("cache read failed for %s: %s", cache_key, e)

    fresh = await fetch_fn()

    try:
        # Empty payloads (transient failures, expired keys, rate limits) get a
        # SHORT TTL so a one-off failure can't poison the cache for hours.
        # Successful payloads use the adapter-requested TTL.
        is_empty = (
            fresh is None
            or fresh == {}
            or fresh == []
            or (isinstance(fresh, dict) and not any(fresh.values()))
        )
        effective_ttl_h = 0.25 if is_empty else ttl_hours  # 15 min for empties
        expires = datetime.utcnow() + timedelta(hours=effective_ttl_h)
        async with get_db() as db:
            await db.execute(
                text(
                    """
                    INSERT INTO dossier_cache
                        (cache_key, source, target_hash, payload, expires_at)
                    VALUES
                        (:k, :s, :h, CAST(:p AS jsonb), :e)
                    ON CONFLICT (cache_key) DO UPDATE
                        SET payload = EXCLUDED.payload,
                            fetched_at = NOW(),
                            expires_at = EXCLUDED.expires_at
                    """
                ),
                {
                    "k": cache_key,
                    "s": source,
                    "h": target_hash,
                    "p": json.dumps(fresh, default=str),
                    "e": expires,
                },
            )
            await db.commit()
    except Exception as e:
        log.debug("cache write failed for %s: %s", cache_key, e)

    return fresh
