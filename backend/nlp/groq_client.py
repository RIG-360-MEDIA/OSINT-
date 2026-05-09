"""
Groq API client with round-robin key rotation and quota tracking.

Single module-level singleton (groq_manager) shared across all callers
in the same process. Keys are rotated round-robin; exhausted keys are
skipped until the daily reset at 00:05 UTC via Celery Beat.

Usage:
    from backend.nlp.groq_client import call_groq, classify, translate, generate, extract_json
    from backend.nlp.groq_client import FAST_MODEL, QUALITY_MODEL, TOKEN_LIMITS
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

import groq as groq_sdk

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

FAST_MODEL = "llama-3.1-8b-instant"
QUALITY_MODEL = "llama-3.3-70b-versatile"

# Token limits — never exceed these per call
TOKEN_LIMITS: dict[str, int] = {
    "classification": 50,
    "translation": 500,
    "profile_extraction": 1000,
    "transcript_analysis": 1500,
    "relevance_explanation": 200,
    "brief_generation": 4000,
    "rag_response": 2048,
}

# Temperature settings
TEMPERATURES: dict[str, float] = {
    "classification": 0.0,
    "translation": 0.1,
    "generation": 0.3,
}

# Task types that use the fast model by default
_FAST_TASK_TYPES = frozenset({"classification", "translation"})


# ── Custom Exceptions ──────────────────────────────────────────────────────────

class GroqQuotaExhausted(Exception):
    """
    Raised when all Groq API keys have hit their rate limits.
    The pipeline should pause and retry after the daily reset at 00:05 UTC.
    """


class GroqCallFailed(Exception):
    """
    Raised when a Groq call fails for a non-quota reason
    (network error, invalid request, auth error, etc.).
    """


# ── Key Manager ────────────────────────────────────────────────────────────────

class GroqKeyManager:
    """
    Manages a pool of Groq API keys with round-robin rotation and quota tracking.

    One instance is created at module import time and shared across all callers
    in the same process. Clients are cached per key index — one AsyncGroq
    client per key, created lazily and reused for all subsequent calls.

    Thread/async safety: an asyncio.Lock guards _index and _exhausted.
    The lock is initialised lazily on first use to avoid event loop issues
    at import time.
    """

    def __init__(self, keys: list[str]) -> None:
        if not keys:
            logger.warning(
                "GroqKeyManager: GROQ_API_KEYS is empty. "
                "Add at least one key to infrastructure/.env. "
                "All Groq calls will raise GroqQuotaExhausted until keys are configured."
            )
        else:
            logger.info("GroqKeyManager initialised with %d key(s)", len(keys))

        self.keys: list[str] = keys
        self._index: int = 0
        # Keys rate-limited by a 429: maps key_index -> unix-ts when the
        # cooldown ends. A key is "available" iff (i not in _exhausted_until)
        # or (_exhausted_until[i] <= now). The Celery beat task at 00:05 UTC
        # still calls reset_exhausted() to clear the whole map at the day
        # boundary (Groq's daily TPD/RPD limits reset there); per-key
        # cooldowns handle short-lived RPM/TPM 429s in between so the pool
        # doesn't get permanently stuck after a burst.
        self._exhausted_until: dict[int, float] = {}
        # Cooldown matches Groq's actual rate-limit window (TPM/RPM is a
        # 60-second rolling window) plus a small buffer. The original 5-minute
        # cooldown was too conservative — a key that 429'd at second 0 is
        # actually retryable at second 60, but the longer cooldown locked
        # out the whole pool when many keys were hit by a burst. The Celery
        # beat task at 00:05 UTC still resets the daily TPD/RPD counters.
        self._cooldown_seconds: float = 60.0
        # Hard cap on any individual key cooldown. Even when the SDK reports
        # a daily-quota (TPD/RPD) 429, we never hold a key out longer than
        # this — if Groq is genuinely still over-quota when the cooldown
        # ends, the next probe will simply 429 again and re-cool. This makes
        # spurious lockouts (e.g. message-classification false positives,
        # transient pool-state corruption) self-healing within minutes
        # instead of locking out the pipeline for hours.
        self._max_cooldown_seconds: float = 300.0
        self._clients: dict[int, "groq_sdk.AsyncGroq"] = {}
        self._lock: asyncio.Lock | None = None

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _get_lock(self) -> asyncio.Lock:
        """Lazy lock init — avoids event loop binding issues at import time."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _get_client(self, key_index: int) -> "groq_sdk.AsyncGroq":
        """
        Return the cached AsyncGroq client for this key index.
        Creates once on first access, reused on all subsequent calls.
        """
        if key_index not in self._clients:
            self._clients[key_index] = groq_sdk.AsyncGroq(
                api_key=self.keys[key_index],
                max_retries=0,
            )
        return self._clients[key_index]

    # ── Public interface ───────────────────────────────────────────────────────

    async def get_key(self) -> tuple[int, "groq_sdk.AsyncGroq"]:
        """
        Return (key_index, cached_client) using round-robin across
        non-exhausted keys.

        Raises GroqQuotaExhausted if all keys are exhausted or no keys exist.
        """
        import time as _time
        async with self._get_lock():
            now = _time.time()
            # Lazily evict any keys whose cooldown has elapsed.
            recovered = [i for i, until in self._exhausted_until.items() if until <= now]
            for i in recovered:
                del self._exhausted_until[i]
            if recovered:
                logger.info(
                    "Groq key cooldown elapsed for %d key(s); restored.",
                    len(recovered),
                )

            available = [
                i for i in range(len(self.keys))
                if i not in self._exhausted_until
            ]
            if not available:
                # Pool fully marked exhausted in local memory. Rather than
                # raise (which permanently stalls extraction whenever the
                # local tracker is wrong), force-restore the key closest to
                # recovery and let the caller probe Groq with it. Three
                # outcomes:
                #   1. Groq accepts → call succeeds, cooldown was wrong.
                #   2. Groq 429s with a TPM (per-minute) limit → re-marked
                #      with 60s cooldown; pipeline recovers in a minute.
                #   3. Groq 429s with TPD/RPD → re-marked with the bounded
                #      cooldown (max 300s); pipeline retries every ~5min.
                # Net effect: stale lockout state can never starve the
                # pipeline for longer than _max_cooldown_seconds.
                if not self.keys:
                    raise GroqQuotaExhausted("No Groq keys configured.")
                soonest_idx = min(
                    self._exhausted_until.items(), key=lambda kv: kv[1]
                )[0]
                soonest_until = self._exhausted_until.pop(soonest_idx)
                eta = max(0, int(soonest_until - now))
                logger.warning(
                    "Groq pool fully exhausted in local tracker; probing "
                    "key [%d] (was %ds from cooldown end). If Groq still "
                    "rate-limits this key it will be re-cooled.",
                    soonest_idx,
                    eta,
                )
                return soonest_idx, self._get_client(soonest_idx)
            # Round-robin within available indices
            position = self._index % len(available)
            idx = available[position]
            self._index = (self._index + 1) % len(available)
            return idx, self._get_client(idx)

    async def mark_exhausted(self, key_index: int) -> None:
        """
        Mark a key as rate-limited for the default `_cooldown_seconds` (75s).
        Use `mark_exhausted_for` to set an explicit cooldown — needed when a
        per-day limit fires and a much longer hold is appropriate.
        """
        await self.mark_exhausted_for(key_index, self._cooldown_seconds)

    async def mark_exhausted_for(self, key_index: int, seconds: float) -> None:
        """
        Mark a key as rate-limited for an explicit number of seconds. The
        key is auto-restored on the next `get_key` call after the cooldown
        elapses.

        Cooldown is hard-clamped to `_max_cooldown_seconds` (5 min) regardless
        of what the caller requests. This is a safety valve: callers used to
        request 4-hour holds on suspected daily-quota 429s, but the parser
        misclassified TPM as TPD often enough that pools went dark for hours.
        With the clamp, the worst-case stall is _max_cooldown_seconds — and
        if Groq genuinely is at TPD, the next probe simply 429s and re-cools.

        When the *last* available key is marked exhausted, emit a CRITICAL
        log — single high-signal pattern that monitoring should alert on.
        (Coverage audit C-12, 2026-04-28.)
        """
        import time as _time
        seconds = min(max(seconds, 0.0), self._max_cooldown_seconds)
        async with self._get_lock():
            self._exhausted_until[key_index] = _time.time() + seconds
            remaining = len(self.keys) - len(self._exhausted_until)
            logger.warning(
                "Groq key [%d] rate limited; cooldown %.0fs. %d/%d key(s) remaining.",
                key_index,
                seconds,
                remaining,
                len(self.keys),
            )
            if remaining == 0:
                logger.critical(
                    "GROQ_POOL_EXHAUSTED: all %d key(s) exhausted. "
                    "Pipeline will stall until earliest cooldown elapses or "
                    "the daily reset task runs at 00:05 UTC.",
                    len(self.keys),
                )

    def reset_exhausted(self) -> None:
        """
        Reset all exhausted keys to available.
        Called by Celery Beat task at 00:05 UTC daily.
        Synchronous — safe to call from a Celery task without an event loop.
        """
        count = len(self._exhausted_until)
        self._exhausted_until.clear()
        self._index = 0
        logger.info(
            "Groq key pool reset. %d exhausted key(s) restored. %d key(s) available.",
            count,
            len(self.keys),
        )

    @property
    def status(self) -> dict[str, int]:
        """For debug dashboard — shows current pool health."""
        return {
            "total_keys": len(self.keys),
            "exhausted_keys": len(self._exhausted_until),
            "available_keys": len(self.keys) - len(self._exhausted_until),
            "current_index": self._index,
        }


# ── Module-level singleton ─────────────────────────────────────────────────────
# Created once at import time. All callers import this instance.

def _init_manager() -> GroqKeyManager:
    keys_str = os.getenv("GROQ_API_KEYS", "")
    keys = [k.strip() for k in keys_str.split(",") if k.strip()]
    return GroqKeyManager(keys)


groq_manager: GroqKeyManager = _init_manager()


# ── Cerebras failover provider ───────────────────────────────────────────────
#
# When Groq's 20-key pool is fully rate-limited (per-minute caps tripping
# during burst windows), we fail over to Cerebras Inference. Same Llama
# models, completely separate quota universe (1M tokens/day per Cerebras
# key, 60-100K TPM — 10-16x Groq's per-key TPM headroom). Free tier, no
# credit card.
#
# Implemented as a minimal raw-httpx client (no SDK install) so the
# failover surface stays small and explicit. Each Cerebras call is gated
# by the same token bucket so the per-process rate limit applies across
# both providers — we don't get extra burst budget by having two
# providers, but we get extra steady-state capacity because each
# provider has its own 30-rpm-per-key Groq-style ceiling.

_CEREBRAS_BASE = "https://api.cerebras.ai/v1/chat/completions"
_CEREBRAS_KEYS: list[str] = [
    k.strip() for k in os.getenv("CEREBRAS_API_KEYS", "").split(",") if k.strip()
]
_cerebras_index: int = 0

# Groq model id → Cerebras model id. Same model weights, different naming
# convention. Anything not in the map falls back to llama3.1-8b.
_GROQ_TO_CEREBRAS_MODEL: dict[str, str] = {
    "llama-3.1-8b-instant": "llama3.1-8b",
    "llama-3.3-70b-versatile": "llama3.3-70b",
    "llama-3.1-70b-versatile": "llama3.3-70b",
    "llama-3.2-3b-preview": "llama3.1-8b",
    "llama3-8b-8192": "llama3.1-8b",
    "llama3-70b-8192": "llama3.3-70b",
}


def _next_cerebras_key() -> str | None:
    """Round-robin pick. None if no keys configured."""
    global _cerebras_index
    if not _CEREBRAS_KEYS:
        return None
    key = _CEREBRAS_KEYS[_cerebras_index % len(_CEREBRAS_KEYS)]
    _cerebras_index = (_cerebras_index + 1) % max(len(_CEREBRAS_KEYS), 1)
    return key


async def _call_cerebras(
    messages: list,
    groq_model: str,
    max_tokens: int,
    temperature: float,
    json_response: bool,
) -> str:
    """
    Failover call to Cerebras Inference. Raises GroqCallFailed on any
    error so caller treats it identically to a Groq failure (returning
    error to the task, which gets retried on next cycle). Acquires the
    same shared rate bucket so concurrent failover doesn't burst.
    """
    if not _CEREBRAS_KEYS:
        raise GroqQuotaExhausted("No Cerebras keys configured for failover.")

    cerebras_model = _GROQ_TO_CEREBRAS_MODEL.get(groq_model, "llama3.1-8b")
    import httpx as _httpx
    # Try up to 3 Cerebras keys before giving up.
    last_exc: Exception | None = None
    for _ in range(min(len(_CEREBRAS_KEYS), 3)):
        await _get_bucket().acquire()
        key = _next_cerebras_key()
        if not key:
            break
        body: dict[str, Any] = {
            "model": cerebras_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_response:
            body["response_format"] = {"type": "json_object"}
        try:
            async with _httpx.AsyncClient(timeout=30.0) as c:
                r = await c.post(
                    _CEREBRAS_BASE,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
            if r.status_code == 429:
                logger.warning("Cerebras key rate-limited; trying next.")
                continue
            if r.status_code >= 400:
                raise GroqCallFailed(
                    f"Cerebras API error {r.status_code}: {r.text[:200]}"
                )
            data = r.json()
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            if not content:
                raise GroqCallFailed("Cerebras returned empty content")
            return content.strip()
        except (GroqCallFailed, GroqQuotaExhausted):
            raise
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("Cerebras call failed: %s", exc)
            continue

    raise GroqCallFailed(
        f"Cerebras failover exhausted: {last_exc}"
        if last_exc else "Cerebras failover exhausted"
    )


# Type imports needed by the Cerebras helper.
from typing import Any  # noqa: E402  — late import keeps the diff localised


# ── Per-process token-bucket rate limiter ────────────────────────────────────
#
# Groq free tier is RPM-bound (~30 requests/min/key × 20 keys = 600 req/min
# total) far more than it is TPD-bound (10M tokens/day). Daily token usage
# for the entire Coverage workload is ~1.3M (13% of cap), but burst load
# during a driver fire is ~7,200 req/min (12× the per-minute cap), causing
# 429 cascades.
#
# A token bucket caps the per-second HTTP rate regardless of how many
# concurrent retry-loops or worker processes are firing. With rate=8/sec
# we sit at 480 req/min — comfortably under the 600/min global cap, and
# average daily volume (~1,200 calls/day = 0.83/min) is unchanged.
#
# Per-process: 4 nlp workers × bucket(8/sec) means total cap is 4 × 8 =
# 32/sec at peak across all workers. Still under 600/min total. (We don't
# need cross-worker coordination because each worker rotates round-robin
# and Groq's per-key per-minute counter is what actually applies — and
# 32/sec across 20 keys = 96/min/key average... wait that's over 30/min.
# Reality check: workers don't burst simultaneously because driver fires
# are 5min-staggered AND each worker's task processing serializes via the
# bucket. Empirically 8/sec/process keeps us well clear.
import time as _time


class _TokenBucket:
    """Simple async token bucket. Fractional tokens, lazy refill."""

    def __init__(self, rate: float, capacity: float) -> None:
        self.rate = rate  # tokens per second
        self.capacity = capacity
        self.tokens = capacity
        self.last_refill = _time.monotonic()
        self._lock: asyncio.Lock | None = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def acquire(self, tokens: float = 1.0) -> None:
        """Block until `tokens` are available, then consume them."""
        while True:
            async with self._get_lock():
                now = _time.monotonic()
                elapsed = now - self.last_refill
                self.tokens = min(
                    self.capacity, self.tokens + elapsed * self.rate
                )
                self.last_refill = now
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return
                deficit = tokens - self.tokens
                wait_s = deficit / self.rate
            # Release lock while sleeping so other coroutines can refill-
            # and-consume. Loop back to re-acquire and re-check after sleep.
            await asyncio.sleep(wait_s)


_GROQ_RATE_PER_SECOND = 4.0
_GROQ_BURST_CAPACITY = 4.0
_groq_bucket: _TokenBucket | None = None


def _get_bucket() -> _TokenBucket:
    """Lazy-init to avoid event-loop binding at import time."""
    global _groq_bucket
    if _groq_bucket is None:
        _groq_bucket = _TokenBucket(
            rate=_GROQ_RATE_PER_SECOND,
            capacity=_GROQ_BURST_CAPACITY,
        )
    return _groq_bucket


# ── Call Wrapper ───────────────────────────────────────────────────────────────

async def call_groq(
    system: str,
    user: str,
    task_type: str = "generation",
    model: str | None = None,
    json_response: bool = False,
) -> str:
    """
    Make a Groq API call with automatic key rotation and retry on rate limit.

    Args:
        system:        System prompt.
        user:          User message.
        task_type:     Key in TOKEN_LIMITS — determines max_tokens and temperature.
        model:         Override model. If None, uses FAST_MODEL for
                       classification/translation, QUALITY_MODEL for everything else.
        json_response: If True, sets response_format to JSON object.

    Returns:
        Stripped response text from Groq.

    Raises:
        GroqQuotaExhausted: All keys are rate limited.
        GroqCallFailed:     Non-quota API error or unexpected failure.
    """
    max_tokens = TOKEN_LIMITS.get(task_type, 1000)

    if model is None:
        model = FAST_MODEL if task_type in _FAST_TASK_TYPES else QUALITY_MODEL

    temperature = TEMPERATURES.get(task_type, TEMPERATURES["generation"])

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    # Cap internal key-rotation retries. The previous policy of trying every
    # key (up to 16) meant ONE oversize / TPD-exhausted call could burn the
    # entire pool in seconds, leaving every later call with nothing. With a
    # cap of 3 the worst-case blast radius is 3 keys per failing call, which
    # leaves plenty of pool for concurrent sections to succeed and for the
    # caller's higher-level retry logic to recover.
    attempts = min(len(groq_manager.keys), 3)

    # Per-process rate limiting happens inside _call_groq_inner — once per
    # HTTP attempt, not per call_groq invocation. That way a single
    # call_groq's 3-key retry loop spreads its requests across the rate
    # cap instead of bursting them all in the same second.
    try:
        return await _call_groq_inner(
            messages, model, max_tokens, temperature, json_response, attempts
        )
    except GroqQuotaExhausted as exc:
        # Groq pool fully cooled. Fail over to Cerebras (separate quota
        # universe, same Llama models). Only triggers when configured.
        if not _CEREBRAS_KEYS:
            raise
        logger.info(
            "Groq pool exhausted — failing over to Cerebras for this call."
        )
        return await _call_cerebras(
            messages, model, max_tokens, temperature, json_response
        )


async def _call_groq_inner(
    messages: list,
    model: str,
    max_tokens: int,
    temperature: float,
    json_response: bool,
    attempts: int,
) -> str:
    for attempt in range(attempts):
        # Token bucket guards the actual HTTP call. Acquired per-attempt
        # so a 3-key retry loop spaces its requests instead of bursting.
        await _get_bucket().acquire()
        key_idx, client = await groq_manager.get_key()

        try:
            kwargs: dict = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if json_response:
                kwargs["response_format"] = {"type": "json_object"}

            response = await client.chat.completions.create(**kwargs)
            return response.choices[0].message.content.strip()

        except groq_sdk.RateLimitError:
            # Groq returns 429 for both per-minute (TPM/RPM) and per-day
            # (TPD/RPD) limits. We treat both with the same bounded cooldown
            # (clamped to _max_cooldown_seconds in mark_exhausted_for) — the
            # previous "parse the error string and hold for 4 hours on TPD"
            # logic was fragile (string format isn't contractual) and
            # routinely misclassified TPM, locking the entire pool out for
            # hours. Now we trust Groq to tell us via the *next* 429 if the
            # key is still over-quota, and self-heal otherwise.
            await groq_manager.mark_exhausted(key_idx)
            if attempt == attempts - 1:
                raise GroqQuotaExhausted(
                    "Retry attempts exhausted due to rate limiting."
                )
            continue

        except groq_sdk.APIConnectionError:
            # Transient network error — retry same key once before rotating
            if attempt < attempts - 1:
                continue
            raise GroqCallFailed("Groq connection error on all attempts")

        except groq_sdk.APIError as exc:
            raise GroqCallFailed(f"Groq API error: {exc}") from exc

        except Exception as exc:
            raise GroqCallFailed(f"Unexpected error calling Groq: {exc}") from exc

    # Unreachable — loop always returns or raises — but satisfies type checker
    raise GroqCallFailed("call_groq exhausted all attempts without a result")


# ── Streaming variant ─────────────────────────────────────────────────────────


async def call_groq_stream(  # type: ignore[no-untyped-def]
    system: str,
    user: str,
    task_type: str = "rag_response",
    model: str | None = None,
):
    """
    Streaming version of call_groq. Yields content chunks as they arrive
    from Groq. Caller is expected to forward chunks to an SSE response.

    Yields:
        str chunks. Empty string at end-of-stream is NOT emitted; caller
        decides how to signal completion (typically `event: done`).

    Raises:
        GroqQuotaExhausted: All keys are rate limited.
        GroqCallFailed:     Non-quota API error or unexpected failure.

    Notes:
        - Uses the same key-rotation + cooldown logic as call_groq.
        - Token budget and temperature are inferred from task_type via
          TOKEN_LIMITS / TEMPERATURES, identical to call_groq.
        - Does NOT support json_response (no use case for streaming JSON yet).
    """
    max_tokens = TOKEN_LIMITS.get(task_type, 1000)

    if model is None:
        model = FAST_MODEL if task_type in _FAST_TASK_TYPES else QUALITY_MODEL

    temperature = TEMPERATURES.get(task_type, TEMPERATURES["generation"])

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    attempts = min(len(groq_manager.keys), 3)

    last_exc: Exception | None = None

    for attempt in range(attempts):
        # Same token-bucket gate as call_groq — streaming calls count
        # against the same per-process rate cap.
        await _get_bucket().acquire()
        key_idx, client = await groq_manager.get_key()

        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
            )

            async for chunk in stream:
                # Groq SDK chunks have .choices[0].delta.content
                # which is None on role-frame chunks; skip those.
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                if content:
                    yield content
            return  # success — exit the retry loop

        except groq_sdk.RateLimitError as exc:
            # See call_groq above: bounded cooldown for all 429s. We no
            # longer parse the error message to distinguish TPM vs TPD —
            # the next probe on the same key (after at most
            # _max_cooldown_seconds) will simply 429 again if still over-
            # quota and re-cool, otherwise recover automatically.
            await groq_manager.mark_exhausted(key_idx)
            last_exc = exc
            if attempt == attempts - 1:
                raise GroqQuotaExhausted(
                    "Retry attempts exhausted due to rate limiting."
                ) from exc
            continue

        except groq_sdk.APIConnectionError as exc:
            last_exc = exc
            if attempt < attempts - 1:
                continue
            raise GroqCallFailed("Groq connection error on all attempts") from exc

        except groq_sdk.APIError as exc:
            raise GroqCallFailed(f"Groq API error: {exc}") from exc

        except Exception as exc:
            raise GroqCallFailed(f"Unexpected error streaming from Groq: {exc}") from exc

    raise GroqCallFailed(
        f"call_groq_stream exhausted all attempts: {last_exc}"
    )


# ── Convenience wrappers ───────────────────────────────────────────────────────

async def classify(system: str, user: str) -> str:
    """Fast classification call using FAST_MODEL."""
    result = await call_groq(
        system=system,
        user=user,
        task_type="classification",
        model=FAST_MODEL,
    )
    # Strip label prefix the model sometimes adds, e.g. "CLASSIFICATION: POLITICS" → "POLITICS"
    if ":" in result:
        result = result.split(":")[-1]
    return result.strip().upper()


async def translate(text: str, target_language: str = "English") -> str:
    """Translate text to the target language. Hard ban on transliteration."""
    return await call_groq(
        system=(
            f"You are a professional translator. Translate the user's text "
            f"into natural, fluent {target_language}. CRITICAL RULES:\n"
            "1. Translate the MEANING — never transliterate. For Telugu "
            "'మృతదేహం' output 'dead body', NOT 'mrutadeham'.\n"
            "2. Do NOT echo the source language back — every word in your "
            f"output must be {target_language}.\n"
            "3. Render proper nouns in their common Roman/English spelling "
            "(KCR, Hyderabad, Revanth Reddy, BJP, Modi).\n"
            "4. Output ONLY the translated text — no quotes, no notes, no "
            "source script, no romanisation.\n\n"
            "Example:\n"
            f"  Input  (Telugu): దొంగల ముఠా అరెస్టు\n"
            f"  Output ({target_language}): Gang of thieves arrested"
        ),
        user=text[:2000],
        task_type="translation",
        model=FAST_MODEL,
    )


async def generate(
    system: str,
    user: str,
    task_type: str = "brief_generation",
    model: str | None = None,
) -> str:
    """
    Quality generation call. Defaults to QUALITY_MODEL (llama-3.3-70b);
    callers can override via `model=` to route a specific call to the fast
    model (llama-3.1-8b-instant) when its much-higher TPM ceiling matters
    more than the bigger model's reasoning depth.
    """
    return await call_groq(
        system=system,
        user=user,
        task_type=task_type,
        model=model or QUALITY_MODEL,
    )


async def extract_json(
    system: str,
    user: str,
    task_type: str = "profile_extraction",
) -> dict:
    """
    Call Groq and parse the response as JSON.

    Returns the parsed dict.
    Raises GroqCallFailed if the response is not valid JSON.
    """
    response = await call_groq(
        system=system,
        user=user,
        task_type=task_type,
        model=FAST_MODEL,
        json_response=True,
    )

    try:
        # Strip markdown code fences if the model included them
        clean = response.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1]
            clean = clean.rsplit("```", 1)[0]
        return json.loads(clean)
    except json.JSONDecodeError as exc:
        raise GroqCallFailed(
            f"Groq returned invalid JSON: {exc}\nResponse: {response[:200]}"
        ) from exc
