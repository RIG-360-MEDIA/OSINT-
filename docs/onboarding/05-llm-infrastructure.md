# 05 - LLM Infrastructure

> **TL;DR.** A unified LLM pool in `backend/nlp/groq_client.py`
> manages **three providers**: 24 Groq keys (restrictive per-minute
> quota), 27 Cerebras keys (generous 1M TPD each), and 1 Ollama slot
> on TRIJYA-7 (unlimited but slower). Routing is gated by
> `LOCAL_LLM_*` env vars. A 32-line watchdog on Hetzner
> (`/tmp/drain_watchdog.sh`) monitors Cerebras consumption and flips
> the drain between MIXED and LOCAL_ONLY modes; it also restarts the
> drain if its process dies.

## The three providers

| Provider     | Keys | Model                             | Quota                                    | Speed       | Cost   |
|--------------|------|-----------------------------------|------------------------------------------|-------------|--------|
| **Cerebras** | 27   | `llama-3.3-70b`                   | 1M TPD per key (27M/day total). RPM/TPM also enforced. | Very fast   | Free tier |
| **Groq**     | 24   | `llama-3.1-8b-instant` (fast), `llama-3.3-70b-versatile` (quality) | 6K TPM per key (restrictive). Resets per-minute. | Very fast   | Free tier |
| **Ollama**   | 1    | `qwen3:30b-a3b`                   | Unlimited (we own the GPU)               | Slow-ish (~10-30s per extraction call) | Sunk cost (RTX 4090) |

## Quota dynamics

- **Cerebras**: per-key 1M TPD. Resets at **00:00 UTC**. Aggregate
  daily budget = 27M tokens, which translates to ~10K extraction
  calls per day at typical token counts. The drain throughput
  controller does NOT track this — it only knows RPM/TPM — which is
  why a single 8-hour run can blow 99.5% of the budget. See
  known-issues #4.
- **Groq**: 6K TPM per key. Resets every minute. Aggregate = 144K
  TPM. Restrictive enough that bursting any single key triggers
  immediate cooldown. Pool rotation handles this transparently.
- **Ollama**: no quota, but capped by `OLLAMA_NUM_PARALLEL=1` (one
  inflight call at a time). Throughput is the bottleneck. With
  qwen3:30b-a3b on RTX 4090, expect ~1.5-3 extractions / minute.

## The unified pool — `backend/nlp/groq_client.py`

Single module-level singleton (`groq_manager`) shared across all
callers in the same Celery process. Key responsibilities:

1. **Round-robin key rotation** across Groq + Cerebras.
2. **Cooldown tracking** per key. On 429, stamp the key with a
   cooldown timestamp; round-robin skips cooled keys until reset.
3. **Provider failover.** If `LOCAL_LLM_PRIMARY=1`, try Ollama
   first; fall through to Cerebras → Groq on Ollama errors. If
   `LLM_LOCAL_ONLY=1`, return ONLY the Ollama slot (cloud is
   disabled entirely for that call site).
4. **Cloudflare-WAF dodge.** The Groq SDK's default httpx UA
   triggers `error code: 1010` (403). The pool overrides with a
   real browser UA. Without this every Groq call 403s.

### Custom exceptions

- `GroqQuotaExhausted` — all keys have hit their rate limits.
  Pipeline should pause and retry after reset.
- `GroqCallFailed` — non-quota failure (network, auth, malformed
  request).
- `OllamaCallFailed` — Ollama HTTP failure or malformed body.

### Env-var contract

| Env var                    | Default | Effect                                                                                  |
|----------------------------|---------|------------------------------------------------------------------------------------------|
| `LOCAL_LLM_ENABLED`        | `1`     | If `0`, Ollama lane removed entirely. Pool is cloud-only.                                |
| `LOCAL_LLM_PRIMARY`        | `0`     | If `1`, Ollama tried first; cloud is fallback.                                            |
| `LOCAL_LLM_MAX_CONCURRENT` | `1`     | Inflight Ollama call cap. Must match `OLLAMA_NUM_PARALLEL`.                              |
| `LLM_LOCAL_ONLY`           | `0`     | If `1`, returns ONLY Ollama. Used by the drain when cloud quota is exhausted.            |
| `OLLAMA_HOST`              | (set in compose) | `http://100.92.126.27:11434` — TRIJYA-7's Tailscale IP.                          |

> **Known inconsistency.** The `LOCAL_LLM_PRIMARY` flag is wired
> only at the unified-pool entry point. `semantic_repass.py` and
> potentially other substrate paths construct provider lists
> manually and bypass the flag. `LLM_LOCAL_ONLY=1` works correctly
> because it gates at the layer all those paths eventually reach.
> See known-issues #6 and `02-substrate-pipeline.md`.

## Ollama on TRIJYA-7

### Daemon setup

- **Scheduled task**: `OllamaServe` (Windows Task Scheduler). Runs
  under the S4U principal so it survives user-logoff. Created by
  `install_ollama_task.ps1` at repo root.
- **Detached launcher**: `launch_ollama_detached.ps1` — used when
  manually relaunching.
- **Env**: `OLLAMA_CONTEXT_LENGTH=8192`, `OLLAMA_NUM_PARALLEL=1`.
- **Model**: `qwen3:30b-a3b` (Mixture-of-Experts, 3B active params
  out of 30B). FP8 variant pulled by `pull_fp8.sh`.
- **Endpoint**: `http://100.92.126.27:11434/api/chat` (native, NOT
  `/v1/chat/completions` — see substrate doc for why).

### Body shape

```json
{
  "model": "qwen3:30b-a3b",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "stream": false,
  "think": false,
  "format": "json",
  "options": {
    "num_predict": 4000,
    "num_ctx": 8192,
    "temperature": 0.1
  }
}
```

The `think: false` field is critical. Without it qwen3 routes
reasoning tokens to a hidden field and the visible `content` is
empty. See mistakes.md #13.

### Install pitfall

The old Ollama install on TRIJYA-7 was 553MB and **missing CUDA
DLLs**, which caused it to silently fall back to CPU inference. The
re-install in May 2026 produced a 2GB installer (with CUDA support)
and actually uses the GPU. If you see Ollama "loaded but slow"
without GPU utilisation, suspect the wrong installer first. See
`10-context-from-may-2026-session.md`.

## The drain watchdog

A 32-line bash script lives at `/tmp/drain_watchdog.sh` on Hetzner
(currently PID 2136723 as of the May 2026 session). It does two
things in a tight loop:

1. **Auto-flips MIXED ↔ LOCAL_ONLY.** Calls
   `/tmp/probe_cerebras.py` to read remaining tokens across all 27
   Cerebras keys. If the aggregate falls below a threshold (~5%
   remaining), it `export LLM_LOCAL_ONLY=1` and signals the drain
   process to reload env, forcing all calls onto Ollama. When the
   daily Cerebras reset happens (00:00 UTC), the watchdog unsets
   `LLM_LOCAL_ONLY` and the drain returns to MIXED mode.
2. **Restarts the drain if it dies.** Polls the drain PID; if dead,
   relaunches with the current mode.

Log: `/tmp/drain_watchdog.log` on Hetzner.

Sibling probe scripts (on Hetzner only, not committed):
- `/tmp/probe_cerebras.py` — queries each Cerebras key for
  remaining TPD.
- `/tmp/probe_groq.py` — same for Groq (per-minute reset, less
  useful for budgeting).

A copy of the watchdog logic should eventually be promoted into
the repo at `backend/ops/drain_watchdog.sh` and the probe scripts
into `backend/ops/`. P1 todo.

## Cooldown logic in detail

Inside `GroqKeyManager`:

- Each key has `next_available_at` (a `datetime`).
- On HTTP 429, parse the response for the suggested retry time
  (Groq returns `Retry-After`; Cerebras embeds reset hints in the
  error message). Set `next_available_at = now + suggested`.
- `get_next_key()` rotates and skips any key with
  `next_available_at > now`.
- If every key is cooled, raise `GroqQuotaExhausted`.
- Beat-scheduled task at 00:05 UTC resets every key's
  `next_available_at = now` (in case a stale cooldown is hanging).

## Three failover paths in practice

### 1. Normal MIXED mode

```
call → pool → LOCAL_LLM_PRIMARY check → tries Ollama
       ↓ on failure or absent → Cerebras (round-robin)
       ↓ on quota exhausted   → Groq (round-robin)
       ↓ on all keys cooled    → GroqQuotaExhausted
```

### 2. LOCAL_ONLY (watchdog-triggered)

```
call → pool → LLM_LOCAL_ONLY check → tries Ollama
       ↓ on failure            → retry Ollama N times
       ↓ on all retries failed → OllamaCallFailed (no cloud fallback)
```

### 3. CLOUD_ONLY (LOCAL_LLM_ENABLED=0)

Used in CI / tests where TRIJYA-7 isn't reachable. Same as MIXED
but Ollama lane is absent.

## Groq Cerebras failover — when do they switch?

Two separate triggers (independent of `LOCAL_LLM_PRIMARY`):

- A single Groq call rate-limits → that key cools → pool rotates
  to next Groq key. No cross-provider switch.
- All Groq keys cool → pool falls over to Cerebras for the next
  call. Same logic on the Cerebras side.

Commit `a819fa7` (recent) added "Cerebras failover when Groq pool
is rate-limited" — that's the formal wiring of the cross-provider
fallback.

## Common foot-guns

1. **Skipping the unified pool.** Manual provider list construction
   in `semantic_repass.py` bypasses `LOCAL_LLM_PRIMARY`. Always
   route through `groq_manager` unless you have a strong reason.
2. **OpenAI-compat shim with qwen3.** Returns `content=""` because
   reasoning tokens go to a hidden field. Use native `/api/chat`
   with `think: false`. See mistakes.md #13.
3. **TPD blindness.** RPM/TPM throttling does not protect you from
   blowing the daily budget in a few hours. The watchdog is the
   only TPD protection today. Don't disable it without a
   replacement.
4. **Restarting Ollama mid-drain.** Kills any in-flight calls. The
   drain will retry but lose ~1 minute of throughput per restart.
   Prefer letting it drain quiescent.
5. **Trusting `LOCAL_LLM_PRIMARY=1` to do what it says.** It does,
   but only at the pool entry-point. Some code paths bypass it.
   `LLM_LOCAL_ONLY=1` is the reliable hammer.

## See also

- `02-substrate-pipeline.md` — Prompt G; how the substrate
  consumes the pool.
- `06-operations-runbook.md` — "How to check quota", "How to read
  watchdog log", "How to spot a stalled drain".
- `07-known-issues.md` — Cerebras burn, semantic_repass env-var
  inconsistency.
- `10-context-from-may-2026-session.md` — Ollama install
  diagnostic and recovery story.
