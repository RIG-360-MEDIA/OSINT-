# 01 - System Architecture

> **TL;DR.** FastAPI + Next.js 15 + Postgres/pgvector on a single
> Hetzner box. Six Celery workers and Beat run inside the
> `rig-backend` container, *not* as separate compose services.
> Ollama qwen3:30b-a3b on a second machine (TRIJYA-7, RTX 4090) is
> reached over Tailscale and acts as the primary LLM provider; Groq
> and Cerebras are cloud failover.

## The 8 product pillars

Each pillar is its own page in the frontend and its own ingestion
pipeline in the backend.

| Pillar         | Frontend route   | Ingest source                                | Queue(s)              |
|----------------|------------------|----------------------------------------------|------------------------|
| **Articles**   | `/coverage`      | RSS + HTML scraping (574 sources)            | `collectors`, `nlp`    |
| **Clips**      | `/clips`         | YouTube transcripts                          | `youtube`              |
| **Cuttings**   | `/cuttings`      | Newspaper editions (PDF e-papers)            | `documents`            |
| **Threads**    | `/threads`       | Reddit / Twitter / Telegram                  | `social`               |
| **Signals**    | `/signals`       | "The Signal Room" — Reddit + Telegram with sentiment + entity matching. Twitter is hidden from UI but the data layer stays active. | `social`         |
| **Documents**  | `/documents`     | Government PDFs (the "archive")              | `documents`            |
| **Brief**      | `/brief`         | Daily generated digest per user              | `brief`                |
| **Analyst**    | `/analyst`       | Per-user RAG over the corpus                 | (synchronous FastAPI)  |

Beyond the 8 pillars there's a **CM political-intelligence** layer
(routed to `nlp` for LLM tasks and `social` for cheap aggregations),
an admin / RBAC layer (super-admin bootstrap on every boot via
`SUPER_ADMIN_EMAILS`), and a hidden `/worldmonitor` and `/debug` UI.

## Container topology

Defined in `infrastructure/docker-compose.yml`.

| Service        | Image                              | What runs in it                                                        |
|----------------|------------------------------------|------------------------------------------------------------------------|
| `rig-postgres` | `ankane/pgvector`                  | Postgres 16 + pgvector. Port `5433:5432`.                              |
| `rig-backend`  | `infrastructure-rig-backend`       | **FastAPI uvicorn + 6 Celery workers + Celery Beat**, all from `/start.sh`. |
| `rig-frontend` | `infrastructure-rig-frontend`      | Next.js 15 dev server.                                                 |
| `rig-searxng`  | `searxng/searxng`                  | Internal web-search proxy. No host port.                               |
| `rig-freshrss` | `lscr.io/linuxserver/freshrss`     | FreshRSS reader — the canonical subscription list for 574 RSS feeds. Port `8081:80`. |
| `rig-caddy`    | (Hetzner only)                     | Dockerised TLS reverse proxy. Caddyfile at `/root/rig/infrastructure/Caddyfile`. |

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

## Celery queues and their consumers

All 6 workers are launched by `backend/start.sh`. There is one Beat
process. Beat schedule is in `backend/celery_app.py` ~line 130 onward.

| Queue        | Worker process       | Concurrency       | What it runs                                                                                  |
|--------------|----------------------|-------------------|-----------------------------------------------------------------------------------------------|
| `collectors` | `worker-collectors`  | 1                 | RSS (`tasks.collect_rss`, `tasks.collect_rss_direct`), HTML, og:image backfill.               |
| `social`     | `worker-social`      | 2, prefetch=1     | Reddit / Twitter / Telegram + entity backfill + cheap CM aggregations.                        |
| `youtube`    | `worker-youtube`     | 1                 | YouTube transcripts + entity tagging.                                                         |
| `documents`  | `worker-documents`   | 2, prefetch=1     | Govt PDF collection + doctor + newspaper editions.                                            |
| `nlp`        | `worker-nlp`         | 4                 | Article NLP (incl. substrate v3), topic, entities, social sentiment, CM stance, clustering, dissent, counter-narratives. |
| `relevance`  | `worker-relevance`   | 4                 | Per-user article + doc scoring, CM voice-share / heatmap / exploitation index.                |
| `brief`      | `worker-relevance`   | (shared)          | Daily brief generation. Routes to the same process as `relevance`.                            |
| `whisper`    | (not currently used) | -                 | Reserved for audio transcription if/when wired up.                                            |

Newspaper collection used to run on `collectors` but was moved to
`documents` because the single-concurrency `collectors` worker was
regularly blocked by 30-60 minute RSS scrapes. Govt-document collection
historically had no consumer at all (`documents` queue was empty); the
2026-04-28 audit added the consumer.

Key beat-schedule entries (from `celery_app.py`):

- `collect-rss-every-15-min` → `tasks.collect_rss` on `collectors`
- `collect-rss-direct-every-30-min` → `tasks.collect_rss_direct` on `collectors`
- `collect-html-every-6-hours` → `tasks.collect_html` on `collectors`
- `fetch-og-images-every-10-min` → `tasks.fetch_og_images_batch` on `collectors`
- `process-nlp-every-30-seconds` → `tasks.process_nlp_batch` on `nlp`
- `generate-briefs-daily` at 00:30 → `tasks.generate_all_briefs` on `brief`
- `score-relevance-every-5-min` → relevance jobs on `relevance`
- nightly Cerebras / Groq cooldown reset at ~00:05 UTC

## TRIJYA-7 (the GPU box)

- Physical: home workstation with RTX 4090.
- Reached over Tailscale at `100.92.126.27:11434` from Hetzner.
- Runs Ollama (currently `qwen3:30b-a3b` is the substrate model).
- Ollama daemon is launched by a Windows scheduled task called
  `OllamaServe`, configured with `OLLAMA_CONTEXT_LENGTH=8192` and
  `OLLAMA_NUM_PARALLEL=1`. Runs as the S4U principal so it survives
  user-logoff.
- See `05-llm-infrastructure.md` for the full LLM pool design and
  `10-context-from-may-2026-session.md` for the Ollama install
  caveats (old build was 553MB, silently CPU-only; new build is 2GB
  with CUDA DLLs and actually uses the GPU).

## Tailscale routing

- Hetzner production server: `178.105.63.154` (public) + Tailscale.
- TRIJYA-7: `100.92.126.27` (Tailscale only).
- The backend reaches Ollama via `http://100.92.126.27:11434/api/chat`
  (native endpoint, not `/v1/chat/completions` — see
  `02-substrate-pipeline.md` for why).
- No public exposure of Ollama. If Tailscale is down between Hetzner
  and TRIJYA-7, the LLM pool fails over to Groq/Cerebras.

## Data flow at a glance

```
  RSS / HTML / YouTube / Govt PDF / Reddit / Telegram / Newspapers
                            │
                            ▼
              collectors / social / youtube / documents queues
                            │
                            ▼
              Postgres (articles, social_posts, govt_documents, …)
                            │
                            ▼
            nlp queue: substrate v3 extraction (Prompt G)
                            │
                            ▼
   articles + 6 child tables (article_quotes, _claims, _stances,
   _numbers, _events, _locations) + article_links, article_media,
   article_tweets, articles.byline_*
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

## Hetzner production access

- SSH: `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154`
- Caddy is **dockerised** (`rig-caddy`), not a host service.
  Caddyfile at `/root/rig/infrastructure/Caddyfile`.
- Repo on Hetzner is at `/root/rig`, branch
  `fix/brief-prod-readiness`. Origin and Hetzner have diverged at
  commit `3a9441a` (2026-05-09). Reconcile before any Phase 7 work;
  origin is canonical for CM editorial UI.

## Frontend conventions

- Next.js 15 (app router). Tests = Vitest unit + Playwright e2e.
- Pages: `frontend/src/app/<pillar>/page.tsx`.
- Components: `frontend/src/components/<pillar>/`.

## Backend conventions

- Pytest in `backend/tests/`.
- Migrations: numbered, idempotent where possible, in
  `scripts/migrations/NNN_name.sql`. Applied at first boot via
  `docker-entrypoint-initdb.d`. Substrate v3 schema = migrations
  063 – 073 (see `02-substrate-pipeline.md`).
- Branches: `fix/<area>-phase-N` for bundled remediation; one PR per
  phase, stacked.
