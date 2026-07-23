"""backend.draftsmith.llm — Cerebras gpt-oss-120b caller for draftsmith.

Mirrors the live generator's call loop (scripts/worldwide_gen_v2.gen()):
round-robins backend.nlp.groq_client._CEREBRAS_KEYS, POSTs to
config.CEREBRAS_URL with config.CEREBRAS_MODEL, and tolerant-parses the
JSON a chat completion returns (strip code fences, de-bold markdown keys,
grab the first {...} span). draftsmith is Cerebras-ONLY here — it does not
touch groq_client's Groq/local/unified pool, only borrows its key list, so
draftsmith load never competes with the NLP pillars' own call budget on
those other providers.

On a JSON parse failure, cerebras_json reprompts (same system/user, next
rotated key) with the temperature stepped down each round — the same
recipe worldwide_gen_v2 uses for its VERIFY/REPAIR passes, where a lower
temperature measurably reduces the odds of the model wrapping JSON in
prose. After config.LLM_MAX_RETRIES rounds with no parseable JSON,
LLMParseError is raised — never silently returns a partial/guessed dict.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import httpx

import backend.nlp.groq_client as gc
from backend.draftsmith import config

logger = logging.getLogger(__name__)

# Cerebras (and Groq) sit behind a Cloudflare WAF that 403s the default
# httpx/urllib User-Agent. Same fix as backend.nlp.groq_client._BROWSER_UA.
_BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_HTTP_TIMEOUT = httpx.Timeout(180.0, connect=15.0)
_TEMP_STEP_DOWN = 0.15
_RETRY_SLEEP_SECONDS = 0.3


class LLMError(Exception):
    """Raised when a Cerebras call fails for a non-parse reason (network
    error, non-200, empty content) after all configured retries."""


class LLMParseError(LLMError):
    """Raised when cerebras_json exhausts config.LLM_MAX_RETRIES attempts
    without ever getting back a JSON object it could parse."""


_key_index = 0
_key_lock: asyncio.Lock | None = None
_key_lock_loop: Any = None


def _get_lock() -> asyncio.Lock:
    """Loop-aware lazy lock. Celery prefork workers run a fresh
    asyncio.run() per task; a lock created in one task's loop deadlocks a
    later task's `await` on a different loop. Same pattern (and the
    incident it fixes) as backend.nlp.groq_client._loop_bound_lock."""
    global _key_lock, _key_lock_loop
    loop = asyncio.get_running_loop()
    if _key_lock is None or _key_lock_loop is not loop:
        _key_lock = asyncio.Lock()
        _key_lock_loop = loop
    return _key_lock


async def _next_key() -> str:
    keys = list(gc._CEREBRAS_KEYS)
    if not keys:
        raise LLMError(
            "No Cerebras keys configured (CEREBRAS_API_KEYS env var is empty)."
        )
    global _key_index
    async with _get_lock():
        key = keys[_key_index % len(keys)]
        _key_index = (_key_index + 1) % len(keys)
    return key


async def _call_cerebras_once(
    system: str, user: str, *, temperature: float, max_tokens: int,
) -> str:
    """One HTTP call against one rotated key. Raises LLMError on any
    network failure or non-200/empty response; the caller decides whether
    to retry."""
    key = await _next_key()
    body: dict[str, Any] = {
        "model": config.CEREBRAS_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(
                config.CEREBRAS_URL,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "User-Agent": _BROWSER_UA,
                },
                json=body,
            )
    except httpx.HTTPError as exc:
        raise LLMError(f"Cerebras network error: {exc}") from exc

    if resp.status_code != 200:
        raise LLMError(f"Cerebras HTTP {resp.status_code}: {resp.text[:300]}")

    try:
        data = resp.json()
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, ValueError) as exc:
        raise LLMError(f"Cerebras returned an unexpected response shape: {exc}") from exc

    content = (message.get("content") or message.get("reasoning") or "").strip()
    if not content:
        raise LLMError("Cerebras returned empty content")
    return content


def _tolerant_json(raw: str) -> dict[str, Any] | None:
    """Best-effort JSON extraction from a chat completion. Mirrors
    scripts/worldwide_gen_v2.parse(): strips ``` fences, un-bolds
    markdown-wrapped keys, grabs the first {...} span. Returns None (never
    raises) when nothing parseable is found so the caller can reprompt."""
    stripped = raw.strip()
    stripped = re.sub(r"^```(json)?", "", stripped).strip()
    stripped = re.sub(r"```$", "", stripped).strip()
    # "**headline**": ... -> "headline": ...
    stripped = re.sub(r'\*\*("?\w[\w\s]*"?)\*\*(\s*:)', r"\1\2", stripped)
    match = re.search(r"\{.*\}", stripped, re.S)
    if not match:
        return None
    candidate = match.group(0)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        try:
            return json.loads(re.sub(r"\*\*", "", candidate))
        except json.JSONDecodeError:
            return None


async def cerebras_text(
    system: str, user: str, *, temperature: float, max_tokens: int = 6000,
) -> str:
    """Plain-text Cerebras call. Retries config.LLM_MAX_RETRIES times
    (rotating keys each attempt) on transient failure; raises LLMError with
    the last error attached after the final attempt."""
    last_exc: Exception | None = None
    for attempt in range(config.LLM_MAX_RETRIES):
        try:
            return await _call_cerebras_once(
                system, user, temperature=temperature, max_tokens=max_tokens,
            )
        except LLMError as exc:
            last_exc = exc
            logger.warning(
                "cerebras_text attempt %d/%d failed: %s",
                attempt + 1, config.LLM_MAX_RETRIES, exc,
            )
            if attempt < config.LLM_MAX_RETRIES - 1:
                await asyncio.sleep(_RETRY_SLEEP_SECONDS)
    raise LLMError(
        f"cerebras_text exhausted {config.LLM_MAX_RETRIES} attempts: {last_exc}"
    ) from last_exc


async def cerebras_json(
    system: str, user: str, *, temperature: float, max_tokens: int = 6000,
) -> dict[str, Any]:
    """JSON-mode Cerebras call with tolerant parsing + reprompt-on-failure.

    Each retry re-sends the same system/user prompt on the next rotated key,
    stepping the temperature down (floor 0.0) — this is the live generator's
    verify/repair recipe for reducing the odds of the model re-wrapping its
    JSON in prose. Network/HTTP failures also consume a retry slot and step
    temperature down the same way, so one exhausted key can't burn through
    LLM_MAX_RETRIES attempts without any real reprompt happening.

    Raises LLMParseError if no attempt ever produced parseable JSON;
    re-raises the underlying LLMError if every attempt failed at the HTTP
    layer instead.
    """
    last_raw: str | None = None
    last_exc: Exception | None = None
    saw_any_response = False
    temp = temperature
    for attempt in range(config.LLM_MAX_RETRIES):
        try:
            raw = await _call_cerebras_once(
                system, user, temperature=temp, max_tokens=max_tokens,
            )
        except LLMError as exc:
            last_exc = exc
            logger.warning(
                "cerebras_json attempt %d/%d call failed: %s",
                attempt + 1, config.LLM_MAX_RETRIES, exc,
            )
            temp = max(0.0, temp - _TEMP_STEP_DOWN)
            if attempt < config.LLM_MAX_RETRIES - 1:
                await asyncio.sleep(_RETRY_SLEEP_SECONDS)
            continue

        saw_any_response = True
        last_raw = raw
        parsed = _tolerant_json(raw)
        if parsed is not None:
            return parsed
        logger.warning(
            "cerebras_json attempt %d/%d returned unparseable JSON (len=%d); "
            "stepping temperature %.2f -> %.2f",
            attempt + 1, config.LLM_MAX_RETRIES, len(raw), temp,
            max(0.0, temp - _TEMP_STEP_DOWN),
        )
        temp = max(0.0, temp - _TEMP_STEP_DOWN)

    if not saw_any_response:
        raise LLMError(
            f"cerebras_json: every call failed after {config.LLM_MAX_RETRIES} "
            f"attempts: {last_exc}"
        ) from last_exc
    raise LLMParseError(
        f"cerebras_json: no parseable JSON after {config.LLM_MAX_RETRIES} attempts. "
        f"last_raw_snippet={(last_raw or '')[:200]!r}"
    )
