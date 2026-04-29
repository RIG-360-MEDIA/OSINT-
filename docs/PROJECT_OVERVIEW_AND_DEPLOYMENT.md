# RIG Surveillance — Project Overview & Cloud Deployment Guide

> Single-file briefing for a cloud / DevOps engineer who is taking over deployment of this stack. Covers what the system is, how it behaves, every external dependency, the Docker topology, and a ready-to-execute production deploy plan.

---

## 1. Executive summary

**RIG Surveillance** is a multi-pillar OSINT / intelligence aggregation platform.

- **Backend:** FastAPI (Python 3.11) + Celery (Postgres-backed broker) + 6 in-container Celery worker pools + Celery Beat.
- **Frontend:** Next.js 15 (Node 20) — currently runs in **dev mode** inside Docker (hot reload). Needs a production build target before public deploy.
- **DB:** Postgres 16 with the `pgvector` extension (LaBSE 768-dim embeddings, HNSW indexes).
- **Auth:** Supabase (JWT bearer tokens; backend validates locally without calling Supabase).
- **Ancillary services:** FreshRSS (RSS reader), SearXNG (private metasearch — only used when Dossier feature flag is on), and a separate "World Monitor" iframe app with its own Redis + AIS relay sidecar.

The system is currently designed for a **single-host Docker Compose** deployment. Scaling out is possible (see §10) but requires planning — workers are launched **inside** the backend container by `start.sh`, not as separate compose services. **Do not naively split workers off without removing them from `start.sh` first** — you will get a double Celery Beat and every periodic task will fire twice.

---

## 2. Pillars (product surface)

Each pillar is a frontend page + an ingest pipeline + a database table family.

| Pillar | Frontend route | Ingest source | Backend router |
|---|---|---|---|
| Articles | `/coverage` | RSS via FreshRSS + direct RSS + HTML scrape | `coverage_router` |
| Clips | `/clips` | YouTube Data API v3 + transcripts | `clips_router` |
| Cuttings | `/cuttings` | Daily newspaper PDFs (CareersWave + others) | `clippings_router` |
| Threads | `/threads` | Story clustering across pillars | `thread_router` |
| Signals | `/signals` | Reddit + Telegram (Twitter hidden in UI) | `signals_router` |
| Documents | `/documents` | 53 government PDF source adapters | `documents_router` |
| Brief | `/brief` | Daily LLM-generated digest | `brief_router` |
| Analyst | `/analyst` | RAG over the corpus (pgvector) | `analyst_router` |
| World Monitor | `/worldmonitor` | Iframe-embedded sibling app (display only) | `worldmonitor_router` (Telangana briefing only) |
| Onboarding / Auth | `/login`, `/signup`, `/onboarding` | Supabase | `onboarding_router` |
| Dossier (flagged) | `/dossier` (UI gated by `NEXT_PUBLIC_DOSSIER_ENABLED`) | OSINT — SearXNG, OpenSanctions, OpenCorporates, GDELT, Wayback, etc. | `dossier_router` |

---

## 3. Docker topology — IMPORTANT

The compose file is **not** a typical "one-service-per-worker" Celery layout. Read this section before changing anything.

### 3.1 Compose services (`infrastructure/docker-compose.yml`)

| Service | Image | Purpose | Host port |
|---|---|---|---|
| `rig-postgres` | `ankane/pgvector:latest` | Postgres 16 + pgvector | **5433** → 5432 |
| `rig-backend` | built from `infrastructure/Dockerfile.backend` | FastAPI **+ all 6 Celery workers + Beat** | **8000** |
| `rig-frontend` | built from `infrastructure/Dockerfile.frontend` | Next.js dev server | **3000** |
| `rig-freshrss` | `lscr.io/linuxserver/freshrss:latest` | RSS reader (data source for the article pillar) | **8081** |
| `rig-searxng` | `searxng/searxng:latest` | Private metasearch (Dossier only) | internal-only |
| `rig-worldmonitor` | built from `../world-monitor/Dockerfile` | World Monitor iframe app | **3001** |
| `rig-wm-ais-relay` | built from `../world-monitor/Dockerfile.relay` | AIS streaming relay | internal-only |
| `rig-wm-redis` | `redis:7-alpine` | World Monitor cache | internal-only |
| `rig-wm-redis-rest` | built (`Dockerfile.redis-rest`) | Upstash-style REST shim over Redis | internal-only |

All services share Docker network `rig-network`.

### 3.2 What runs **inside** `rig-backend`

`Dockerfile.backend` ends in `CMD ["/start.sh"]`. The script forks 6 Celery worker processes + 1 Beat in the background, then runs uvicorn in the foreground:

| Queue | Worker name | Concurrency | Tasks |
|---|---|---|---|
| `collectors` | `worker-collectors` | 1 | RSS, HTML scraping |
| `social` | `worker-social` | 2 | Reddit / Twitter / Telegram |
| `youtube` | `worker-youtube` | 1 | Transcript fetch + entity tagging |
| `documents` | `worker-documents` | 1 | Govt PDF extraction (Java JVM heavy) |
| `nlp` | `worker-nlp` | 4 | Language detect, entities, topic, geo, embedding |
| `relevance` | `worker-relevance` | 4 | Per-user scoring + brief generation (`brief` queue is shared) |
| `beat` | celery beat | 1 | Periodic schedule |
| `uvicorn` | foreground | — | FastAPI on :8000 |

> **Verify it's actually running:** `docker exec rig-backend ps -ef`.
> **Known historical gap:** the `documents` queue used to have no consumer; the worker line was added to `start.sh`. Confirm in your build that the `worker-documents` line is present.

### 3.3 Heavy build dependencies in the backend image

`Dockerfile.backend` installs all of these — your build host needs the disk + RAM headroom:

- `default-jre-headless` — required by `opendataloader-pdf` for newspaper PDF layout extraction.
- Playwright + Chromium + native libs (`libnss3`, `libatk*`, `libcups2`, etc.) — used by the JS-rendered govt portal adapters (SEBI, SCI, NGT, MCA, ADB, IMF, UN, CERC, PNGRB).
- `crawl4ai-setup` (extra Chromium + JS snippets) — runtime dependency.
- SpaCy `en_core_web_sm` — pre-downloaded into the image.
- `LaBSE` sentence-transformer (~1.8 GB) — pre-cached into the image so workers never need outbound HuggingFace traffic.

Image size is large (multi-GB). Build on a host with **≥ 8 GB free disk** and **≥ 4 GB RAM during build**.

### 3.4 Volumes & persistence

| Volume | Backs | Critical to back up? |
|---|---|---|
| `rig-postgres-data` | Postgres `/var/lib/postgresql/data` | **Yes — primary state** |
| `rig-freshrss-data` | FreshRSS config + feed list | Yes — feed catalog |
| `rig-wm-redis-data` | World Monitor cache | No (rebuildable) |
| Bind: `../scripts/migrations` → `/docker-entrypoint-initdb.d` | First-boot SQL | Source-controlled |
| Bind: `../backend` → `/app/backend` | Live code | **Dev-only mount — REMOVE IN PROD** |
| Bind: `../frontend/src` → `/app/src` | Live code | **Dev-only mount — REMOVE IN PROD** |
| Bind: `./searxng` → `/etc/searxng` | SearXNG settings | Source-controlled |

> The backend and frontend services **bind-mount source code** for hot reload. This is a **dev convenience** and must be removed for production — see §9.

---

## 4. Database

- **Engine:** Postgres 16 (`ankane/pgvector` image — pgvector pre-installed).
- **Schema bootstrap:** `scripts/migrations/*.sql` are mounted into `/docker-entrypoint-initdb.d` and applied **on first boot only**. Subsequent migrations require manual application (`docker exec rig-postgres psql -U rig -d rig -f /path/to/file.sql`) — there is **no migration tool** (Alembic, Prisma) in use today.
- **Migration files (current):** `001_initial_schema.sql` … `020_briefs_evidence.sql` — numbered, idempotent where possible.
- **Embeddings:** LaBSE 768-dim vectors stored in pgvector, HNSW indexes on the article corpus.
- **Connection strings (set as env vars on `rig-backend`):**
  - `DATABASE_URL=postgresql+asyncpg://rig:${POSTGRES_PASSWORD}@rig-postgres:5432/rig`
  - `DATABASE_URL_SYNC=postgresql://rig:${POSTGRES_PASSWORD}@rig-postgres:5432/rig`
- **Async engine config:** uses `NullPool`. **Do not** swap to a persistent pool — Celery tasks each call `asyncio.run()`, which destroys the loop; pooled asyncpg connections bound to the dead loop produce `cannot perform operation: another operation is in progress`.

---

## 5. External APIs & secrets

Every external dependency, why it's needed, and where to provision it.

### 5.1 Required for core operation

| Service | Env var(s) | What it powers | Where to get |
|---|---|---|---|
| **Supabase** | `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` | All user auth (JWT) | supabase.com project |
| **Groq** | `GROQ_API_KEYS` (comma-separated for rotation) | All LLM calls — briefs, summaries, RAG, onboarding | console.groq.com |
| **Postgres password** | `POSTGRES_PASSWORD` | DB auth | self |

### 5.2 Required per pillar

| Pillar | Env var(s) | Notes |
|---|---|---|
| YouTube / Clips | `YOUTUBE_API_KEY`, `YOUTUBE_API_KEY_2`, `YOUTUBE_API_KEY_3` (rotation), `YOUTUBE_PROXY_URL` (SOCKS5 — optional, used to bypass IP blocks; current value points to a host-side Cloudflare WARP proxy) | Daily quotas; rotation is in code |
| Twitter / Signals | `TWITTER_BEARER_TOKEN` | Optional — pillar skips silently if unset |
| Telegram / Signals | `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION_STRING` (MTProto user account — read public channels), `TELEGRAM_BOT_TOKEN` (alt path, requires bot in channel) | One of the two paths must be configured |
| FreshRSS / Articles | `FRESHRSS_URL` (defaults to internal `http://rig-freshrss:80`), `FRESHRSS_USERNAME`, `FRESHRSS_PASSWORD` | First boot of FreshRSS requires manual UI setup at :8081 to create user + import feeds |
| Govt documents | `GOVT_DEFAULT_SINCE_DAYS` (default 30), `GOVT_PER_PORTAL_CAP` (default 100) | No external key — public portals |
| Newspaper PDFs | none | Public CareersWave + per-paper portals |
| World Monitor / Telangana | `ACLED_ACCESS_TOKEN` (free tier), `WM_TG_CACHE_TTL_S` (default 1800) | Telangana briefing endpoint |

### 5.3 Optional — Dossier feature (`DOSSIER_ENABLED=true`)

| Env var | Service |
|---|---|
| `OPENSANCTIONS_API_KEY` | OpenSanctions sanctions/PEP screening |
| `OPENCORPORATES_API_KEY` | OpenCorporates company registry |
| `SEARXNG_URL` | Internal (`http://rig-searxng:8080`) |
| `DOSSIER_PER_ADAPTER_TIMEOUT_S` (default 12) | Per-adapter timeout |
| `DOSSIER_GDELT_TIMEOUT_S` (default 25) | GDELT adapter is slower |
| `NEXT_PUBLIC_DOSSIER_ENABLED=true` | Frontend gate |

If left disabled, neither the SearXNG container nor the Dossier router consume credentials.

### 5.4 World Monitor sub-stack (separate iframe app)

These pass through to the WM container; only the ones you actually use need values:

`AISSTREAM_API_KEY`, `FINNHUB_API_KEY`, `EIA_API_KEY`, `FRED_API_KEY`, `NASA_FIRMS_API_KEY`, `CLOUDFLARE_API_TOKEN`, `AVIATIONSTACK_API`, `WM_LLM_API_URL`, `WM_LLM_API_KEY`, `WM_LLM_MODEL`, `WM_GROQ_API_KEY`, `WM_REDIS_TOKEN` (default `wm-local-token`).

### 5.5 Tuning / non-secret

`ENVIRONMENT` (`development` / `production`), `NLP_BATCH_SIZE` (default 25), `BRIEF_ARTICLE_LIMIT` (default 30), `NEXT_PUBLIC_API_URL` (frontend → backend URL).

> **Source of truth for required vars:** `backend/main.py` runs a `_REQUIRED` env-var check at boot and refuses to start if any are missing. Read it before planning the secret set.

---

## 6. Celery schedule (Beat)

Defined in `backend/celery_app.py`. Runs inside `rig-backend`. Times in UTC.

| Task | Schedule | Queue |
|---|---|---|
| `tasks.collect_rss` | every 15 min | collectors |
| `tasks.collect_rss_direct` | every 30 min | collectors |
| `tasks.collect_html` | every 6 h | collectors |
| `tasks.process_nlp_batch` | every 30 s | nlp |
| `tasks.score_unscored_articles` | every 30 min | relevance |
| `tasks.generate_all_briefs` | daily 00:30 | brief |
| `tasks.reset_groq_keys` | daily 00:05 | default |
| `tasks.collect_govt_documents` | daily 06:30 | documents |
| `tasks.govt_doctor` | daily 07:00 | documents |
| `tasks.collect_newspapers` | daily 07:30 | collectors |
| `tasks.dict_reload` | every 5 min | default |
| (social tasks: Reddit/Twitter/Telegram + sentiment aggregation) | various | social |

**Footgun:** running two `rig-backend` replicas → two Beat schedulers → every periodic task fires twice. If you scale out, run **exactly one** Beat (see §10).

---

## 7. Authentication flow

1. User logs in via Supabase on the Next.js frontend (`/login`).
2. Frontend stores the Supabase session, sends `Authorization: Bearer <JWT>` on every API call.
3. Backend `auth_middleware.get_current_user` decodes the JWT **locally** (base64 + JSON) — no network call to Supabase. It checks the `exp` claim and returns `{id, email}`.
4. Signature is **not** verified today — the comment notes "sufficient for a local-only dev tool". **For production this must be hardened** (verify JWT against the Supabase JWKS) — flag this to the security review before public exposure.

---

## 8. Observability & health

- Postgres: `pg_isready` healthcheck (5s interval).
- FreshRSS: HTTP healthcheck on :80.
- Backend: **no healthcheck defined** — recommend adding `GET /health` (already exists per `main.py`) to compose.
- Frontend: no healthcheck.
- Logs: stdout from each container; collect with `docker logs` or wire to your logging stack.
- There is no APM / metrics export. If you need one, add OTEL or Prometheus exporters.

---

## 9. Going to production — concrete checklist

The current compose is dev-tuned. Before exposing this to the internet:

### 9.1 Frontend (`rig-frontend`)

- [ ] Switch `Dockerfile.frontend` from `npm run dev` to a multi-stage build: `npm ci && npm run build` → run `next start -p 3000`.
- [ ] Drop the `WATCHPACK_POLLING` / `CHOKIDAR_USEPOLLING` env vars and the bind mounts (`../frontend/src`, `../frontend/public`, `next.config.ts`).
- [ ] Set `NEXT_PUBLIC_API_URL` to the **public** backend URL (HTTPS) — it is baked into the build at `next build` time.
- [ ] Put it behind a CDN / reverse proxy (Cloudflare, ALB, or Caddy/Nginx).

### 9.2 Backend (`rig-backend`)

- [ ] Remove the `../backend` and `../scripts` bind mounts so the running code is the image, not the host filesystem.
- [ ] Set `ENVIRONMENT=production` — this disables `/api/admin/*` and `/api/debug/*` routers.
- [ ] **Harden Supabase JWT verification** — fetch JWKS and verify signatures (not just decode).
- [ ] Tighten CORS in `backend/main.py` — currently allows `http://localhost:3000` and `:3001` only; add the public origin.
- [ ] Run uvicorn with multiple workers (`--workers 4`) **or** put it behind gunicorn — currently single-process.
- [ ] Add a `HEALTHCHECK` to the Dockerfile (`curl -f http://localhost:8000/health || exit 1`).

### 9.3 Database

- [ ] Move Postgres off the app host or use a managed Postgres with pgvector (Supabase's own Postgres, AWS RDS + pgvector extension, Neon, etc.). Update `DATABASE_URL` / `DATABASE_URL_SYNC`.
- [ ] First-boot init via `/docker-entrypoint-initdb.d` only runs on an empty data directory — for managed DB you must run `scripts/migrations/*.sql` manually in numeric order.
- [ ] Set up automated backups (snapshots or `pg_dump` to S3).
- [ ] Rotate `POSTGRES_PASSWORD` from any value committed to a `.env`.

### 9.4 Secrets

- [ ] Move every secret out of `infrastructure/.env` into your secret manager (AWS Secrets Manager, GCP Secret Manager, HashiCorp Vault, Doppler, etc.).
- [ ] **Audit the repo for any committed real keys** before public hosting — there are example keys visible in `.env.example` files (YouTube keys in particular look real). Rotate anything that ever sat in a committed file.
- [ ] The MTProto Telegram session string (`TELEGRAM_SESSION_STRING`) authenticates as a real user account — treat it like a long-lived password.

### 9.5 Networking

- [ ] Public TLS termination via Cloudflare / ALB / Caddy. Only `:3000` (frontend) and possibly `:8000` (backend) need to be reachable; everything else stays on the internal network.
- [ ] Consider **not** exposing the backend publicly — proxy `/api/*` from the frontend host (Next.js rewrites already exist for `/world-monitor-app/*`; extend the same pattern).
- [ ] Lock FreshRSS (`:8081`) behind basic auth or a VPN — it's an admin UI for the feed catalog.
- [ ] SearXNG is internal-only by design — keep it that way.

### 9.6 Worker scaling

If single-host CPU isn't enough:

- [ ] Pull worker boot lines out of `start.sh` into a separate image / compose service.
- [ ] **Set `--without-beat` semantics** — only one container should run Beat. Concretely: keep the Beat line **only** in the FastAPI container (or a dedicated `rig-beat` service) and remove it everywhere else.
- [ ] Switch the broker from Postgres-backed Celery to Redis or RabbitMQ if throughput becomes an issue (current setup uses `sqlalchemy+postgresql://`).

---

## 10. Recommended target deployment shape

Two viable paths, pick one:

**(A) Lift-and-shift to a single VM** (fastest, mirrors current setup)
- 1× compute instance: ≥ 4 vCPU, ≥ 16 GB RAM, ≥ 100 GB disk (image is large + Postgres data).
- Docker + docker compose plugin.
- Reverse proxy (Caddy or Nginx) on :443 → frontend :3000 and :8000.
- Managed Postgres (Supabase / RDS / Neon — must support pgvector).
- Daily cron'd `pg_dump` to object storage.
- Suitable for: pilots, internal tools, < 50 concurrent users.

**(B) Container-orchestrated** (ECS / Fly / Railway / Kubernetes)
- 1× FastAPI service (autoscale on CPU).
- 1× Beat service — **single replica, never scaled**.
- N× worker services (one per queue, scale independently). Pull workers out of `start.sh` first.
- Managed Postgres + pgvector.
- Redis or managed RabbitMQ for Celery broker.
- FreshRSS + SearXNG as their own services.
- World Monitor as a sibling app on the same network.
- Frontend as a static deploy (Vercel) **or** containerised Next.js standalone.

---

## 11. Operational cheatsheet

```bash
# What's actually running inside the backend container
docker exec rig-backend ps -ef

# Tail logs from one worker
docker exec rig-backend tail -f /var/log/celery-nlp.log   # if logging is wired up; else use docker logs

# Apply a new migration to a running Postgres
docker exec -i rig-postgres psql -U rig -d rig < scripts/migrations/021_my_change.sql

# Check pgvector indexes
docker exec rig-postgres psql -U rig -d rig -c "\d articles"

# Force-run a Celery task
docker exec rig-backend python -c "from backend.tasks.collector_tasks import collect_rss; collect_rss.delay()"

# Rebuild after changing requirements.txt or Dockerfile
docker compose -f infrastructure/docker-compose.yml build rig-backend
docker compose -f infrastructure/docker-compose.yml up -d rig-backend

# Frontend dep change — the dev container does NOT bind-mount node_modules
docker compose -f infrastructure/docker-compose.yml build rig-frontend
docker compose -f infrastructure/docker-compose.yml up -d rig-frontend
```

---

## 12. Common foot-guns (carry these forward)

1. **Adding `rig-celery-worker-*` compose services without removing in-container workers** → double consumers + double Beat → every periodic task fires twice.
2. **Restarting `rig-frontend` / `rig-backend` after host-side `npm install` / `pip install`** → no effect. Neither container bind-mounts `node_modules` / `site-packages`. Always rebuild the image.
3. **`docker images` shows `infrastructure-celery-worker-*` from a prior compose iteration** → orphans, ignore.
4. **The frontend bakes `NEXT_PUBLIC_*` env vars at build time, not run time.** Changing them requires `docker compose build rig-frontend`.
5. **First boot reads `scripts/migrations/*.sql` only on an empty Postgres data volume.** Subsequent migrations are manual. Document this for the on-call.
6. **JWT signature is not verified.** Acceptable for internal/dev; **must** be fixed before public exposure.

---

## 13. Where to look when something breaks

| Question | Where |
|---|---|
| What workers are actually running? | `docker exec rig-backend ps -ef` |
| What tasks are queued? | `psql -U rig -d rig -c "SELECT * FROM kombu_message LIMIT 20;"` |
| Why is X env var required? | `backend/main.py` (`_REQUIRED` block + boot validators) |
| What's in the Beat schedule? | `backend/celery_app.py` (`beat_schedule` dict) |
| Govt-pillar source list | `backend/collectors/sources/*.py` (53 adapters) |
| Per-source defect register | `docs/qa/documents-defects.md` |
| Worker queue routing | `backend/celery_app.py` `task_routes` dict |
| Frontend → API base URL | `NEXT_PUBLIC_API_URL` env var |

---

## 14. Hand-off summary for the cloud engineer

You need to provision:

1. **Compute** — one VM (option A) or an orchestrator (option B). Sizing in §10.
2. **Postgres 16 + pgvector** — managed instance preferred. Run `scripts/migrations/*.sql` in order on first deploy.
3. **Secret store** — populate every variable enumerated in §5. The `_REQUIRED` list in `backend/main.py` is authoritative for what blocks boot.
4. **Frontend hosting** — either keep the container (after switching it to `next build && next start` per §9.1) or deploy `frontend/` to Vercel and point `NEXT_PUBLIC_API_URL` at the backend.
5. **Reverse proxy + TLS** — Cloudflare / ALB / Caddy.
6. **Backups** — Postgres + FreshRSS volume.
7. **Logging / metrics** — wire `docker logs` into your stack; consider OTEL.
8. **Production hardening** — JWT verification, CORS allowlist, uvicorn workers, drop dev bind mounts (§9).

Build the backend image on a host with ≥ 8 GB free disk; the LaBSE model + Playwright Chromium + JRE make the image multi-GB but are pre-cached so workers do not need outbound network at runtime.

End of document.
