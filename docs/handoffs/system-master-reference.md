# RIG Surveillance — Master System Reference

**Audience:** internal — prepared so the team can answer any deep technical question from a tech-savvy client or partner.
**Status:** living document. Generated from the codebase, the `docs/onboarding/` set, and the `docs/handoffs/db-reference/` schema reference.

---

## ⚠️ Confidentiality & redaction notice

This document is an **internal** reference. Several sections contain information that should **NOT** be handed to a client verbatim. Redact before any external share:

- **Infrastructure secrets & addresses** — production server IP, SSH keys, Supabase keys, Groq API keys, database credentials, Caddy config.
- **Anti-blocking infrastructure** — the residential-IP relay setup for YouTube/Instagram, cookie handling, IP-reputation tactics. (Operationally sensitive.)
- **Private GPU fleet** — the TRIJYA-7 / TRIJYA-8 workstation nodes and tunnel topology.
- **Exact LLM key pool & rotation** — counts, org IDs, TPD budgets.

A client-facing version should keep the **architecture, capabilities, data model concepts, API surface, and feature logic** but strip the specific hostnames, keys, and anti-bot tradecraft.

---

## How to use this document

| Section | Answers questions about… |
|---|---|
| 1. Executive summary | "What is the product, in one page?" |
| 2. Architecture, tech stack & deployment | stack, containers, hosting, how it ships |
| 3. Data ingestion & scraping | where data comes from, how we collect it |
| 4. Extraction, NLP, embeddings, clustering | how raw text becomes structured intelligence |
| 5. Database & storage | the data model, tables, where everything lives |
| 6. Scheduling, workers & LLM infrastructure | cron, Celery, the AI compute layer |
| 7. Features, API surface, RAG & access control | every feature + the logic behind it |
| 8. Client delivery & integration options | **how a client can consume our data/features** |
| 9. Portability, secrets & "what transfers" | what can/can't move to a client's environment |

---

## Glossary (quick reference)

- **Substrate** — the unified v3 processing pipeline every article rides through (translate → extract → entities → stances → summary…).
- **Pillar** — a content vertical with its own ingest + page (Articles, Clips, Cuttings, Threads, Signals, Documents, Brief, Analyst).
- **night-desk / ROBIN-OSINT** — the productized client-facing web app served at `desk.rig360media.com`.
- **Ask-RIG** — the retrieval-augmented (RAG) chat product over the corpus.
- **Stance vs emotion** — *directed stance* (supportive/critical toward a target) is the bias measure; *register_emotion* is event-emotion (alarm = alarming events), NOT hostility.
- **Surfaceable** — a cluster/story confident enough to show a user (precision-gated).
- **org / RBAC** — multi-tenant access: each client is an org; data is scoped by `org_id`; roles are super_user / admin / client.


---

# 1. Executive Summary

## What it is

**RIG Surveillance** is a multi-pillar **media & open-source intelligence (OSINT) aggregation and analysis platform**. It continuously ingests news and public signals across multiple languages and formats, runs them through an AI-driven processing pipeline that extracts structured intelligence (entities, claims, quotes, stance/sentiment, topics, events, geography), clusters them into stories, and surfaces it through a personalized analyst-grade web product.

The productized, client-facing surface is **ROBIN-OSINT (the "night-desk")**, live at **`desk.rig360media.com`**, plus **Ask-RIG**, a retrieval-augmented chat assistant over the whole corpus.

## The content pillars

| Pillar | Source type | What it delivers |
|---|---|---|
| **Articles** (`/coverage`) | RSS / HTML news scraping | The core news corpus |
| **Clips** (`/clips`) | YouTube transcripts | Video coverage, transcribed + analyzed |
| **Cuttings** (`/cuttings`) | Newspaper PDF editions | Print coverage, OCR/text-layer extracted |
| **Threads / Signals** | Reddit / Telegram / Twitter | Social signals with sentiment + entity matching ("The Signal Room") |
| **Documents** (`/documents`) | Government PDFs | The "archive" — 53 official source adapters |
| **Brief** (`/brief`) | Generated | Daily personalized situation digest |
| **Analyst** (`/analyst`) | Generated (RAG) | Per-user question-answering over the corpus |

## What makes it differentiated (talking points)

- **Cross-lingual by design** — English + Indian-language (Telugu, Hindi, etc.) content is translated and embedded in a shared multilingual vector space (LaBSE), so a query in one language retrieves coverage in another.
- **Directed stance analysis** — not just "positive/negative sentiment," but *who is supportive vs critical toward a specific subject*, computed per-article and aggregated per-outlet.
- **Same-event story clustering** — millions of articles are deduplicated and grouped into surfaceable stories/storylines ("sagas") with precision gating.
- **Personalized per watchlist** — every client (org) sees the desk scoped to their entities/regions/topics; the brief, analytics, map, and dossier all re-rank around their watchlist.
- **Agentic RAG** — Ask-RIG plans multi-step retrieval (corpus + live web), fuses vector + keyword search, and answers with inline citations and auto-generated charts.
- **Self-hosted AI compute** — a hybrid LLM pool (cloud + private GPU nodes) keeps inference cost and throughput under control.

## The shape of the system (one paragraph)

A **FastAPI + Celery** Python backend ingests via a fleet of source adapters, processes through the **substrate** pipeline using a **hybrid LLM pool**, and stores everything in **Postgres 16 + pgvector**. A **Vite/React** SPA (night-desk) and a separate **Ask-RIG** RAG service read from a read-only analytics API. Everything runs in **Docker on a single Hetzner server** behind **Caddy**, with **Supabase** handling authentication and a role-based, org-scoped multi-tenant access model.


---

# 2. Architecture, Tech Stack & Deployment

> Scope: this section describes how **RIG Surveillance** is built, what
> runs where, and how code reaches production. Everything below is drawn
> from the live repository (`infrastructure/docker-compose.yml`,
> `infrastructure/Caddyfile`, `infrastructure/Dockerfile.backend`,
> `backend/start.sh`, the two product backends under `products/`) and the
> internal onboarding docs. Where a detail is not present in the codebase
> it is explicitly marked **"not documented."**

---

## 1. System at a glance

RIG Surveillance is a multi-pillar OSINT intelligence aggregator. It
ingests roughly 574 RSS feeds, 80+ HTML sources, YouTube transcripts,
newspaper editions, social signals (Reddit / Telegram / Twitter) and
government PDFs; runs every article through an LLM extraction
"substrate"; scores per-user relevance; and surfaces the result through
a single-page web desk plus a conversational RAG assistant.

The entire production system runs on **one Hetzner server**
(`178.105.63.154`) as a set of Docker containers behind a dockerised
Caddy TLS reverse proxy. The public entry point is
**`https://desk.rig360media.com`**.

A second machine — **TRIJYA-7** (RTX 4090, reached over Tailscale) —
runs a local LLM (Ollama / TabbyAPI) used as the primary inference
provider, with Groq and Cerebras as cloud failover. The LLM tier is
covered in its own section; this section focuses on the application,
container, and deployment architecture.

---

## 2. Tech stack

| Layer | Technology | Notes |
|---|---|---|
| Ingestion / API backend | **Python 3 + FastAPI** (uvicorn) | The core `backend/` service. Async; served by uvicorn on port 8000. |
| Background processing | **Celery** + **Celery Beat** | Multiple workers + one Beat scheduler, all inside the backend container (see §4). |
| OSINT / desk API | **Python 3.12 + FastAPI** | Separate service in `products/osint/backend` (the `osint-backend` container). |
| Ask-RIG (RAG assistant) | **Python + FastAPI** | Separate service in `products/ask-rig`; streaming (SSE) answer API. |
| Primary frontend ("night-desk") | **Vite + React** (SPA) | Source in `products/osint/design/night-desk`; built to a static `dist/` and served by Caddy. |
| Legacy frontend | **Next.js 15** dev server | Referenced in onboarding docs as `rig-frontend`; **not present** in the current `infrastructure/docker-compose.yml` (see §3 note). |
| Database | **PostgreSQL 16 + pgvector** | `ankane/pgvector` image. Vector search for embeddings + relational store. |
| Reverse proxy / TLS | **Caddy** (dockerised) | Auto-HTTPS, gzip/zstd, SPA fallback, same-origin API routing. |
| Web-search proxy | **SearXNG** | Internal-only; reached by backend via Docker DNS. |
| RSS reader / feed registry | **FreshRSS** (LinuxServer image) | Canonical subscription list (~574 feeds); queried via its GReader API. |
| Auth | **Supabase** (JWT, HS256) | Backends verify Supabase access tokens via a shared `SUPABASE_JWT_SECRET`; super-admin bootstrap on boot. |
| OCR / document extraction | **Tesseract `tessdata_best`**, **PaddleOCR PP-Structure** | Baked into the backend image for Indic-language newspaper extraction. |

Languages in the repo: **Python** (backends, Celery tasks, collectors),
**JavaScript/JSX** (Vite/React night-desk, legacy Next.js), **SQL**
(numbered migrations), and shell (`start.sh`, ops scripts).

---

## 3. Container topology

All containers are defined in `infrastructure/docker-compose.yml` and
share a single bridge network, **`rig-network`** (subnet `172.30.0.0/24`,
IPv6 enabled). Inter-service traffic uses Docker DNS (e.g.
`rig-postgres:5432`, `http://rig-searxng:8080`).

| Container | Image | What runs inside it | Host port |
|---|---|---|---|
| `rig-postgres` | `ankane/pgvector:latest` | PostgreSQL 16 + pgvector. Migrations auto-applied at first boot from `scripts/migrations/` via `docker-entrypoint-initdb.d`. | `5433:5432` |
| `rig-backend` | `infrastructure-rig-backend` (built from `Dockerfile.backend`) | **FastAPI (uvicorn) + all Celery workers + Celery Beat**, launched by `/start.sh` (see §4). | `8000:8000` |
| `rig-freshrss` | `lscr.io/linuxserver/freshrss:latest` | FreshRSS reader; the canonical RSS subscription list. Internal cron every 15 min (`CRON_MIN`). | `8081:80` |
| `rig-searxng` | `searxng/searxng:latest` | Internal web-search proxy. **No host port** — reachable only on `rig-network` at `http://rig-searxng:8080`. | — |
| `osint-backend` | built from `products/osint/backend/Dockerfile` | FastAPI desk/OSINT API (`python:3.12-slim`, uvicorn `main:app` on 8000). Connects to Postgres as the read-mostly `analytics_user` role. | `8002:8000` |
| `rig-caddy` | Caddy (Hetzner only) | Dockerised TLS reverse proxy. Caddyfile at `/root/rig/infrastructure/Caddyfile`. Serves the night-desk SPA + routes `/osint/*`. | 80/443 |

**Note on `rig-frontend` and `rig-askrig`:** The onboarding docs and
internal memory describe a `rig-frontend` (Next.js 15 dev server) and a
`rig-askrig` sidecar container (Ask-RIG, build context `/root/askrig`,
wired into Caddy under `/ask/*` with SSE). **Neither service is defined
in the `infrastructure/docker-compose.yml` checked into this repo.** Per
the decommission note (2026-06-10), the legacy Next.js frontend was
removed and the deployment was collapsed to serve only
`desk.rig360media.com` via the static night-desk SPA. The Ask-RIG
container is deployed out-of-band on the Hetzner host (its build context
and Dockerfile live under `/root/askrig`, **not** in this repo's
`products/ask-rig/`, which has no `Dockerfile`). Treat the running
Hetzner host as the source of truth for these two; the compose file in
this repo does not capture them.

The `mc.*` / `mc-api.*` hosts in the Caddyfile (Mission Control,
`mc-frontend:3030` / `mc-backend:8088`, behind HTTP basic auth) are a
separate app and are **not** part of the compose file here.

### Stale images on disk

`docker images` on the host shows several `infrastructure-celery-worker-*`
images ~2 weeks old. These are **orphans** from a previous compose
iteration and are **not** part of the current deployment. Do not infer
worker topology from them.

---

## 4. Where the Celery workers actually live (non-obvious)

This is the single most counter-intuitive part of the architecture, and
the docs flag it repeatedly:

> **There is no `rig-celery-worker-*` service in the compose file.**
> Anyone reading `docker-compose.yml` in isolation will conclude "no
> workers" — and be wrong.

The workers and the Beat scheduler run as **background processes inside
the `rig-backend` container**. The container's CMD is `["/start.sh"]`
(`Dockerfile.backend`). `start.sh` forks each Celery worker with `&`,
then `exec`s uvicorn in the foreground to keep the container alive.

Workers launched by `backend/start.sh` (verified from the script):

| Worker (`--hostname`) | Queue(s) | Concurrency | Responsibility |
|---|---|---|---|
| `worker-collectors` | `collectors` | 3 | RSS, HTML scraping, og:image backfill |
| `worker-social` | `social` | 2 (prefetch=1) | Reddit / Telegram / Twitter + entity backfill + cheap CM aggregations |
| `worker-youtube` | `youtube` | 1 | YouTube transcript fetch + entity detection + embedding |
| `worker-documents` | `documents` | 2 (prefetch=1) | Govt PDF extraction (heavy JVM; isolated from RSS) |
| `worker-nlp` | `nlp` | 4 | Article NLP / topic / entities / sentiment / stance / clustering |
| `worker-relevance` | `relevance`, `brief` | 4 | Per-user relevance scoring + daily brief generation |
| `worker-whisper` | `whisper` | 1 (prefetch=1) | NEWSROOM 3-Lens transcript pipeline + live HLS monitors (CPU-bound ASR) |
| Celery **Beat** | — | 1 process | Periodic-task scheduler |
| **uvicorn** (FastAPI) | — | foreground | `backend.main:app` on `0.0.0.0:8000 --reload` |

> **Doc drift to flag:** the onboarding text and the compose-file header
> comment describe "6 workers." The live `start.sh` actually forks
> **seven** workers (the `documents` and `whisper` workers were added
> later) plus Beat. The script is authoritative.

Operational implications:

- **To see what's truly running:** `docker exec rig-backend ps -ef`.
- **Beat persistence:** Beat's last-run-times DB is stored on the
  `rig-beat-schedule` named volume (mounted at `/app/beat`). Without it,
  every `docker compose up` resets the schedule to "now" and
  crontab/timedelta entries silently drift. `start.sh` also clears a
  stale `celerybeat.pid` on boot.
- **Footgun — never split Beat:** adding `rig-celery-worker-*` services
  to compose *without first removing the in-container workers* produces
  **two Beat schedulers running side by side**, which double-fires every
  periodic task. This is a confirmed, documented hazard. Do not do it.

---

## 5. Networking, ports, reverse proxy & domains

### Public surface (Caddy)

The Caddyfile (`infrastructure/Caddyfile`) terminates TLS and defines the
public site. For `desk.rig360media.com`:

- **`/osint/*`** → `reverse_proxy osint-backend:8000` (same-origin API,
  so no CORS needed). The path prefix is stripped (`handle_path`).
- **everything else** → static files from `/srv/night-desk` with
  SPA history-API fallback (`try_files {path} /index.html`).
- Security headers applied: HSTS (1 year, includeSubDomains),
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`,
  `Referrer-Policy: strict-origin-when-cross-origin`. Responses are
  gzip/zstd encoded.

Per internal memory, Ask-RIG is exposed at `desk.rig360media.com/ask`
via an additional Caddy route (`/ask/*`) with `flush_interval -1` for
SSE streaming — but that route is **not** in the repo's Caddyfile (it
lives in the host's deployed Caddyfile). **Not documented in-repo.**

### Host-published ports

| Service | Host port | Container port |
|---|---|---|
| Postgres | 5433 | 5432 |
| rig-backend (FastAPI) | 8000 | 8000 |
| FreshRSS | 8081 | 80 |
| osint-backend | 8002 | 8000 |
| Caddy | 80 / 443 | — |
| SearXNG | (none — internal only) | 8080 |

### Internal DNS

- Backend → DB: `rig-postgres:5432` (async via `asyncpg`).
- Backend → FreshRSS: `http://rig-freshrss:80` (GReader API).
- Backend → SearXNG: `http://rig-searxng:8080`.
- Caddy → desk API: `osint-backend:8000`.

---

## 6. The two backends — `rig-backend` vs `osint-backend`

This is a deliberate **two-backend split**, and the distinction matters
operationally:

**`rig-backend` — the ingestion/processing engine.**
- Source: `backend/` (repo root).
- Owns all data collection, the LLM extraction substrate, NLP, Celery
  workers, Beat, and the write path into Postgres.
- Connects to Postgres as the **`rig`** superuser/owner role
  (`postgresql+asyncpg://rig:...@rig-postgres:5432/rig`).
- Has the full LLM pool, YouTube relay config, FreshRSS credentials,
  Supabase keys, and super-admin bootstrap (`SUPER_ADMIN_EMAILS`).

**`osint-backend` — the desk / read API.**
- Source: `products/osint/backend/` (`python:3.12-slim`,
  uvicorn `main:app`).
- Serves the night-desk SPA's data: home sections, map, war room,
  entities, stories/chronicle, KPIs, voices, executive reports, etc.
  (routers: `home`, `map_router`, `war_room_router`, `entities`,
  `chronicle_router`, `analytics_router`, `executive`, `report_router`,
  `sources_router`, `top_articles`, and more).
- Connects to Postgres as the **read-mostly `analytics_user`** role
  (read-only on `public.*`, read-write on the `analytics` schema —
  Postgres-enforced). This isolates the user-facing read API from the
  ingestion write path.
- Verifies Supabase JWTs (`SUPABASE_JWT_SECRET`) and has its own
  super-admin bootstrap (`OSINT_BOOTSTRAP_ADMIN_EMAIL`).
- Has a small dedicated LLM path (`groq_client.py`, `llm_synth.py`) with
  `LOCAL_LLM_ENABLED=0` — it uses cloud LLMs only, not the local node.

**Ask-RIG** (`products/ask-rig/`) is a third, read-only RAG service
(hybrid retrieval: pgvector v4 embeddings + full-text + RRF, with a
cite-ID guardrail). Structure: `app/routers/` (`agent`, `intel`,
`brief`, `web`, `users`, `account`), `app/agent/` (`loop.py`,
`tools.py`), `app/appdb/`, `app/static`, `app/web`. It ships with its
own `eval/`, `tests/`, and a local `askrig_app.db` SQLite file for app
state. It is deployed as a sidecar container on Hetzner (see §3 note).

---

## 7. Hosting & deployment model

### Single-server hosting

Everything production runs on **one Hetzner box** (`178.105.63.154`),
accessed via `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154`. The repo on
the host lives at **`/root/rig`**. There is **no CI/CD pipeline** —
deployment is manual and container-specific. (The repo's branch on
Hetzner has historically diverged from origin; origin is canonical for
editorial UI work — reconcile before shipping.)

### Baked vs bind-mounted — the critical distinction

How code reaches a running container differs per service, and getting
this wrong is the most common foot-gun:

| Service | Code delivery | How to deploy a change |
|---|---|---|
| `rig-backend` | **Bind-mounted.** `docker-compose.yml` mounts `../backend → /app/backend` and `../scripts → /app/scripts`. Code on the host (`/root/rig`) is live in the container. Per internal reference, the Hetzner backend is bind-mounted, **not** baked (this contradicts older CLAUDE.md text). | Edit on host, then restart/reload the workers. uvicorn runs `--reload`; Celery workers must be restarted to pick up changes. No image rebuild needed for pure code edits. |
| `rig-backend` **image contents** | **Baked.** OCR models (Tesseract `tessdata_best`, PaddleOCR PP-Structure), Python deps from `requirements.txt`, and `start.sh` are baked into `Dockerfile.backend`. | Dependency / `start.sh` / model changes require `docker compose build` (re-installs do **not** happen via host `pip install` — there is no `site-packages` bind-mount). |
| `osint-backend` | **Baked.** Its Dockerfile does `COPY . .` — the source is copied into the image at build time; there is no source bind-mount in compose. | Per internal memory, the live osint-backend is updated by **`docker cp` of changed files + container restart** (the host `/root/rig` source can be **stale** vs the running container). A clean deploy is `docker compose build osint-backend` + restart. |
| night-desk frontend | **Static `dist/` served by Caddy.** Built with Vite (`products/osint/design/night-desk`) and the compiled bundle is placed at `/srv/night-desk` (host path `/root/rig/night-desk-dist`), served directly by `rig-caddy`. | Build the Vite bundle, **`scp`/copy the `dist/` to the host**, and Caddy serves it immediately (no container rebuild). |
| `rig-askrig` (Ask-RIG) | **Baked**, built from `/root/askrig` on the host (not from this repo). Reranker model must be baked in (rebuild required to pick it up). | Rebuild the sidecar image on the host. |
| `rig-postgres` migrations | **First-boot only.** `scripts/migrations/*.sql` mount into `docker-entrypoint-initdb.d` and apply **only on an empty data volume**. | New migrations on an existing DB must be applied manually (e.g. `docker exec rig-postgres psql ...`); they are **not** auto-run on restart. |

### Baked-container foot-guns (documented)

1. **Restarting `rig-frontend`/`rig-backend` does not pick up host-side
   `npm install` / `pip install`.** Neither container bind-mounts
   `node_modules` / `site-packages`. Re-installs must happen *inside* the
   container, or via `docker compose build`.
2. **Editing `package.json` and expecting hot reload** — the dev server
   runs inside the container; its cache lives at `/app/.next`. Restart
   the container after dependency changes.
3. **`docker commit` cannot capture bind-mounts** — committing the
   `rig-backend` container will not snapshot the bind-mounted
   `/app/backend` code.
4. **`/root/rig` git index is shared across concurrent sessions** — do
   not blindly commit into it from an automated session.
5. **Stale `infrastructure-celery-worker-*` images** (see §3) must be
   ignored when reasoning about deployment.

---

## 8. Repository layout (monorepo)

The repo is a monorepo rooted at the project directory. Principal trees:

```
rig-surveillance/
├── backend/                  # FastAPI ingestion engine + all Celery tasks
│   ├── start.sh              # Forks all Celery workers + Beat, then exec uvicorn
│   ├── celery_app.py         # task_routes dict + Beat schedule (source of truth for routing)
│   ├── main.py               # FastAPI app (backend.main:app)
│   ├── collectors/           # 53+ source adapters (@register_source), tiered fetcher
│   ├── nlp/                  # groq_client.py (unified LLM pool), NLP processors
│   └── tasks/                # Celery tasks (substrate, social, nlp, clipping, cm, ...)
├── products/
│   ├── osint/
│   │   ├── backend/          # osint-backend service (FastAPI, analytics_user)
│   │   │   ├── main.py, Dockerfile, routers/, auth/, data/
│   │   ├── design/night-desk/# Vite + React SPA (src/, dist/, server/, public/)
│   │   └── frontend/brief-next/  # legacy/alt frontend
│   └── ask-rig/              # Ask-RIG RAG service
│       ├── app/ (agent/, routers/, appdb/, static/, web/)
│       ├── eval/, tests/, scripts/
│       └── askrig_app.db     # local SQLite app state
├── infrastructure/
│   ├── docker-compose.yml    # Container definitions (the deployment)
│   ├── Dockerfile.backend    # rig-backend image (OCR models, deps, start.sh)
│   ├── Dockerfile.frontend(.prod)
│   ├── Caddyfile             # TLS reverse proxy config
│   ├── .env / .env.example   # Secrets + tunables
│   ├── searxng/              # SearXNG config
│   └── cf-workers/           # Cloudflare Worker(s)
├── scripts/
│   └── migrations/           # Numbered, idempotent SQL (applied at first DB boot)
└── docs/
    ├── onboarding/           # 00–10 numbered onboarding docs
    ├── qa/                   # Defect registers + per-source verdicts
    ├── handoffs/             # Session handoffs, DB schema reference
    └── mistakes.md           # Chronological incident log
```

### Source-of-truth files (per `CLAUDE.md`)

- **Worker topology:** `backend/start.sh` (and `docker exec rig-backend
  ps -ef` for what is actually running).
- **Task routing & Beat schedule:** `backend/celery_app.py`
  (the `task_routes` dict, ~lines 60–260).
- **Database schema:** `scripts/migrations/*.sql` (numbered, applied in
  order at first boot).
- **What containers run:** `infrastructure/docker-compose.yml`.
- **Public routing/TLS:** `infrastructure/Caddyfile`.

---

## 9. Request & data flow (summary)

1. **Ingest:** Beat schedules collection tasks → queue-specific Celery
   workers in `rig-backend` scrape RSS (via FreshRSS), HTML, YouTube,
   newspapers, social, and govt PDFs.
2. **Enrich:** the `nlp` worker runs each item through the LLM extraction
   substrate (translate → claims → summary → entities → stance →
   clustering), calling the local LLM node first with Groq/Cerebras
   failover. Results land in Postgres (relational + pgvector).
3. **Score:** the `relevance` worker computes per-user relevance and
   generates the daily brief.
4. **Serve:** `osint-backend` (as `analytics_user`) reads the enriched
   corpus and feeds the night-desk SPA, which Caddy serves at
   `desk.rig360media.com`. **Ask-RIG** answers free-text analyst queries
   over the same corpus via hybrid retrieval + a cited LLM answer.

---

## 10. Known documentation gaps (flagged, not invented)

- **Worker count:** docs say "6 workers"; `start.sh` forks **7** + Beat.
  The script is authoritative.
- **`rig-frontend` / `rig-askrig` containers:** described in docs/memory
  but **absent from the repo's `docker-compose.yml`**; they exist (if at
  all) only on the deployed Hetzner host.
- **Ask-RIG Dockerfile / `/ask/*` Caddy route:** **not present in this
  repo** — deployed from `/root/askrig` on the host.
- **`CLAUDE.md` vs reality:** the root `CLAUDE.md` predates the
  2026-06-10 decommission and describes a Next.js frontend and a baked
  backend; the live backend is bind-mounted and the live frontend is the
  static Vite night-desk. Trust the compose file, `start.sh`, the
  Caddyfile, and the running host over the prose.
```


---

# 3. Data Ingestion & Scraping

RIG Surveillance is fed by a fleet of pillar-specific collectors. Each pillar
has its own fetch strategy, cadence, and failure profile, but they share a
common design philosophy: **keep the central server's IP reputation clean,
push high-ban-risk fetches out to residential relays, and land every raw item
in a database table with a `status`/`substrate_status` flag that the
downstream NLP pipeline drains asynchronously.**

This section documents how each data source is collected, the registration
pattern that makes new sources easy to add, the relay architecture that
protects against IP bans, the scheduling cadence, and how raw items enter the
processing pipeline.

> Source-of-truth files for this section:
> `backend/collectors/` (collector entry-points + adapters),
> `backend/collectors/sources/registry.py` (`@register_source` pattern),
> `backend/collectors/youtube_v2/transcript_relay.py` (the relay),
> `backend/celery_app.py` (the Beat schedule), and
> `docs/onboarding/04-scrapers.md`.

---

## 1. Architecture overview

Collection runs as scheduled Celery **Beat** tasks. A central scheduler fires
each collector task on a fixed cadence; the task fans out across that pillar's
active sources, fetches new items, and writes them to a pillar table with an
"unprocessed" flag. A separate set of enrichment tasks (the NLP substrate
pipeline, documented elsewhere) drains those rows independently.

Two cross-cutting principles govern the whole layer:

1. **Decouple discovery from fetch.** For high-risk sources (YouTube,
   Instagram), the server only does the cheap, low-risk part (RSS discovery)
   and queues work. The expensive, ban-prone fetch happens on a separate
   residential machine via a *relay*.
2. **Tiered fallback per fetch.** For articles, fetching escalates through
   four mechanisms (FreshRSS → Direct RSS → HTML → Playwright), stopping at the
   first that succeeds. Cheaper, lower-IP-burn methods are tried first.

### Collector entry-points

| File | Pillar | Role |
|---|---|---|
| `rss_collector.py` | Articles | Beat-driven FreshRSS sync (15-min cadence) |
| `direct_rss_collector.py` | Articles | Tier-2 direct-RSS fallback (30-min cadence) |
| `html_collector.py` | Articles | Tier-3 HTML scrape + Trafilatura (6-hour cadence) |
| `playwright_helper.py` | Articles | Tier-4 full-browser render (last resort) |
| `tiered_fetcher.py` | Articles | Orchestrates the 4-tier cascade |
| `govt_collector.py` | Documents | Government PDF collection |
| `newspaper_collector.py` | Cuttings | Newspaper-edition PDF collection |
| `youtube_v2/` | Clips | YouTube discovery + relay fetch + clip extraction |
| `social_collector.py` | Threads / Signals | Reddit / Telegram dispatch |
| `telegram_user_collector.py` | Threads / Signals | Telegram user-channel sweep |
| `instagram_relay.py` | Threads / Signals | Residential Instagram relay service |

---

## 2. Articles — RSS / HTML scraping

The Articles pillar (`/coverage`) is the highest-volume source (~30k items/day
intake). Fetching is a **4-tier cascade** implemented in
`backend/collectors/tiered_fetcher.py`. Each tier is tried in order; first
success wins.

| Tier | Mechanism | When used |
|---|---|---|
| 1 | **FreshRSS** (GReader API at `http://rig-freshrss:80`) | Default for any `source_type='rss'`. Cheap, batched, low-IP-burn. |
| 2 | **Direct RSS** (httpx GET on the feed URL) | Fallback when FreshRSS doesn't have the feed subscribed or returns empty. |
| 3 | **HTML** (httpx + Trafilatura + per-source adapter) | For `source_type='html'`, or as fallback when RSS is unavailable. |
| 4 | **Playwright** (full Chromium render) | Last resort. Used for sources with anti-bot detection that reject httpx user-agents (common when data-centre IPs hit Indian govt portals). Slow + expensive. |

### FreshRSS as a source

FreshRSS is run as its own container (`rig-freshrss`,
`lscr.io/linuxserver/freshrss`) and acts as a **batched RSS aggregation
layer** in front of the article collector. The collector talks to it via the
GReader API rather than hitting hundreds of feed URLs directly. This is the
preferred path because it is cheap, batched, and burns very little of the
server's IP reputation — FreshRSS does the polling, the collector pulls a
consolidated digest.

### Body extraction — Trafilatura

The HTML tier (and HTML-capable per-source adapters) use **Trafilatura** to
strip tag soup down to clean body text. Empirical precision on Indian news
sources is **~93%**, better than `newspaper3k` or `readability-lxml` on the
same sample. (Per the onboarding doc, do not swap it out without an A/B test.)

### SearXNG web-search proxy

A `rig-searxng` container (`searxng/searxng`) is deployed as a web-search
proxy. Its role as a *data source* for the article collector is **not
documented** in the files reviewed — it is present in the deployment topology
as a web-search proxy, but no article-collector call into SearXNG was found in
`html_collector.py`. Treat SearXNG as available infrastructure whose
collection wiring is not documented here.

### Where article items land

The RSS collector inserts directly into the **`articles`** table
(`backend/collectors/rss_collector.py`), e.g.:

```sql
INSERT INTO articles (
  source_id, url, url_hash, title,
  lead_text_original, full_text_scraped,
  published_at, collected_at,
  content_type, source_tier,
  thumbnail_url, author_name,
  nlp_processed
) VALUES (..., 'article', $8, ..., FALSE)
ON CONFLICT (url_hash) DO NOTHING
```

Key landing semantics:
- **`nlp_processed = FALSE`** marks the row as awaiting enrichment.
- **`collected_at = NOW()`** is the ingest timestamp.
- **`ON CONFLICT (url_hash) DO NOTHING`** dedupes on a hash of the URL, so
  re-fetching the same article is a no-op.

The substrate/NLP pipeline (the `tasks.substrate_drain` and
`tasks.process_nlp_batch` Beat tasks) then picks up unprocessed rows
asynchronously and advances `substrate_status` (`pending → processing → ok /
extract_failed / junk`).

---

## 3. Clips — YouTube transcripts (relay-driven)

The Clips pillar (`/clips`) is the most operationally delicate collector
because YouTube aggressively rate-limits and IP-bans caption fetches. The
design **decouples discovery (safe) from transcript fetch (ban-prone)** and
pushes the fetch onto a residential relay.

### The pipeline, end to end

1. **Discovery (on the server, safe).** `tasks.discover_youtube_channels`
   runs every **30 min**, reading the Atom RSS feed of every active channel in
   `youtube_channels` (~72 channels, tiered `tier_1`/`tier_2`/`tier_3`). RSS
   discovery is *not* IP-blocked, so it runs directly from the server. New
   video IDs are inserted into **`pending_youtube_videos`** with
   `status = 'pending'`.
2. **Transcript fetch (on the residential relay, ban-prone).** The server
   calls out to a **relay** at `YT_RELAY_URL` (a laptop / residential machine
   on Tailscale) which actually fetches the transcript. The relay writes the
   transcript JSON back into `pending_youtube_videos` and flips
   `status → transcribed`.
3. **Clip extraction (on the server).** `tasks.run_youtube_extraction` runs
   every **5 min**, draining `transcribed` rows: it windows the transcript,
   matches monitored entities, and writes clips into **`youtube_clips_v2`**
   (the live clips table), flipping the source row to `status = 'extracted'`.

### The relay (`youtube_v2/transcript_relay.py`)

The relay is a small HTTP service run on a residential machine (laptop /
TRIJYA-7), listening on `:8888`, reachable from the server via its Tailscale
IP (`YT_RELAY_URL=http://<tailscale-ip>:8888`).

- **Fetch engine:** `yt-dlp` + **authenticated cookies** (replaced the old
  `youtube-transcript-api`). With a logged-in cookie jar, requests are treated
  as an authenticated user — YouTube's authenticated threshold is ~2000
  videos/hr vs ~300/hr anonymous; the system deliberately stays far under.
- **Cookies:** a Netscape-format `cookies.txt` from a **throwaway** Google
  account (`YT_COOKIES` env var), never a personal one. Operational
  foot-gun: do **not** keep a YouTube tab open in the browser the cookies were
  exported from — YouTube rotates session cookies on open tabs and the export
  goes stale.
- **Token-bucket rate limiter:** 1 YouTube call per 7s (~8.5/min ceiling),
  an order of magnitude under the authenticated ban threshold.
- **Exponential backoff:** on 429 / bot-wall → 10s, 20s, 40s, 80s.
- **yt-dlp client quirk:** as of yt-dlp 2026.06.09, `web`/`mweb`/`web_safari`
  clients return 0 caption tracks; `tv`/`android` clients return them — the
  relay selects accordingly.

### IP-reputation throttling (hard-won calibration)

The *sustained* rate is **not** set by the relay's per-call limiter — it is set
by the server's Beat cadence, round-robined across the relay pool. The
empirically-derived safe rate is documented in the Beat config:

- A single residential IP gets **YouTube-blocked above ~40/hr**. (A desktop
  died at ~60/hr; one node was clean at 40/hr in the pool but blocked after 37
  fetches when pushed to 60/hr solo.)
- **Safe sustained per-IP rate ≈ 20/hr.** Total throughput =
  `~20/hr × (number of healthy relay IPs)`.
- Beat normally sets `tasks.fetch_youtube_transcripts` to `limit 1` every
  3 min (~20/hr) for one IP; raised to `limit 2` (~40/hr split two ways) when
  a second IP is healthy.
- **As committed in the source reviewed**, the task is in a *temporary
  cool-down*: schedule `timedelta(minutes=360)` with `limit 1` (~2/hr),
  applied 2026-06-12 after both residential IPs were throttled by a day of
  debugging fetches. The comment instructs restoring to `limit 1 / 3 min` once
  a live fetch through the relay succeeds.

### Status lifecycle in `pending_youtube_videos`

| status | meaning |
|---|---|
| `pending` | Discovered, awaiting relay fetch. |
| `fetching` | Currently being fetched (added migration 109 to detect relay crashes; stale rows indicate a crashed relay). |
| `transcribed` | Relay delivered the transcript JSON. |
| `extracted` | Clips extracted into `youtube_clips_v2`. Terminal success. |
| `no_transcript` | Video has no captions (live chat, music, etc.). |
| `failed` | Relay or extractor exhausted retries. |
| `skipped` | Aged out by the hourly cull (newest-first policy bounds queue size). |

Retry/attempt counters: `attempts` (fetch) and `extract_attempts` (extraction,
added migration 110 after a bug set `status=extracted` unconditionally even on
429 errors).

> **Discovery ≫ fetch capacity.** Discovery runs ~2400 videos/day but the
> fetch ceiling is ~480/day, so an hourly cull (`skipped`) keeps the queue
> bounded newest-first. Coverage is capped until more relay IPs are added or
> channels are pruned.

---

## 4. Cuttings — newspaper PDF editions

The Cuttings pillar (`/cuttings`) ingests full newspaper **PDF editions**,
segments each page into individual articles ("clippings"), extracts text, and
maps each clipping to a district.

### Collection cadence

Newspaper collection runs as two idempotent passes on the `documents` queue
(`backend/celery_app.py`):

- **Primary:** `tasks.collect_newspapers` at **02:00 UTC** (07:30 IST) — fans
  out across every active paper in `newspaper_sources` (~50 publications).
- **Fallback:** `tasks.collect_newspapers_fallback` at **03:00 UTC** (08:30
  IST) — only papers with no clipping row for today, covering late
  CareersWave portal uploads + primary-pass failures.
- **Catch-up drain:** `tasks.drain_pending_clippings` every **10 min** picks
  up any clipping left in `substrate_status = 'pending'` (e.g. an enrich
  enqueue lost on a restart). Cheap no-op when empty.

PDFs are sourced from each publication's CareersWave portal
(`newspaper_sources.careerswave_url`) or a direct PDF URL
(`newspaper_sources.direct_pdf_url`).

### Text-layer vs OCR localization

Each page is segmented into clipping regions, then the body text is extracted
via a cascade that records its provenance in `clippings.text_source` and
`clippings.clip_source` (extraction code in
`backend/collectors/newspaper_layout/`):

- **Embedded text layer (best).** Digital PDFs (e.g. The Hindu) carry an
  embedded text layer; anchoring off that layer is the highest-quality path.
  `clip_source = 'text'` indicates a localized text-layer anchor.
- **OCR.** When there is no usable text layer, PaddleOCR extracts text;
  `text_source = 'ocr'`.
- **Vision fallback.** A vision model handles cases OCR fails;
  `text_source = 'vision'` (the page crop is stored transiently as
  `clipping_image_b64`).
- **Failed.** `text_source = 'none'`.

`extraction_confidence` (0–1) and `needs_review` flag low-confidence
extractions for human review. `is_notice` (legal/public notices) and
`is_duplicate` clippings are filtered off the cuttings surface.

### District mapping

Geo tagging is part of the substrate enrichment that runs over clippings:
- `geo_primary` — primary location string (e.g. `"Bengaluru"`).
- `geo_district` — matched district id (e.g. `"hyderabad"`), resolving to the
  `districts` table (~59 districts).

### Where cutting items land

Clippings land in the **`clippings`** table (the live cuttings table;
`newspaper_clippings`/`newspaper_editions` are frozen legacy as of 2026-05-26).
A new row starts with `substrate_status = 'pending'`. The Beat task
`clipping_enrich` (`backend/tasks/clipping_enrich.py`) runs OCR/vision
extraction then enrichment (via the `GROQ_SYS_NEWSPAPER` prompt), advancing
`substrate_status` to `ok` / `extract_failed`. Clippings carry the **same
article substrate** (summary, topic, entities, claims/quotes/stances/locations
in child tables) plus a LaBSE v4 embedding for semantic search.

---

## 5. Threads / Signals — social collectors

The Threads (`/threads`) and Signals (`/signals`, "The Signal Room") pillars
ingest social signals. **Reddit and Telegram are live; Twitter/X is removed**
and Instagram runs through a dedicated residential relay.

### Reddit + Telegram (`social_collector.py`)

Both collectors return a common post-dict shape that is stored in the
**`social_posts`** table. Design notes from the source:

- **Error isolation:** all network errors are swallowed and logged — a single
  platform failure must not poison a Celery task that covers multiple
  monitors.
- **Reddit:** uses a fixed UA (`RIGSurveillance/1.0 ...`); has 429-throttle
  telemetry (SIG-8) that surfaces in `/api/health/social` and escalates
  WARNING → ERROR after a configured number of consecutive throttles.
- **Telegram:** uses the Telegram Bot API (`https://api.telegram.org`).
- **Telegram user-channel sweep:** `telegram_user_collector.py` is a separate
  collector for sweeping Telegram user channels.

> **Twitter / X — removed 2026-04-29.** The API free tier returns HTTP 402 on
> user lookups, making collection non-functional. The data layer remains, but
> Twitter is hidden from the user UI. Restore from git tag
> `pre-twitter-removal` if a paid tier is procured.

Social tasks run on the dedicated **`social`** queue (concurrency 2).

### Instagram relay (`instagram_relay.py`)

Instagram is fetched through a **residential relay**, mirroring the YouTube
pattern: a data-centre IP is restricted, but a residential IP + valid session
is not.

- Runs on a residential machine, listening on `:8890`, reached via
  `INSTAGRAM_RELAY_URL=http://<tailscale-ip>:8890`.
- **Session auth:** authenticates with an Instagram `sessionid` cookie
  (`INSTA_SESSIONID` env var); the relay refuses to start without it. It
  builds both a web session (cookie set on `.instagram.com`) and a
  mobile-cookie variant.
- **Rate limiting:** `RELAY_RATE_INTERVAL` (default 5.0s between calls).

### Where social items land

Reddit/Telegram posts land in **`social_posts`** in a common shape and are
then picked up by the social/NLP enrichment tasks (sentiment + entity
matching) on the `social`/`nlp` queues.

---

## 6. Documents — government PDFs (the "archive")

The Documents pillar (`/documents`, the "archive") collects government PDFs
from Indian state and central portals. This is where the **`@register_source`
adapter pattern** is most heavily used.

### The 53 source adapters

There are **53 per-source Python adapters** in
`backend/collectors/sources/*.py`, each decorated with `@register_source`.
Adapter families present in the reviewed tree include:

- `central_regulators.py` — SEBI, RBI, NSE, BSE, etc.
- `courts.py` — court portals.
- `parliament.py` — parliamentary sources.
- `telangana_state.py` — Telangana state portals.
- `international.py`, `ip_permits.py`, `notifications.py`,
  `opposition_pr.py` — additional families.
- `_dateparse.py` — shared date-parsing helper.

### How an adapter is fetched

`govt_collector.py:fetch_document_urls` consults the `SOURCE_REGISTRY` first.
If a registered adapter matches the portal URL it is used; otherwise the
collector falls back to original PIB / Telangana / generic PDF scrapers for
backwards compatibility (`_scrape_generic_pdfs` collects any `.pdf` link from a
portal page).

PDF download/extraction:
- `download_pdf` fetches with `verify=False` (many Indian govt CDNs ship cert
  chains with hostname-mismatched intermediates).
- `extract_text_from_pdf` prefers `opendataloader_pdf` and falls back to
  PyMuPDF (`fitz`).
- A per-call junk-drop counter (`record_junk_dropped`) is written to
  `govt_collection_runs.urls_filtered_junk` for selector-drift detection
  (defect D-26).

### Cadence and known state

Govt-document and newspaper collections used to be once-daily crontabs;
because a single failed run would silence the pillar for 24h, the schedule was
moved to **every 12h** with a belt-and-braces safety re-fire when the last
successful run is >24h old. Per CLAUDE.md, the `documents` queue historically
had no consumer (now resolved — `worker-documents`, concurrency 2,
prefetch 1), which is why the database held only a handful of manually-run
rows for a period.

---

## 7. The source-adapter registration pattern

The registry (`backend/collectors/sources/registry.py`) is a simple,
extensible decorator-based plug-in system.

### How it works

```python
from backend.collectors.sources.registry import register_source

@register_source("rbi.org.in")
async def scrape_rbi_circulars(portal_url: str, document_type: str,
                               since_days: int = 2) -> list[dict]:
    ...
```

- `SOURCE_REGISTRY` is a `dict[str, ScraperFn]` mapping a **URL substring** →
  an async scraper with the shared signature
  `(portal_url, document_type, since_days) -> list[dict]`.
- **Auto-import:** on first lookup, every module under
  `backend/collectors/sources/*.py` (except `__init__` and `registry`) is
  imported so its `@register_source` decorators take effect.
- `govt_collector.py` consults the registry first and falls back to generic
  scrapers when no key matches.

### Adding a new source

1. Drop a new module (or a new function in an existing family module) under
   `backend/collectors/sources/`.
2. Decorate the async scraper with `@register_source("<url-substring>")`.
3. Return canonicalised dicts ready for DB insertion. No central wiring change
   is needed — auto-import discovers it.

### Article-source registry (separate)

The *article* pillar also has a source registry concept via the `sources`
table, which carries:
- `source_type` (`rss` / `html`) — selects the entry-point tier.
- `source_tier` (integer 1/2/3) — priority/quality tier.
- A **health-scoring system** that auto-disables a source
  (`is_active = false`) after **10 consecutive failures**. This is a soft
  circuit-breaker; `tasks.reset_source_circuit_breakers` runs weekly (Monday
  00:00 UTC) to revive floored sources. **Caveat from the onboarding doc:**
  ~30–50% of currently-disabled sources are actually alive — they were
  bulk-disabled by an uncommitted manual SQL run on 2026-04-25; 174 of 406
  have been re-enabled after live probe, ~232 remain.

---

## 8. The relay pattern (general)

Several pillars share one defensive pattern: **never fetch a ban-prone target
from the central server's data-centre IP.** Instead:

1. The server does the cheap/safe part (RSS discovery) and queues work into a
   DB table.
2. A **relay** — a small HTTP service on a *residential* machine reachable
   over **Tailscale** — does the ban-prone fetch using authenticated
   sessions/cookies.
3. The relay writes results back to the DB; the server processes them.

| Relay | File | Port | Auth | Configured via |
|---|---|---|---|---|
| YouTube transcripts | `youtube_v2/transcript_relay.py` | 8888 | `yt-dlp` + throwaway-account `cookies.txt` | `YT_RELAY_URL`, `YT_COOKIES` |
| Instagram | `instagram_relay.py` | 8890 | `sessionid` cookie | `INSTAGRAM_RELAY_URL`, `INSTA_SESSIONID` |

The relay pool can have multiple residential IPs; the server round-robins
fetches across healthy ones, and total throughput scales linearly with the
number of healthy IPs.

---

## 9. Scheduling cadence (summary)

All cadences are defined in the Celery Beat schedule in
`backend/celery_app.py`. Selected entries:

| Task | Cadence | Queue |
|---|---|---|
| `tasks.collect_rss` (FreshRSS) | every 15 min | `collectors` |
| `tasks.collect_rss_direct` (tier-2) | every 30 min | `collectors` |
| `tasks.collect_html` (tier-3) | every 6 h | `collectors` |
| `tasks.discover_youtube_channels` | every 30 min | `collectors` |
| `tasks.fetch_youtube_transcripts` (relay) | normally ~3 min (~20/hr); **currently 360 min cool-down** | `youtube` |
| `tasks.run_youtube_extraction` | every 5 min | `youtube` |
| `tasks.drain_pending_clips` | every 10 min | `youtube` |
| `tasks.collect_newspapers` (primary) | 02:00 UTC daily | `documents` |
| `tasks.collect_newspapers_fallback` | 03:00 UTC daily | `documents` |
| `tasks.drain_pending_clippings` | every 10 min | `documents` |
| Govt-doc collection | every 12 h (+ >24h-stale re-fire) | `documents` |
| `tasks.fetch_og_images_batch` (thumbnails, Playwright) | every 10 min | `collectors` |
| `tasks.backfill_bylines_periodic` | every 6 h | `collectors` |
| `tasks.refresh_rss_urls` (follow 30x redirects) | every 6 h (`*/6 :20`) | `collectors` |
| `tasks.reset_source_circuit_breakers` | weekly Mon 00:00 UTC | `collectors` |

Atlas-layer external scrapers (mandi prices, CPCB AQI, IMD weather, TGSPDCL
power, ACLED, welfare coverage) also run on `collectors` at 30-min to daily
cadences; their target tables are largely empty/planned at the time of
writing.

---

## 10. IP-reputation foot-guns

These are the operational traps that most often break ingestion:

1. **Never call `yt-dlp` / transcript-api raw from a debug shell on the
   server.** CLI probes burnt the server IP on 2026-05-09; recovery is
   24–72h. All YouTube fetches must go through the throttled relay.
2. **A single residential IP YouTube-blocks above ~40/hr** (safe sustained
   ~20/hr). Pushing one IP to 60/hr solo blocked it after ~37 fetches.
3. **Keeping a YouTube tab open** in the browser the relay cookies were
   exported from rotates the session cookie and silently invalidates the
   export.
4. **Govt CDN cert chains** are frequently mis-issued — `download_pdf` uses
   `verify=False` deliberately; do not "fix" it.
5. **Anti-bot detection on Indian govt portals** rejects httpx UAs from
   data-centre IPs, forcing the slow/expensive Playwright tier-4 path.

---

## 11. How raw items enter the pipeline

Every pillar lands raw items in a pillar table with an "unprocessed" flag,
then an asynchronous enrichment/substrate pass drains them:

| Pillar | Landing table | Initial flag | Drained by |
|---|---|---|---|
| Articles | `articles` | `nlp_processed = FALSE` | `tasks.process_nlp_batch` (30s), `tasks.substrate_drain` (2 min) |
| Clips | `pending_youtube_videos` → `youtube_clips_v2` | `status='pending'` → clip `substrate_status='pending'` | relay (fetch) + `tasks.run_youtube_extraction` (5 min) + `tasks.drain_pending_clips` (10 min) |
| Cuttings | `clippings` | `substrate_status='pending'` | `clipping_enrich` + `tasks.drain_pending_clippings` (10 min) |
| Documents | govt-document tables | per-collector | govt enrichment tasks |
| Threads / Signals | `social_posts` | per-collector | social + NLP tasks on `social`/`nlp` queues |

The substrate enrichment then advances each row through a shared status
machine (`pending → processing → ok / extract_failed / junk`), producing the
summary, topics, entities, claims, quotes, stances, and embeddings that the
rest of the platform reads. Dedup is enforced at landing time (e.g. articles
on `url_hash`, pending videos on `video_id`).

---

### Items marked "not documented"
- **SearXNG as an article data source** — present as a web-search-proxy
  container, but no collector call into it was found in the reviewed files.
- Exact govt-document landing table name(s) and their initial status flag were
  not pinned down in the reviewed files (the registry, scraper cascade, and
  `govt_collection_runs` telemetry are documented; the final destination
  table is not quoted here).


---

# 4. Extraction, NLP, Embeddings, Clustering & Relevance

This section explains how a raw scraped article becomes structured intelligence:
the per-article fact substrate, the cross-lingual embedding, the same-event story
graph, and the per-user relevance score. For each stage we give the *logic* — why
it works the way it does — not just the table names.

The `articles` table is the spine. Every structured fact in the system is a child
row foreign-keyed back to `articles.id`. The pipeline is a fan-out of independent
Celery tasks, each gated on a status flag on the parent article row, so stages can
fail, retry, and drain independently without blocking each other.

---

## 1. The substrate v3 pipeline, end to end

"Substrate" is the project's name for the layer of structured facts extracted from
each article. It is "v3" because the extraction prompt is on its third generation
(tracked by `articles.extraction_version`: `v1` = legacy/unprocessed, `v2` = old
prompt, `v3` = current **Prompt G**, the winner of a 7-variant head-to-head eval on
2026-05-15/16).

### 1.1 Stage map

The pipeline is a sequence of status-gated Celery tasks. The core extraction is
**one structured-JSON LLM call per article** (Prompt G) that emits six child-table
payloads at once; translation, embeddings, entities, topics, and the byline/tweet
enrichers run as separate tasks around it.

| Stage | What it does | Where / model |
|---|---|---|
| **Collect** | RSS/HTML scrape writes a raw `articles` row (`substrate_status='pending'`). Dedup at insert via `url_hash` (SHA/MD5 of normalised URL); softer `canonical_url` dedup is secondary. | `collectors` queue |
| **Translate** | Original-language `lead`/`full_text`/`title` translated to English (`lead_text_translated`, `full_text_translated`). Quotes get `quote_text_en` + `speaker_name_en`. | Groq pool (`llama-3.1-8b-instant`) |
| **Extract** | The single Prompt G JSON call → 6 child payloads (quotes, claims, stances, numbers, events, locations). Sets `substrate_status` → `ok` / `junk` / `*_failed` and `extraction_version='v3'`. | `nlp` queue, `run_corpus_pass.py`, Groq pool |
| **Summary** | Per-card / per-panel LLM summaries (4-section card summaries, coverage panels). Article-level summary historically truncates ~85% of the time (`groq_semantic` single-call limit) — the fix is a split-summary call. | `llama-3.1-8b-instant` |
| **Claims** | Subject-predicate-object claim rows into `article_claims` (default `extracted_by_model='llama-3.1-8b-instant'`); contradictions cross-linked by an NLI pass into `article_contradictions` (`llama-3.3-70b-versatile`). | Groq pool |
| **Quotes** | Attributed quotations → `article_quotes` with speaker, role, context, char offsets, `is_direct`, and English translation. | `llama-3.1-8b-instant` |
| **Entities** | spaCy NER candidate spans → dictionary resolution → `entities_extracted` on the article + `article_entity_mentions` matview. | local spaCy (CPU), no LLM |
| **Stances** | Directed stance per (article, target-entity): `article_stances`. The author/source is the implicit agent; the row records the *target*. | Groq pool |
| **Sentiment** | Directed sentiment toward each target entity (the `stance` + `intensity` on `article_stances`); per-user sentiment surfaced as `sentiment_for_user`. | Groq pool |
| **Topics** | Classify into the closed `topic_categories` vocabulary (`topic_category` + finer `topic_fine`); unmatched → `OTHER`. | `topic_fill` task |
| **Speakers** | Speaker resolution on quotes — `speaker_entity_id` resolved against `entity_dictionary`. | within quotes extraction |
| **Embed** | LaBSE v4 vector written by `embed_fill` (independent of NLP; gated on `substrate_status='ok'`). | `embeddings` queue + GPU embed server |

### 1.2 Why one combined LLM call

Quotes, claims, stances, numbers, events and locations all require the model to
read and reason over the *same* article body. Issuing six separate calls would pay
the input-token cost six times and risk inconsistent reads. Prompt G asks for all
six payloads in a single JSON object, so the model reads once and emits a coherent
structured view. The trade-off is JSON fragility — a single malformed response
loses all six payloads — which is why the prompt opens with a strict "emit only
valid JSON, no prose" contract and a full schema block with per-field types,
nullability, and max-cardinality (locations ≤ 5, events ≤ 6).

### 1.3 Prompt G structure (the logic)

1. **Role + JSON-only contract** — forces machine-parseable output.
2. **Schema definition** — every field typed and bounded so the model cannot
   over-generate.
3. **Article-type vocabulary** — closed set of 12 types
   (`news, opinion, analysis, explainer, listicle, horoscope, recipe, live_blog,
   photo_essay, interview, press_release, sports_result, other`); anything that
   doesn't fit → `other`. A closed set keeps downstream filters reliable.
4. **Location rules block (the most load-bearing section)** — three sub-rules:
   - *India city aggression*: if the body names any Indian district/town/mandal/
     constituency, `city` MUST be populated and country MUST be `"India"`.
   - *India anchor list*: a hard-coded place list (Hyderabad, Khammam, Bengaluru, …)
     to disambiguate against.
   - *State-vs-city decision tree*: a state-cabinet meeting in Hyderabad is a
     *Telangana* story (`region=Telangana, city=null`), not a Hyderabad story; a
     crash at a named Hyderabad landmark is a *city* story. National-level stories
     only get `city="New Delhi"` if the body anchors there. This rule is what stops
     the geo-relevance layer from drowning state stories in city noise.
5. **Few-shot location examples** — worked examples lock the output shape.
6. **EVENT DATE RULE addendum** (the C→G difference) — every event must carry a
   `date` (`YYYY-MM-DD` or explicit `null`), stopping the model from silently
   dropping date inference.

Post-drain quality (2026-05-16): ~1.4 quotes and ~3.2 claims per article (medians),
80% of claims rated factual on spot-check, 0% null-subject claims (a v2 failure mode
Prompt G eliminated).

### 1.4 The drain

`backend/tasks/substrate/run_corpus_pass.py` pulls rows where
`extraction_version != 'v3'` oldest-first, runs Prompt G, parses the JSON, inserts
to the six child tables transactionally, and stamps `extraction_version='v3'`.
`semantic_repass.py` is a sibling backlog driver — note its known quirk: it builds
its own provider list and historically ignored `LOCAL_LLM_PRIMARY`, so
`LLM_LOCAL_ONLY=1` is the reliable lever to force the local lane.

---

## 2. Translation & cross-lingual handling

The corpus is multilingual — English, Telugu (`te`), Hindi (`hi`) and others
(`articles.language_iso`, preferred over the legacy `language_detected`). The
strategy is **translate-to-English early, then operate in English** for extraction
and summarisation, while preserving originals:

- `lead_text_original` / `full_text_scraped` keep the source-language text.
- `lead_text_translated` / `full_text_translated` hold the Groq English translation.
- Quotes carry both `quote_text` (verbatim, original language) and `quote_text_en`,
  plus `speaker_name_en` for transliterated names.

Doing extraction on the English translation lets one English-tuned prompt (Prompt G)
serve every language. Cross-lingual *retrieval* is handled differently — by the
LaBSE embedding (§4), which is language-agnostic, so a Telugu article and an English
query land in the same vector space without translation.

---

## 3. Entities: extraction, resolution & disambiguation

Entity handling is a two-layer pipeline (`backend/nlp/` entities module) and is
deliberately **local/CPU, not LLM** — it runs on spaCy so it is cheap, deterministic,
and quota-free.

- **Layer 1 — spaCy NER** produces candidate spans from the article text.
- **Layer 2 — dictionary resolution.** Each span is resolved against
  `entity_dictionary` (the canonical vocabulary, ~11.6K rows). A module-level
  singleton `_ENTITY_DICT` is keyed by lowercased canonical name *and* every alias,
  giving O(1) lookup per span. A fuzzy `_ENTITY_NORM` map provides a normalized-surface
  fallback, but only for keys that resolve to a *single* canonical — ambiguous/homonym
  keys are dropped at load time to avoid wrong merges.

**Honorific stripping (migration 095, Tier 4).** Leading honorifics/office-titles/
article-particles (`Chief Minister`, `Sri`, `Dr`, `the`, `CM`, …) are stripped
*before* the dictionary lookup, so `"Chief Minister Revanth Reddy"` resolves to the
bare `Revanth Reddy` entry even when no alias was pre-loaded. Without this, fresh
titled mentions created brand-new duplicate entity rows (entity sprawl).

**Disambiguation.** `entity_aliases` is a small (~14-row) *curated* override table
holding `alias → canonical_name` plus a `notes` field explaining *why* — almost
entirely Telangana political figures where name collisions are common (e.g. KTR is
*not* KCR; "son of KCR — NOT KCR himself"). It includes Telugu-script aliases. It is
read only at dictionary *rebuild* time, not at query time.

**The resolution chain** (the mental model used everywhere): spaCy surface forms →
`entity_lookup` (normalized surface → `entity_id`) → `entity_dictionary` (canonical
entity) → `article_entity_mentions` matview (the shared, alias-resolved surface every
product joins to; mirrored per pillar as `clipping_entity_mentions` /
`youtube_clip_entity_mentions`, kept separate so article metrics stay article-only).

---

## 4. Embeddings: LaBSE v4, pgvector, throughput

### 4.1 The v4 recipe

The locked production recipe is **`v4-tr-title-1024`**: embed the **English-translated
title + lead** with `sentence-transformers/LaBSE`. `embed_fill` is the *sole owner*
of the vector columns — it writes both `labse_embedding` and `labse_embedding_v4` and
stamps `embedding_revision='v4-tr-title-1024'`.

**Why a single owner matters.** `nlp_processor` previously also wrote
`labse_embedding` using a *lead-only* recipe. Two incompatible recipes in one column
("recipe-mix drift") poisons cosine search and blocked `embed_fill` (which skips
non-null rows) from filling v4. The fix removed nlp_processor's write. **Practical
rule: always filter `embedding_revision = 'v4-tr-title-1024'` before any cosine
query**, because the legacy `labse_embedding` column still contains mixed-recipe rows.
Clipping/clip embeddings are *not* on the v4 recipe, so cross-pillar cosine is
unreliable.

### 4.2 Why LaBSE over BGE-M3

LaBSE is **cross-lingual by construction**: a Telugu sentence and its English
translation map to nearly the same vector, so an English query retrieves
Telugu/Hindi articles. A measured A/B against BGE-M3 was a **NO-GO**: LaBSE v4 beat
BGE-M3 by roughly +6.7 points overall and +12 points on Telugu specifically. The
project stays on LaBSE. (The known recall ceiling in clustering, §5, traces back to
this title+lead LaBSE embedding — an embedding upgrade is a deferred, post-launch
item, not a BGE swap.)

### 4.3 Storage & throughput

Vectors are stored in **pgvector** on `articles`. Embedding is an independent Celery
task gated on `substrate_status='ok'`. Throughput was a bottleneck — only ~52% of
articles were embedded, which is *why* there were few multi-article clusters. Two
fixes lifted it: a dedicated CPU `worker-embed` on its own `embeddings` queue
(~3,750/hr; the trap was a beat `options:{queue}` override) and a GPU LaBSE embed
server on the 4090 box (FastAPI on :8055 via autossh, `executemany` + no-sort
backfill ~41k/hr) to drain the 138k tail.

---

## 5. Clustering: same-event story graph (v8 keeper / v9 builder)

### 5.1 What the keeper is

The **live keeper** is the triple
`analytics.story_clusters_v8` / `story_cluster_members_v8` / `story_edges_v8`
(~200K clusters). It is a *graph*: `story_edges_v8` holds pairwise LaBSE-cosine
similarity between articles; `story_cluster_members_v8` records membership; every
enrichment table (`story_facts_v8`, `story_quotes_v8`, `story_timeline_v8`,
`story_geo_v8`, `story_sources_v8`, `story_stance_v8`, …) hangs off `story_id`.
LLM-generated headlines/decks/bodies live in `story_generated_v8` with a `member_hash`
regen-skip guard and a `guard_c` faithfulness JSONB.

### 5.2 How v9 builds it (the logic)

`cluster_v9` rebuilds the keeper with **igraph/Louvain** over the similarity graph
(run_id-stamped, additive, reversible); `_v9_graph_incr` extends it incrementally.
The v9 algorithm is **same-event clustering**, designed to put articles about the
*same event* together, not merely the same *topic*. Its three moves:

1. **Cascade candidate-gen** over cosine edges.
2. **Hub-purity split** — dense topic-cliques (e.g. "Iran") otherwise chain unrelated
   events through a hub article; v9 splits on hub purity. Resolution tuning (Leiden
   θ-sweep) is a *dead lever* here because the graph is dense cliques, not chains.
3. **2-vote recall** — a recall backstop that re-admits members two independent
   signals agree on.

**Surfaceable precision** is the metric that matters: among clusters large enough to
*show a user* (≥3 independent sources), how many are genuinely one event. v9 hits
**~80.7%** (≥3 src) versus a ~25% baseline. ~80% is the **hub-purity ceiling**;
breaking past 90% needs an edge-level rebuild (deferred).

A cluster is "surfaceable" when its discriminator fields agree:
`is_template_family`, `title_cohesion`, `entity_core_cov`, and
`independent_source_count` (= `min(distinct source_id, distinct reprint_key)` —
reprint-aware so wire reprints don't inflate the count).

### 5.3 Recall is bounded by design

Precision is high (~94% on the strict eval) but recall is ~40% — *only* big,
multi-angle mega-events fragment; normal stories cluster tightly (member-fit ~0.92).
This is candidate-gen-bound and rooted in the LaBSE title+lead embedding, **not**
fixable by θ-sweep / ef_search / full-text (all tested and rejected). Mega-events are
handled as **"B+" event hubs** (an umbrella card linking sub-stories), not force-merged.

### 5.4 The discriminator: entity-signature Jaccard

The split/keep decision uses a deterministic verifier: the **mean pairwise Jaccard of
each sub-community's top-5 entities**. Real mega-events that *should* split have a low
cross-child entity overlap; template piles that are accidentally grouped have high
overlap. The clean separation observed is ~0.112 vs ~0.152 (34/34), and the nightly
janitor's quality gate uses **θ = 0.195** (Gate B: cross-child entity-Jaccard < 0.195
to allow a split; Gate C: eject cosine < 0.80; Gate A: golden/recall backstop). The
janitor itself is an **LLM repair pass with an independent deterministic gate**:
triage → detector (Leiden + cross-model 2-vote, `gpt-oss-120b` + `qwen2.5:32b`) →
capped split/eject → per-story rollback of any failure, logged reversibly to
`story_repair_log_v8` / `story_repair_undo_members_v8`, armed nightly at 03:30 behind
a kill-switch.

### 5.5 Sagas / storylines layer

Above same-event clusters sits a **saga/storyline** layer
(`analytics.story_sagas` + `story_saga_members`): one card per *storyline*, showing
the latest chapter. It is built by **Louvain over article-surfaceable chapters**
(edges require ≥2 clean shared entities and cos ≥ 0.62), with a stable
`saga_id = uuid5(anchors + topic)`. The builder (`_saga_build.py`) runs on a 30-min
cron; a sample state was 119 sagas / 572 members (US–Iran = 45 chapters). Levers
`SAGA_COS_EDGE` / `MIN_SHARED` tune over-grouping.

> **Chronicle caveat (known trap):** `chronicle_cache` and `user_story_assignments`
> foreign-key to the *frozen* `story_clusters_archive` (34,599 stories), while
> `chronicle_router.py` queries unsuffixed `story_*` names that do not exist — an
> unresolved naming mismatch that breaks Chronicle reads at runtime.

---

## 6. Directed stance vs emotion (the known trap)

This is the single most error-prone distinction in the schema. Two columns look like
they measure "negativity"; only one does.

| | `article_stances` | `register_emotion` (on `articles`) |
|---|---|---|
| **Measures** | **Directed stance** toward a target entity | **Event-emotion** of the story |
| **Use for** | Negativity, bias, hostility toward an entity | Nothing bias-related |
| **Example** | "critical of KCR" → stance row | `alarm` on a flood story is about the *flood*, not editorial hostility |

**Always use `article_stances` for any negativity/bias measure. Never use
`register_emotion` as a hostility proxy** — its `alarm` is event-emotion and skews
everything negative.

**Second trap inside `article_stances`:** the column literally named **`actor` is the
TARGET of the stance, not its actor.** The article's source is the implicit agent.
To ask "what is the sentiment toward KCR?", filter `actor = 'KCR'` (or
`actor_entity_id = <KCR uuid>`). This is a legacy naming bug; the true semantic is
`target`. One row per (article, target-entity); `stance` ∈
{`positive`,`negative`,`neutral`,`critical`,`supportive`,…}, `intensity` 0.0–1.0,
auto-linked to `entity_dictionary` by the `trg_link_stance_entity` trigger.

---

## 7. Sentiment (directed) & topics

**Directed sentiment** is not a single article-level score. It is the per-target
`stance` + `intensity` in `article_stances` (§6). When surfaced to a user it becomes
`sentiment_for_user` — the sentiment of the article *toward that user's tracked
entities*, computed during relevance scoring (§9). This avoids the classic mistake of
calling an article "negative" when it is merely critical of one named entity.

**Topics** use a closed vocabulary in `topic_categories` (~25 rows): the original 15
coarse `topic_category` values (`is_new=FALSE`) plus 10 finer `topic_fine` buckets
(`is_new=TRUE`), with `rolls_up_to` mapping each fine bucket back to a coarse parent.
The `topic_fill` task classifies each article into this set. **`OTHER` is the explicit
escape hatch** — anything that doesn't fit a defined category is bucketed to `OTHER`
rather than forced into a wrong one (mirrors the `other` article-type handling in
Prompt G). Live distribution skews `Politics`, `Crime`, `Economy`, `International`.

---

## 8. Claims, quotes & speakers

- **Claims** (`article_claims`) are subject-predicate-object triples:
  `claim_text`, `subject_text` / `subject_entity_id`, `predicate`, `object_text`,
  `confidence` (default 0.5), with a `vector(768)` embedding for claim-level
  similarity. Default extractor `llama-3.1-8b-instant`. Divergent claim *pairs* are
  cross-linked into `article_contradictions` by an NLI pass
  (`llama-3.3-70b-versatile`), enabling "who disagrees" views.
- **Quotes** (`article_quotes`) are attributed quotations: `quote_text` (verbatim,
  original language) + `quote_text_en` (translation), `speaker_name`, `context`,
  `char_offset_start/end` (provenance back into the body), and `is_direct`
  (verbatim vs paraphrase). Populated by `llama-3.1-8b-instant`, gated on
  `quotes_extracted=false`.
- **Speakers** are resolved *within* quote extraction: the raw `speaker_name` is
  matched to a canonical `speaker_entity_id` in `entity_dictionary`, so quotes can be
  retrieved by speaker even across spelling/transliteration variants.

---

## 9. Relevance scoring (v3) & cross-pillar

> **Doc reconciliation note.** The onboarding file `03-relevance-system.md` describes
> v3 as "designed but not implemented." That doc is **stale** relative to production:
> the live `user_article_relevance` schema and the `worker-relevance` queue show the
> v3 scorer **is running** (it writes `score_stage1`, `score_final`,
> `geo_multiplier_applied`, `relevance_tier`, `sentiment_for_user`,
> `matched_entity_names` per (user, article)). The description below reflects the live
> schema; the layered-embedding/behaviour roadmap in the onboarding doc is the *next*
> evolution, not the current state.

### 9.1 The two-stage score

The v3 scorer (`tasks/relevance`, `worker-relevance`, concurrency 4) writes one row
per (user, article) and computes the score in two stages:

1. **Stage 1 (pre-geo): `score_stage1` = canon + recency + mute.**
   - **Canon** — weighted match of the article's resolved entities against the user's
     watchlist (`user_watched_entities`); `matched_entity_names[]` records the hits.
     Entity importance and match count feed the weight.
   - **Recency** — a freshness boost so newer matches outrank stale ones.
   - **Mute** — explicit user suppression of entities/sources subtracts.
2. **Stage 2 (post-geo): `score_final` = `score_stage1 × geo_multiplier_applied`.**
   - The geo multiplier boosts/penalises based on how the article's primary
     location (from `article_locations`, §1.3) aligns with the user's geographic
     interest (`geo_states`, weighted-by-state). NULL = no geo adjustment. This is
     where the Prompt G state-vs-city discipline pays off: a clean primary location
     keeps geo weighting accurate.

`relevance_tier` is an integer bucket used for feed pagination; `sentiment_for_user`
attaches the directed sentiment (§6/§7) toward the user's matched entities; the human
`relevance_explanation` records which factors fired.

### 9.2 Cross-pillar scoring

The same scorer is mirrored across pillars so the Entity page can rank all evidence
types together:
- `user_article_relevance` (articles) — dominant by volume.
- `user_clip_relevance` (YouTube clips) — event-driven, quality noted as strong.
- `user_cutting_relevance` (newspaper clippings, migration 114) — event-driven after
  clipping enrichment; coverage noted as **weak / geo-over-surfacing** (the cuttings
  geo signal over-fires relative to entity surfacing).
- `score_govt_doc_relevance` scores government documents on the same model.

All share the `score_stage1 / score_final / geo_multiplier / relevance_tier /
matched_entity_names` shape, which is what lets the Entity page interleave articles,
clips and cuttings into one ranked cross-pillar feed.

### 9.3 The new-user cold-start problem

The canon layer needs a non-empty watchlist to score above zero, so a brand-new user
with an empty `user_watched_entities` sees an empty feed. Today's mitigation is
seeding super-admins with a default org watchlist; the onboarding doc's Layer-2
(semantic centroid) / Layer-3 (behaviour learning) plan is the intended fix so every
user gets *some* score regardless of watchlist depth.

---

## 10. Substrate status states & row flow

Each article carries `substrate_status` (extraction lifecycle) plus independent
boolean/timestamp gates for the parallel stages. Stages do not block one another —
embeddings and NLP both simply gate on `substrate_status='ok'`.

| `substrate_status` | Meaning |
|---|---|
| `pending` | Collected, not yet extracted (recent uncollected tail). |
| `ok` | Prompt G succeeded; six child tables populated. The gate for embed + downstream NLP. |
| `junk` | Model classified the row as non-article / no extractable content. |
| `fetch_failed` | Body could not be fetched. |
| `extract_failed` | LLM/JSON extraction failed. |

Companion gates on the `articles` row drive the other tasks independently:
`extraction_version` (`v1`→`v2`→`v3` drain progress), `nlp_processed`,
`quotes_extracted`, `embedding_revision` + `embedded_at`, `substrate_processed_at`.

**Flow:** `collect` → row at `pending` → **extract** flips to `ok`/`junk`/`*_failed`
and stamps `extraction_version='v3'` → in parallel, gated on `ok`: **embed_fill**
writes the v4 vector (`embedded_at`), the **entity** task fills `entities_extracted`,
the **topic** task fills `topic_category`, and the remaining substrate enrichers run.
Pipeline-lag views (`pipeline_lag_view`, `v_freshness_*`) track p50/p95 minutes from
`collected_at` to `embedded_at` / `substrate_processed_at`, against an hourly
freshness target.

> **Operational footgun:** orphaned rows can wedge in a `processing` state (hard-kill
> leaks); these are reclaimed by a SKIP-LOCKED reset plus a cron orphan-reset guard
> (gated on `collected_at` older than ~20 min) — a missing summary/claim is usually a
> wedged row or LLM-quota starvation, *not* a code defect.


---

# 5. Database & Storage

RIG Surveillance is a database-centric system: nearly every pillar (Articles, Clips,
Cuttings, Threads, Signals, Documents, Brief, Analyst) is ultimately a different read
view over one PostgreSQL instance. This section documents the engine, schema layout,
the ~134 relations grouped by domain, embedding storage, materialized views, migration
conventions, and the known data-health traps.

> **Provenance.** The table-level facts here are drawn from
> `docs/handoffs/db-reference/` (a field-level reference generated 2026-06-19 from the
> *live* schema via `pg_class`/`pg_attribute`, `COMMENT ON` metadata, the migration
> files, and real sampled production values) and from the migration files themselves
> (`scripts/migrations/*.sql`). Row counts and freshness timestamps are point-in-time
> snapshots (2026-06-19) and drift with ingestion. Anything not verifiable from those
> sources is marked **(inferred)** or **(unknown)**.

---

## 1. Engine & deployment

- **Engine:** PostgreSQL 16 with the **pgvector** extension, running as the
  `rig-postgres` container from the **`ankane/pgvector`** image (see project
  `CLAUDE.md` and `infrastructure/docker-compose.yml`). pgvector supplies the
  `vector` column type used for LaBSE embeddings (see §6).
- **Host / access:** Single instance on the Hetzner host. Maintenance access is
  `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154` → `docker exec -i rig-postgres
  psql -U rig -d rig`. The superuser/owner role is `rig`; the database is `rig`.
- **Backend coupling:** Backend code is bind-mounted `/root/rig → /app`. Two backends
  read this database: the night-desk live API (`products/osint/backend`, FastAPI) and
  the ingestion stack (`backend/` — FastAPI + Celery workers). Neither bakes the DB;
  the DB is its own container with its own volume.

### How migrations apply at first boot

Migrations live in `scripts/migrations/NNN_*.sql` and are wired into the Postgres
image's standard **`docker-entrypoint-initdb.d`** mechanism: on a *fresh* data
directory (first boot only), the official Postgres entrypoint executes every script
it finds there in **lexical filename order**, which — given the zero-padded numeric
prefixes — is the intended apply order. Consequences worth internalizing:

- The init scripts run **once**, only when the data volume is empty. On an existing
  volume they are skipped. Schema changes against a live database are therefore
  applied manually (`psql -f`), not by restarting the container.
- Because apply order is purely lexical, the numeric prefix *is* the dependency
  contract. Two files sharing a prefix (e.g. `038_districts_resolution.sql` and
  `038_seed_telangana_district_sources.sql`) are ordered by their suffix string —
  acceptable only when they are genuinely order-independent.
- Several migrations seed fallback rows at creation time (e.g.
  `040_coverage_panel_summaries.sql` inserts static panel text) specifically so the
  first page load isn't empty before the relevant cron has run.

---

## 2. Schema overview — `public` vs `analytics`, and `analytics_user`

The database spans **two schemas** (per the 2026-06-19 reference: 134 relations —
tables + views + matviews — and 1,325 columns total):

| Schema | Contents | Write access |
|---|---|---|
| `public` | The ingestion corpus and all derived per-article substrate: `articles`, `sources`, the eight `article_*` substrate tables, entities, clippings, YouTube, districts, the older `public.users` RBAC system, and the legacy product layer (`event_clusters_archive`). | Owned/written by the ingestion backend (`rig`). |
| `analytics` | The night-desk product layer: the `story_*_v8` clustering keeper and its enrichment/generation tables, the night-desk user system (`analytics.users`, `analytics.orgs`, `analytics.user_brief_prefs`), entity-image cache, translation cache (`analytics.text_en`), and various caches. | Read-write for the `analytics` role; **read-only** for `analytics_user`. |

### The `analytics_user` read-only role

`analytics_user` is a deliberately constrained role: **read-only on `public.*`,
read-write on the `analytics` schema** (the constraint is Postgres-enforced via
GRANTs, not application convention). The night-desk live API connects as
`analytics_user`, which means:

- It can freely write its own product artifacts (story enrichment, caches) into
  `analytics.*`, but
- It **cannot mutate the corpus** — `public.articles` and all substrate are
  read-only to it. Corpus writes flow exclusively through the ingestion backend.

This split is the storage-level enforcement of the "global ingestion, per-user
product view" architecture.

---

## 3. The ~134 relations grouped by domain

The master table below groups the **key** relations by domain. It is not exhaustive
(134 relations total); it lists the spine tables and the ones a reader must know to
reason about the system. Row counts / sizes are the 2026-06-19 snapshot.

| Domain | Key relation(s) | Schema | Kind | Purpose |
|---|---|---|---|---|
| **Corpus / substrate** | `articles` (~354,839 rows, 9.6 GB) | public | table | Spine of the corpus — one row per collected article/page; every substrate table FKs back here. |
| | `sources` | public | table | Registry of RSS/HTML origins that feed `articles`. |
| | `article_claims`, `article_stances`, `article_quotes`, `article_numbers`, `article_events`, `article_locations`, `article_media`, `article_links` | public | tables | The eight v3-substrate child tables, one fact-type each, populated per-article by Groq tasks on the `nlp` queue. |
| | `article_tweets`, `article_contradictions` | public | tables | Embedded-tweet scrape; NLI-flagged divergent claim pairs. |
| **Entities** | `entity_dictionary` (~19,356 canonical entities) | public | table | Canonical entity registry: `canonical_name`, `entity_type`, country/state/party. |
| | `entity_lookup` (~55k rows) | public | table | Exact `name_norm → entity_id` surface-form index. |
| | `article_entity_mentions` (~1,307,767 rows, 292 MB) | public | **matview** | Canonical article↔entity cross-reference; the shared join surface for every product. |
| | `entity_mention_daily` (~320k rows) | public | table | Hourly cross-pillar entity aggregation (migration 113); the *only* path by which clips/clippings contribute entity signal. |
| | `analytics.entity_image` (~134 rows) | analytics | table | Cached entity-card image URLs (~0.7% entity coverage). |
| **Stances / sentiment** | `article_stances` (~483,322 rows, 100 MB) | public | table | Directed-sentiment, one row per (article, target-entity). See §7 trap: `actor` column is the **target**, not the subject. |
| **Clustering / stories** | `analytics.story_clusters_v8` (~200,823), `story_cluster_members_v8` (~325,077), `story_edges_v8` (~449,344) | analytics | tables | The **`_v8` keeper** — master cluster registry, membership, and the edge graph. `story_id` (uuid) is the stable cluster identity. |
| | `story_facts_v8`, `story_quotes_v8`, `story_sources_v8`, `story_timeline_v8`, `story_geo_v8`, `story_stance_v8`, `story_stance_by_source_v8`, `story_enrichment_status_v8`, `story_facts_series_v8` | analytics | tables | Per-cluster enrichment layer (facts, quotes, sources, timeline, geo, stance). |
| | `story_generated_v8` (~6,963) | analytics | table | LLM-generated story write-ups. |
| | `story_repair_log_v8`, `story_repair_undo_members_v8` (~30,692) | analytics | tables | Nightly janitor split log + reversible pre-split member snapshot. |
| | `story_clusters_archive` (34,599, FROZEN 2026-06-03) | analytics | table | Previous keeper, retained as rollback. |
| | `event_clusters_archive` (~6,859, FROZEN) | public | table | Legacy product-layer cluster engine. |
| | `chronicle_cache` | analytics | table | Single-row cache for the Chronicle deep-story page. |
| | **`story_sagas` / `story_saga_members`** | analytics | tables | Storyline/saga layer (one card per storyline, latest chapter; Louvain over chapters). **Not present in the 2026-06-19 reference snapshot** — added afterward per the RIG Wire saga work; treat schema details as **(unknown)** here, confirm against live `\d`. |
| **YouTube / clips** | `youtube_clips_v2` (~5,056, 50 MB) | public | table | **Current** live clips table (substrate-style). |
| | `youtube_clips` (~13,735, 118 MB, FROZEN 2026-06-07) | public | table | Legacy clips table; no child tables. |
| | `youtube_clip_claims`, `youtube_clip_quotes`, `youtube_clip_stances`, `youtube_clip_locations` | public | tables | Per-clip substrate children. |
| | `youtube_clip_entity_mentions` (~660) | public | matview | Clip↔entity mapping, kept separate so CM metrics stay article-only. |
| | `pending_youtube_videos` (~19,837, 38 MB) | public | table | Discovery→fetch queue (decoupled); `is_political` priority (mig 112). |
| | `youtube_channels` (~72), `newsroom_channels` (~25) | public | tables | Channel registries (clips vs the Newsroom /clips redesign). |
| | `newsroom_broadcasts`, `newsroom_segments` (~37), `newsroom_entity_mentions`, `newsroom_breaking_segments` | public | tables | NEWSROOM live-TV schema — largely **stalled since 2026-05-10** (see §7). |
| **Clippings / newspapers** | `clippings` (~12,180 rows) | public | table | **Current** cuttings table; full article substrate per row (OCR/vision extraction + enrichment). |
| | `newspaper_clippings` (FROZEN 2026-05-26, 387 MB) | public | table | Legacy cuttings (base64 image blobs); superseded by `clippings`. |
| **Districts / geo** | `article_districts` | public | table | Article↔district tagging (**tagging stalled** — last insert 2026-06-11). |
| | `mv_district_news_volume_24h` | public | matview | 24h district volume — currently EMPTY because tagging stalled. |
| | `district_geo_backfill_cursor` | public | table | Resumable backfill cursor per surface. |
| **Briefs & caches** | `coverage_panel_summaries` (~5) | public | table | One LLM 2–3 line summary per /coverage panel; daily 04:15 UTC refresh; seeded fallback. |
| | `brief_quality_scores` | public | table | Daily rubric scorecard for the Brief pillar. |
| | `content_items` | public | **view** | Unified read surface — `UNION ALL` of articles + clippings + clips, with `src` discriminator. |
| | `analytics.text_en` (~12,908) | analytics | table | Translation cache keyed by MD5 of source string. |
| **Users / RBAC / orgs** | `analytics.users` (6), `analytics.orgs` | analytics | tables | Night-desk staff accounts + org grouping; authz via `is_super_admin` bool. |
| | `analytics.user_brief_prefs` | analytics | table | Per-user brief personalization (watchlist/regions/topics/etc., all JSONB). |
| | `public.users` (3), `public.user_profiles` | public | tables | Older onboarding system; `role` text CHECK (`'user'|'super_admin'`). |
| | `user_page_access`, `impersonation_sessions`, `impersonation_actions` | public | tables | Page-grant RBAC + impersonation audit (hang off `public.users`). |
| | `user_*_relevance` (articles ~323k/131 MB, clips ~2.6k, cuttings ~6.9k, docs ~274) | public | tables | Per-user v3 relevance scores. |
| | `user_watched_entities` | public | table | Per-user ally/opponent/neutral entity buckets driving personalized scoring (mig 068). |
| | `analyst_sessions`, `analyst_turns` | public | tables | Per-user Analyst (RAG) chat. |

> **Two isolated user systems.** `analytics.users`/`analytics.orgs` (night-desk staff)
> and `public.users`/`public.user_profiles` (older onboarding) **share no ID space and
> no FK**. Code that queries one cannot join to the other without an explicit
> cross-schema lookup. This is a structural fact to respect, not a bug to "fix" in a query.

---

## 4. Embedding storage (pgvector)

- Article embeddings live on `articles` as **`labse_embedding`** plus
  **`labse_embedding_v4`**, both pgvector `vector` columns. The model is
  **LaBSE** (`sentence-transformers/LaBSE`, ~1.8 GB), which is cross-lingual: an
  English query embeds into the same space as Telugu/Hindi article text, enabling
  cross-lingual retrieval.
- The **locked V4 recipe** (`embedding_revision = 'v4-tr-title-1024'`) embeds the
  English-translated lead + title; `embed_fill` writes **both** columns. Embedding is
  an independent Celery task from NLP extraction, but both gate on
  `substrate_status = 'ok'`.
- Clippings and clips carry their own `labse_embedding` columns (surfaced through
  the `content_items` view), so vector search can span pillars.
- Query-side embedding is handled by `embedding.py` (`LabseEmbedder`); vectors are
  bound as text and cast `(:qvec)::vector` in SQL — never string-concatenated — so
  there is no injection surface on the vector path.
- The Threads pillar runs its own incremental HNSW-style clustering over article
  embeddings (cosine; assignment threshold 0.45, merge 0.20) rather than reusing the
  story-cluster graph.

---

## 5. The substrate pipeline & how rows link together

The corpus is a star schema with `articles` at the center:

```
RSS/HTML scrape ──▶ articles (raw collect)
                      │  substrate_status: pending → ok | junk | failed
                      ├─▶ article_claims / article_stances / article_quotes /
                      │     article_numbers / article_events / article_locations /
                      │     article_media / article_links   (FK article_id → articles.id)
                      ├─▶ embed_fill ──▶ labse_embedding(_v4)   (gated on status='ok')
                      └─▶ entities_extracted (JSONB) ──▶ refresh_article_entity_mentions()
```

### Key join paths

- **Article → source:** `articles.source_id → sources.id` (`sources` is the RSS/HTML
  origin registry).
- **Article → entities (the canonical path):** `articles.entities_extracted` (JSONB
  array of `{name,label}`) → `entity_lookup.name_norm` → `entity_lookup.entity_id` →
  `entity_dictionary.id`. This resolution is **materialized** into
  `article_entity_mentions`. Any product asking "which entities are in article X" or
  "which articles mention entity Y" should JOIN that matview, not re-resolve the JSONB.
- **Article → stance:** `article_stances.article_id → articles.id`; the stance's
  target entity is `article_stances.actor_entity_id → entity_dictionary.id` (note the
  `actor`-means-target trap in §7).
- **Article → cluster:** `story_cluster_members_v8.article_id → articles.id` and
  `story_cluster_members_v8.story_id → story_clusters_v8.story_id`. Enrichment tables
  (`story_facts_v8`, `story_quotes_v8`, …) all key on `story_id`.
- **Cross-pillar entity signal:** clippings and clips do **not** have entity-mention
  matviews into the article surface; they contribute only via
  `entity_mention_daily.n_entities` (migration 113). There are intentionally no
  `clipping_entity_mentions` / `youtube_clip_entity_mentions` *article-merged* tables.

---

## 6. Materialized views & the refresh cron

Several derived surfaces are PostgreSQL **materialized views**, not live tables —
they are stale until refreshed:

- **`article_entity_mentions`** (1.3 M rows) — the canonical article↔entity surface,
  rebuilt by the `refresh_article_entity_mentions()` function.
- **`youtube_clip_entity_mentions`** — clip↔entity mapping.
- **`mv_district_news_volume_24h`** — 24h district volume (currently empty; see §7).
- Plus CM/district matviews referenced by the refresh cron.

A host-level cron, **`/etc/cron.d/rig-matview-refresh`**, refreshes
`article_entity_mentions` together with the CM and district matviews on a **30-minute**
cadence — so the worst-case staleness on entity joins is ~30 minutes. (These matviews
previously had *no* scheduled refresh; the cron was added to fix silent staleness.)
Separately, `tasks.refresh_coverage_summaries` (Celery beat) refreshes the
`coverage_panel_summaries` cache daily at **04:15 UTC**.

---

## 7. Migration conventions

- **Naming:** `scripts/migrations/NNN_<name>.sql`, zero-padded numeric prefix. The
  prefix defines apply order at first boot (§1).
- **Idempotency:** Migrations are written to be re-runnable — `CREATE TABLE IF NOT
  EXISTS`, `ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, idempotent seed
  upserts (e.g. `040` explicitly notes "Idempotent — safe to re-run").
- **Numbering scheme & gaps:** The range runs 001 → 116 but is **not dense**, and
  prefixes are reused across feature lines (there are *two* `006_`, `008_`, `009_`,
  `010_`, `011_`, `031_`, `038_`, `039_`, `040_`, `041_`, `051_`, `052_`, `055_`,
  `056_`, `106_`, `109_` files). This reflects parallel feature branches that each
  grabbed the next free-looking number; it is a known smell, not an intended design.
  Treat the prefix as a *loose* timeline, and rely on the live schema (not the file
  set) as the source of truth.
- **What the major migrations do (representative):**
  - `001_initial_schema.sql` — base corpus schema.
  - `002_entity_dict_meta.sql` — entity dictionary metadata.
  - `003`/`004` — first YouTube clips + channel seeds.
  - `005`/`006`/`008` (newspaper) — newspaper clippings + editions.
  - `007`/`009`/`011` — social signals + signal intel.
  - `010_social_clusters.sql`, `042_breaking_clusters.sql`,
    `051_story_clustering_v2.sql`, `052_event_clusters.sql`,
    `055_cluster_importance.sql`, `056_entity_mention_daily.sql`,
    `061_drop_breaking_clusters.sql`, `070_narrative_clusters.sql` — the clustering
    lineage (several of these layers are now frozen/archived; see §8).
  - `031_rbac_and_impersonation.sql`, `115_user_roles.sql` — RBAC.
  - `036_brief_quality_scores.sql`, `040_coverage_panel_summaries.sql` — brief/caches.
  - `038`/`041_districts_multitenant.sql` — district resolution + multi-tenant.
  - `063_articles_substrate_cols.sql` + `064`–`068` — the v3 article substrate columns
    and child tables (links/media/locations/events) and `user_watched_entities`.
  - `106_youtube_clips_v2.sql`, `107_clippings_substrate.sql`,
    `108_youtube_substrate.sql` — moving clips and cuttings onto the article
    substrate model.
  - `109`–`112` (pending-YouTube) — fetch-status, extract-attempt counter, keep-all
    clips, transcript priority queue.
  - `113_entity_mention_daily_cross_pillar.sql`,
    `114_cross_pillar_relevance.sql` — cross-pillar entity + relevance.
  - `116_replay_clock.sql` — analytics replay clock (added during the OSINT desk audit).

  The full file list (88 files) is in `scripts/migrations/`. Note that many `cm_*`,
  `govt_*`, `dossier_*`, `social_*`, and `narrative_*` migrations exist on disk but
  created tables that were **dropped 2026-06-19** (see §8) — the migration files are
  historical, not a description of the current schema.

---

## 8. Data health & known issues

Read this before trusting any single table. (Verified against live production
2026-06-19 per `90-known-issues-and-data-health.md`.)

### Dropped pillars (not in the current schema)

The dead/frozen pillars — `cm_*`, `social_*`, `govt_*`, `dossier_*`, `narrative_*`,
and `story_threads` — were **dropped 2026-06-19** (drop list:
`docs/handoffs/db-cleanup-drop-list-2026-06-19.md`). Their migration files still exist,
which makes the file set a misleading map of the live schema.

### Frozen / stalled (rows exist but are STALE — do not treat as current)

- **`youtube_clips` (legacy)** — frozen since 2026-06-07; use **`youtube_clips_v2`**.
- **NEWSROOM** (`newsroom_broadcasts`/`_segments`/`_entity_mentions`) — effectively
  stalled since **2026-05-10** (2 broadcasts, 37 segments, 86 mentions; liveness
  checker last ran 2026-05-25; `newsroom_breaking_segments` empty).
- **`newspaper_clippings` (legacy)** — frozen since 2026-05-26; superseded by
  **`clippings`**. Still 387 MB on disk (base64 image blobs per row).
- **`article_districts` tagging stalled** — last insert 2026-06-11, so
  **`mv_district_news_volume_24h` is EMPTY** (24h window). The `tag_article_districts`
  task has stopped.
- **`pending_youtube_videos`** — 6 stale `fetching` rows from a 2026-06-17 relay
  crash; the dominant status is `skipped` (~14,337), the hourly newest-first cull
  bounding the queue.

### Semantic traps

- **`article_stances.actor` is the TARGET, not the subject.** The article's
  author/source is the implicit agent. To get "sentiment toward KCR", filter
  `actor = 'KCR'` (or `actor_entity_id = <uuid>`). This naming is a legacy bug; the
  semantic is `target`. Any negativity/bias measure built on the wrong reading of this
  column will be inverted.
- **`article_entity_mentions` can be up to ~30 min stale** (matview + cron). Don't
  assume freshly-ingested articles are already joinable to entities.
- **Two isolated user systems** (§3) — no shared IDs; cross-system "joins" silently
  return nothing.
- **`entity_image` coverage is ~0.7%** — most entities have no image; `ok=false` rows
  (16) mean "no image available". UI must degrade gracefully.

### Unknowns flagged in this section

- `story_sagas` / `story_saga_members` schema details — **post-date the 2026-06-19
  reference**; confirm against live `\d` before relying on column names.
- Exact GRANT statements behind `analytics_user` are described by behavior in the
  reference, not reproduced verbatim — verify with `\dp` if precise privileges matter.


---

# 6. Scheduling, Workers & LLM Infrastructure

RIG Surveillance runs every ingestion, enrichment, scoring, and
generation job through a single Celery cluster co-located inside the
`rig-backend` container, fed by a Celery Beat scheduler and supplemented
by host-level cron jobs on the Hetzner box. All LLM calls funnel through
one unified provider pool. This section documents that machinery exactly
as it is wired in the source — anything inferred from session notes
rather than read from code is marked **(memory)**, and anything the
files don't establish is marked **(unknown)**.

---

## 1. Celery architecture

### 1.1 Broker and result backend

The broker is **PostgreSQL, not Redis**. `backend/celery_app.py`
derives both URLs from `DATABASE_URL_SYNC`:

- **Broker**: `sqla+postgresql://…` (SQLAlchemy-backed Postgres broker).
- **Result backend**: `db+postgresql://…` (Postgres result store).

Serialization is JSON in/out (`task_serializer`, `result_serializer`,
`accept_content = ["json"]`), timezone is UTC, `enable_utc = True`.
Using Postgres as the broker means there is no separate message-queue
service to operate — the same `rig-postgres` container that holds the
corpus also carries the task queue. This is unusual and worth
remembering when reasoning about throughput: queue depth, locking, and
broker load all land on the database.

### 1.2 The queues and their consumers

Workers are **not** separate compose services. They are forked inside
`rig-backend` by `backend/start.sh` (baked into the image via
`infrastructure/Dockerfile.backend`, `CMD ["/start.sh"]`). The script
launches **seven Celery worker processes + Beat + uvicorn**.

> Note: the project `CLAUDE.md` table lists `collectors` at
> concurrency 1, but the live `start.sh` launches it at **concurrency
> 3**, and adds a **`whisper`** worker not shown in that table. The
> values below are read directly from `backend/start.sh` and are
> authoritative.

| Queue | Worker hostname | Concurrency | Extra flags | What runs on it |
|---|---|---|---|---|
| `collectors` | `worker-collectors` | 3 | `max-mem 2.5GB/child` | RSS collection, direct-RSS, HTML scraping, OG-image backfill, byline/tweet substrate backfill, RSS-URL refresh, circuit-breaker reset, YouTube channel discovery, atlas scrapers (mandi/AQI/IMD/power/welfare/ACLED) |
| `social` | `worker-social` | 2 | `prefetch-multiplier=1` | Reddit / Telegram (and hidden Twitter) signal ingestion + entity backfill. Isolated so social never starves behind a slow HTML scrape (the "SIG-11" fix) |
| `youtube` | `worker-youtube` | 1 | `max-mem 2.5GB/child` | Transcript fetch (via relay), clip extraction, clip substrate enrichment, pending-clip drain |
| `documents` | `worker-documents` | 2 | `prefetch-multiplier=1` | Govt-PDF collection + "doctor", newspaper edition collection (primary + fallback + single-paper), clipping substrate enrichment, pending-clipping drain. JVM-heavy PDF work is isolated from RSS here |
| `nlp` | `worker-nlp` | 4 | `max-mem 2.5GB/child` | Article NLP batch, **substrate drain** (summary/claims/quotes), journalist enrichment, entity-dict version check, quality postfix/regression/compare, entity-mention aggregation, embed-fill, topic-fill, contradiction refresh |
| `relevance` + `brief` | `worker-relevance` | 4 (shared) | `max-mem 2.5GB/child` | Per-user article + document relevance scoring, cross-pillar (clip/cutting) scoring, **and** daily brief fan-out + per-user brief generation. One worker drains both queues |
| `whisper` | `worker-whisper` | 1 | `prefetch-multiplier=1` | THE NEWSROOM 3-Lens transcript pipeline + live HLS channel monitors. Concurrency 1 because L3 local ASR is CPU-bound and a `live_monitor` streams a single channel for hours |

Each worker is capped at `--max-memory-per-child=2500000` (≈2.5 GB)
so a leaking child is recycled rather than OOM-killing the container.

### 1.3 Per-queue rationale

- **`collectors` (conc 3):** the busiest ingest lane. A single RSS or
  HTML scrape can run 30–60 min; concurrency 3 keeps Beat-scheduled
  collectors from backing up behind one slow source. When it does back
  up, the runbook flushes it selectively (see §6).
- **`social` / `documents` / `whisper` (`prefetch=1`):** prefetch is
  pinned to 1 so one long-running task (a slow Telegram pull, a heavy
  govt PDF, a multi-hour live monitor) cannot hold a second reserved
  task hostage behind it (a P5 fix, 2026-04-28).
- **`nlp` (conc 4):** the LLM-heavy substrate engine. The drain task
  uses `FOR UPDATE SKIP LOCKED`, so all four workers can pull article
  batches concurrently without colliding. Sizing note from the code:
  4 workers × ~200 articles/tick × 30 ticks/hr ≈ 24k articles/hr of
  headroom against ~30k/day intake.
- **`relevance`+`brief` shared (conc 4):** scoring is decoupled from
  NLP so per-user relevance never waits behind substrate work. Brief
  generation rides the same worker on its own queue.

---

## 2. How workers are launched — and the single-Beat rule

`backend/start.sh`:

1. **Stale-pidfile cleanup.** The Beat schedule DB and pidfile live on
   a persistent named volume (`rig-beat-schedule` → `/app/beat`). If
   Beat died ungracefully, its `celerybeat.pid` would block restart, so
   the script checks whether the PID is actually alive (`kill -0`) and
   clears the file only if it is stale.
2. **Forks the 7 workers** (each with `&`, backgrounded).
3. **Starts exactly one Beat** with a persistent schedule file:
   `celery beat --schedule=/app/beat/celerybeat-schedule
   --pidfile=/app/beat/celerybeat.pid`. The persistent schedule file
   matters: without it, a restart resets Beat's last-run timestamps and
   crontab/timedelta anchors drift — a once-daily newspaper cron could
   skip a day if the stack bounced between the prior run and the next
   anchor.
4. **`exec uvicorn backend.main:app` in the foreground** (port 8000,
   `--reload`) to keep the container alive (PID 1).

### The double-Beat foot-gun

There must be **exactly one** Beat process for the whole deployment.
Because workers + Beat live *inside* `rig-backend`, adding a separate
`rig-celery-worker-*` / Beat service to compose would create a **second
scheduler**, and every periodic task would **fire twice** — double
RSS pulls, double brief generation, double LLM spend. The project
`CLAUDE.md` flags this as a confirmed footgun. Orphan
`infrastructure-celery-worker-*` images on disk are remnants of an old
compose iteration and are not part of the running deployment.

---

## 3. Celery Beat periodic tasks

All entries from the `beat_schedule` dict in `backend/celery_app.py`.
Cadence is either a `timedelta` (relative interval) or a `crontab`
(wall-clock UTC). Times in IST are noted where the source comments give
them.

| Beat entry | Task | Cadence | Queue |
|---|---|---|---|
| collect-rss | `tasks.collect_rss` | every 15 min | collectors |
| collect-rss-direct | `tasks.collect_rss_direct` | every 30 min | collectors |
| collect-html | `tasks.collect_html` | every 6 h | collectors |
| backfill-bylines | `tasks.backfill_bylines_periodic` | every 6 h | collectors |
| backfill-tweets | `tasks.backfill_tweets_periodic` | every 6 h | collectors |
| fetch-og-images | `tasks.fetch_og_images_batch` | every 10 min | collectors |
| process-nlp | `tasks.process_nlp_batch` | **every 30 s** | nlp |
| substrate drain | `tasks.substrate_drain` | every 2 min | nlp |
| enrich-journalist | `tasks.enrich_journalist_batch` (batch 200) | every 5 min | nlp |
| reset-source-circuit-breakers | `tasks.reset_source_circuit_breakers` | Mon 00:00 UTC | collectors |
| refresh-rss-urls | `tasks.refresh_rss_urls` (limit 80) | every 6 h at :20 | collectors |
| reset-groq-keys | `tasks.reset_groq_keys` | daily 00:05 UTC | default |
| collect-newspapers (primary) | `tasks.collect_newspapers` | daily 02:00 UTC (07:30 IST) | documents |
| collect-newspapers (fallback) | `tasks.collect_newspapers_fallback` | daily 03:00 UTC (08:30 IST) | documents |
| drain-pending-clippings | `tasks.drain_pending_clippings` (limit 50) | every 10 min | documents |
| cross-pillar-relevance | `tasks.relevance.cross_pillar` (limit 400, 3 d) | every 15 min | relevance |
| discover-youtube-channels | `tasks.discover_youtube_channels` | every 30 min | collectors |
| fetch-youtube-transcripts | `tasks.fetch_youtube_transcripts` (limit 1) | every 360 min* | youtube |
| run-youtube-extraction | `tasks.run_youtube_extraction` (limit 10) | every 5 min | youtube |
| drain-pending-clips | `tasks.drain_pending_clips` (limit 20) | every 10 min | youtube |
| check-entity-dict | `tasks.check_entity_dict_version` | every 5 min | nlp |
| collectors-mandi-agmarknet | atlas mandi | every 4 h | collectors |
| collectors-cpcb-aqi | atlas AQI | every 30 min | collectors |
| collectors-imd-weather | atlas weather | every 1 h | collectors |
| collectors-tgspdcl-power | atlas power | every 30 min | collectors |
| collectors-welfare-coverage | atlas welfare | daily 04:15 UTC | collectors |
| collectors-acled-sink | atlas ACLED | every 6 h | collectors |
| quality-gold-regression | `tasks.quality.gold_regression` | daily 21:30 UTC (03:00 IST) | nlp |
| quality-postfix | `tasks.quality.postfix` (lookback 1 h) | every 15 min | nlp |
| quality-compare | `tasks.quality.compare` | daily 22:00 UTC (03:30 IST) | nlp |
| entity-mentions | `tasks.quality.entity_mentions` | every 60 min | nlp |
| embed-fill | `tasks.quality.embed_fill` | every 4 min | nlp |
| topic-fill | `tasks.quality.topic_fill` | every 5 min | nlp |
| contradictions | `tasks.refresh_contradictions` | daily 23:00 UTC (04:30 IST) | nlp |
| generate-briefs | `tasks.generate_all_briefs` | daily 00:30 UTC (06:00 IST) | brief |

\* **`fetch-youtube-transcripts` is in a deliberate cool-down.** The
schedule is set to 360 min (limit 1), not its calibrated ~20/hr rate.
The source comment records that both residential relay IPs were
throttled on YouTube's caption endpoint after a day of debugging
fetches; the rate was dropped so the IPs rest. Intended steady state is
`limit 1 / 3 min` (~20/hr per IP, round-robined across the relay pool).
This is a live calibration knob, not a fixed value.

**Disabled-in-place (commented out, kept for context):**
`cluster-importance` (disabled 2026-06-14 — read archived
`event_clusters`/`story_*` tables that no longer exist) and
`v3-upgrade-nightly` (disabled 2026-05-29 — new articles go straight to
v3, making the v1→v2 repass redundant).

---

## 4. Task routing (`task_routes`)

Routing in `celery_app.py` maps task names to queues. Highlights:

- **Collection → `collectors`:** `tasks.collect_rss*`,
  `tasks.collect_html`, OG-image fetch, byline/tweet backfill, RSS-URL
  refresh, circuit-breaker reset, all `tasks.collectors.*` atlas
  scrapers, and `tasks.discover_youtube_channels` (RSS discovery is
  IP-safe from Hetzner, so it stays on collectors).
- **LLM / substrate / quality → `nlp`:** `tasks.process_nlp_batch`,
  all `tasks.quality.*` (gold-regression, postfix, compare,
  entity-mentions, embed-fill, topic-fill, v3-upgrade), and
  `tasks.enrich_journalist_batch`.
- **Newspapers → `documents` (never `nlp`):** an explicit design rule
  (§6.2) — `tasks.collect_newspapers*`, `tasks.collect_one_newspaper`,
  `tasks.enrich_clipping`, `tasks.drain_pending_clippings`. The `nlp`
  queue is reserved for *article* NLP.
- **YouTube fetch/extract/enrich → `youtube`:**
  `tasks.fetch_youtube_transcripts`, `tasks.run_youtube_extraction`,
  `tasks.enrich_clip`, `tasks.drain_pending_clips`.
- **Scoring → `relevance`; briefs → `brief`:**
  `tasks.relevance.cross_pillar`, `tasks.relevance.score_one_clip`,
  `tasks.relevance.score_one_cutting` → `relevance`;
  `tasks.generate_all_briefs`, `tasks.generate_brief_for_user` →
  `brief`.

> **On `tasks.cm.*` (CM political-intelligence):** the project
> `CLAUDE.md` states CM tasks route to either `nlp` (LLM-heavy) or
> `social` (cheap aggregations). The current `celery_app.py`
> `task_routes` dict read for this document does **not** contain explicit
> `tasks.cm.*` entries — they are not in the routing table as checked
> in on this branch. The CM split is documented behavior **(memory)**;
> the exact current routing of CM tasks on this branch is **(unknown
> from the read files)** and should be re-verified against the deployed
> `celery_app.py` before relying on it.

---

## 5. Host-level cron jobs (`/etc/cron.d`)

Separate from Celery Beat, the Hetzner host runs standalone cron jobs
for work that sits outside the worker topology (matview maintenance,
graph/clustering builds, the broadcast engine, the nightly janitor).
These are described in the onboarding docs and session memory; the cron
*files* themselves live only on the host and were not read for this
document, so cadences below are sourced as noted.

| Cron job | Cadence | What it does | Source |
|---|---|---|---|
| `rig-matview-refresh` | every 30 min | Refreshes `article_entity_mentions` + CM + district matviews, which otherwise had no scheduled refresh | memory |
| `rig-saga` | every 30 min | Runs `_saga_build.py` — Louvain over article-surfaceable chapters to rebuild `analytics.story_sagas` + members (one card per storyline) | memory |
| `rig-v9-forward` | every 6 h | The v9 "smart" forward clustering loop (kill-switch `.v9_forward_OFF`, runaway tripwire). Supersedes the old cosine `rig-forward` cron (commented out) | memory |
| substrate orphan-reset guard | periodic (cron) | Resets rows wedged in `substrate_status='processing'` past a `collected_at > 20 min` gate, so hard-killed/leaked drains don't permanently stall summary coverage | memory |
| RIG World Brief broadcast | hourly | Generates the hourly AI news broadcast (engine repointed Ollama→TabbyAPI; ~17 min JSON; TTS via Chatterbox/CosyVoice) | memory |
| night-detector (janitor) | daily 03:30 | The `_v8` LLM story-repair pipeline: detector + writer with an eval-gate auto-halt and reversible undo; corrects cluster `dom_share` triage and splits over-merged megas | memory |

> These crons are **(memory)**-sourced. The authoritative definitions
> are the files under `/etc/cron.d/` on `root@178.105.63.154` (e.g.
> `rig-matview-refresh`, `rig-saga`, `rig-v9-forward`,
> `rig-broadcast`, `rig-saga`/janitor entries). Confirm exact minute
> fields and kill-switch paths there before editing.

---

## 6. LLM infrastructure — the unified pool

All model calls go through a single module-level singleton in
`backend/nlp/groq_client.py` (the `UnifiedPool` / `groq_manager`),
shared across every caller in a Celery process. The pool abstracts
**four provider lanes** behind one slot allocator: `local` (Ollama),
`lmstudio` (a TabbyAPI / OpenAI-compatible local node), `groq`, and
`cerebras`.

### 6.1 Models

The code's default models are **Qwen3-32B for both fast and quality**:

```
FAST_MODEL    = "qwen/qwen3-32b"
QUALITY_MODEL = "qwen/qwen3-32b"
```

`_resolve_chain()` builds an ordered try-list per call:

- Fallback off (`LLM_MODEL_FALLBACK=0`) → single model (legacy,
  byte-for-byte behaviour).
- Fast task types → cheap-fast chain
  `["llama-3.1-8b-instant", "llama-3.3-70b-versatile", qwen3-32b]`.
- Explicit model → honour it, then append the shared fallback tail.

> The onboarding doc `05-llm-infrastructure.md` describes an older
> three-provider picture (24 Groq keys on llama-3.1-8b / llama-3.3-70b,
> 27 Cerebras keys on llama-3.3-70b, 1 Ollama slot on qwen3:30b-a3b).
> The current `groq_client.py` has **evolved past that doc**: Qwen3-32B
> is now the primary model, and an `lmstudio` (TabbyAPI) lane has been
> added. Treat the table below (from code) as current and the doc's
> table as historical baseline.

### 6.2 Providers, quota, and key rotation

| Lane | Source of slots | Model(s) | Quota / limit | Notes |
|---|---|---|---|---|
| **Groq** | `GROQ_API_KEYS` (≈24 keys, per doc) | `qwen/qwen3-32b`, `llama-3.1-8b-instant`, `llama-3.3-70b-versatile` | ~6K TPM per key, resets per-minute | Round-robin with per-key cooldown |
| **Cerebras** | `CEREBRAS_API_KEYS` (≈27 keys, per doc) | mapped from Groq model via `_GROQ_TO_CEREBRAS_MODEL` (e.g. 70b → `zai-glm-4.7`) | 1M TPD per key (≈27M/day), resets 00:00 UTC | Cross-provider failover when Groq pool is cooled |
| **local (Ollama)** | `OLLAMA_BASE_URL` (default `http://100.92.126.27:11434`, TRIJYA-7 Tailscale IP) | `qwen3:30b-a3b` (default) | No quota; capped by `LOCAL_LLM_MAX_CONCURRENT` (default 4) | Native `/api/chat` with `think:false`, `format:json` |
| **lmstudio (TabbyAPI)** | `LMSTUDIO_BASE_URL` + `LMSTUDIO_MODEL` | local EXL3 model | `LMSTUDIO_CLIENT_SLOTS` (default 8, clamped ≤16) | OpenAI-compatible local node; only added when base+model are set |

**Key rotation & cooldown (Groq/Cerebras):** each key/slot is a
`_UnifiedSlot`. On HTTP 429 the slot is stamped with a cooldown
(`_cooldown_seconds = 15s`, hard-clamped at `_max_cooldown_seconds =
300s`). The 15s value is deliberate (was 60s; cut 2026-05-28 because
Groq TPM 429s usually clear in 5–15s and 60s held keys out 4× too
long). The clamp exists because Groq's error parser sometimes
misclassified a per-minute (TPM) limit as a daily (TPD) one and
requested multi-hour holds, blacking out the pool; the clamp caps the
worst-case stall and lets the next probe re-cool if it really is TPD.
When every slot is cooled, the pool raises `GroqQuotaExhausted`. A Beat
task at **00:05 UTC (`tasks.reset_groq_keys`)** clears any stale
cooldowns. Cerebras 429s are bucketed TPM vs TPD by inspecting the
error body.

**Custom exceptions:** `GroqQuotaExhausted` (all keys cooled — pause &
retry after reset), `GroqCallFailed` (non-quota: network/auth/malformed),
`OllamaCallFailed` (local HTTP/body failure).

**Cloudflare-WAF dodge:** the Groq SDK's default httpx User-Agent
triggers `error code: 1010` (403). The pool overrides it with a real
browser UA — without this, every Groq call 403s and logs phantom
"rate limit" errors.

### 6.3 Local-first slot selection

`UnifiedPool.get_slot()` implements the preference order:

1. If `LOCAL_LLM_PRIMARY` (default **on**, `=1`), iterate slots and
   prefer any `local`/`lmstudio` slot first.
2. Under `LLM_LOCAL_ONLY=1`, return **only** a local slot — cloud lanes
   (`groq`, `cerebras`) are excluded from the pool at build time.
3. If a local slot is busy beyond `_LOCAL_MAX_CONCURRENT`, fall through
   to cloud (Groq → Cerebras overflow).
4. If everything is cooled, return the **soonest-to-recover** slot
   rather than failing hard.

Concurrency on local lanes is gated by `_local_inflight` against
`LOCAL_MAX_CONCURRENT`; `release_local()` decrements it after each call.
This is the mechanism that keeps a 2 GB-class GPU from being asked to
run more inflight generations than it can hold.

Env contract (from doc + code):

| Env var | Default | Effect |
|---|---|---|
| `LOCAL_LLM_ENABLED` | 1 | If 0, local lane removed (cloud-only; used in CI) |
| `LOCAL_LLM_PRIMARY` | 1 | Try local first, cloud as fallback |
| `LOCAL_LLM_MAX_CONCURRENT` | 4 | Inflight local-call cap |
| `LLM_LOCAL_ONLY` | 0 | If 1, **only** local slots (the watchdog's hammer) |
| `OLLAMA_BASE_URL` | `http://100.92.126.27:11434` | TRIJYA-7 |
| `LMSTUDIO_BASE_URL` / `_MODEL` | (unset) | Enables the TabbyAPI lane |

### 6.4 Local GPU nodes (memory)

The local lanes are backed by two Windows GPU workstations reached over
Tailscale + autossh tunnels into the Docker subnet:

- **TRIJYA-7 (RTX 4090):** runs TabbyAPI + ExLlamaV3 serving
  **Qwen3-14B-EXL3** (recovered from a Code-43 driver fault; cache 65536
  ≈ 8 concurrent without wedging). Also the original Ollama node
  (`qwen3:30b-a3b`, `OLLAMA_NUM_PARALLEL=1`, `OllamaServe` Windows
  scheduled task).
- **TRIJYA-8 (RTX 4070):** runs TabbyAPI + ExLlamaV3 + **Qwen3-14B-EXL3**
  on `:5000`, wired into the pool as the `lmstudio` lane via an autossh
  tunnel (`172.30.0.1:5000` → node `127.0.0.1:5000`, IPv4-only, UFW 5000
  open) and a compose env block. ~76 client slots; patched to be
  **local-first** so it is preferred even under `skip_local`.

Tunnels are **not reboot-safe** by default; on a node reboot the
autossh tunnel and/or the TabbyServe watchdog must come back before the
lane is healthy. Heavy generation and visible-window tasks are kept off
the in-use workstation node where noted.

### 6.5 The drain watchdog (memory + doc)

A small bash watchdog on Hetzner (`/tmp/drain_watchdog.sh`) does two
jobs in a loop: (1) probes remaining Cerebras TPD across the keys via
`/tmp/probe_cerebras.py` and, when aggregate budget drops below ~5%,
flips the substrate drain into `LLM_LOCAL_ONLY=1` (LOCAL_ONLY) mode;
at the 00:00 UTC reset it flips back to MIXED; (2) restarts the drain
process if it dies. This is the **only** TPD-budget protection — the
pool's per-call rotation tracks RPM/TPM but not the daily budget, so an
unsupervised run can burn most of a day's Cerebras tokens in hours.

---

## 7. The embeddings GPU server

Embeddings are LaBSE vectors stored in `articles.labse_embedding` /
`labse_embedding_v4` (pgvector). Two paths exist:

1. **In-process, scheduled (canonical):** `tasks.quality.embed_fill`
   (`backend/tasks/embed_fill_task.py`) runs **every 4 min** on the
   `nlp` queue. It selects up to 250 newest articles that have a
   **translated** lead but no embedding (V4 SSOT eligibility — embedding
   pre-translation craters cross-lingual recall), builds the embedding
   text via `embedding_recipe.build_embedding_text`, and embeds with the
   local LaBSE model (`get_labse_model()`). It exists because embeddings
   were once produced only inline by the legacy NLP path; when the
   substrate pipeline replaced it (no embed step), `labse_embedding`
   silently went NULL (2026-06-11). This task closes that gap
   permanently regardless of which pipeline writes the article.

2. **GPU embed server (backfill, memory):** a standalone FastAPI LaBSE
   service on the **TRIJYA-7 4090** (`:8055`, reached via autossh
   `172.30.0.1:5055`, UFW 5055) was built to drain the ~138k-vector
   backfill tail at ~41k/hr using `executemany` + no-sort. A dedicated
   CPU `worker-embed` on its own `embeddings` queue (~3,750/hr) was also
   added for steady-state throughput. **(memory)** — these throughput
   components are described in session notes; the live `start.sh`
   read for this document does **not** show a `worker-embed` process,
   so whether the dedicated embed worker/queue is currently part of the
   baked image is **(unknown)** and should be confirmed via
   `docker exec rig-backend ps -ef`.

---

## 8. Source-of-truth quick reference

- **Queues, concurrency, Beat launch:** `backend/start.sh` (baked via
  `infrastructure/Dockerfile.backend`).
- **Task routing + Beat schedule:** `backend/celery_app.py`
  (`task_routes`, `beat_schedule`).
- **LLM pool, models, key rotation, slot selection:**
  `backend/nlp/groq_client.py`.
- **Embedding fill:** `backend/tasks/embed_fill_task.py`.
- **LLM provider/quota/watchdog narrative:**
  `docs/onboarding/05-llm-infrastructure.md` (historical baseline) +
  `06-operations-runbook.md` (ops procedures).
- **Host crons:** `/etc/cron.d/*` on `root@178.105.63.154` (not in the
  repo; the authoritative cron definitions).
- **Live truth:** `docker exec rig-backend ps -ef` — what is actually
  running.


---

# 7. Features, API Surface, RAG & Access Control

> Scope: the **OSINT product** (`products/osint`) — its FastAPI backend
> (`products/osint/backend`), the **night-desk** React client
> (`products/osint/design/night-desk`), and the **Ask-RIG** RAG sidecar
> (`products/ask-rig`). This is the user-facing intelligence surface that sits
> on top of the shared ingestion corpus (`articles`, `article_stances`,
> `entity_dictionary`, `story_clusters_v8`, the `analytics.*` schema).
>
> A reader who wants the *logic* behind each feature should read this top to
> bottom. Where the source did not make something explicit it is marked
> **(unverified)**.

---

## 1. Design philosophy (read this first)

Three principles run through the whole product and explain why the endpoints
look the way they do:

1. **One relevance core, many personas.** Almost every "read" — the home
   briefing, the executive top-fold, the defining stories, the voices panel,
   the war-room cables — is computed by a single generic engine
   (`relevance.score_relevant` + `posture.compute_posture`) driven by the
   signed-in user's **prefs row** (`analytics.user_brief_prefs`): a
   `primary_subject_id` (the "principal"), a tiered `watchlist`, `regions`,
   `topics`, `languages`. A Telangana CM sees Telangana; a Delhi police chief
   sees Delhi; a PR lead sees their client — *same code, different prefs row*.
   A brand-new user with a fresh prefs row works with zero code changes.

2. **Everything is source-grounded with receipts.** No card states a number it
   cannot back with real articles. Directional sentiment always reads
   `article_stances` (the directed 18-label → polarity map, `POL`), never
   `register_emotion` (whose "alarm" is *event*-emotion and skews everything
   negative). Every qualitative read is one click from its evidence via the
   `/sources` receipts endpoint. Each card carries `n` + a `confidence` band so
   thin scores can be softened or hidden.

3. **Honest degradation.** Unauthenticated or un-onboarded callers get a public
   fallback (`{"personalized": false}` or generic newest-India headlines) —
   never an empty screen, never a fabricated personalization.

---

## 2. Night-desk product pages

The night-desk SPA (`src/pages/*.jsx`) is the operator surface. Each page is a
thin renderer over one or two backend endpoints.

### 2.1 Home — the situation brief (`Home.jsx`)
The personalized landing page. A **single** `GET /api/brief/home` call returns
the whole payload as a unit so all numbers are cross-section-consistent (they
derive from one posture + relevance computation): a masthead, **THE BRIEFING**
(executive read), **PEOPLE TO WATCH**, and **THE SIX** (defining stories). A
toggle (`/cross-pillar`) swaps the story rail between **Top stories ⇄ Clips ⇄
Cuttings** — YouTube clips and newspaper cuttings scored against the *same*
watchlist prefs. Inline watchlist editing (`/watchlist/add`,
`/watchlist/{id}`) and an entity search (`/onboarding/search_entities`) let the
user tune their world without leaving home. A "Breaking" marquee is fed by the
`/ticker` endpoint. There is also a `sentiment-explain` drill-down for the
pressure-point readout.

### 2.2 War Room — the live crisis desk (`WarRoom.jsx`)
A cable-desk metaphor over `GET /api/brief/warroom`. It answers *"what is
attacking the principal, how bad, and what's the ammo?"*. Built by
`war_room.build_war_room` (30-min precompute cache, lazy-fills on miss), reusing
the vetted posture family (`weighted_pressure`, `counter_speed`,
`attack_origination`, `target_heat`, `friend_foe_fence`, `stance_trajectory`,
`issue_ownership`). It renders a **STATION** header (mood + 21-day trend), a
**LEAD** cable (the dominant adverse storyline + a situation summary), a stack
of **CABLES** (adverse storylines grouped by topic, each with a severity tag),
and an **ARSENAL** ("YOUR BEST LINES" — counter-talking-points). Severity logic
is deliberately volume-aware: a lone harsh article is `WATCH`, never `HIGH`
(`_sev`: `CRITICAL` at n≥8 or n≥5 & neg≥0.5; `HIGH` at n≥3; else `WATCH`) so a
single hostile outlet can't inflate the board. Each cable links to its sources.

### 2.3 Analytics — "The Instrument Panel" (`Analytics.jsx`)
One `GET /api/brief/analytics` call returns ~20 **pure-data cards** (no LLM)
over the persona's coverage universe. For speed the backend materialises the
universe (all articles mentioning any watchlist entity / the principal in the
window) into a temp table once, then each card is a count / distribution /
cross-tab off that table. Every card carries a `source`, an `n`, a `confidence`,
and an `explain`/`verify` payload; a "Receipts" row surfaces the real stories
behind specific cards. The cards are organised into three bands:

**THE BIG PICTURE**
- `volume` — *Coverage Volume* (area chart of coverage over time)
- `topics` — *What They're Talking About* (topic rank)
- `rising` — *Issues Rising & Falling* (small-multiples deltas)
- `forvsagainst` — *For You vs Against You* (supportive/critical stack)
- `battlefield` — *Issues — Praised vs Attacked* (per-issue lean)
- `sov` — *You vs Your Rivals* (share-of-voice rank)

**WHO & WHERE**
- `outlets` — *Who's Covering You* (outlet rank)
- `outletlean` — *Outlets — Friendly vs Hostile* (per-outlet lean)
- `language` — *English vs Telugu* (language donut)
- `langbyissue` — *Telugu vs English by Issue* (grouped bars)
- `geo` — *Where It's Landing* (geographic rank)
- `quoted` — *Who's Being Quoted* (speaker list)
- `writers` — *Who's Writing* (byline list)

**THE DETAIL**
- `tone` — *Tone of Coverage* (tone rank)
- `upcoming` — *What's Coming Up* (event calendar)
- `events` — *What's Happening* (event rank)
- `quotes` — *In Their Words* (quote cards)
- `claims` — *What's Being Claimed* (claim cards)
- `figures` — *The Numbers in the News* (extracted figures)
- `pictures` — *The Picture Wall* (image wall, tone-coloured, each linking back
  to its article)

### 2.4 Dossier — entity roster + drill-down (`Dossier.jsx`)
The persona's watched-entity roster (`/dossier/roster`, with photos). Selecting
an entity opens its **file** — `/dossier/entity/{eid}` returns ~14 panels
(prominence, posture, quotes, etc., ~0.7s live) — and a newest-first,
**cursor-paginated** article feed (`/dossier/entity/{eid}/articles?limit&cursor`,
~0.15s). RBAC is enforced at this endpoint: a persona may only open entities on
their own watchlist or their principal (matches the per-user view-by-entity
scope).

### 2.5 Map — the situation map (`MapPage.jsx`)
A deck.gl map (`/map?scope=`) of persona-scoped district/state bubbles
(choropleth or extruded columns), tone-coloured by net stance. Scopes include
`mine` (the persona's footprint) and `global`. Overlays: live embeddable news
**channels** (`/channels`), and for GLOBAL scope external **world layers**
(`/global-layers` — ACLED conflict + NASA EONET natural events). Clicking a
shape opens a **drawer**: districts via `/district/{did}` (+
`/district/{did}/articles`) and countries via `/country/{iso}` (+
`/country/{iso}/articles`), each with **"more stories" cursor pagination**
(`?limit=15&cursor=`).

### 2.6 Dispatch — reports & delivery (`Dispatch.jsx`)
A thin shell around the `ReportDispatch` component: compose, verify, and ship
the **Daily State Intelligence Brief** as PDF or Gmail. It is backed by the
report endpoints (`/report`, `/report.pdf`, `/report/send` — see §3).

### 2.7 Ask — the RAG console (`Ask.jsx`)
The in-product chat surface. It streams from the Ask-RIG sidecar (`/ask/*`) and
renders three body shapes per turn: a **markdown answer + sources**
(`AskAnswer` + `AskSources`), an **enumerate list** (`AskList`), or an
**in-chat chart** (`AskChart`). While the model thinks it shows a live `status`
line. A `/ask/stats` call labels the corpus ("N sources · 4 languages"). Full
pipeline in §4.

### 2.8 Chronicle — deep story pages (`Chronicle.jsx`)
Admin-pushed deep-dive story pages over the `_v8` story layer and `analytics.*`
enrichment (timeline, sources, geo, quotes, stance, facts). `/api/chronicle/mine`
lists the stories assigned to the user (`user_story_assignments`);
`/api/chronicle/{story_id}` returns the full multi-layer page;
`/{story_id}/meta`, `/{story_id}/articles`, and `/{story_id}/v2-compare`
(a clustering-version comparison) supply the sub-views. Admins assign/unassign
via `/api/admin/chronicle/assign` (POST/DELETE) and list with
`/api/admin/chronicle/assignments`.

---

## 3. API surface

All routers are mounted in `main.py`. Most carry `APIRouter(prefix="/api/brief")`;
the exceptions are dossier (`/api/brief/dossier`), chronicle (absolute
`/api/chronicle/*`), me (`/api`), admin (`/api/admin`), and onboarding
(`/api/onboarding`). Identity flows through `get_optional_user` /
`get_current_principal`, which is also where impersonation is applied (§5).

### 3.1 Home & personalization
| Method & path | Logic |
|---|---|
| `GET /api/brief/home` | Full home payload (masthead + briefing + people-to-watch + the-six) from one posture+relevance pass; `{personalized:false}` when no persona. |
| `GET /api/brief/cross-pillar` | Top clips + cuttings for the persona, scored on the same watchlist core (powers the Home story-rail toggle). |
| `GET /api/brief/clipping-image/{id}` | Serves a newspaper clipping snapshot (decoded b64), cached 1 day; unauth (an `<img>` can't carry a bearer) but *which* clippings a persona sees stays gated via `/cross-pillar`. |
| `POST /api/brief/watchlist/add` · `DELETE /api/brief/watchlist/{id}` | Mutate the persona's watchlist in `user_brief_prefs`. |
| `GET /api/brief/ticker` | Newest **persona** headlines for the "Breaking" marquee: subject-naming articles first → broader watchlist → generic newest-India (unauth). Titles in original language (translating ~20/load hung the marquee). |
| `GET /api/brief/morning_ritual` | The single highest-signal "one card to see today". |
| `GET /api/brief/watchlist_relevance` | Overload-killer: the persona's relevant articles ranked to a defensible top-N. |
| `GET /api/brief/expand_watchlist` | Rising entities co-occurring with the persona's world but not yet watched → suggested adds. |
| `GET /api/brief/smart_filter` | Agentic ranked + reasoned top stories. |
| `GET /api/brief/coverage_qa?q=` | Grounded coverage Q&A agent. |

### 3.2 Situation reads (top-fold blocks)
| Method & path | Logic |
|---|---|
| `GET /api/brief/executive` | Block 1 "The Executive Read": the persona's own relevant stream (watchlist tiered + alias-expanded, region/keyword), salience-gated & noise-demoted; real headline + `summary_executive` + matched entity; deterministic severity. |
| `GET /api/brief/cm_perspective` | Block 2 "how the principal is being covered": left = written read of coverage; right = "Needs Your Attention" (opposition attacks + high-severity coverage about the principal), source-linked. Persona-agnostic. |
| `GET /api/brief/posture` | Category-1 posture metrics (~15) — principal = `primary_subject_id`, targets = watchlist; each metric carries `n` + `confidence`. |
| `GET /api/brief/textual` | Category-2 textual intelligence (LLM, faithfulness-gated, English-pinned, cold-start safe); `?features=a,b` runs a subset to bound LLM cost. |
| `GET /api/brief/warroom` | War-room payload (station/lead/cables/arsenal), 30-min cache (§2.2). |

### 3.3 Stories, entities & trends
| Method & path | Logic |
|---|---|
| `GET /api/brief/stories` | Defining stories for the persona: relevant stream de-duplicated into distinct stories (syndicated re-scrapes merged by headline), ranked by relevance; enriched with principalQuote, coverage %, top-3 cite blocks, thumbnail, vs-baseline %, peak time. |
| `GET /api/brief/top-articles` | Most-relevant **individual articles** (not clusters) via `score_relevant`, tier-aware (national entities surface only when a story also touches the persona's region); default-window call served from the 30-min page cache (raised statement_timeout). |
| `GET /api/brief/entities` | 4 watched-entity cards (hybrid FK-then-ILIKE matching). |
| `GET /api/brief/entity_read` | On-demand grounded LLM "read" + recommended actions for one figure (fired only on card expand, so the grid stays LLM-free). |
| `GET /api/brief/emerging` | Top-N surging entities (stopword filter + NEW-today boost + surge-ratio scoring over `entity_mention_daily`). |
| `GET /api/brief/climbing` | Entities surging in the last rolling window vs a 24h baseline of same-width buckets; `since_hours` is both window width and baseline-bucket width (apples-to-apples). |
| `GET /api/brief/horizon` | Genuinely-scheduled **future** events (`article_events.effective_event_date > today`) gated to the persona's score-floored relevant articles — a calendar, not a forecast. |
| `GET /api/brief/voices` | "Voices Overnight": featured best quote + editorial (anonymous, `speaker_entity_id IS NULL`) + opposition (politician, matched to `entity_dictionary`); personalized to the persona's coverage. |
| `GET /api/brief/mood` | Mood waveform: hourly sentiment series (mean `article_stances.intensity` per hour bucket) + aggregate "now" mood. |
| `GET /api/brief/kpi` | The 4 KPI tiles (last-24h volume / language / source counts over `articles` + `article_stances`, read-only). |

### 3.4 Drill-down, dossier & map
| Method & path | Logic |
|---|---|
| `GET /api/brief/sources` | **Receipts**: the real articles behind any read. For negative/supportive/neutral/outlet/topic the directed-stance TARGET is the persona's principal; `kind=entity` returns that entity's coverage. Reuses posture's `POL` + `_BODY_PRESENT` anti-hallucination guard so rows match the metric exactly. |
| `GET /api/brief/dossier/roster` | Every watched entity (+ photo). |
| `GET /api/brief/dossier/entity/{eid}` | The open entity file (~14 panels). RBAC: own-watchlist/principal only. |
| `GET /api/brief/dossier/entity/{eid}/articles` | Newest-first cursor-paginated feed. |
| `GET /api/brief/map` | Persona-scoped district/state bubbles (cache). |
| `GET /api/brief/channels` | Live embeddable news channels for the scope (25-min cache). |
| `GET /api/brief/global-layers` | ACLED conflict + NASA EONET layers (GLOBAL scope). |
| `GET /api/brief/country/{iso}` · `/country/{iso}/articles` | Country drawer + cursor-paginated stories. |
| `GET /api/brief/district/{did}` · `/district/{did}/articles` | District drawer + cursor-paginated stories. |

### 3.5 Reports, export & meta
| Method & path | Logic |
|---|---|
| `GET /api/brief/report` | Structured Daily State Intelligence Brief JSON (Dispatch preview). |
| `GET /api/brief/report.pdf` | Rendered PDF download. |
| `POST /api/brief/report/send` | Email the brief. |
| `GET /api/brief/export` · `GET /api/brief/send_test` | Export payload + test-send. |
| `GET /api/me` | The caller's effective principal (impersonation-aware). |
| `GET /api/chronicle/*` | Chronicle deep story pages (§2.8). |

### 3.6 Admin & onboarding
| Method & path | Logic |
|---|---|
| `POST /api/admin/orgs` · `GET /api/admin/orgs` | Create / list orgs (super_user only). `role_template ∈ {govt, pr, journalist, academic, corporate}`. |
| `POST /api/admin/invites` · `GET /api/admin/invites` | Mint / list invite links (super_user only). |
| `POST /api/admin/bootstrap` | One-shot seed of the first super-admin row. |
| `GET /api/admin/users` · `PATCH /api/admin/users/{uid}/role` | Super_user dashboard: list users / change a role. |
| `GET /api/onboarding/search_entities` | Entity autocomplete for the wizard. |
| `GET /api/onboarding/invite/{token}` · `POST /api/onboarding/accept` · `POST /api/onboarding/complete` | Validate an invite → accept (create user under the org) → complete the prefs wizard (writes `user_brief_prefs`). |

---

## 4. Ask-RIG — the RAG pipeline (`products/ask-rig/app`)

Ask-RIG is a **read-only** RAG service (every DB statement is a `SELECT`)
exposed behind `/ask/*` and embedded as the night-desk **Ask** tab. It is a
unified chat orchestrator — *no mode toggles in the UI*; the pipeline decides
how to answer.

### 4.1 Hybrid retrieval (`retrieval.py`)
Retrieval runs over `articles` (article-only for V1 — clip/cutting embeddings
are not in the v4 space, so cross-pillar cosine is unreliable):
- **Semantic** — LaBSE **v4** vectors (the corpus embedding recipe).
- **Lexical** — Postgres **FTS**.
- **Fusion** — **Reciprocal Rank Fusion**: `score(d) = Σ_i 1/(k + rank_i(d))`
  (1-based ranks). Pure, unit-tested; rewards docs ranking high in *either*
  list and boosts **consensus** docs that appear in both.
- `multi_retrieve_and_curate` fans the fused search over the **expanded query
  variants** (RAG-Fusion) and curates a single ranked, de-duplicated context
  block.

### 4.2 Turn routing & agentic modes
Latency was the design driver: a turn used to fire up to **four** sequential
Groq calls before the first token (parse_dossier? + parse_count? + parse_list?
+ plan_turn). Two collapsing layers fix that:

- **`router.py` (`route_turn`)** — **one** LLM call classifies the **mode** and
  extracts only that mode's fields. Best-effort: returns `None` on failure so
  the caller falls back to plain synthesis (correctness never depends on it).
- **`planner.py` (`plan_turn`)** — the synthesis-path planner: resolves a
  follow-up into a **standalone** query (pronouns → the real subject, using
  history), classifies the question shape (broad roundup / specific / profile /
  comparison / explainer), decides whether the **live web** is actually needed,
  and names the **entity** to pull a feed for.

The modes (`chat.py` stream functions):
- **synthesis (default)** — expand → fan out (corpus + web + on-demand entity
  feed) → fuse → stream a structure-adaptive, cited answer.
- **enumerate (`enumerate.py` / `_enumerate_stream`)** — *"give me ALL articles
  matching X"*: a **structured** query (entity-resolved and/or FTS keyword +
  time window + language + limit), returning the **full filtered set** as cards.
  Recency is correct by construction (a hard `published_at` window), sidestepping
  the RAG path's no-recency-boost weakness. "All NEGATIVE about X" is a separate
  on-the-fly LLM stance classification over headlines (the stance table is too
  sparse to filter on).
- **quantify (`_quantify_stream`)** — real corpus counts/trends; the answer is
  grounded in those numbers, never invented. Sentiment rates are a clearly
  **labelled sampled estimate** (~40 latest classified; ~22/day for charts).
- **dossier (`_dossier_stream`)** — multi-signal coverage on one entity →
  structured, cited dossier (skips if below `_ENTITY_MIN_ARTICLES`).
- **drill-down (`_drilldown_stream`)** — drill into **one** article by id: fetch
  its full text + quotes and explain it. No retrieval — precise by construction.
- **research agent (`agent/loop.py`, `agent/tools.py`)** — an LLM
  tool-calling loop (plan → call tool → observe → repeat → final cited answer)
  over corpus search, web search, entity resolve/feed/stances, and quotes. Each
  article-bearing tool registers results in a **SourceBook** so the final answer
  cites `[S#]` over everything gathered, and returns a **tool trace** ("show its
  work").

### 4.3 The SSE chat pipeline (`chat_stream`)
The whole orchestrator is an async generator of SSE event dicts so the UI
renders progressively. Event types emitted: **`status`** (stage labels —
"Building the dossier", etc.), **`sources`** (the `[S#]` source panel),
**`token`** (streamed answer text), **`list`** (enumerate cards), **`chart`**
(in-chat visualizations), **`done`** (carries a `faithful` flag), and
**`error`**. The blocking LLM stream is bridged onto the event loop via a worker
thread feeding a queue (`_stream_llm`). Entity retrieval fires **only** when the
question clearly names a known person/org/place (a significant word of the
canonical name must appear in the query — `_entity_is_relevant` guards loose
ILIKE matches); corpus + web run every turn.

### 4.4 Web full-text supply, charts & guardrails
- **Live web** — full-text web results are fused into the same context block
  alongside corpus hits (planner decides when web is worth the round-trip).
- **In-chat charts** — `chart` events carry chart specs (e.g. `kind:"bar"`)
  rendered by `AskChart`; `quantify`/`classify_labels` produce sentiment
  distributions for trend/breakdown charts.
- **Cite-ID guardrail** — the answer is **validated against the cite IDs the
  SourceBook actually gathered**; the model can only cite `[S#]` markers that
  map to real retrieved sources, and `done` reports a `faithful` flag. This is
  the anti-fabrication backbone shared by the synthesis path and the agent loop.

---

## 5. RBAC & multi-tenancy (`auth/middleware.py`, `routers/admin.py`)

### 5.1 Identity — Supabase JWT
Auth is a Supabase **HS256 JWT** (`python-jose`), verified against
`OSINT_SUPABASE_JWT_SECRET` / `SUPABASE_JWT_SECRET`. In **production** a missing
secret **refuses** to start rather than skip signature verification; in dev it
falls back to unverified decode. The token's `sub` → user id, `email` → email;
expiry is checked. `get_current_user` returns `{id,email}`;
`get_optional_user` returns `None` instead of 401 for public endpoints.

### 5.2 Roles & the principal
Users live in **`analytics.users`** (kept separate from `public.users` so the
OSINT product is self-contained), joined to **`analytics.orgs`**. The role model:
- **`role` column** ∈ `super_user | admin | client` (with a legacy
  `is_super_admin` boolean kept for backward compat).
- `get_current_principal` resolves the full principal:
  `id, email, full_name, designation, is_super_admin, role, org_id, org_name,
  role_template, onboarded, impersonating`.
- Guards: `require_super_admin` (super_user only), `require_admin` (admin or
  super_user), `require_onboarded` (must have finished the wizard).

Auto-seeding: emails in **`OSINT_SUPER_USER_EMAILS`** (default
`sycek@…`, `rohit@…`) are upserted as `super_user` on first login (idempotent),
under an auto-created internal org — no Supabase admin step required.

### 5.3 Per-org data scoping
Every data endpoint resolves identity through the principal and scopes to that
user's **`org_id`** + **prefs row**. A client's data isolation is therefore a
property of *what their prefs + org allow them to query*: the dossier endpoint
explicitly refuses entities outside the persona's own watchlist/principal, and
the relevance core only ever surfaces the persona's relevant stream. Orgs carry
a `role_template` (`govt | pr | journalist | academic | corporate`) that shapes
the onboarding wizard and defaults.

### 5.4 Super-user impersonation (`X-Impersonate`)
A `super_user` caller may send **`X-Impersonate: <uuid>`**. The middleware's
`_effective_user` / `get_current_principal` **transparently substitute** the
target user's principal so **all data endpoints scope to the impersonated user's
org/prefs** — not just `/api/me`. Safety rails: a missing header, a non-super
caller, self-impersonation, or an unknown target are all **no-ops** that return
the caller's own identity; an unknown target on `/api/me` returns 404. The
substituted principal carries `impersonating: <uuid>` so the UI can show the
"viewing as" state. Impersonation is auditable via `impersonation_sessions` /
`impersonation_actions` (FK'd to `users`). **(unverified: whether every action
is logged to `impersonation_actions` by middleware — the tables exist per the
schema reference but logging wiring was not read.)**

### 5.5 Org & invite lifecycle (`admin.py`, `onboarding.py`)
Super-users create orgs (`POST /api/admin/orgs`) and mint invite links
(`POST /api/admin/invites`). A recipient validates the token
(`GET /api/onboarding/invite/{token}`), accepts (`POST /api/onboarding/accept`,
creating their `analytics.users` row under the inviting org), and finishes the
wizard (`POST /api/onboarding/complete`, writing `user_brief_prefs`). The first
super-admin is seeded once via `POST /api/admin/bootstrap`.

---

## 6. Brief generation & the Analyst

### 6.1 The daily brief
Personalization lives in **`analytics.user_brief_prefs`** (PK/FK → `analytics.users`):
`primary_subject_id` + `primary_subject_meta`, `watchlist`
(`{entity_ids, entity_meta:[{id,name,type,party}], auto_adjacents}`), `regions`
(`{states, countries, districts}`), `topics`, `languages`, `sources`, `stance`,
`events`, `delivery` (schedule/channel), and `personality` (tone). It is written
by the onboarding wizard and read by both the brief-generation Celery task and
the brief API. The **Dispatch** page (§2.6) and the `/report*` endpoints (§3.5)
compose, preview, render-to-PDF, and email the resulting **Daily State
Intelligence Brief**.

### 6.2 Analyst — per-user RAG over the corpus
The **Analyst** pillar is per-user RAG over the corpus, persisted in
`analyst_sessions` / `analyst_turns` (FK'd to `users`) per the schema reference.
In the OSINT product this capability surfaces as **Ask-RIG** (§4): the same
read-only, cite-guarded hybrid-retrieval engine, scoped to the signed-in
persona. **(unverified: the exact relationship between the legacy
`analyst_sessions` tables in `rig-backend` and the Ask-RIG sidecar's own session
handling — Ask-RIG's chat path was read; a separate `analyst_*`-backed service
in this product was not.)**

---

## 7. Cross-references
- Worker topology & queues: `CLAUDE.md`, `infrastructure/Dockerfile.backend`.
- Relevance/posture core: `products/osint/backend/relevance.py`, `posture.py`.
- Story/enrichment layer (Chronicle): `analytics.story_*_v8`,
  `docs/handoffs/db-reference/30-*`.
- Users/RBAC schema: `docs/handoffs/db-reference/60-users.md`
  (`analytics.users`, `analytics.orgs`, `user_brief_prefs`,
  `impersonation_sessions`).


---

# 8. Client Delivery & Integration Options

This section answers the core commercial question: **"Can a client get our data, systems, and features into their environment?"** Yes — and because the platform is already **API-first and multi-tenant (org-scoped)**, most of the plumbing exists. There is a spectrum of delivery models with very different effort, risk, and IP implications.

## The five models

### 1. Scoped API access — *recommended default*
Issue the client API credentials scoped to their **org**. They pull from the existing endpoints (`/api/brief/*` for briefs, analytics, map, dossier, entities; Ask-RIG `/chat` and `/ask` for RAG) and build their own integration/UI.
- **Pros:** ~90% already built (RBAC scopes data per org); code/IP stays on our servers; always-live data; metered, billable, revocable.
- **Build needed:** an API-key auth layer (alongside the Supabase JWT path), per-key rate limiting, usage logging, and a published API spec (OpenAPI).
- **Best when:** the client wants to integrate our intelligence into *their* apps/dashboards.

### 2. Embedded / white-labeled desk
Give them the full night-desk UI — as an embed (iframe) or a white-labeled deployment — pointed at our backend with their branding and org scoping.
- **Pros:** the entire feature set instantly; minimal work; we keep the backend + pipeline.
- **Best when:** the client wants a turnkey analyst product, not to build their own.

### 3. Data feed / warehouse sync
Push processed data (articles, stances, entities, briefs, clusters) into the client's database/warehouse via scheduled exports, a replication feed, or webhooks on new items.
- **Pros:** native to *their* analytics stack; good for data-science teams.
- **Cons:** they get **data, not the analysis/UI features**.

### 4. Hybrid (most common in practice)
Scoped API (#1) for programmatic access **+** white-label desk (#2) for human analysts **+** optional webhook alerts. Covers both machine and human consumers without giving up the platform.

### 5. Full self-hosted handover (whole stack on their infrastructure)
Ship the Docker stack (Postgres+pgvector, FastAPI, Celery workers, frontend) to run on the client's servers.
- **This is a licensing / commercial decision, not a technical toggle.** Honest caveats:
  - Hands over the **entire codebase / IP**.
  - The corpus is **continuously ingested** — a one-time copy is stale within hours; they'd need the *live pipeline*, not a dump.
  - **Hard dependencies don't transfer** (see §9): the LLM pool runs on our Groq accounts/billing and our private GPU nodes; the scrapers depend on our residential-IP relays. Re-creating "the backend" on their side means re-provisioning all of it.
- **Best when:** there's a genuine data-residency/compliance mandate or a platform-license deal with commercial terms to match.

## Decision guide

| If the client's real need is… | Recommend |
|---|---|
| Integrate our intelligence into their software | **#1 Scoped API** |
| Give their analysts a ready product | **#2 White-label desk** |
| Land raw data in their warehouse | **#3 Data feed** |
| Both machine + human consumption | **#4 Hybrid** |
| Data must physically reside on their servers (compliance) | **#5 Self-host** (license deal) |

## The three questions to ask the client

1. **Why "their system"?** Compliance / data-residency (data must physically sit on their servers) — or just integration into their app/dashboards? This single answer eliminates most options.
2. **Data, features, or both?** Raw data into their stack, the analysis + UI, or both?
3. **Commercial nature?** Paid API/subscription access, or an actual platform license / handover?

## What we'd build for the recommended path (#1/#4)

1. **API gateway layer** — API-key issuance + validation in front of the existing routers (the org-scoping/`X-Impersonate` principal model already isolates data per org).
2. **Rate limiting + quotas** per key/org.
3. **Usage metering** for billing.
4. **OpenAPI spec + developer docs** (the endpoint surface already exists — see §7).
5. *(Optional)* **Webhook/alert service** for "new coverage on watchlist X."
6. *(Optional)* **White-label theming** of night-desk per org.

> Estimated lift for #1: small-to-moderate — the data API and tenant isolation already exist; the new work is the key/quota/metering/doc layer, not the core platform.


---

# 9. Portability, Secrets & "What Transfers"

If the conversation moves toward a self-hosted or partial deployment on the client's side, this section is the reality check: **what moves cleanly, what needs re-provisioning, and what is operationally sensitive.**

## What transfers cleanly (code & schema)

| Asset | Portability |
|---|---|
| Application code (FastAPI, Celery, night-desk, Ask-RIG) | ✅ Containerized; ships as Docker images |
| Database schema (numbered SQL migrations) | ✅ Re-runs idempotently on a fresh Postgres+pgvector |
| The processing logic (substrate, clustering, relevance, RAG) | ✅ In code |
| A point-in-time data snapshot | ✅ `pg_dump` — but **goes stale immediately** (corpus is live) |

## What does NOT transfer without re-provisioning

| Dependency | Why it's stuck to us | Client would need |
|---|---|---|
| **LLM inference** | Runs on **our** Groq API accounts (billing, TPD budgets, key rotation) **and** private GPU nodes (TRIJYA-7 RTX 4090, TRIJYA-8 RTX 4070 running local Qwen3 models) | Their own LLM keys/billing or their own GPU hardware + model deployment |
| **YouTube / Instagram scraping** | Depends on **residential-IP relays** + authed cookies to dodge datacenter IP blocks; reputation-managed | Their own residential relay infrastructure (datacenter IPs are blocked) |
| **Live ingestion feed** | The collectors run continuously against hundreds of sources | Either keep pulling from our pipeline (API/feed) or stand up + maintain all source adapters themselves |
| **Embeddings GPU server** | LaBSE v4 embedding server runs on our 4090 | A GPU embedding service on their side |
| **Auth** | Supabase project (hosted) | Their own Supabase project or auth provider |

**Implication:** "all our backend on their system" is feasible as *code*, but the **data only stays fresh if they either (a) keep consuming our live pipeline via API/feed, or (b) rebuild the entire ingestion + AI-compute + anti-blocking stack on their side.** Option (b) is a major undertaking and a different commercial conversation. This is the single most important thing to communicate.

## Secrets & configuration inventory (what's externalized)

All secrets are environment-variable / `.env` driven (never hardcoded). A deployment is configured via:

- **Database** — `OSINT_DB_URL` / Postgres credentials (read-only `analytics_user` for the API layer).
- **Auth** — `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`, `SUPABASE_JWT_SECRET`, `OSINT_SUPER_USER_EMAILS`.
- **LLM pool** — Groq API keys (rotated), local node endpoints (`OLLAMA_ENDPOINTS` / TabbyAPI URLs), tunnel config.
- **Scraping** — relay URLs (`YT_RELAY_URL`, Instagram relay), source cookies/sessions.
- **CORS / hosts** — `OSINT_CORS_ORIGINS`, domain config in Caddy.

> A client deployment is therefore a matter of supplying *their* values for each of these — but the LLM-pool and scraping entries are exactly the ones that can't just be "set," they require real infrastructure behind them.

## Recommended posture

For almost any client, lead with **API access and/or white-label (models #1/#2 in §8)**: they get the live data and the full feature set, we retain the IP and operate the hard-to-move pipeline, and it is billable and revocable. Reserve **self-hosting (#5)** for a deliberate, well-priced platform-license deal where data residency is a hard requirement — and scope the LLM/scraping re-provisioning explicitly into that deal.


---

