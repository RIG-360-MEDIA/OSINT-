"""
Polite throttle + circuit breaker for THE NEWSROOM YouTube calls.

YouTube IP-bans hosts that hit it too aggressively. The existing
youtube_collector adds a 1.5–3.5 s random delay between transcript
fetches; this module gives the newsroom pipeline the same protection,
plus a circuit breaker so we don't keep poking the wall after we've
already been told to back off.

Design:
  - One process-wide minimum gap between YouTube-bound calls
    (configurable, default ~2.5 s average with ±1 s jitter).
  - Circuit breaker: 3 consecutive `RequestBlocked` / yt-dlp bot-wall
    failures and we open the breaker for 10 minutes. Any newsroom
    YouTube call inside that window raises `YoutubeCircuitOpen`
    immediately rather than wasting the request.
  - The breaker resets on the first successful call after it closes.

Both async and sync entry points are provided because the lens
modules mix both call styles. State is shared via a threading.Lock
so they cannot stomp on each other inside the same worker process.

Tunables via env vars:
  NEWSROOM_YT_MIN_GAP_SEC          default 2.5
  NEWSROOM_YT_JITTER_SEC           default 1.0
  NEWSROOM_YT_BREAKER_THRESHOLD    default 3
  NEWSROOM_YT_BREAKER_COOLDOWN_SEC default 600
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import threading
import time

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


_MIN_GAP        = _env_float("NEWSROOM_YT_MIN_GAP_SEC", 2.5)
_JITTER         = _env_float("NEWSROOM_YT_JITTER_SEC", 1.0)
_CB_THRESHOLD   = _env_int("NEWSROOM_YT_BREAKER_THRESHOLD", 3)
_CB_COOLDOWN    = _env_int("NEWSROOM_YT_BREAKER_COOLDOWN_SEC", 600)


class YoutubeCircuitOpen(RuntimeError):
    """Raised when the circuit breaker is open. Caller should bail
    rather than blast YouTube and entrench the block."""


class _State:
    lock: threading.Lock = threading.Lock()
    last_call_ts: float = 0.0
    fail_streak: int = 0
    breaker_opened_until: float = 0.0


def _compute_wait_locked(now: float) -> float:
    """Compute how long to wait. Caller must hold _State.lock."""
    if now < _State.breaker_opened_until:
        wait = _State.breaker_opened_until - now
        raise YoutubeCircuitOpen(
            f"YouTube circuit breaker open for ~{int(wait)}s more "
            f"({_State.fail_streak} consecutive blocks); not making call"
        )
    gap = now - _State.last_call_ts
    target_gap = _MIN_GAP + random.uniform(-_JITTER, _JITTER)
    return max(0.0, target_gap - gap)


async def throttle_async() -> None:
    """Async: sleep until the next call is safe. Raises if breaker open."""
    with _State.lock:
        wait = _compute_wait_locked(time.time())
    if wait > 0:
        await asyncio.sleep(wait)
    with _State.lock:
        _State.last_call_ts = time.time()


def throttle_sync() -> None:
    """Sync: same as throttle_async, used inside threads / sync code paths."""
    with _State.lock:
        wait = _compute_wait_locked(time.time())
    if wait > 0:
        time.sleep(wait)
    with _State.lock:
        _State.last_call_ts = time.time()


def record_block() -> None:
    """Record a YouTube-block-style failure. Trips the breaker after
    `NEWSROOM_YT_BREAKER_THRESHOLD` consecutive blocks."""
    with _State.lock:
        _State.fail_streak += 1
        if _State.fail_streak >= _CB_THRESHOLD and time.time() >= _State.breaker_opened_until:
            _State.breaker_opened_until = time.time() + _CB_COOLDOWN
            logger.warning(
                "YouTube circuit breaker tripped — cooling for %ds (%d consecutive blocks)",
                _CB_COOLDOWN, _State.fail_streak,
            )


def record_success() -> None:
    """Reset the failure counter on a successful YouTube call."""
    with _State.lock:
        if _State.fail_streak > 0:
            logger.info("YouTube call succeeded — resetting fail streak from %d", _State.fail_streak)
        _State.fail_streak = 0
        _State.breaker_opened_until = 0.0


def status() -> dict:
    """For debug endpoints / logging."""
    with _State.lock:
        now = time.time()
        return {
            "min_gap_sec":        _MIN_GAP,
            "jitter_sec":         _JITTER,
            "fail_streak":        _State.fail_streak,
            "breaker_open":       now < _State.breaker_opened_until,
            "breaker_seconds_remaining": max(0, int(_State.breaker_opened_until - now)),
            "last_call_age_sec":  int(now - _State.last_call_ts) if _State.last_call_ts else None,
        }
