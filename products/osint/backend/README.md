# osint-backend

Read-only FastAPI service powering the RIG OSINT Morning Brief frontend.

Connects to `rig-postgres` as `analytics_user` — Postgres enforces read-only access on the `public.*` schema, so no application bug can corrupt the data engine.

## Endpoints

All under `/api/brief`:

| Path | Purpose |
|---|---|
| `GET /kpi` | The 4 KPI tiles (articles parsed, outlets, languages, sentiment) |
| `GET /entities` | 4 Watched Entity cards (Naidu, Rahul, Akhilesh, Owaisi) |
| `GET /emerging?limit=5` | Top-N surging entities for the EmergingSignals chips |
| `GET /stories?limit=5` | Defining Stories panel — ranked by importance_score |
| `GET /health` | Liveness — no DB call, always returns ok |
| `GET /ready` | Readiness — round-trips DB |

## Run it locally

```bash
# 1. Open SSH tunnel to Hetzner Postgres (in a separate terminal)
ssh -i ~/.ssh/rig_hetzner -L 5433:rig-postgres:5432 root@178.105.63.154 -N

# 2. Set up venv + deps
cd products/osint/backend
python -m venv .venv
source .venv/bin/activate         # or .venv\Scripts\activate on Windows
pip install -r requirements.txt

# 3. Configure
cp .env.example .env               # then edit OSINT_DB_URL with the real password

# 4. Run
uvicorn main:app --reload --port 8002

# 5. Smoke test
curl http://localhost:8002/health
curl http://localhost:8002/api/brief/kpi | jq .
```

## Run via Docker

```bash
docker build -t osint-backend .
docker run --rm -p 8002:8000 --env-file .env osint-backend
```

For production, deploy alongside `rig-backend` on Hetzner — connect via the Docker network at `rig-postgres:5432` (no tunnel).

## Architecture decisions

See `docs/BRIEF_PRODUCT_BUILD_PLAN.md` and `docs/OSINT_BRIEF_ROADMAP.md`.

**Path A:** This service is intentionally separate from `backend/` (the rig-surveillance data engine). It re-implements the same SQL queries the parallel session shipped at `backend/routers/brief_router.py`, but uses the read-only `analytics_user` role. The two services can be redeployed independently.

**Read-only safety:** SELECT-only privileges on `public.*` are verified at startup via `analytics_user`'s role grants — see migration `076_analytics_readonly_role.sql`.

## What this service does NOT do

- No mutation of `public.*` tables (Postgres blocks it; tested)
- No LLM calls (it's a query-and-shape layer)
- No Celery work (Celery lives in the data engine)
- No write paths at all — analytical views, if needed, go in the `analytics` schema (RW for this role)
