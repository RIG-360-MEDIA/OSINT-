"""Cloud-direct LLM fallback for substrate drains.

The shared local-first unified pool (`groq_client`) prefers local TabbyAPI slots
and, when the local tunnel is down, raises ConnectError instead of falling back
to cloud — which stalls any drain that depends on it. Drains that must not stall
(newspapers, youtube clips) use this as a *fallback*: try the cheap local pool
first, and only when it fails call the cloud providers directly with key
rotation across a small chain of known-good models.

Every failure is swallowed → None so the caller NEVER crashes; it marks the row
extract_failed (retryable).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"

# Ordered (provider, model) chain. llama-3.3-70b-versatile is the most reliable
# strict-JSON model on Groq; gpt-oss-120b (Groq then Cerebras) backs it up.
# Model ids VERIFIED live against each provider's /models endpoint 2026-07-01.
_CHAIN = [
    ("groq", "llama-3.3-70b-versatile"),
    ("groq", "openai/gpt-oss-120b"),
    ("cerebras", "gpt-oss-120b"),
    ("cerebras", "zai-glm-4.7"),
]

# Status codes that mean "this KEY is bad/exhausted" → rotate to next key.
_KEY_ROTATE = {401, 403, 429}
# Status codes that mean "this MODEL/request is bad" → skip to next model.
_MODEL_SKIP = {400, 404, 422}


def _keys(provider: str) -> list[str]:
    import os

    env = "GROQ_API_KEYS" if provider == "groq" else "CEREBRAS_API_KEYS"
    return [k.strip() for k in os.getenv(env, "").split(",") if k.strip()]


async def cloud_call(sys_prompt: str, user_msg: str, max_tokens: int) -> str | None:
    """Direct cloud chat-completion. Returns content str or None. Never raises.

    Walks the model chain; within each model rotates keys on auth/rate errors and
    skips to the next model on request/model errors.
    """
    import httpx

    def _url(provider: str) -> str:
        return _GROQ_URL if provider == "groq" else _CEREBRAS_URL

    def _body(model: str) -> dict:
        return {
            "model": model,
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg},
            ],
        }

    async with httpx.AsyncClient(timeout=60) as client:
        for provider, model in _CHAIN:
            keys = _keys(provider)
            if not keys:
                continue
            body = _body(model)
            url = _url(provider)
            skip_model = False
            for key in keys:
                if skip_model:
                    break
                try:
                    r = await client.post(
                        url,
                        json=body,
                        headers={
                            "Authorization": "Bearer %s" % key,
                            "User-Agent": "rig-substrate/1.0",
                        },
                    )
                    if r.status_code in _KEY_ROTATE:
                        continue  # bad/exhausted key → next key
                    if r.status_code in _MODEL_SKIP:
                        skip_model = True  # model/request bad → next model
                        continue
                    r.raise_for_status()
                    return r.json()["choices"][0]["message"]["content"]
                except Exception:  # noqa: BLE001 — transport/5xx → try next key
                    continue
    return None
