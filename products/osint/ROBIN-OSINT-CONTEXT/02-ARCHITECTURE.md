# 02 — Architecture & Deployment Topology

```
Browser (SPA)  ──►  Caddy (TLS, dockerized rig-caddy)  ──►  osint-backend (FastAPI)
desk.rig360media.com    /osint/* (same-origin, no CORS)        read-only analytics_user
static files from           │                                        │
/srv/night-desk             └────────────► rig-postgres (Postgres 16 + pgvector)
```

## Frontend (the SPA)
- **Code:** `products/osint/design/night-desk/` (Vite + React 18; deck.gl,
  react-map-gl/maplibre, framer-motion). Folder name is still `night-desk`
  (branding is ROBIN-OSINT).
- **Auth:** Supabase email/password → JWT in localStorage → `GET /api/me`.
- **Routing:** History-API; pages have real URLs (`/`, `/war-room`, `/analytics`,
  `/dossier`, `/map`, `/dispatch`). Sidebar collapsed by default + persisted.
- **API base:** `VITE_BRIEF_API`. **Prod = `/osint`** (relative, same-origin via
  Caddy → no CORS). Pinned in `.env.production` (`VITE_BRIEF_API=/osint`).
  Local `.env` points at the absolute `https://robin-osi.rig360media.com/osint`
  for dev — do NOT ship that to prod.
- **Build:** `npm run build` → `dist/`. Only `VITE_*` vars get baked into the
  browser bundle (other secrets in `.env` are server-side only and safe).
- **Serving:** Caddy site `desk.rig360media.com` serves static files from host
  dir **`/root/rig/night-desk-dist`** (mounted read-only to `/srv/night-desk` in
  the `rig-caddy` container). Deploy = copy `dist/` contents into that host dir.

## Backend (osint-backend)
- **Code:** `products/osint/backend/` (FastAPI). Container WORKDIR `/app`.
- **DB user:** `analytics_user` — **read-only on `public.*`, RW on `analytics.*`**
  (Postgres-enforced). Connection string in env `OSINT_DB_URL`.
- **Image is BAKED** (no bind mount): build context `../products/osint/backend`,
  `dockerfile: Dockerfile`. Code changes require scp + rebuild.
- **Defined in:** `infrastructure/docker-compose.yml` (service `osint-backend`).
- **Env:** uses the **DEFAULT `.env`** for variable substitution (NOT `.env.prod`).
  See the landmine in 09-OPERATIONS-RUNBOOK.md.
- **Endpoints:** `/api/me`, `/api/brief/*` (home, top-articles, warroom,
  analytics, dossier/*, map, channels, global-layers, country/*, district/*,
  report, report.pdf, report/send), `/health`, `/ready`.

## Database
- **Container:** `rig-postgres` (image `ankane/pgvector`, Postgres 16). Shared
  with the wider RIG platform.
- **Local access:** `docker exec -i rig-postgres psql -U rig -d rig` (trusts the
  local `rig` superuser; no password needed inside the container).
- **`analytics.now_sim()`** — the replay-safe "current time" used by ALL time
  windows. Currently equals real time (lag 0). If it ever drifts, the whole app
  looks frozen — check it first when "nothing updates."
- **`analytics.*`** holds caches + per-user prefs + translation cache (see 05).

## Caddy / TLS
- Dockerized **`rig-caddy`** (`caddy:2-alpine`). Caddyfile at
  `/root/rig/infrastructure/Caddyfile`; compose in
  `infrastructure/docker-compose.prod.yml`.
- `desk.rig360media.com` block: `/osint/*` → `osint-backend:8000`; everything
  else → static SPA from `/srv/night-desk` with SPA history fallback.

## Hosts & access
- **Hetzner prod:** `178.105.63.154`. SSH `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154`.
- **Repo on host:** `/root/rig/` (a separate checkout; may diverge from your
  local clone — always diff before overwriting whole files).
- **Two backends, two env files (CRITICAL):**
  - `osint-backend` → default **`.env`**.
  - `rig-backend` (the main RIG platform) → **`--env-file .env.prod`**.
  - The two files have **different `ANALYTICS_DB_PASSWORD`**. Mixing them up
    breaks DB auth. (This happened on 2026-06-05 and was fixed.)
