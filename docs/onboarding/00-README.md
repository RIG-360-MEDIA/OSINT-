# 00 - Onboarding README

> **If you're a new Claude session working on RIG Surveillance, read
> these docs in numerical order. After 5-10 minutes you'll have full
> context on the architecture, current state, known issues, and
> operational procedures — enough to start contributing without
> burning hours on rediscovery.**
>
> **Last meaningful refresh: 2026-05-28.** All 12 docs updated
> together with the 26 D-task fixes shipped this session. If you
> notice anything stale, fix it — this folder is the canonical
> memory.

---

## What RIG Surveillance is

RIG Surveillance is a multi-pillar intelligence aggregator targeted
at government, PR, and MNC analysts in India. Backend is a FastAPI
service plus 6 background Celery workers running inside a single
Docker container; frontend is a Next.js 15 client. The system
scrapes ~550 active RSS sources, ~80+ HTML sources, YouTube
transcripts, newspaper editions, Reddit / Telegram / Twitter, and
government PDFs; runs every article through an LLM extraction
substrate (**Prompt G + D1 SPO fix**) on a 4-provider pool (Ollama
local + optional llama.cpp + Groq + Cerebras); scores per-user
relevance; and generates a daily brief plus answers analyst queries
via RAG.

Production lives on a single Hetzner box (`178.105.63.154`) behind a
dockerised Caddy reverse proxy. A second machine, **TRIJYA-7**
(**Windows 11**, RTX 4090, local Tailscale at `100.92.126.27`), runs
Ollama as the primary LLM provider.

---

## Read in this order

| # | File | What you'll learn |
|---|---|---|
| 00 | [00-README.md](00-README.md) | This file. Entry point + reading order. |
| 01 | [01-architecture.md](01-architecture.md) | System overview — 8 pillars, container topology, Celery queues, Tailscale routing. |
| 02 | [02-substrate-pipeline.md](02-substrate-pipeline.md) | The v3 LLM extraction — Prompt G + **D1 SPO fix** (99% triple completeness), 6 child tables, drain mechanics, atomic claim. |
| 03 | [03-relevance-system.md](03-relevance-system.md) | How per-user article scoring works today + the v3 redesign plan. |
| 04 | [04-scrapers.md](04-scrapers.md) | Ingestion — 4-tier fetch cascade (Playwright DISABLED), Trafilatura, 53 adapters, source health + UA rotation. |
| 05 | [05-llm-infrastructure.md](05-llm-infrastructure.md) | The unified LLM pool — 27 Cerebras keys (zai-glm-4.7 with reasoning_effort=none), 21 Groq keys, 8 Ollama slots, failover, watchdog. |
| 06 | [06-operations-runbook.md](06-operations-runbook.md) | How to do common ops tasks — check drain, restart, probe quotas, read logs, pause/resume. |
| 07 | [07-known-issues.md](07-known-issues.md) | Current frustrations — 🟢 resolved, 🟡 mitigated, 🔴 open. |
| 08 | [08-future-plans.md](08-future-plans.md) | Strategic roadmap — relevance v3, frontend redesign, monitoring layer. |
| 09 | [09-todos-prioritized.md](09-todos-prioritized.md) | Concrete backlog — P0 (now) through P3 (someday). |
| 10 | [10-context-from-may-2026-session.md](10-context-from-may-2026-session.md) | Critical learnings from the early-May debugging session. |
| **11** | **[11-session-2026-05-28-learnings.md](11-session-2026-05-28-learnings.md)** | **Full lessons from D1-D26 today.** Cerebras qwen deprecation, zai-glm reasoning trap, Ollama NUM_PARALLEL reality, llama.cpp ctx-per-slot trap, LMStudio attempt-then-revert, pool rotation bias, Trijya-is-Windows discovery, 5 migrations shipped, 30K articles processed. |
| | [REQUIREMENTS.md](REQUIREMENTS.md) | Documentation discipline — what to write when finishing a feature. |

---

## Cross-cutting source-of-truth files

When in doubt these are authoritative (live in the repo, not in
onboarding):

- `CLAUDE.md` (repo root) — top-level project rules. Read after this dir.
- `docs/mistakes.md` — chronological incident log
- `docs/qa/` — defect registers + per-source verdicts from the QA pass
- `docs/PAUSE_INGEST_RUNBOOK.md` — SIGSTOP / SIGCONT collectors procedure
- `docs/PHASE1_20_COUNTRIES.md` — source-expansion plan (P1)
- `docs/BEST_SOURCES_GLOBAL.md` — 3,263 LIVE sources analysis (Excel)
- `docs/DATA_QUALITY_AUDIT_2026-05-28.md` — per-field health report
- `docs/PROJECT_DOCS_INDEX.md` — full inventory of all .md docs in repo
- `infrastructure/docker-compose.yml` — what containers actually run
- `backend/celery_app.py` (lines 60-260) — task routing + beat schedule
- `backend/start.sh` — how 6 Celery workers + uvicorn + Beat are
  launched inside `rig-backend`
- `backend/tasks/substrate/run_corpus_pass.py` — v3 extraction driver.
  Search for `GROQ_SYS` for the live prompt
- `backend/nlp/groq_client.py` — the unified LLM pool. 4 provider
  types (local Ollama + lmstudio + Groq + Cerebras)
- `scripts/migrations/*.sql` — numbered, idempotent. Current latest:
  **075** (source country + article.source_country trigger, 2026-05-28)
- `scripts/deploy/trijya_ollama_tune.ps1` — Windows PowerShell admin
  script for Trijya Ollama env-var setup

---

## TL;DR for a new session

- The deployment is **not** a typical multi-worker compose setup. All
  6 workers + Beat + FastAPI run inside one `rig-backend` container
  via `/start.sh`. Anyone reading the compose file in isolation will
  conclude "no workers" and be wrong. See `01-architecture.md`.

- The current extraction prompt is **Prompt G + D1 SPO addendum**.
  D1 (shipped 2026-05-27) compressed 4 worked examples into 1 with
  explicit SPO schema → predicate/object fill rate **14% → 99%**. See
  `02-substrate-pipeline.md`.

- The LLM pool has **four provider types**: 8 Ollama slots (local),
  optional 8 lmstudio/llama.cpp slots, 21 Groq keys (qwen/qwen3-32b,
  6K TPM per ORG not per key), 27 Cerebras keys (zai-glm-4.7 with
  `reasoning_effort:"none"`). Routing controlled by `LOCAL_LLM_*` env
  vars + `LMSTUDIO_BASE_URL`. See `05-llm-infrastructure.md`.

- **Cerebras retired the `qwen-3-235b-a22b-instruct-2507` tag on
  2026-05-27.** Don't use dated Cerebras tags. Probe `GET /v1/models`
  for currently-available identifiers.

- **TRIJYA-7 is Windows 11**, not Linux. All admin scripts use
  PowerShell. SSH password is in `Connection_Guide.pdf` but **AI
  must not use it directly** (security policy). Give the user a PS
  script to paste in their already-open admin terminal.

- **Trafilatura's 4090 ceiling is ~25-30 substrate calls/min** for
  qwen3:14b at our prompt size. Cannot exceed regardless of which
  local server (Ollama, llama.cpp, LMStudio). NUM_PARALLEL helps
  utilization but doesn't multiply throughput.

- A drain watchdog at `/tmp/drain_watchdog.sh` on Hetzner flips
  between `MIXED` and `LOCAL_ONLY` modes based on Cerebras quota.
  Lives in `/tmp/`, NOT version-controlled — P1 todo to promote into
  the repo.

- **~30-50% of "disabled" sources are actually alive** — bulk-
  disabled by uncommitted manual SQL on 2026-04-25. 174 of 406
  re-enabled after live probe; ~232 remain to investigate. See
  `04-scrapers.md` and `09-todos-prioritized.md`.

- **Playwright DISABLED** via `PLAYWRIGHT_ENABLED=false` since
  2026-05-27 due to memory leak (5+ GB Chromium accumulated over 8h).
  Don't re-enable without OOM fix.

- **The user wants the frontend redesigned from scratch** in an
  intelligence-publication style ("Particle"-inspired, 5 editions per
  day). This is a P2 future-plan. See `08-future-plans.md`.

---

## Today's status (2026-05-28 03:30 UTC)

- ~30,000 articles processed v3 today, 0.28% failure rate
- ~52,500 articles still `substrate_status='pending'` (D1 drain in
  progress)
- 5 migrations shipped today: 070, 072, 073, 074, 075
- 26 D-task fixes shipped (D1-D26). See task list in active session
  or `11-session-2026-05-28-learnings.md` for the narrative.
- Drain rate: ~30-50/min (Cerebras free-tier TPD exhausted, recovers
  at 00:05 UTC daily reset)
- Collectors workers SIGSTOPed (paused) for the drain duration. See
  `docs/PAUSE_INGEST_RUNBOOK.md` for resume procedure.

---

## Don't break

Four operational invariants. Confirm against the live system before
touching:

1. **The drain process and its watchdog** on Hetzner. If they're
   running, leave them alone unless explicitly asked to intervene.
2. **The Ollama service on TRIJYA-7** (now with NUM_PARALLEL=8 +
   flash_attn + q8_0 KV cache per D21). It has cold-start latency;
   restarting kills any in-flight drain calls.
3. **The FreshRSS admin user.** It was deleted by an unidentified
   cause on 2026-05-15 and recreating it costs ~574 feed
   resubscriptions. See `07-known-issues.md` E1.
4. **`PLAYWRIGHT_ENABLED=false`** — three guard checks in
   `playwright_helper.py` will reject any call. Don't re-enable
   without first fixing the Chromium memory leak.

When you're done reading the rest of this folder, pop back to
`CLAUDE.md` at the repo root for the higher-level project rules.
Then check the active session's task list (D27+ if numbering
continues) for what's currently in flight.
