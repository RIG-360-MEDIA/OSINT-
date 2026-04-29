# CLAUDE.md

Project context for any Claude session working in this repo. Read this
before touching infrastructure or making assumptions about how things run.

## What this project is

RIG Surveillance — a multi-pillar intelligence aggregator. Backend is a
FastAPI service plus Celery workers; frontend is a Next.js 15 client.

Pillars (each a separate page + ingest pipeline):
- **Articles** (`/coverage`) — RSS / HTML scraping
- **Clips** (`/clips`) — YouTube transcripts
- **Cuttings** (`/cuttings`) — newspaper editions
- **Threads** (`/threads`) — social signals (Reddit/Twitter/Telegram)
- **Signals** (`/signals`) — "The Signal Room": Reddit + Telegram feed
  with sentiment + entity matching. Twitter is **hidden from the user
  UI** for now (data layer remains active). Tasks run on the dedicated
  `social` queue (see `start.sh` and `backend/tasks/social_task.py`).
- **Documents** (`/documents`) — government PDFs (this is the "archive")
- **Brief** (`/brief`) — daily generated digest
- **Analyst** (`/analyst`) — per-user RAG over the corpus

## Deployment topology — IMPORTANT

The Docker deployment is **not** what most multi-worker Celery setups look
like. Read this before drawing inferences from compose alone.

### Containers (defined in `infrastructure/docker-compose.yml`)

| Service | Image | What runs in it |
|---|---|---|
| `rig-postgres` | `ankane/pgvector` | Postgres 16 + pgvector |
| `rig-backend`  | `infrastructure-rig-backend` | FastAPI **+ all Celery workers + Beat** |
| `rig-frontend` | `infrastructure-rig-frontend` | Next.js dev server |
| `rig-searxng`  | `searxng/searxng` | Web-search proxy |
| `rig-freshrss` | `lscr.io/linuxserver/freshrss` | RSS reader (data source) |

**There is no separate `rig-celery-worker-*` service.** Anyone reading
the compose file in isolation will conclude "no workers" and be wrong.

### Where workers actually live

`rig-backend` boots via `/start.sh`, which forks 6 background Celery
processes plus the FastAPI uvicorn in the foreground. The script lives
at `infrastructure/Dockerfile.backend` (CMD `["/start.sh"]`); to read
the actual launched processes, exec into the container:
`docker exec rig-backend ps -ef`.

### Queues and their consumers

| Queue | Consumer process | Concurrency | Tasks |
|---|---|---|---|
| `collectors` | `worker-collectors` | 1 | RSS, HTML |
| `social`     | `worker-social`     | 2 | Reddit / Twitter / Telegram + entity backfill |
| `youtube`    | `worker-youtube`    | 1 | YouTube transcript + entity tagging |
| `documents`  | `worker-documents`  | 2 (prefetch=1) | govt PDF collection + doctor + newspapers |
| `nlp`        | `worker-nlp`        | 4 | Article NLP / topic / entities / social sentiment / CM stance + speakers + clustering + dissent + counter-narratives |
| `relevance`  | `worker-relevance`  | 4 | Per-user article + doc scoring + CM voice-share / heatmap / exploitation index |
| `brief`      | `worker-relevance`  | (shared) | Daily brief generation |

Newspapers historically lived on `collectors` but were moved to
`documents` because the single-concurrency `collectors` worker was
regularly blocked by 30–60 minute RSS scrapes. CM political-intelligence
tasks (`tasks.cm.*`) route to either `nlp` (LLM-heavy) or `social`
(cheap aggregations).

**Resolved gap:** the `documents` queue had no consumer until the
2026-04-28 audit. `start.sh` now launches `worker-documents` with
concurrency=2 prefetch=1. Govt PDFs and newspapers drain on schedule.
Two compose-level beat schedulers running side-by-side would
double-fire every periodic task — confirmed footgun, do not split.

### Stale infrastructure on disk

`docker images` shows several `infrastructure-celery-worker-*` images
~2 weeks old. These are orphans from a previous compose iteration that
was bulk-committed away. They are not part of the current deployment
and should not inform inferences about which workers run.

## Source-of-truth files

When in doubt, these are authoritative:

- **Worker topology**: `infrastructure/Dockerfile.backend` + `/start.sh`
  inside the running `rig-backend` container.
- **Task routing**: `backend/celery_app.py` (the `task_routes` dict).
- **Database schema**: `scripts/migrations/*.sql` (numbered, applied in
  order at first boot via `docker-entrypoint-initdb.d`).
- **Frontend pages**: `frontend/src/app/<page>/page.tsx`.

## Govt-documents pillar — current state

- 53 source adapters registered (`backend/collectors/sources/*.py`,
  decorated with `@register_source`).
- 5 phases of fixes have shipped on branches `fix/archive-phase-1`
  through `fix/archive-phase-5`.
- 26 defects (D-1 → D-26) tracked in `docs/qa/documents-defects.md`.
- Per-source verdict matrix in `docs/qa/sources-per-source-verdict.md`.
- The `documents` queue has no consumer (see above) — that is why the
  database has only 15 rows from a 2026-04-23 manual run.

## Common foot-guns

1. **Adding a `rig-celery-worker-*` service to compose** without
   removing the in-container worker → double consumers, double Beat,
   double-fired periodic tasks.
2. **Restarting just `rig-frontend` or `rig-backend`** assuming it picks
   up host-side `npm install` or `pip install` — neither container
   bind-mounts `node_modules` / `site-packages`. Re-installs must
   happen *inside* the container, or via `docker compose build`.
3. **Editing `package.json` and assuming hot reload** — the dev server
   runs inside `rig-frontend`. Cache lives at `/app/.next`. Restart the
   container after dep changes.

## Conventions

- Migrations: numbered, idempotent where possible
  (`scripts/migrations/NNN_name.sql`).
- Frontend tests: Vitest unit + Playwright e2e
  (`frontend/src/app/**/__tests__/`, `frontend/e2e/`).
- Backend tests: pytest in `backend/tests/`.
- Branches: `fix/<area>-phase-N` for bundled remediation; one PR per
  phase, stacked.

## When in doubt

- `docker exec rig-backend ps -ef` — what's *actually* running.
- `docker exec rig-postgres psql -U rig -d rig -c "<sql>"` — DB state.
- `docs/qa/` — every audit and defect register from the QA pass.
