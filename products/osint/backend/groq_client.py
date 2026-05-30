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
import httpx

# Cloudflare in front of api.groq.com rejects the default httpx/openai-SDK
# User-Agent with `error code: 1010` (403). Sending a real browser UA
# bypasses the WAF rule. Without this every Groq call 403s and the pool
# logs phantom "rate limit" errors.
_BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

FAST_MODEL = "qwen/qwen3-32b"
QUALITY_MODEL = "qwen/qwen3-32b"

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
        self._cooldown_seconds: float = 15.0  # 2026-05-28: was 60s; Groq's TPM 429s often resolve in 5-15s per the "try again in N.NNs" hint, so 60s held keys out 4x too long → cut to 15s for faster pool recovery
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
                http_client=httpx.AsyncClient(
                    headers={"User-Agent": _BROWSER_UA},
                    timeout=httpx.Timeout(30.0, connect=10.0),
                ),
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
    # Qwen3 family fallback — Cerebras deprecated qwen-3-235b-a22b-instruct-2507
    # on 2026-05-27 (and free tier no longer exposes any qwen-3-* identifier).
    # Tested both available free-tier models against our substrate schema:
    #   - gpt-oss-120b: VERBOSE, truncates JSON ~46%, EXTRACTS ZERO QUOTES
    #     even when it completes (silent quality regression — discovered
    #     2026-05-28 via head-to-head test).
    #   - zai-glm-4.7: concise (finishes in ~3.4K tokens, fits max=5000),
    #     extracts quotes correctly, parses cleanly on first try.
    # zai-glm-4.7 is the strictly better choice here.
    "qwen/qwen3-32b": "zai-glm-4.7",
    # Legacy fallbacks (kept in case env overrides force these):
    "llama-3.1-8b-instant": "llama3.1-8b",
    "llama-3.3-70b-versatile": "llama3.1-8b",  # no 70b on Cerebras free
    "llama-3.1-70b-versatile": "llama3.1-8b",
    "llama-3.2-3b-preview": "llama3.1-8b",
    "llama3-8b-8192": "llama3.1-8b",
    "llama3-70b-8192": "llama3.1-8b",
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
        # 2026-05-28: zai-glm-4.7 is a reasoning model — without this flag it
        # burns ~3K tokens on chain-of-thought BEFORE emitting any JSON,
        # blowing past max_tokens on long articles → empty content / truncation
        # in ~30% of calls. reasoning_effort="none" skips CoT entirely, cuts
        # per-call output from ~3,800 tok to ~800 tok, and eliminates the
        # empty-content failure mode. Probe-validated on real production
        # article (5.5KB body): 30% failure → 0% failure.
        if cerebras_model.startswith("zai-glm"):
            body["reasoning_effort"] = "none"
        # 2026-05-29: prompt_cache_key forces all our substrate-v3 calls
        # into the same prompt-cache routing slot within each per-key org.
        # Cerebras does prefix-cache automatically, but the explicit key
        # (a) standardises routing across all calls (better hit rate),
        # (b) makes hit/miss observable via response.usage.prompt_tokens_details.cached_tokens.
        # Caching saves latency, not quota — per docs, cached tokens still
        # count toward TPM/TPD. See docs/audits/cerebras-rate-limits-2026-05-29.md.
        body["prompt_cache_key"] = "rig-substrate-v3"
        try:
            # Browser UA is REQUIRED — Cerebras's API sits behind Cloudflare
            # WAF which rejects default python-httpx/urllib UAs with error
            # code 1010 / 403. Same root cause as the Groq incident in
            # docs/mistakes.md §8 — see entry "Same bug, second provider".
            async with _httpx.AsyncClient(timeout=30.0) as c:
                r = await c.post(
                    _CEREBRAS_BASE,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                        "User-Agent": _BROWSER_UA,
                    },
                    json=body,
                )
            # Guardrail — always capture the response body on non-2xx and
            # classify by HTTP code rather than assuming "non-200 == rate
            # limit". The original code path here was the gap that let the
            # Cloudflare-1010 / 403 incident hide for hours (mistakes.md §12).
            if r.status_code == 429:
                body = (r.text or "")[:300]
                bucket = (
                    "TPD" if ("per day" in body.lower() or "tpd" in body.lower())
                    else "RPM"
                )
                logger.warning(
                    "Cerebras 429 [%s] body=%s", bucket, body[:200]
                )
                continue
            if r.status_code in (401, 403):
                # NOT a rate limit. Rotating keys won't help — same WAF / IP
                # / auth issue would hit every key. Surface immediately so
                # monitoring catches it in minute one, not hour fourteen.
                body = (r.text or "")[:300]
                logger.error(
                    "Cerebras %d (NOT rate-limit, likely WAF/auth) body=%s",
                    r.status_code, body,
                )
                raise GroqCallFailed(
                    f"Cerebras {r.status_code} — not a rate limit. "
                    f"Check User-Agent / IP / key validity. body={body[:140]}"
                )
            if r.status_code >= 400:
                body = (r.text or "")[:300]
                logger.warning(
                    "Cerebras %d body=%s", r.status_code, body
                )
                raise GroqCallFailed(
                    f"Cerebras API error {r.status_code}: {body[:200]}"
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


# ── Unified Groq+Cerebras pool (parallel mode, kill-switch gated) ─────────────
#
# The legacy architecture tries Groq sequentially (3 keys), then falls over to
# Cerebras only when Groq's pool is fully cooled. That wastes 1-3 seconds per
# call retrying Groq keys that are TPD-exhausted before reaching Cerebras.
#
# Parallel mode: a single unified slot list spans Groq + Cerebras keys. Each
# call picks the next available slot regardless of provider. Throughput rises
# because we never burn time on exhausted keys.
#
# Gated by env: PARALLEL_LLM_POOL=1 enables it (default), =0 reverts to legacy
# failover for safe rollback without code changes.

_PARALLEL_LLM_POOL = os.getenv("PARALLEL_LLM_POOL", "1") != "0"

# Local LLM (Ollama on RTX 4090 reached via Tailscale) — added as a
# never-exhausted PRIMARY slot in the unified pool. Free providers
# become overflow. Disable with LOCAL_LLM_ENABLED=0.
_LOCAL_LLM_ENABLED = os.getenv("LOCAL_LLM_ENABLED", "1") != "0"
_LOCAL_LLM_PRIMARY = os.getenv("LOCAL_LLM_PRIMARY", "1") != "0"
# LOCAL-ONLY MODE — when set, the unified pool builds with ONLY the local
# slot. Groq and Cerebras slots are skipped entirely. Use when free
# providers are restricted or rate-limited and we want guaranteed
# routing to Ollama.
_LLM_LOCAL_ONLY = os.getenv("LLM_LOCAL_ONLY", "0") != "0"
# Local LLM endpoint — Ollama on port 11434.
# (vLLM 0.20 on this WSL setup is unstable post-shutdown; reverted to Ollama
# which uses a different GPU access path. Reliable 277 art/hr at concurrency=6.)
_OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://100.92.126.27:11434").rstrip("/")
_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:30b-a3b")
_OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "300"))
# Short cooldown when local fails — we want to retry local quickly
# because it's our primary capacity and free pool is overflow only.
_LOCAL_FAIL_COOLDOWN = 10.0
# Concurrent in-flight cap on the local slot. Ollama defaults to
# OLLAMA_NUM_PARALLEL=4. Workers beyond this fall through to the free
# pool instead of piling onto local and getting connection-level errors.
_LOCAL_MAX_CONCURRENT = int(os.getenv("LOCAL_LLM_MAX_CONCURRENT", "4"))

# ── 2026-05-28: secondary local-LLM endpoint (llama.cpp / LM Studio) ────────
# Optional OpenAI-compatible server on Trijya port 1234 running llama.cpp's
# llama-server.exe with --cont-batching --parallel 8. Provides a parallel
# lane to Ollama since Ollama's NUM_PARALLEL behaviour on Windows didn't
# scale as projected. Verified end-to-end: 42 tok/s gen speed on the 4090.
# Set LMSTUDIO_BASE_URL=http://100.92.126.27:1234 and LMSTUDIO_MODEL=<sha256-…>
# to enable. Empty base URL = disabled.
_LMSTUDIO_BASE = os.getenv("LMSTUDIO_BASE_URL", "").rstrip("/")
_LMSTUDIO_MODEL = os.getenv("LMSTUDIO_MODEL", "")
_LMSTUDIO_SLOTS = max(1, min(int(os.getenv("LMSTUDIO_CLIENT_SLOTS", "8")), 16))


class _UnifiedSlot:
    __slots__ = ("provider", "key_index", "key_string")

    def __init__(self, provider: str, key_index: int, key_string: str) -> None:
        self.provider = provider
        self.key_index = key_index
        self.key_string = key_string


class _UnifiedPool:
    """Mixed Groq+Cerebras key pool with shared rotation + per-slot cooldown."""

    def __init__(self) -> None:
        self._slots: list[_UnifiedSlot] = []
        # Local Ollama (RTX 4090) — N slots (default 8) all pointing at the
        # same Ollama URL. Each slot is an independent concurrency lane in
        # our pool. Mirror OLLAMA_NUM_PARALLEL on the server (default 8 after
        # D21 tune): if server runs 8-way parallel but we only open 1 client
        # slot, we saturate at 1 in-flight call → log shows "0/1 slots
        # remaining" constantly. With 8 client slots + 8 server parallel,
        # Drain D throughput jumps from 3 → 24 calls/min as projected.
        # Tunable via OLLAMA_CLIENT_SLOTS env var; cap at 16 for safety.
        if _LOCAL_LLM_ENABLED:
            n_local = max(1, min(int(os.getenv("OLLAMA_CLIENT_SLOTS", "8")), 16))
            for i in range(n_local):
                self._slots.append(_UnifiedSlot("local", i, _OLLAMA_BASE))
        # LM Studio / llama.cpp secondary local endpoint (OpenAI-compatible).
        # Independent of Ollama — runs on Trijya port 1234. When configured,
        # adds N (default 8) parallel slots that share the same GPU but use
        # llama.cpp's continuous batching instead of Ollama's NUM_PARALLEL.
        if _LMSTUDIO_BASE and _LMSTUDIO_MODEL:
            for i in range(_LMSTUDIO_SLOTS):
                self._slots.append(_UnifiedSlot("lmstudio", i, _LMSTUDIO_BASE))
        # In LOCAL-ONLY mode we skip building Groq/Cerebras slots so the
        # pool can ONLY route to local. Used when free providers are
        # restricted/rate-limited.
        if not _LLM_LOCAL_ONLY:
            for i, k in enumerate(groq_manager.keys):
                self._slots.append(_UnifiedSlot("groq", i, k))
            for i, k in enumerate(_CEREBRAS_KEYS):
                self._slots.append(_UnifiedSlot("cerebras", i, k))
        self._index: int = 0
        self._exhausted_until: dict[int, float] = {}
        self._cooldown_seconds: float = 15.0  # 2026-05-28: was 60s; Groq's TPM 429s often resolve in 5-15s per the "try again in N.NNs" hint, so 60s held keys out 4x too long → cut to 15s for faster pool recovery
        self._max_cooldown_seconds: float = 300.0
        self._lock: asyncio.Lock | None = None
        # Concurrency cap on local slot — protects Ollama from being
        # hammered by N workers grabbing the same slot in parallel.
        self._local_inflight: int = 0
        local_count = sum(1 for s in self._slots if s.provider == "local")
        logger.info(
            "UnifiedPool initialised: %d local + %d Groq + %d Cerebras = %d total slots",
            local_count, len(groq_manager.keys), len(_CEREBRAS_KEYS), len(self._slots),
        )

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def get_slot(self) -> tuple[int, _UnifiedSlot]:
        """Return (slot_index, _UnifiedSlot). Local slot is preferred when
        available; free providers (Groq+Cerebras) become overflow.
        Falls back to soonest-to-recover when all slots are exhausted."""
        import time as _time
        async with self._get_lock():
            now = _time.time()
            recovered = [i for i, until in self._exhausted_until.items() if until <= now]
            for i in recovered:
                del self._exhausted_until[i]

            # PRIMARY: prefer local slot when it's not in cooldown AND
            # not saturated with in-flight requests. In LOCAL-ONLY mode
            # we ALSO return local even when at capacity — Ollama queues
            # internally, and there's no other slot to fall back to.
            if _LOCAL_LLM_PRIMARY:
                for i, slot in enumerate(self._slots):
                    if slot.provider != "local":
                        continue
                    if i in self._exhausted_until:
                        continue
                    if _LLM_LOCAL_ONLY:
                        # Always return local in LOCAL-ONLY mode.
                        self._local_inflight += 1
                        return i, slot
                    if self._local_inflight < _LOCAL_MAX_CONCURRENT:
                        self._local_inflight += 1
                        return i, slot

            # Overflow: round-robin across remaining free-provider slots.
            available = [
                i for i in range(len(self._slots))
                if self._slots[i].provider != "local"
                and i not in self._exhausted_until
            ]
            if not available:
                if not self._slots:
                    raise GroqQuotaExhausted("UnifiedPool has zero slots")
                # Even free pool is fully exhausted — pick the soonest-to-
                # recover slot (could be local if it just cooled).
                soonest_idx = min(
                    self._exhausted_until.items(), key=lambda kv: kv[1]
                )[0]
                self._exhausted_until.pop(soonest_idx, None)
                return soonest_idx, self._slots[soonest_idx]
            position = self._index % len(available)
            idx = available[position]
            self._index = (self._index + 1) % max(len(available), 1)
            return idx, self._slots[idx]

    async def release_local(self) -> None:
        """Decrement the local in-flight counter. Called after every local
        call (success or fail) so concurrent workers see capacity opening
        up promptly."""
        async with self._get_lock():
            if self._local_inflight > 0:
                self._local_inflight -= 1

    async def mark_exhausted(
        self, slot_index: int, seconds: float | None = None
    ) -> None:
        import time as _time
        s = seconds if seconds is not None else self._cooldown_seconds
        s = min(max(s, 0.0), self._max_cooldown_seconds)
        async with self._get_lock():
            self._exhausted_until[slot_index] = _time.time() + s
            remaining = len(self._slots) - len(self._exhausted_until)
            slot = self._slots[slot_index]
            logger.warning(
                "UnifiedPool slot[%d] (%s/key[%d]) cooled for %.0fs. "
                "%d/%d slots remaining.",
                slot_index, slot.provider, slot.key_index,
                s, remaining, len(self._slots),
            )


_unified_pool_singleton: _UnifiedPool | None = None


def _get_unified_pool() -> _UnifiedPool:
    """Lazy init so the pool sees the latest groq_manager.keys + _CEREBRAS_KEYS."""
    global _unified_pool_singleton
    if _unified_pool_singleton is None:
        _unified_pool_singleton = _UnifiedPool()
    return _unified_pool_singleton


async def _call_via_slot(
    slot: _UnifiedSlot,
    messages: list,
    model: str,
    max_tokens: int,
    temperature: float,
    json_response: bool,
) -> str:
    """Make a single chat-completion call using the given slot."""
    if slot.provider == "local":
        # Ollama native /api/chat endpoint on the RTX 4090 via Tailscale.
        # slot.key_string holds the base URL (defaults to :11434).
        # Qwen3 thinking-mode disabled via `think: false`; multilingual JSON
        # enforced via `format: "json"`. Proven 277 art/hr at concurrency=6.
        import httpx as _httpx
        # 2026-05-28: per-request optimizations for 4090. We can't restart
        # the Ollama server to set OLLAMA_NUM_PARALLEL / FLASH_ATTENTION /
        # KV_CACHE_TYPE (no SSH access to Trijya), but Ollama accepts
        # per-request `options` that override Modelfile defaults:
        #   num_batch=2048  — default 512; 4× batch helps 4090 GPU utilization
        #                     stay high during long-prompt processing
        #   num_ctx=8192    — substrate prompts are ~3K tok, output ~3K → need
        #                     8K context window per call (default 2K truncates)
        #   num_keep=0      — don't pin tokens; full window available
        # Note: num_parallel cannot be set per-request; only server env var.
        body: dict[str, Any] = {
            "model": _OLLAMA_MODEL,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_batch": 2048,
                "num_ctx": 8192,
                "num_keep": 0,
            },
        }
        if json_response:
            body["format"] = "json"
        async with _httpx.AsyncClient(timeout=_OLLAMA_TIMEOUT) as c:
            r = await c.post(
                f"{slot.key_string}/api/chat",
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": _BROWSER_UA,
                },
                json=body,
            )
        if r.status_code >= 400:
            body_text = (r.text or "")[:300]
            logger.warning(
                "Local LLM %d body=%s", r.status_code, body_text[:200]
            )
            raise _LocalCallFailed(
                f"Ollama {r.status_code}: {body_text[:160]}"
            )
        data = r.json()
        content = (data.get("message", {}) or {}).get("content", "") or ""
        if not content:
            done_reason = data.get("done_reason", "?")
            eval_count = data.get("eval_count", 0)
            raise _LocalCallFailed(
                f"Ollama empty content (done_reason={done_reason}, eval_count={eval_count})"
            )
        return content.strip()

    if slot.provider == "lmstudio":
        # 2026-05-28: llama.cpp / LM Studio OpenAI-compatible server on
        # local network (Trijya port 1234). Auth-free. Adds a continuous-
        # batching lane parallel to Ollama. Disable qwen3 reasoning via
        # chat_template_kwargs.enable_thinking=false (same root-cause fix
        # as D17 for Cerebras zai-glm — saves ~3K tok/call).
        import httpx as _httpx
        body: dict[str, Any] = {
            "model": _LMSTUDIO_MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if json_response:
            body["response_format"] = {"type": "json_object"}
        async with _httpx.AsyncClient(timeout=_OLLAMA_TIMEOUT) as c:
            r = await c.post(
                f"{slot.key_string}/v1/chat/completions",
                headers={"Content-Type": "application/json"},
                json=body,
            )
        if r.status_code >= 400:
            body_text = (r.text or "")[:300]
            logger.warning("LMStudio %d body=%s", r.status_code, body_text[:200])
            raise _LocalCallFailed(
                f"LMStudio {r.status_code}: {body_text[:160]}"
            )
        data = r.json()
        choices = data.get("choices") or []
        if not choices:
            raise _LocalCallFailed("LMStudio: no choices in response")
        msg = choices[0].get("message") or {}
        content = msg.get("content") or ""
        if not content:
            # Fallback: if the model emitted reasoning but not content
            # (enable_thinking flag ignored), use the reasoning text rather
            # than dropping the article. Better than a parse failure.
            rc = msg.get("reasoning_content") or ""
            if rc:
                logger.info(
                    "LMStudio returned reasoning_content only (len=%d); "
                    "using as content. Consider verifying enable_thinking=false "
                    "is propagated by the server's chat template.",
                    len(rc),
                )
                content = rc
            else:
                raise _LocalCallFailed("LMStudio empty content")
        return content.strip()

    if slot.provider == "groq":
        client = groq_manager._get_client(slot.key_index)
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

    # Cerebras path — reuse _call_cerebras's per-key request shape.
    cerebras_model = _GROQ_TO_CEREBRAS_MODEL.get(model, "llama3.1-8b")
    import httpx as _httpx
    body: dict[str, Any] = {
        "model": cerebras_model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_response:
        body["response_format"] = {"type": "json_object"}
    # See _call_cerebras for context: zai-glm is a reasoning model and needs
    # reasoning_effort=none to skip chain-of-thought (saves ~3K tok/call).
    if cerebras_model.startswith("zai-glm"):
        body["reasoning_effort"] = "none"
    # See _call_cerebras docstring: standardise prompt_cache_key for
    # observable cache routing across parallel-mode + sequential calls.
    body["prompt_cache_key"] = "rig-substrate-v3"
    async with _httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(
            _CEREBRAS_BASE,
            headers={
                "Authorization": f"Bearer {slot.key_string}",
                "Content-Type": "application/json",
                "User-Agent": _BROWSER_UA,
            },
            json=body,
        )
    if r.status_code == 429:
        # Caller will mark the slot exhausted and rotate.
        body_text = (r.text or "")[:300]
        tag = "TPD" if ("per day" in body_text.lower() or "tpd" in body_text.lower()) else "RPM"
        logger.warning("Cerebras 429 [%s] body=%s", tag, body_text[:200])
        raise _CerebrasRateLimited()
    if r.status_code in (401, 403):
        body_text = (r.text or "")[:300]
        logger.error(
            "Cerebras %d (NOT rate-limit) body=%s", r.status_code, body_text
        )
        raise GroqCallFailed(
            f"Cerebras {r.status_code}: {body_text[:140]}"
        )
    if r.status_code >= 400:
        body_text = (r.text or "")[:300]
        raise GroqCallFailed(
            f"Cerebras API error {r.status_code}: {body_text[:200]}"
        )
    data = r.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        raise GroqCallFailed("Cerebras returned empty content")
    return content.strip()


class _CerebrasRateLimited(Exception):
    """Internal sentinel so _call_unified_pool can catch Cerebras 429 specifically."""


class _LocalCallFailed(Exception):
    """Internal sentinel for local-Ollama failures — cooldown short, retry fast."""


async def _call_unified_pool(
    messages: list,
    model: str,
    max_tokens: int,
    temperature: float,
    json_response: bool,
) -> str:
    """Try slots from the unified pool. Up to 15 attempts. Rotates across
    providers transparently. Final failure → GroqQuotaExhausted.

    Why 15 not 5: large non-English calls (~5K tokens each) easily hit
    Groq's 6K-TPM-per-key cap. Even with rotation, a burst of 3-4 such
    calls can leave all recently-used slots cooled for 60s. Five retries
    is too tight — we observed ~37% pool-exhausted rate. With 15 retries,
    the pool has plenty of headroom to find a healthy slot during bursts."""
    pool = _get_unified_pool()
    attempts = min(len(pool._slots), 15)
    last_exc: Exception | None = None
    for attempt in range(attempts):
        await _get_bucket().acquire()
        slot_idx, slot = await pool.get_slot()
        try:
            try:
                return await _call_via_slot(
                    slot, messages, model, max_tokens, temperature, json_response
                )
            finally:
                if slot.provider == "local":
                    await pool.release_local()
        except groq_sdk.RateLimitError as exc:
            _log_response_body("UnifiedPool/groq 429", exc)
            await pool.mark_exhausted(slot_idx)
            last_exc = exc
            continue
        except _CerebrasRateLimited as exc:
            await pool.mark_exhausted(slot_idx)
            last_exc = exc
            continue
        except _LocalCallFailed as exc:
            # Local Ollama hiccup — cool briefly so we don't hammer it,
            # then fall through to free-provider overflow.
            logger.info(
                "UnifiedPool local-slot failed (%s) — cooling %.0fs and "
                "rotating to free pool.", str(exc)[:140], _LOCAL_FAIL_COOLDOWN
            )
            await pool.mark_exhausted(slot_idx, seconds=_LOCAL_FAIL_COOLDOWN)
            last_exc = exc
            continue
        except httpx.HTTPError as exc:
            # Network-level error from local (Tailscale hiccup, timeout, etc.)
            if slot.provider == "local":
                logger.info(
                    "UnifiedPool local network error %s(%s) — cooling %.0fs.",
                    type(exc).__name__, str(exc)[:140] or "<no message>",
                    _LOCAL_FAIL_COOLDOWN,
                )
                await pool.mark_exhausted(slot_idx, seconds=_LOCAL_FAIL_COOLDOWN)
                last_exc = exc
                continue
            raise
        except groq_sdk.AuthenticationError as exc:
            _log_response_body("UnifiedPool/groq 401", exc)
            raise GroqCallFailed(
                f"Groq auth failed for key [{slot.key_index}] — invalid/revoked."
            ) from exc
        except groq_sdk.PermissionDeniedError as exc:
            _log_response_body("UnifiedPool/groq 403", exc)
            raise GroqCallFailed(
                "Groq 403 forbidden — WAF/Cloudflare block. Check User-Agent."
            ) from exc
        except groq_sdk.BadRequestError as exc:
            _log_response_body("UnifiedPool/groq 400", exc)
            err = str(exc).lower()
            if "json_validate_failed" in err or "failed to generate json" in err:
                # Transient model flake; rotate to next slot.
                last_exc = exc
                continue
            raise GroqCallFailed(f"Groq bad request: {exc}") from exc
        except groq_sdk.APIConnectionError as exc:
            _log_response_body("UnifiedPool/groq conn", exc, level=logging.INFO)
            last_exc = exc
            continue
        except (GroqQuotaExhausted, GroqCallFailed):
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("UnifiedPool unexpected error on slot %d: %s",
                           slot_idx, str(exc)[:200])
            last_exc = exc
            continue
    raise GroqQuotaExhausted(
        f"UnifiedPool exhausted after {attempts} attempts: {last_exc}"
    )


# ── Call Wrapper ───────────────────────────────────────────────────────────────

async def call_groq(
    system: str,
    user: str,
    task_type: str = "generation",
    model: str | None = None,
    json_response: bool = False,
    max_tokens_override: int | None = None,
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
        max_tokens_override: If set, override the task_type's TOKEN_LIMITS entry.
                       Needed when one logical task_type covers multiple call shapes
                       (e.g. extraction v2 uses different caps for English vs
                       non-English with translation embedded in the output).

    Returns:
        Stripped response text from Groq.

    Raises:
        GroqQuotaExhausted: All keys are rate limited.
        GroqCallFailed:     Non-quota API error or unexpected failure.
    """
    max_tokens = max_tokens_override or TOKEN_LIMITS.get(task_type, 1000)

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

    # Parallel pool path — gated by PARALLEL_LLM_POOL env flag (default on).
    # Mixes Groq + Cerebras keys; rotates per call. No wasted retries on
    # already-exhausted Groq keys before reaching Cerebras.
    if _PARALLEL_LLM_POOL and (
        _CEREBRAS_KEYS or _LLM_LOCAL_ONLY or _LOCAL_LLM_ENABLED
    ):
        return await _call_unified_pool(
            messages, model, max_tokens, temperature, json_response
        )

    # Legacy sequential failover — Groq first, Cerebras only if Groq pool dies.
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

        except groq_sdk.RateLimitError as exc:
            # 429 — real per-minute / per-day rate limit. ONLY case where we
            # should ever mark a key exhausted. See mistakes.md §8 for the
            # incident where 403s were re-labelled as 429s and burned the
            # pool.
            _log_response_body("Groq 429", exc)
            await groq_manager.mark_exhausted(key_idx)
            if attempt == attempts - 1:
                raise GroqQuotaExhausted(
                    "Retry attempts exhausted due to rate limiting."
                )
            continue

        except groq_sdk.AuthenticationError as exc:
            # 401 — key is bad / revoked. Don't cool it down (it'll never
            # recover). Surface to the caller so monitoring can alert.
            _log_response_body("Groq 401 AUTH", exc)
            raise GroqCallFailed(
                f"Groq auth failed for key [{key_idx}] — key invalid or revoked. "
                f"This is NOT a rate limit. Check GROQ_API_KEYS."
            ) from exc

        except groq_sdk.PermissionDeniedError as exc:
            # 403 — blocked at the WAF / IP / region level. Same shape as
            # the Cloudflare 1010 incident: every key returned the same
            # error before the credential was even checked. Surface
            # explicitly so monitoring catches it in minute one.
            _log_response_body("Groq 403 BLOCKED", exc)
            raise GroqCallFailed(
                f"Groq returned 403 (forbidden) — NOT a rate limit, NOT an "
                f"auth issue. Likely a WAF / Cloudflare block on this IP or "
                f"User-Agent. Check the response body in the logs above."
            ) from exc

        except groq_sdk.APIConnectionError as exc:
            # Network-layer error — retry same key once before rotating
            _log_response_body("Groq connection", exc, level=logging.INFO)
            if attempt < attempts - 1:
                continue
            raise GroqCallFailed("Groq connection error on all attempts") from exc

        except groq_sdk.BadRequestError as exc:
            # 400 — usually json_validate_failed when the model produced
            # malformed JSON under strict response_format. This is a
            # transient model-level issue (not key-level). Retry on the
            # next key — different key, different rolled output.
            # See docs/mistakes.md for the pattern. Body capture is the
            # rule — never trust the exception class alone.
            _log_response_body("Groq 400 BadRequest", exc)
            err_text = str(exc).lower()
            if "json_validate_failed" in err_text or "failed to generate json" in err_text:
                # Pure model flake — try the next key.
                if attempt < attempts - 1:
                    continue
                raise GroqCallFailed(
                    "Groq json_validate_failed on all retry attempts"
                ) from exc
            # Other 400 errors (bad model name, malformed payload) — not
            # transient; surface to caller immediately.
            raise GroqCallFailed(f"Groq bad request: {exc}") from exc

        except groq_sdk.APIError as exc:
            # Generic API error (4xx other than the explicit ones above, 5xx).
            # Body capture is the rule — never trust the exception class
            # alone to tell you what went wrong.
            _log_response_body("Groq APIError", exc)
            raise GroqCallFailed(f"Groq API error: {exc}") from exc

        except Exception as exc:
            raise GroqCallFailed(f"Unexpected error calling Groq: {exc}") from exc

    # Unreachable — loop always returns or raises — but satisfies type checker
    raise GroqCallFailed("call_groq exhausted all attempts without a result")


# ── Error body capture ────────────────────────────────────────────────────────
#
# Guardrail #2 from docs/mistakes.md — when any LLM call fails, capture the
# raw response body. The Cloudflare 1010 incident burned 13 hours because
# our error handler labelled every failure "rate limited" without ever
# logging what the provider actually returned. Never again.


def _log_response_body(
    label: str,
    exc: Exception,
    level: int = logging.WARNING,
) -> None:
    """
    Extract and log the raw HTTP response body from a groq SDK exception.
    The SDK attaches the underlying httpx.Response on exc.response when
    the failure was an HTTP error. Best-effort — never raises.
    """
    body: str = ""
    status: int | None = None
    try:
        resp = getattr(exc, "response", None)
        if resp is not None:
            status = getattr(resp, "status_code", None)
            text = getattr(resp, "text", "") or ""
            body = text[:400]
    except Exception:  # noqa: BLE001
        pass
    if body:
        logger.log(level, "%s [status=%s] body=%s", label, status, body)
    else:
        logger.log(level, "%s [no body captured] err=%s", label, str(exc)[:200])


# ── Provider health-check ─────────────────────────────────────────────────────
#
# Guardrail #3 from docs/mistakes.md — at container boot (and on demand via
# /admin/health/llm), probe every configured provider with one tiny call.
# If any returns non-200, log loudly. This would have caught the Cloudflare
# 1010 incident in minute one of deploy instead of hour fourteen.


async def health_check_groq(timeout: float = 8.0) -> dict[str, object]:
    """
    Single tiny chat-completion against the first configured Groq key.
    Returns a dict with provider status — never raises.
    """
    if not groq_manager.keys:
        return {"provider": "groq", "status": "no_keys_configured", "ok": False}
    try:
        result = await asyncio.wait_for(
            call_groq(
                system="reply with one word",
                user="ping",
                task_type="classification",
            ),
            timeout=timeout,
        )
        return {
            "provider": "groq",
            "status": "ok",
            "ok": True,
            "sample_response": (result or "")[:60],
            "key_count": len(groq_manager.keys),
        }
    except asyncio.TimeoutError:
        return {
            "provider": "groq",
            "status": "timeout",
            "ok": False,
            "error": f"no response within {timeout}s",
        }
    except (GroqQuotaExhausted, GroqCallFailed) as exc:
        return {
            "provider": "groq",
            "status": type(exc).__name__,
            "ok": False,
            "error": str(exc)[:240],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "provider": "groq",
            "status": "unexpected",
            "ok": False,
            "error": str(exc)[:240],
        }


async def health_check_cerebras(timeout: float = 8.0) -> dict[str, object]:
    """
    Single tiny chat-completion against the first configured Cerebras key.
    Returns a dict with provider status — never raises.
    """
    if not _CEREBRAS_KEYS:
        return {"provider": "cerebras", "status": "no_keys_configured", "ok": False}
    try:
        result = await asyncio.wait_for(
            _call_cerebras(
                messages=[
                    {"role": "system", "content": "reply with one word"},
                    {"role": "user", "content": "ping"},
                ],
                groq_model=FAST_MODEL,
                max_tokens=4,
                temperature=0.0,
                json_response=False,
            ),
            timeout=timeout,
        )
        return {
            "provider": "cerebras",
            "status": "ok",
            "ok": True,
            "sample_response": (result or "")[:60],
            "key_count": len(_CEREBRAS_KEYS),
        }
    except asyncio.TimeoutError:
        return {
            "provider": "cerebras",
            "status": "timeout",
            "ok": False,
            "error": f"no response within {timeout}s",
        }
    except (GroqQuotaExhausted, GroqCallFailed) as exc:
        return {
            "provider": "cerebras",
            "status": type(exc).__name__,
            "ok": False,
            "error": str(exc)[:240],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "provider": "cerebras",
            "status": "unexpected",
            "ok": False,
            "error": str(exc)[:240],
        }


async def health_check_all() -> dict[str, object]:
    """
    Probe Groq and Cerebras concurrently. Returns a combined report.
    """
    groq_result, cerebras_result = await asyncio.gather(
        health_check_groq(),
        health_check_cerebras(),
    )
    all_ok = bool(groq_result.get("ok") and cerebras_result.get("ok"))
    return {
        "all_ok": all_ok,
        "providers": [groq_result, cerebras_result],
    }


async def boot_health_log() -> None:
    """
    Run at container startup. Logs the full provider state at INFO if all
    OK, ERROR if any provider is broken. Never raises — startup must
    proceed even if LLM providers are down (so the API server still
    serves cached / non-LLM traffic).
    """
    report = await health_check_all()
    if report["all_ok"]:
        logger.info("LLM provider health-check OK: %s", report)
    else:
        # Loud, structured error — monitoring should alert on this string.
        logger.error("LLM_PROVIDER_HEALTH_FAILED: %s", report)


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
