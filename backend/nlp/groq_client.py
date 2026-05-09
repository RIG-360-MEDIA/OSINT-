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


# ── Per-process concurrency limit ─────────────────────────────────────────────
#
# Without this, nlp workers (default concurrency=4) all pick up Celery
# tasks in parallel and fire 4+ concurrent Groq HTTPS POSTs from the
# same process. Combined with extraction + translation + classification
# + breaking detector + top-stories all running at the same time, we
# routinely produced 200+ requests/sec to Groq, blowing per-key per-
# minute rate caps even though daily TPD was healthy. The 429 cascade
# locked all keys in the local _exhausted_until tracker for 60s, and
# the next batch of tasks immediately re-tripped them on recovery.
#
# Limiting in-process concurrency to 2 means at most 2 × 4 workers = 8
# concurrent HTTPS calls per backend container. With round-robin across
# 20 keys that's ~24 req/min/key average — safely under the 30 rpm cap.
_GROQ_INPROC_CONCURRENCY = 2
_groq_call_sem: asyncio.Semaphore | None = None


def _get_call_sem() -> asyncio.Semaphore:
    """Lazy-init the semaphore on first use to avoid event-loop binding
    issues at import time."""
    global _groq_call_sem
    if _groq_call_sem is None:
        _groq_call_sem = asyncio.Semaphore(_GROQ_INPROC_CONCURRENCY)
    return _groq_call_sem


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

    # In-process concurrency throttle. See _get_call_sem() comment block
    # at the module level. Caller awaits the semaphore before doing the
    # actual key rotation + HTTP call, so only N concurrent requests can
    # leave this process at a time.
    async with _get_call_sem():
        return await _call_groq_inner(
            messages, model, max_tokens, temperature, json_response, attempts
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
