# 01 - System Architecture

> **TL;DR.** FastAPI + Next.js 15 + Postgres/pgvector on a single
> Hetzner box (`178.105.63.154`). Six Celery workers + Beat run inside
> the `rig-backend` container, NOT as separate compose services.
> Trijya-7 (Windows 11 + RTX 4090) hosts Ollama and is reached over
> Tailscale (`100.92.126.27`) — primary LLM lane. Groq and Cerebras
> are cloud failover. As of 2026-05-28: 793 sources (550 active),
> ~119K articles, 75 migrations applied.

---

## The 8 product pillars

Each pillar is its own page in the frontend and its own ingestion
pipeline in the backend.

| Pillar | Frontend route | Ingest source | Queue(s) |
|---|---|---|---|
| **Articles** | `/coverage` | RSS + HTML scraping (550 active sources) | `collectors`, `nlp` |
| **Clips** | `/clips` | YouTube transcripts | `youtube` |
| **Cuttings** | `/cuttings` | Newspaper editions (PDF e-papers) | `documents` |
| **Threads** | `/threads` | Reddit / Twitter / Telegram | `social` |
| **Signals** | `/signals` | "The Signal Room" — Reddit + Telegram + sentiment + entity matching. Twitter is hidden from UI but data layer stays active. | `social` |
| **Documents** | `/documents` | Government PDFs (the "archive") | `documents` |
| **Brief** | `/brief` | Daily generated digest per user | `brief` |
| **Analyst** | `/analyst` | Per-user RAG over the corpus | (synchronous FastAPI) |

Beyond the 8 pillars there's a **CM political-intelligence** layer
(routed to `nlp` for LLM tasks, `social` for cheap aggregations), an
admin/RBAC layer (super-admin bootstrap on every boot via
`SUPER_ADMIN_EMAILS`), and hidden `/worldmonitor` + `/debug` UI.

---

## Container topology

Defined in `infrastructure/docker-compose.yml`.

| Service | Image | What runs in it |
|---|---|---|
| `rig-postgres` | `ankane/pgvector` | Postgres 16 + pgvector. Port `5433:5432`. |
| `rig-backend` | `infrastructure-rig-backend` | **FastAPI uvicorn + 6 Celery workers + Beat**, all from `/start.sh`. |
| `rig-frontend` | `infrastructure-rig-frontend` | Next.js 15 dev server. |
| `rig-searxng` | `searxng/searxng` | Internal web-search proxy. No host port. |
| `rig-freshrss` | `lscr.io/linuxserver/freshrss` | FreshRSS reader — canonical subscription list for ~574 RSS feeds. Port `8081:80`. |
| `rig-caddy` | (Hetzner only) | Dockerised TLS reverse proxy. Caddyfile at `/root/rig/infrastructure/Caddyfile`. |

> **Why no separate worker container?** Anyone reading the compose
> file in isolation will see no `rig-celery-worker-*` service and
> conclude "no workers." That conclusion is **wrong**. The 6 workers
> are launched as background processes inside `rig-backend` by
> `backend/start.sh` (CMD `["/start.sh"]` in `Dockerfile.backend`).
>
> **Footgun.** Adding `rig-celery-worker-*` services to compose
> without first removing the in-container workers gives you two Beat
> schedulers running side-by-side, which double-fires every periodic
> task. Confirmed bad. Don't do it.
>
> To see what's actually running:
> `docker exec rig-backend ps -ef`.

There are several `infrastructure-celery-worker-*` images ~2 weeks
old visible in `docker images` — those are orphans from a prior
compose iteration that was bulk-committed away. Ignore them.

---

## Celery queues and their consumers (current, post-D44)

All 6 workers launched by `backend/start.sh`. One Beat process. Beat
schedule in `backend/celery_app.py` from line ~130.

| Queue | Worker process | Concurrency | What it runs |
|---|---|---|---|
| `collectors` | `worker-collectors` | **3** (was 1, bumped in D44 2026-05-27) | RSS (`tasks.collect_rss`, `tasks.collect_rss_direct`), HTML, og:image backfill, weekly source-health reset, 6h URL refresh, journalist enrichment. |
| `social` | `worker-social` | 2, prefetch=1 | Reddit / Twitter / Telegram + entity backfill + cheap CM aggregations. |
| `youtube` | `worker-youtube` | 1 | YouTube transcripts + entity tagging. |
| `documents` | `worker-documents` | 2, prefetch=1 | Govt PDF collection + doctor + newspaper editions. |
| `nlp` | `worker-nlp` | 4 | Substrate v3 (Prompt G + D1 SPO), topic, entities, social sentiment, CM stance, clustering, dissent, counter-narratives. |
| `relevance` | `worker-relevance` | 4 | Per-user article + doc scoring, CM voice-share / heatmap / exploitation index. |
| `brief` | `worker-relevance` | (shared) | Daily brief generation. Routes to the same process as `relevance`. |
| `whisper` | (not currently used) | — | Reserved for audio transcription. |

Newspaper collection used to run on `collectors` but was moved to
`documents` because the single-concurrency `collectors` worker was
regularly blocked by 30-60 minute RSS scrapes. Govt-document
collection historically had no consumer (`documents` queue empty);
2026-04-28 audit added the consumer.

### Beat schedule (current, post-D29/D33/D34)

| Task | Cadence | Notes |
|---|---|---|
| `tasks.collect_rss` | every 15 min | tier-1 FreshRSS sync |
| `tasks.collect_rss_direct` | every 30 min | tier-2 direct RSS |
| `tasks.collect_html` | every 6 hours | tier-3 HTML |
| `tasks.fetch_og_images_batch` | every 10 min | Thumbnails (Playwright disabled — httpx fallback) |
| `tasks.refresh_rss_urls` | every 6h:20min | UA rotation + URL redirect refresh |
| `tasks.reset_source_health_weekly` | Monday 00:00 UTC | Reset health_score=0 sources to 0.1 |
| `tasks.enrich_journalist_batch` | every 5 min | Parse `byline` → `author_name` (D28/D29) |
| `tasks.process_nlp_batch` | every 30 sec | NLP processing dispatcher |
| `tasks.generate_all_briefs` | daily 00:30 UTC | Brief generation |
| relevance scoring | every 5 min | Per-user article scoring |
| Cerebras / Groq cooldown reset | daily 00:05 UTC | Clears spurious cooldowns |
| **D1 corpus pass (cron, BROKEN)** | daily 00:05 UTC | Script-path mismatch — see known-issues O3 |

---

## TRIJYA-7 (the GPU box) — IMPORTANT: Windows 11

**Confirmed 2026-05-28:** Trijya-7 is a **Windows 11** machine (per
Tailscale status `tdsworks@ windows active`). All admin scripts must
use PowerShell + `setx /M` + `Restart-Service`, NOT systemd/bash.

- Physical: home workstation with RTX 4090 (24 GB VRAM)
- Reached over Tailscale at `100.92.126.27:11434` from Hetzner
- Owner Tailscale account: `tdsworks@gmail.com`
- SSH: `Admin@100.92.126.27` (password Red@0909, see
  Connection_Guide.pdf). **AI MUST NOT use password to SSH directly
  — security policy. Give the user a PowerShell script to paste in
  their already-open admin terminal.**

### Ollama runs as Windows service (or user-app)

Env vars must be set at Machine scope via PowerShell:
```powershell
setx /M OLLAMA_NUM_PARALLEL 8
setx /M OLLAMA_FLASH_ATTENTION 1
setx /M OLLAMA_KV_CACHE_TYPE q8_0
setx /M OLLAMA_KEEP_ALIVE 4h
setx /M OLLAMA_MAX_LOADED_MODELS 2
setx /M OLLAMA_HOST 0.0.0.0:11434
setx /M OLLAMA_MAX_QUEUE 2048
Restart-Service Ollama
```

(Full script: `scripts/deploy/trijya_ollama_tune.ps1`.)

Models loaded: `qwen3:14b` (10.7 GB, primary substrate model) +
`qwen3:30b-a3b` (18.5 GB, MoE).

See `05-llm-infrastructure.md` for full LLM pool design and
`11-session-2026-05-28-learnings.md` for the NUM_PARALLEL reality
check (it helps utilization but doesn't multiply throughput linearly
on a single GPU).

---

## Tailscale routing

- Hetzner production server: `178.105.63.154` (public) + Tailscale
- TRIJYA-7: `100.92.126.27` (Tailscale only)
- Backend reaches Ollama via `http://100.92.126.27:11434/api/chat`
  (native endpoint, NOT `/v1/chat/completions` — see
  `02-substrate-pipeline.md` for why)
- No public exposure of Ollama. Tailscale down between Hetzner ↔
  Trijya → pool falls over to Groq + Cerebras

---

## Database schema highlights (post-session-2026-05-28)

`articles` table key fields:
- `id`, `url`, `url_hash`, `source_id` (FK to `sources`)
- `title`, `full_text_scraped`, `language_iso`
- `published_at`, `collected_at`
- `extraction_version` (INTEGER: 0/null/1/2/3)
- `substrate_status` (`pending` | `processing` | `ok` | `extract_failed` | `fetch_failed` | `junk`)
- `summary_preview / snippet / executive`, `primary_subject`
- `article_type`, `register_style`, `register_emotion`
- `byline`, `author_name`
- `labse_embedding` (vector(768))
- **`source_country` CHAR(2)** — added by migration 075, auto-populated via trigger

`sources` table key fields:
- `id`, `name`, `domain`, `rss_url`
- `source_type` (`rss` | `scrape` | `api`)
- `source_tier` (1=high-trust, 2=standard, 3=experimental)
- `language`, `geo_states[]` (legacy, mixed)
- **`country` CHAR(2)** — added by migration 075, ISO 3166-1 alpha-2
- `health_score` (floor 0.1 after D33)
- `consecutive_failures` (auto-disable at 25, was 10 pre-D33)
- `is_active`

Six v3 child tables: `article_claims` (with SPO triples since D1),
`article_quotes`, `article_locations` (scope derived via migration
074), `article_events` (with `effective_event_date` via migration
072), `article_numbers`, `article_stances`.

Plus enrichment: `article_links`, `article_media`, `article_tweets`,
`article_districts`, `entity_dictionary` (15,755 entities, type
normalized via migration 073).

Narrative tables (scaffolded, not yet populated by code):
`narrative_clusters`, `narrative_cluster_members`, `narrative_drafts`
— created by migration 070.

---

## Data flow at a glance

```
  RSS / HTML / YouTube / Govt PDF / Reddit / Telegram / Newspapers
                            │
                            ▼
          collectors / social / youtube / documents queues
                            │
                            ▼
        Postgres: articles, social_posts, govt_documents, …
                            │
                            ▼
         nlp queue: substrate v3 (Prompt G + D1 SPO via Ollama/
                                  Cerebras/Groq unified pool)
                            │
                            ▼
   article_claims (with SPO), article_quotes, article_locations
   (with scope), article_events (with effective_event_date),
   article_numbers, article_stances, article_links, article_media,
   article_tweets, articles.byline_*, articles.source_country
                            │
                            ▼
       relevance queue: per-user scoring → user_article_relevance
                            │
                            ▼
                brief queue: daily digest per user
                            │
                            ▼
     Frontend pages (/coverage, /signals, /brief, /analyst, …)
```

---

## Hetzner production access

- SSH: `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154`
- Caddy is **dockerised** (`rig-caddy`), not a host service. Caddyfile
  at `/root/rig/infrastructure/Caddyfile`.
- Repo on Hetzner at `/root/rig`, branch `fix/brief-prod-readiness`.
- Origin and Hetzner diverged at commit `3a9441a` (2026-05-09).
  Reconcile before Phase 7 work; origin is canonical for CM editorial
  UI.

---

## Frontend conventions

- Next.js 15 (app router). Tests = Vitest unit + Playwright e2e.
- Pages: `frontend/src/app/<pillar>/page.tsx`
- Components: `frontend/src/components/<pillar>/`

---

## Backend conventions

- Pytest in `backend/tests/`
- Migrations numbered, idempotent where possible, in
  `scripts/migrations/NNN_name.sql`. Applied at first boot via
  `docker-entrypoint-initdb.d`. **Current latest: 075** (source +
  article country, 2026-05-28).
- Substrate v3 schema = migrations 043, 063-075 (see
  `02-substrate-pipeline.md`)
- Branches: `fix/<area>-phase-N` for bundled remediation; one PR per
  phase, stacked

---

## Migration log (recent session, 2026-05-26 → 2026-05-28)

| # | Name | What it does |
|---|---|---|
| 070 | narrative_clusters | Adds 3 tables: clusters, members, drafts |
| 072 | effective_event_date_smart_fix | Adds column + trigger, 4-tier year-fix rule |
| 073 | entity_type_and_unit_normalize | Dedupes org/organisation/organization + 11 unit variants |
| 074 | location_scope_derive_from_columns | Adds function + trigger, derives city/state/country/continent |
| 075 | source_country_and_article_source_country | Adds ISO codes, trigger auto-populates articles |

---

## See also

- `02-substrate-pipeline.md` — v3 extraction details, child tables
- `03-relevance-system.md` — per-user scoring
- `04-scrapers.md` — ingestion mechanics
- `05-llm-infrastructure.md` — LLM pool internals
- `06-operations-runbook.md` — operational procedures
- `07-known-issues.md` — current frustrations
- `11-session-2026-05-28-learnings.md` — full migration 070-075
  context + Trijya Windows discovery + everything else from today
- `scripts/migrations/070-075` — migrations applied this session
