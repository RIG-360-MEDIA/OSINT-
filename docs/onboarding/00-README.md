# 00 - Onboarding README

> **If you're a new Claude session working on RIG Surveillance, read these
> docs in numerical order. After 5-10 minutes you'll have full context on
> the architecture, current state, known issues, and operational
> procedures — enough to start contributing without burning hours on
> rediscovery.**

## What RIG Surveillance is

RIG Surveillance is a multi-pillar intelligence aggregator targeted at
government, PR, and MNC analysts in India. Backend is a FastAPI service
plus 6 background Celery workers running inside a single Docker
container; frontend is a Next.js 15 client. The system scrapes ~574 RSS
feeds, ~80+ HTML sources, YouTube transcripts, newspaper editions,
Reddit / Telegram / Twitter, and government PDFs; runs every article
through an LLM extraction substrate (Prompt G on Ollama
qwen3:30b-a3b + Groq + Cerebras failover); scores per-user relevance;
and generates a daily brief plus answers analyst queries via RAG.

Production lives on a single Hetzner box (`178.105.63.154`) behind a
dockerised Caddy reverse proxy. A second machine, **TRIJYA-7** (RTX
4090, local Tailscale), runs Ollama as the primary LLM provider.

## Read in this order

| #  | File                                                 | What you'll learn                                                                                  |
|----|------------------------------------------------------|----------------------------------------------------------------------------------------------------|
| 00 | [00-README.md](00-README.md)                         | This file. Entry point + reading order.                                                            |
| 01 | [01-architecture.md](01-architecture.md)             | System overview — 8 pillars, container topology, Celery queues, Tailscale routing.                 |
| 02 | [02-substrate-pipeline.md](02-substrate-pipeline.md) | The v3 LLM extraction pipeline — Prompt G, child tables, drain mechanics.                          |
| 03 | [03-relevance-system.md](03-relevance-system.md)     | How per-user article scoring works today + the v3 redesign plan.                                   |
| 04 | [04-scrapers.md](04-scrapers.md)                     | Ingestion — 4-tier fetch cascade, Trafilatura, 53 adapters, source health.                         |
| 05 | [05-llm-infrastructure.md](05-llm-infrastructure.md) | The unified LLM pool — 27 Cerebras keys, 24 Groq keys, 1 Ollama slot, failover, watchdog.          |
| 06 | [06-operations-runbook.md](06-operations-runbook.md) | How to do common ops tasks — check drain, restart, probe quotas, read logs.                        |
| 07 | [07-known-issues.md](07-known-issues.md)             | Current frustrations — symptoms, root causes, workarounds, proper fixes.                           |
| 08 | [08-future-plans.md](08-future-plans.md)             | Strategic roadmap — relevance v3, frontend redesign, monitoring layer.                             |
| 09 | [09-todos-prioritized.md](09-todos-prioritized.md)   | Concrete backlog — P0 (now) through P3 (someday).                                                  |
| 10 | [10-context-from-may-2026-session.md](10-context-from-may-2026-session.md) | Critical learnings from the most recent multi-day debugging session.       |

## Cross-cutting source-of-truth files

When in doubt these are authoritative (live in the repo, not in
onboarding):

- `CLAUDE.md` (repo root) — top-level project rules. Read after this dir.
- `docs/mistakes.md` — chronological incident log (~25 incidents, 911
  lines). Search this *before* re-debugging a problem.
- `docs/future-todo.md` — pending work items, kept in priority order.
- `docs/qa/` — defect registers + per-source verdicts from the QA pass.
- `infrastructure/docker-compose.yml` — what containers actually run.
- `backend/celery_app.py` (lines 60-260) — task routing + beat
  schedule.
- `backend/start.sh` — how the 6 Celery workers + uvicorn + Beat are
  launched inside the `rig-backend` container.
- `backend/tasks/substrate/run_corpus_pass.py` — the v3 extraction
  driver. Search for `GROQ_SYS` for the live Prompt G.
- `backend/nlp/groq_client.py` — the unified LLM pool. Cerebras + Groq
  + Ollama routing lives here.
- `scripts/migrations/*.sql` — numbered, idempotent, applied at first
  boot. The 060-073 range is the substrate v3 schema.

## TL;DR for a new session

- The deployment is **not** a typical multi-worker compose setup. All 6
  workers + Beat + FastAPI run inside one `rig-backend` container via
  `/start.sh`. Anyone reading the compose file in isolation will
  conclude "no workers" and be wrong. See `01-architecture.md`.
- The current extraction prompt is **Prompt G** (= prompt C base +
  "EVENT DATE RULE" addendum). It is the winner of a 7-variant eval
  done 2026-05-15/16. See `02-substrate-pipeline.md`.
- The LLM pool has **three lanes**: Cerebras (27 keys, 1M TPD each =
  27M/day, generous), Groq (24 keys, 6K TPM each, restrictive), and
  Ollama qwen3:30b-a3b on TRIJYA-7 (unlimited but slower). Routing is
  controlled by `LOCAL_LLM_*` env vars. See `05-llm-infrastructure.md`.
- A 32-line drain watchdog at `/tmp/drain_watchdog.sh` on Hetzner
  flips between `MIXED` and `LOCAL_ONLY` modes based on Cerebras
  quota, and restarts the drain process if it dies. See
  `05-llm-infrastructure.md` and `10-context-from-may-2026-session.md`.
- ~30-50% of "disabled" sources are actually alive — they were
  bulk-disabled by uncommitted manual SQL on 2026-04-25. 174 of 406
  have been re-enabled after live probe; ~232 remain to investigate.
  See `04-scrapers.md` and `09-todos-prioritized.md`.
- The user wants the **frontend redesigned from scratch** in an
  intelligence-publication style ("Particle"-inspired, 5 editions per
  day). This is a P2 future-plan, not in flight yet. See
  `08-future-plans.md`.

## Don't break

Three operational invariants. Confirm against the live system before
touching:

1. The drain process and its watchdog on Hetzner. If they're running,
   leave them alone unless explicitly asked to intervene.
2. The Ollama daemon on TRIJYA-7 (scheduled task `OllamaServe`). It
   has cold-start latency; restarting kills any in-flight drain calls.
3. The FreshRSS admin user. It was deleted by an unidentified cause on
   2026-05-15 and recreating it costs ~574 feed resubscriptions. See
   `07-known-issues.md` #1.

When you're done reading the rest of this folder, pop back to
`CLAUDE.md` at the repo root for the higher-level project rules.
