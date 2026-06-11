# 05 - LLM Infrastructure

> **TL;DR.** A unified LLM pool in `backend/nlp/groq_client.py` manages
> **four provider types**: 8 local Ollama slots, 8 (optional) llama.cpp/
> LM-Studio slots, 21 Groq keys, 27 Cerebras keys. Each substrate call
> rotates through the slot list; failed slots cool down, rest of pool
> takes over. Trijya-7 (Windows 11 + RTX 4090) hosts the local LLMs.
> A drain watchdog auto-flips MIXED ↔ LOCAL_ONLY based on Cerebras
> token-per-day burn. **The 4090 is the hard speed ceiling
> (~25-30 calls/min for qwen3:14b at substrate prompt size); no amount
> of cloud provider tuning exceeds that for sustained local load.**

---

## The four provider types (as of 2026-05-28)

| Provider     | Slots in pool | Model in use                                       | Daily quota                                  | Speed              | Notes |
|--------------|--------------|----------------------------------------------------|----------------------------------------------|--------------------|-------|
| **Local — Ollama** | 8 (configurable via `OLLAMA_CLIENT_SLOTS`) | `qwen3:14b` (Q4_K_M, 10.7 GB VRAM)          | Unlimited                                    | ~15-20s per call (~25-30 calls/min ceiling) | Primary lane. No quota anxiety. |
| **Local — llama.cpp / LM Studio** | 0 by default (8 if `LMSTUDIO_BASE_URL` env set) | Same GGUF blob as Ollama (sha256-a8cc1361...)  | Unlimited                                    | Same speed as Ollama (shared GPU) | Available as backup local lane. Reverted after testing — no aggregate speedup, shares 4090 with Ollama. |
| **Groq**     | 21 keys     | `qwen/qwen3-32b` (substrate), `llama-3.3-70b-versatile` (relevance) | 6,000 **TPM per org** (NOT per key). ~5-7 distinct orgs across our 21 keys. | Very fast (~1-2s)  | Restrictive. Burst quickly hits per-org TPM 429s. Cooldown=15s. |
| **Cerebras** | 27 keys     | `zai-glm-4.7` (substrate, with `reasoning_effort:"none"`) | 1M TPD per key (~27M aggregate); also TPM/RPM | Very fast (~1-2s)  | Big daily budget but heavy substrate runs exhaust in 5-6 hours. Daily reset 00:05 UTC. |

---

## Critical knowledge — read before touching the pool

### 1. `reasoning_effort: "none"` is MANDATORY for zai-glm-4.7

zai-glm-4.7 is a chain-of-thought reasoning model. Without that flag,
every call burns ~3,000 tokens on hidden `reasoning_content` BEFORE
emitting any actual JSON. At our max_tokens=3000, the `content` field
is **empty** (no 'content' key at all in the response). With the flag,
output drops from ~3,800 tokens to ~800 — **5× faster, 0% truncation,
0% empty content**. Wired in `_call_one` (both code paths) under
`if cerebras_model.startswith("zai-glm")`.

**Other Cerebras reasoning models will likely need this same flag.**
Tested negative params (all return 400):
`enable_thinking`, `thinking`, `reasoning`,
`chat_template_kwargs.enable_thinking`. Only `reasoning_effort` is
OpenAI-standard and accepted.

### 2. Cerebras dated model tags get retired without warning

On 2026-05-27 Cerebras retired `qwen-3-235b-a22b-instruct-2507`. All
27 of our keys started returning `404 model_not_found` on that tag.
Never use a dated tag for production — use the un-dated or current
preferred name. Probe `GET https://api.cerebras.ai/v1/models` to see
what's currently available on the free tier.

### 3. The Groq TPM is PER-ORG, not per-key

Multiple Groq keys can share the same org. Hitting one key's TPM
cools that key, but the org's other keys also start 429-ing. Our 21
keys span ~5-7 distinct orgs (visible as `org_*` IDs in 429 response
bodies). Aggregate Groq TPM ceiling ≈ 36-42K/min — **NOT** 126K (21 ×
6K) as naive math would suggest.

### 4. Daily TPD exhaustion is real and undetected

The unified pool only tracks per-minute cooldowns. It does NOT know
when a key has burned through its daily TPD. After Cerebras quota
exhausts (~5h into a heavy drain), the pool keeps trying exhausted
keys; each call wastes a round-trip + propagates wasted cooldown
state. **Workaround today:** watchdog flips drain to LOCAL_ONLY when
aggregate Cerebras remaining drops below 5%. **Permanent fix
(pending):** add TPD-aware probe and disable exhausted keys for the
day.

### 5. The 4090 is the binding constraint, not provider count

qwen3:14b on a 4090 at our substrate prompt size (~3K input + ~1K
output tokens) generates at ~30-50 tokens/sec → ~15-20s per call →
~25-30 calls/min ceiling regardless of which local server you use
(Ollama, llama.cpp, vLLM, LM Studio). Adding more local providers
doesn't multiply throughput — they all share the same GPU. Vertical
scaling = swap to smaller model (qwen3:7b ~2× faster) or upgrade GPU.

---

## The unified pool — `backend/nlp/groq_client.py`

Single module-level singleton (`_get_unified_pool()`) shared across all
callers in the same Python process. Key responsibilities:

1. **Slot composition** at process start, from env vars:
   - 8 `local` slots if `LOCAL_LLM_ENABLED=1` (default) — Ollama at `OLLAMA_BASE_URL`
   - 8 `lmstudio` slots if `LMSTUDIO_BASE_URL` set (off by default)
   - 21 `groq` slots, one per key in `GROQ_API_KEYS` env (skipped if `LLM_LOCAL_ONLY=1`)
   - 27 `cerebras` slots, one per key in `CEREBRAS_API_KEYS` env (skipped if `LLM_LOCAL_ONLY=1`)

2. **Round-robin rotation** with `SKIP LOCKED`-style cooldown skipping.
   Cooled slots are skipped for `_cooldown_seconds` (default 15s after
   D14, was 60s).

3. **Provider failover.** Cooldown → rotate to next slot. If LOCAL is
   primary and fails, fall through to Cerebras → Groq. If
   `LLM_LOCAL_ONLY=1`, return ONLY local (Ollama + lmstudio if
   configured); cloud lane is omitted from pool entirely.

4. **Per-provider request shape** in `_call_one`:
   - `local` → POST `/api/chat` with `think:false`, `format:"json"`,
     options.num_batch=2048, options.num_ctx=8192
   - `lmstudio` → POST `/v1/chat/completions` (OpenAI-compatible),
     with `chat_template_kwargs.enable_thinking:false` (qwen3 family)
   - `groq` → Groq SDK with `response_format={"type":"json_object"}`
   - `cerebras` → POST `/v1/chat/completions` with browser User-Agent
     (Cloudflare WAF dodge) and `reasoning_effort:"none"` for zai-glm

5. **Cloudflare-WAF dodge.** The Groq SDK's default httpx UA triggers
   `error code 1010` (403). The pool overrides with a real browser UA
   (`_BROWSER_UA`). Same applies to Cerebras direct httpx calls.

### Custom exceptions

- `GroqQuotaExhausted` — all keys hit rate limits. Pipeline pauses and
  retries after reset.
- `GroqCallFailed` — non-quota failure (network, auth, malformed).
- `_LocalCallFailed` — Ollama or LMStudio HTTP failure / malformed body.
- `_CerebrasRateLimited` — Cerebras-specific 429 sentinel.

### Env-var contract

| Env var                    | Default | Effect |
|----------------------------|---------|--------|
| `LOCAL_LLM_ENABLED`        | `1`     | If `0`, Ollama slots removed from pool entirely. |
| `LOCAL_LLM_PRIMARY`        | `1`     | If `1`, prefer local first; cloud is fallback. |
| `LOCAL_LLM_MAX_CONCURRENT` | `4`     | Inflight Ollama call cap. |
| `LLM_LOCAL_ONLY`           | `0`     | If `1`, returns ONLY local (Ollama + lmstudio if configured). Used by drain when cloud quota exhausted. |
| `OLLAMA_BASE_URL`          | `http://100.92.126.27:11434` | Trijya-7's Tailscale IP. |
| `OLLAMA_MODEL`             | `qwen3:30b-a3b` | Model to request. Use `qwen3:14b` for substrate (faster). |
| `OLLAMA_CLIENT_SLOTS`      | `8`     | Number of local slots in our pool. Should mirror Ollama's `NUM_PARALLEL`. |
| `OLLAMA_TIMEOUT_SECONDS`   | `300`   | Per-call timeout. |
| **`LMSTUDIO_BASE_URL`**    | `""`    | If set, adds 8 lmstudio slots to pool. Empty = disabled. |
| **`LMSTUDIO_MODEL`**       | `""`    | GGUF sha256 hash (llama.cpp) or model name (LM Studio). Required if BASE_URL set. |
| **`LMSTUDIO_CLIENT_SLOTS`** | `8`    | Number of lmstudio slots. |

---

## Ollama on TRIJYA-7 (Windows 11 + RTX 4090)

### CRITICAL: TRIJYA-7 is a Windows box

Discovered 2026-05-28 via Tailscale status (`tdsworks@ windows
active`). All deploy scripts use PowerShell + setx / Restart-Service,
NOT systemd/bash. Owned by Tailscale user `tdsworks@gmail.com`.
SSH access for `Admin@100.92.126.27` exists (password Red@0909, in
Connection_Guide.pdf). **AI must not use the password to SSH directly
— security policy. Instead: hand the user a PowerShell script to
paste.**

### Daemon setup

- Ollama runs as a Windows Service OR as a user-app (Start-Process
  "ollama" "serve"). The PowerShell admin script in
  `scripts/deploy/trijya_ollama_tune.ps1` detects which and handles
  both via `Get-Service` + `Restart-Service` fallback to `taskkill`.
- Env vars MUST be set at Machine scope (`setx /M`) and then Ollama
  restarted — running processes don't pick up new vars.

### Required env vars on Trijya (set via `trijya_ollama_tune.ps1`)

| Env var | Value | Why |
|---|---|---|
| `OLLAMA_NUM_PARALLEL` | `8` | Concurrent sequences per model. Default 1 = serial → very slow. |
| `OLLAMA_MAX_LOADED_MODELS` | `2` | Keep both qwen3:14b AND qwen3:30b-a3b warm. |
| `OLLAMA_FLASH_ATTENTION` | `1` | 30-50% KV-cache VRAM saving. Required for cache quantization. |
| `OLLAMA_KV_CACHE_TYPE` | `q8_0` | Half the cache memory vs f16. |
| `OLLAMA_KEEP_ALIVE` | `4h` | Default 5min unloads models between bursts. |
| `OLLAMA_HOST` | `0.0.0.0:11434` | Listen on Tailscale interface. |
| `OLLAMA_MAX_QUEUE` | `2048` | Larger queue for concurrent drain demand. |

### Per-request options we send

```json
{
  "model": "qwen3:14b",
  "messages": [...],
  "stream": false,
  "think": false,
  "format": "json",
  "options": {
    "num_predict": 3000,
    "num_batch": 2048,
    "num_ctx": 8192,
    "num_keep": 0,
    "temperature": 0.1
  }
}
```

`think:false` is critical — without it qwen3 returns empty `content`
field with reasoning tucked in a hidden key.

### Model choice

- **`qwen3:14b`** (dense, ~10.7 GB) — preferred for substrate. Faster
  per-call than the larger MoE.
- **`qwen3:30b-a3b`** (MoE, 3B active, ~18.5 GB) — higher capability
  ceiling, slower per-call. Default in `_OLLAMA_MODEL` for legacy
  compatibility.

### Reality check on NUM_PARALLEL

Setting `OLLAMA_NUM_PARALLEL=8` increases utilization but does NOT 8×
throughput on a single 4090. GPU compute is the binding constraint.
Observed sustained rate: ~25-30 calls/min for substrate prompts
regardless of NUM_PARALLEL=1, 4, or 8.

---

## llama.cpp / LM Studio — optional secondary local lane

llama.cpp's `llama-server.exe` provides an OpenAI-compatible endpoint
with native continuous batching. Wired in pool as provider="lmstudio".
**Currently DISABLED** (no `LMSTUDIO_BASE_URL` env set) because:

- Shares GPU with Ollama → no aggregate throughput gain
- Pool rotation gave LMStudio bias over Cerebras (slot order), hurting
  cloud utilization

If you want to re-enable: ensure GPU has headroom (stop Ollama or use
qwen3:7b for one of them), set `LMSTUDIO_BASE_URL=http://100.92.126.27:1234`
and `LMSTUDIO_MODEL=sha256-a8cc1361...` in the drain env. Code path is
tested and working.

llama.cpp gotchas:
- `--ctx-size` is DIVIDED across `--parallel` slots. `--ctx-size 32768
  --parallel 8` = 4K per slot. Substrate prompts (~5K) → 400 errors.
  Use `--ctx-size 131072` (16K per slot).
- `--flash-attn` is an enum since ≥b9000: must be `--flash-attn on`.
- The "llama-bin" zip != "cudart" zip. cudart contains only CUDA DLLs;
  llama-bin contains binaries + CUDA DLLs.

---

## Cooldown logic in detail

Inside `KeyManager` / `UnifiedPool`:

- Each slot has `_exhausted_until[slot_idx]` (unix timestamp).
- On HTTP 429, parse the response for retry-after hint (Groq returns
  `Retry-After`; Cerebras embeds reset hints in error body). Default
  cooldown=15s. Hard cap=300s.
- `_pick_next_slot()` rotates and skips any slot with
  `_exhausted_until > now`.
- If every slot in pool is cooled, raise `GroqQuotaExhausted`.
- Beat-scheduled task at 00:05 UTC resets every key's
  `_exhausted_until = 0` (handles spurious daily-quota lockouts).

---

## Three failover paths in practice

### 1. Normal MIXED mode (default)

```
call → pool → LOCAL_LLM_PRIMARY=1 → tries local (Ollama)
       ↓ on failure or all local cooled → Cerebras (rotating slots)
       ↓ on Cerebras 429 / quota → Groq (rotating slots)
       ↓ on all slots cooled    → GroqQuotaExhausted
```

### 2. LOCAL_ONLY (watchdog-triggered after Cerebras burn)

```
call → pool → LLM_LOCAL_ONLY=1 → tries Ollama slots only
       ↓ on failure → retry next local slot
       ↓ on all local cooled → _LocalCallFailed (NO cloud fallback)
```

### 3. CLOUD_ONLY (LOCAL_LLM_ENABLED=0)

Used in CI / tests where Trijya-7 isn't reachable. Same as MIXED but
local lane is absent.

---

## The `groq_semantic` retry loop (D15)

The substrate call in `backend/tasks/substrate/run_corpus_pass.py`
wraps the LLM call + JSON parse in a 2-attempt loop:

```python
for attempt in range(2):
    raw = await call_groq(...)
    try:
        parsed = json.loads(raw)
        break
    except (TypeError, ValueError):
        # Strip markdown fences, isolate outermost {...}, retry parse
        parsed = json.loads(cleaned)
        break
    except (TypeError, ValueError):
        if attempt == 0:
            continue  # retry — pool rotates slot, often succeeds
        return None   # 2nd parse fail → article skipped (rare)
```

**Net effect:** article-loss rate from 25% (D17 era) → ~2% today.

---

## Common foot-guns (post-session-2026-05-28)

1. **Skipping the unified pool.** Some legacy code constructs provider
   lists manually. Always route through `_get_unified_pool()`.
2. **Using OpenAI-compat shim with qwen3.** Returns `content=""`
   because reasoning tokens go to a hidden field. Use native `/api/chat`
   with `think:false`. See known-issues + session-2026-05-28 #2.
3. **TPD blindness.** RPM/TPM throttling does not protect against
   blowing daily budget. Watchdog is the only TPD protection today.
4. **Restarting Ollama mid-drain.** Kills any in-flight calls. Drain
   retries but loses ~1min throughput per restart. Quiesce first.
5. **Trusting `LOCAL_LLM_PRIMARY=1` to do what it says.** It does, but
   only at the pool entry-point. Some code paths bypass. `LLM_LOCAL_ONLY=1`
   is the reliable hammer.
6. **Adding new providers without GPU headroom.** Two local servers
   on same GPU = same compute ceiling. Doesn't multiply.
7. **Setting Ollama env vars but forgetting to restart.** `setx /M`
   doesn't propagate to running processes.
8. **Using SSH passwords on AI's behalf.** Security policy forbids;
   hand the user a script to paste in their own admin shell instead.

---

## See also

- `02-substrate-pipeline.md` — Prompt G, D1 SPO fix, how substrate
  consumes the pool.
- `06-operations-runbook.md` — Drain commands, watchdog config.
- `07-known-issues.md` — Cerebras burn, semantic_repass env-var
  inconsistency.
- `10-context-from-may-2026-session.md` — Ollama install diagnostic
  story (553MB CPU-only fiasco).
- **`11-session-2026-05-28-learnings.md`** — Full lessons from today
  (provider rotation bias, llama.cpp ctx-per-slot trap, etc.).
- `scripts/deploy/trijya_ollama_tune.ps1` — Windows PowerShell admin
  script for Trijya Ollama env-var setup.
