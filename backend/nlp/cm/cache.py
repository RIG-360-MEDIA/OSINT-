"""
In-process TTL cache for CM Page endpoints.

Mirrors the pattern used in backend/routers/worldmonitor_router.py
(env-driven TTL, simple dict, no external dependency) but generalises to a
keyed-by-tuple store so each section can be cached at its own cadence.

Per-section TTL defaults (overridable via env CM_TTL_<NAME>_S):
    pulse / silence / quotes              5 min
    spokespersons / voice_share /
    dissent / divergence_*                15 min
    issues / trajectory / counter /
    risk_window / heatmap                 30 min
    promises                               1 h

This is a single-process cache — fine for the single rig-backend container
running both FastAPI and the Celery workers. If the deployment ever splits
into multiple FastAPI replicas this should move to Redis or to Postgres
with the same key shape.
"""
from __future__ import annotations

import os
import time
from threading import RLock
from typing import Any

_DEFAULT_TTLS: dict[str, int] = {
    "dashboard": 300,
    "pulse": 300,
    "issues": 1800,
    "silence": 300,
    "spokespersons": 900,
    "cabinet_onmessage": 900,
    "dissent": 1800,
    "trajectory": 1800,
    "heatmap": 3600,
    "promises": 3600,
    "counter_narratives": 1800,
    "risk_window": 1800,
    "quotes": 300,
    "voice_share": 1800,
    "language_divergence": 1800,
    "medium_divergence": 1800,
}


def _ttl_for(section: str) -> int:
    env = os.getenv(f"CM_TTL_{section.upper()}_S")
    if env and env.isdigit():
        return int(env)
    return _DEFAULT_TTLS.get(section, 600)


_store: dict[tuple, tuple[float, Any]] = {}
_lock = RLock()


def get(section: str, key: tuple) -> Any | None:
    """Return cached value if fresh, else None. key should already include
    user_id, state, window so different users / states do not collide."""
    full_key = (section, *key)
    with _lock:
        entry = _store.get(full_key)
        if entry is None:
            return None
        ts, value = entry
        if time.time() - ts > _ttl_for(section):
            _store.pop(full_key, None)
            return None
        return value


def put(section: str, key: tuple, value: Any) -> None:
    full_key = (section, *key)
    with _lock:
        _store[full_key] = (time.time(), value)


def invalidate(section: str | None = None) -> int:
    """Drop all cached entries for a section (or everything if None).
    Returns count of entries dropped."""
    with _lock:
        if section is None:
            n = len(_store)
            _store.clear()
            return n
        keys = [k for k in _store if k and k[0] == section]
        for k in keys:
            _store.pop(k, None)
        return len(keys)


def stats() -> dict[str, int]:
    """Diagnostic: count of entries per section."""
    with _lock:
        out: dict[str, int] = {}
        for k in _store:
            section = k[0] if k else "?"
            out[section] = out.get(section, 0) + 1
        return out
