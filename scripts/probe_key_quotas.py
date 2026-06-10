"""
Probe every Groq + Cerebras key with a minimal 1-token request and classify
each as: OK (budget left) / DAILY (TPD/RPD exhausted today) / MINUTE (TPM/RPM
only — not finished) / BADKEY / ERROR.

Costs ~1 output token per key. Run inside rig-backend where the env keys live:
    docker exec rig-backend python /app/scripts/probe_key_quotas.py
"""
from __future__ import annotations

import asyncio
import os

import httpx

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"
GROQ_MODEL = os.getenv("GROQ_PRIMARY_MODEL", "qwen/qwen3-32b")
CEREBRAS_MODEL = "zai-glm-4.7"

_BODY = {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}


def _keys(*names: str) -> list[str]:
    for n in names:
        raw = os.getenv(n, "")
        if raw.strip():
            return [k.strip() for k in raw.split(",") if k.strip()]
    return []


def _classify(status: int, body: str) -> str:
    low = body.lower()
    if status == 200:
        return "OK"
    if status == 401:
        return "BADKEY"
    if status == 429:
        if "tpd" in low or "rpd" in low or "per day" in low or "tokens per day" in low:
            return "DAILY-EXHAUSTED"
        if "tpm" in low or "rpm" in low or "per minute" in low:
            return "MINUTE-ONLY (not finished)"
        return "429-OTHER"
    return f"ERR-{status}"


async def _probe(client: httpx.AsyncClient, url: str, key: str, model: str) -> str:
    try:
        r = await client.post(
            url,
            headers={"Authorization": f"Bearer {key}"},
            json={**_BODY, "model": model},
            timeout=30,
        )
        return _classify(r.status_code, r.text)
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {type(exc).__name__}"


async def _run() -> None:
    groq = _keys("GROQ_API_KEYS", "GROQ_API_KEY")
    cere = _keys("CEREBRAS_API_KEYS", "CEREBRAS_API_KEY")
    print(f"Groq keys: {len(groq)}   Cerebras keys: {len(cere)}")
    print(f"Probing Groq model={GROQ_MODEL}  Cerebras model={CEREBRAS_MODEL}\n")

    async with httpx.AsyncClient() as client:
        groq_res = await asyncio.gather(
            *[_probe(client, GROQ_URL, k, GROQ_MODEL) for k in groq]
        )
        cere_res = await asyncio.gather(
            *[_probe(client, CEREBRAS_URL, k, CEREBRAS_MODEL) for k in cere]
        )

    def summarize(label: str, res: list[str]) -> None:
        print(f"=== {label} ({len(res)} keys) ===")
        for i, verdict in enumerate(res):
            print(f"  key[{i:>2}]: {verdict}")
        counts: dict[str, int] = {}
        for v in res:
            head = v.split(":")[0]
            counts[head] = counts.get(head, 0) + 1
        print(f"  TOTALS: {counts}\n")

    summarize("GROQ", list(groq_res))
    summarize("CEREBRAS", list(cere_res))


if __name__ == "__main__":
    asyncio.run(_run())
