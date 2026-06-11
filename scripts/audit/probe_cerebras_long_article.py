"""Reproduce production Cerebras failures: long real article + production params."""
from __future__ import annotations
import asyncio
import json
import sys

sys.path.insert(0, "/app")
import httpx  # noqa: E402

from backend.nlp.groq_client import _CEREBRAS_KEYS  # noqa: E402
from backend.tasks.substrate.run_corpus_pass import (  # noqa: E402
    GROQ_SYS,
    MAX_TOKENS_ENGLISH,
    MAX_BODY_FOR_GROQ_ENGLISH,
)


async def probe_one(max_tok: int, body: str) -> None:
    msgs = [
        {"role": "system", "content": GROQ_SYS},
        {
            "role": "user",
            "content": (
                f"TITLE: test\n\n"
                f"BODY:\n{body[:MAX_BODY_FOR_GROQ_ENGLISH]}\n\n"
                f"Return ONLY the JSON object."
            ),
        },
    ]
    payload = {
        "model": "zai-glm-4.7",
        "messages": msgs,
        "max_tokens": max_tok,
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }
    async with httpx.AsyncClient(timeout=40) as c:
        r = await c.post(
            "https://api.cerebras.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {_CEREBRAS_KEYS[0]}"},
            json=payload,
        )
    if r.status_code != 200:
        print(f"max={max_tok} STATUS={r.status_code} body={r.text[:200]}")
        return

    data = r.json()
    msg = data["choices"][0]["message"]
    print(f"   msg KEYS: {list(msg.keys())}")
    content = msg.get("content", "")
    reasoning = msg.get("reasoning_content") or msg.get("reasoning") or msg.get("thinking")
    if reasoning:
        print(f"   reasoning_len={len(reasoning)}  reasoning[:120]={reasoning[:120]!r}")
    finish = data["choices"][0].get("finish_reason")
    u = data.get("usage", {})
    in_tok = u.get("prompt_tokens")
    out_tok = u.get("completion_tokens")
    total_tok = u.get("total_tokens")
    is_empty = content == ""
    try:
        json.loads(content)
        parse = "OK"
    except Exception as e:  # noqa: BLE001
        parse = f"FAIL ({str(e)[:50]})"
    print(
        f"max={max_tok:>5d}  in_tok={in_tok}  out_tok={out_tok}  total={total_tok}  "
        f"finish={finish}  content_len={len(content)}  empty={is_empty}  parse={parse}"
    )


async def probe_with_extras(label: str, max_tok: int, body: str, extras: dict) -> None:
    msgs = [
        {"role": "system", "content": GROQ_SYS},
        {"role": "user", "content": f"TITLE: test\n\nBODY:\n{body[:MAX_BODY_FOR_GROQ_ENGLISH]}\n\nReturn ONLY the JSON object."},
    ]
    payload = {
        "model": "zai-glm-4.7",
        "messages": msgs,
        "max_tokens": max_tok,
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
        **extras,
    }
    async with httpx.AsyncClient(timeout=40) as c:
        r = await c.post("https://api.cerebras.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {_CEREBRAS_KEYS[0]}"}, json=payload)
    if r.status_code != 200:
        print(f"  {label:35s} STATUS={r.status_code} body={r.text[:150]}")
        return
    data = r.json()
    msg = data["choices"][0]["message"]
    content = msg.get("content", "")
    reasoning = msg.get("reasoning") or ""
    u = data.get("usage", {})
    try:
        json.loads(content); parse = "OK"
    except Exception:
        parse = "FAIL"
    print(f"  {label:35s} reason_len={len(reasoning):>5d}  content_len={len(content):>5d}  out_tok={u.get('completion_tokens')}  parse={parse}")


async def main() -> None:
    body = open("/tmp/longbody.txt").read()
    print(f"body_chars_raw={len(body)} truncated={len(body[:MAX_BODY_FOR_GROQ_ENGLISH])}")
    print()

    print("=== Try to DISABLE reasoning via various params ===")
    candidates = [
        ("baseline (no extras)", {}),
        ("reasoning_effort=none", {"reasoning_effort": "none"}),
        ("reasoning_effort=low",  {"reasoning_effort": "low"}),
        ("enable_thinking=false (top)", {"enable_thinking": False}),
        ("chat_template_kwargs", {"chat_template_kwargs": {"enable_thinking": False}}),
        ("thinking=false", {"thinking": False}),
        ("reasoning=false", {"reasoning": False}),
    ]
    for label, extras in candidates:
        await probe_with_extras(label, 5000, body, extras)


if __name__ == "__main__":
    asyncio.run(main())
