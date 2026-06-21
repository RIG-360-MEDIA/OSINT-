"""Pluggable LLM provider (OpenAI-compatible) with Groq key-pool rotation.

Default target is Groq, but the same client works against OpenAI, Together, or a
local vLLM/Ollama OpenAI-compatible endpoint — swap via ``ASKRIG_LLM_*`` env.

Groq enforces a per-key, per-model daily token limit (TPD). A single key drains
fast, so we rotate across a pool of keys (``ASKRIG_LLM_API_KEYS``): on a 429 we
advance to the next key and retry. The rotation index is shared process-wide so
an exhausted key is skipped on subsequent requests, not retried first every time.
"""
from __future__ import annotations

import logging
import threading
from typing import Protocol

from app.config import Settings

logger = logging.getLogger(__name__)


class LLMProvider(Protocol):
    def complete(self, system: str, user: str) -> str: ...

    def chat(self, messages: list[dict], tools: list[dict] | None = None): ...

    def stream_messages(self, messages: list[dict]): ...


class RotatingProvider:
    """OpenAI-compatible chat provider that rotates over a key pool on 429."""

    def __init__(self, settings: Settings, model: str | None = None) -> None:
        keys = list(settings.llm_api_keys)
        if not keys:
            raise RuntimeError(
                "No LLM API keys configured (set ASKRIG_LLM_API_KEYS or ASKRIG_LLM_API_KEY)"
            )
        from openai import OpenAI

        self._OpenAI = OpenAI
        self._keys = list(dict.fromkeys(keys))  # dedupe, preserve order
        self._base_url = settings.llm_base_url
        self._model = model or settings.llm_model
        self._temperature = settings.llm_temperature
        self._idx = 0
        self._lock = threading.Lock()
        self._clients: dict[str, object] = {}
        self._dead: set[int] = set()  # keys that returned 401/403 — never retried

    def _client_for(self, key: str):
        client = self._clients.get(key)
        if client is None:
            client = self._OpenAI(api_key=key, base_url=self._base_url)
            self._clients[key] = client
        return client

    def _advance_from(self, idx: int) -> None:
        # Advance only if no other thread already rotated past this key.
        with self._lock:
            if self._idx == idx:
                self._idx = (self._idx + 1) % len(self._keys)

    def _mark_dead(self, idx: int) -> None:
        with self._lock:
            self._dead.add(idx)

    def _run(self, call):
        """Run call(client) with key rotation: skip dead keys, rotate on 401/403/429."""
        from openai import APIStatusError, AuthenticationError, RateLimitError

        last_err: Exception | None = None
        n = len(self._keys)
        for _ in range(n):
            with self._lock:
                idx = self._idx
            if idx in self._dead:
                self._advance_from(idx)
                continue
            try:
                return call(self._client_for(self._keys[idx]))
            except AuthenticationError as exc:
                last_err = exc
                logger.warning("LLM key #%d invalid (auth) — marking dead", idx)
                self._mark_dead(idx)
                self._advance_from(idx)
            except (RateLimitError, APIStatusError) as exc:
                status = getattr(exc, "status_code", None)
                if status in (401, 403):
                    last_err = exc
                    logger.warning("LLM key #%d auth error %s — marking dead", idx, status)
                    self._mark_dead(idx)
                    self._advance_from(idx)
                elif isinstance(exc, RateLimitError) or status == 429:
                    last_err = exc
                    logger.warning("LLM key #%d rate-limited; rotating", idx)
                    self._advance_from(idx)
                else:
                    raise
        live = n - len(self._dead)
        raise RuntimeError(
            f"All LLM keys unavailable ({len(self._dead)} dead, {live} rate-limited). "
            f"Last error: {last_err}"
        )

    def complete(self, system: str, user: str) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        resp = self._run(
            lambda c: c.chat.completions.create(
                model=self._model, temperature=self._temperature, messages=messages
            )
        )
        return (resp.choices[0].message.content or "").strip()

    def chat(self, messages: list[dict], tools: list[dict] | None = None):
        """Tool-calling chat — returns the assistant message (may carry tool_calls)."""
        def call(client):
            kwargs: dict = {"model": self._model, "temperature": self._temperature, "messages": messages}
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            return client.chat.completions.create(**kwargs)

        return self._run(call).choices[0].message

    def stream_messages(self, messages: list[dict]):
        """Yield answer text deltas as they arrive (blocking generator).

        Rotation happens at stream-open / first-chunk so an exhausted key is
        skipped before any tokens are emitted. A failure AFTER the first chunk
        propagates as an exception (rare; the caller surfaces it as an error event).
        """
        from openai import APIStatusError, AuthenticationError, RateLimitError

        last_err: Exception | None = None
        n = len(self._keys)
        for _ in range(n):
            with self._lock:
                idx = self._idx
            if idx in self._dead:
                self._advance_from(idx)
                continue
            try:
                client = self._client_for(self._keys[idx])
                stream = client.chat.completions.create(
                    model=self._model,
                    temperature=self._temperature,
                    messages=messages,
                    stream=True,
                )
                iterator = iter(stream)
                try:
                    first = next(iterator)  # forces the request; surfaces 401/403/429 here
                except StopIteration:
                    return

                def _emit(chunk):
                    if chunk.choices:
                        return chunk.choices[0].delta.content
                    return None

                delta = _emit(first)
                if delta:
                    yield delta
                for chunk in iterator:
                    delta = _emit(chunk)
                    if delta:
                        yield delta
                return
            except AuthenticationError as exc:
                last_err = exc
                logger.warning("LLM key #%d invalid (auth) — marking dead", idx)
                self._mark_dead(idx)
                self._advance_from(idx)
            except (RateLimitError, APIStatusError) as exc:
                status = getattr(exc, "status_code", None)
                if status in (401, 403):
                    last_err = exc
                    logger.warning("LLM key #%d auth error %s — marking dead", idx, status)
                    self._mark_dead(idx)
                    self._advance_from(idx)
                elif isinstance(exc, RateLimitError) or status == 429:
                    last_err = exc
                    logger.warning("LLM key #%d rate-limited; rotating", idx)
                    self._advance_from(idx)
                else:
                    raise
        live = n - len(self._dead)
        raise RuntimeError(
            f"All LLM keys unavailable ({len(self._dead)} dead, {live} rate-limited). "
            f"Last error: {last_err}"
        )


# Process-wide singleton so the rotation index persists across requests.
_PROVIDER: RotatingProvider | None = None
_PROVIDER_LOCK = threading.Lock()


def get_llm(settings: Settings) -> LLMProvider:
    global _PROVIDER
    if _PROVIDER is None:
        with _PROVIDER_LOCK:
            if _PROVIDER is None:
                _PROVIDER = RotatingProvider(settings)
    return _PROVIDER


def make_provider(settings: Settings, model: str | None = None) -> LLMProvider:
    """Build a fresh provider (not the singleton) with an optional model override.

    Used for the faithfulness judge so it can run on a different model than the
    generator — judging with the same model that wrote the answer biases the score.
    """
    return RotatingProvider(settings, model=model)
