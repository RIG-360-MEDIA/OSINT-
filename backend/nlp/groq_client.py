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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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
        self._exhausted: set[int] = set()
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
            import groq as groq_sdk_module
            self._clients[key_index] = groq_sdk_module.AsyncGroq(
                api_key=self.keys[key_index]
            )
        return self._clients[key_index]

    # ── Public interface ───────────────────────────────────────────────────────

    async def get_key(self) -> tuple[int, "groq_sdk.AsyncGroq"]:
        """
        Return (key_index, cached_client) using round-robin across
        non-exhausted keys.

        Raises GroqQuotaExhausted if all keys are exhausted or no keys exist.
        """
        async with self._get_lock():
            available = [
                i for i in range(len(self.keys))
                if i not in self._exhausted
            ]
            if not available:
                raise GroqQuotaExhausted(
                    f"All {len(self.keys)} Groq key(s) exhausted. "
                    "Resets at 00:05 UTC."
                )
            # Round-robin within available indices
            position = self._index % len(available)
            idx = available[position]
            self._index = (self._index + 1) % len(available)
            return idx, self._get_client(idx)

    async def mark_exhausted(self, key_index: int) -> None:
        """Mark a key as rate-limited. Logs at WARNING — always visible in docker logs."""
        async with self._get_lock():
            self._exhausted.add(key_index)
            remaining = len(self.keys) - len(self._exhausted)
            logger.warning(
                "Groq key [%d] rate limited. %d/%d key(s) remaining.",
                key_index,
                remaining,
                len(self.keys),
            )

    def reset_exhausted(self) -> None:
        """
        Reset all exhausted keys to available.
        Called by Celery Beat task at 00:05 UTC daily.
        Synchronous — safe to call from a Celery task without an event loop.
        """
        count = len(self._exhausted)
        self._exhausted.clear()
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
            "exhausted_keys": len(self._exhausted),
            "available_keys": len(self.keys) - len(self._exhausted),
            "current_index": self._index,
        }


# ── Module-level singleton ─────────────────────────────────────────────────────
# Created once at import time. All callers import this instance.

def _init_manager() -> GroqKeyManager:
    keys_str = os.getenv("GROQ_API_KEYS", "")
    keys = [k.strip() for k in keys_str.split(",") if k.strip()]
    return GroqKeyManager(keys)


groq_manager: GroqKeyManager = _init_manager()


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
    import groq as groq_sdk

    max_tokens = TOKEN_LIMITS.get(task_type, 1000)

    if model is None:
        model = FAST_MODEL if task_type in _FAST_TASK_TYPES else QUALITY_MODEL

    temperature = TEMPERATURES.get(task_type, TEMPERATURES["generation"])

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    # Attempt up to min(total_keys, 3) times — try next key on rate limit
    attempts = min(max(len(groq_manager.keys), 1), 3)

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
            await groq_manager.mark_exhausted(key_idx)
            if attempt == attempts - 1:
                raise GroqQuotaExhausted(
                    "All retry attempts exhausted due to rate limiting."
                )
            # Try next available key
            continue

        except groq_sdk.APIError as exc:
            raise GroqCallFailed(f"Groq API error: {exc}") from exc

        except Exception as exc:
            raise GroqCallFailed(f"Unexpected error calling Groq: {exc}") from exc

    # Unreachable — loop always returns or raises — but satisfies type checker
    raise GroqCallFailed("call_groq exhausted all attempts without a result")


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
    """Translate text to the target language, preserving proper nouns."""
    return await call_groq(
        system=(
            f"Translate the following text to {target_language}. "
            "Preserve all proper nouns exactly. "
            "Output only the translated text, nothing else."
        ),
        user=text[:2000],
        task_type="translation",
        model=FAST_MODEL,
    )


async def generate(
    system: str,
    user: str,
    task_type: str = "brief_generation",
) -> str:
    """Quality generation call using QUALITY_MODEL."""
    return await call_groq(
        system=system,
        user=user,
        task_type=task_type,
        model=QUALITY_MODEL,
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
