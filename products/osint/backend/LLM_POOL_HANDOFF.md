# OSINT LLM Pool — integration handoff (2026-05-30)

The multi-key Groq/Cerebras pool from rig-backend has been copied into this
service. Below is a **paste-able prompt** for the OSINT session, then the
reference details.

---

## ⮕ PASTE THIS INTO THE OSINT SESSION

> You are working in `products/osint/backend`. A unified multi-key LLM pool has
> been added: `groq_client.py` (ported verbatim from rig-backend, self-contained,
> 1580 lines) plus keys in `.env`. Wire the brief/LLM features to use it so that
> **every key is used automatically with rotation + provider failover** — do not
> hand-pick keys or add retry loops; the pool already handles 429s, exhaustion
> cooldown, and Groq→Cerebras failover.
>
> Tasks:
> 1. Add `groq==0.11.0` to the venv: `pip install -r requirements.txt`.
> 2. Ensure env is loaded **before** importing the pool (it builds its key
>    manager at import time and raises if `GROQ_API_KEYS` is empty):
>    ```python
>    from dotenv import load_dotenv; load_dotenv()
>    from groq_client import classify, generate, call_groq, groq_manager, FAST_MODEL, QUALITY_MODEL
>    ```
>    (Adjust to the package layout — file is at backend root; use
>    `from .groq_client import ...` if imported as a package.)
> 3. Sanity check on boot: `print(groq_manager.get_stats())` → expect
>    `total_keys` = 22 (Groq) and `available_keys` = 22.
> 4. Route brief generation through `await generate(system=..., user=...)` and
>    any fast labelling through `await classify(system=..., user=...)`. The pool
>    rotates across all keys per call.
> 5. Keep `LOCAL_LLM_ENABLED=0` (this box has no local GPU). Do not commit `.env`.
> 6. `CEREBRAS_API_KEYS` (27 keys) is already set — the pool spans 22 Groq + 27
>    Cerebras with automatic Groq→Cerebras failover. No further key setup needed.

---

## Reference

### What landed
| File | What |
|---|---|
| `groq_client.py` | The pool — `GroqKeyManager` (round-robin + exhaustion cooldown) + unified Groq/Cerebras pool + async call API. Only deps: `groq`, `httpx`, stdlib. |
| `.env` | `GROQ_API_KEYS` = **22 Groq keys** (from local `infrastructure/.env`) + `CEREBRAS_API_KEYS` = **27 Cerebras keys** (pulled from Hetzner `.env.prod`), `LOCAL_LLM_ENABLED=0`. **Pool = 49 slots.** |
| `requirements.txt` | added `groq==0.11.0`. |

### Public API (import from `groq_client`)
- `await classify(system, user) -> str` — fast one-shot label (FAST_MODEL = `qwen/qwen3-32b`).
- `await generate(system, user, ...) -> str` — quality generation (QUALITY_MODEL).
- `await translate(...)`, `await extract_json(...)`, `await call_groq(...)`.
- `groq_manager` — `.get_stats()`, key rotation/exhaustion state.
- Constants: `FAST_MODEL`, `QUALITY_MODEL`, `TOKEN_LIMITS`.

### How "use all of them" works (automatic)
You never select a key. Each call asks `groq_manager` for the next available
key; a key that returns 429/quota is benched and retried after a cooldown; when
Groq is saturated the unified pool fails over to Cerebras. Calling code stays a
one-liner — `await generate(...)`.

### Cerebras (27 keys) — ENABLED
`CEREBRAS_API_KEYS` (27 keys) was pulled from Hetzner `/root/rig/infrastructure/.env.prod`
into `.env` on 2026-05-30. The unified pool now spans **22 Groq + 27 Cerebras = 49 slots**
with automatic Groq→Cerebras failover. No further action needed.

### Guardrails
- `.env` is gitignored — only `.env.example` is committed. Never paste keys into source or chat.
- Free-tier keys: the manager handles rate limits; don't wrap your own retries.
- Keep `LOCAL_LLM_ENABLED=0` so the Ollama/local lane stays inert.
