# Decommission Plan — keep only desk.rig360media.com (night-desk)

## Verified keep-boundary (the ONLY things the night-desk needs)
1. **`products/osint/*`** — osint-backend + frontend + queries (the night-desk app).
2. **`night-desk-dist`** — deployed Vite build (the `.bak-*` copies can go).
3. **rig-backend INGESTION WORKERS ONLY** — the Celery tasks/collectors/NLP that fill
   `public.*` (articles, article_districts, sources, entity_dictionary, districts,
   event_clusters, entity-mention data). NOT rig-backend's HTTP API.
4. **rig-postgres** + migrations (shared DB; osint-backend = analytics_user).
5. **rig-caddy** — reconfigured to serve ONLY desk.rig360media.com.
6. **Ingestion support containers** (VERIFY each is still used by kept workers before
   keeping): rig-freshrss (RSS source), rig-searxng (web search), rig-ytproxy +
   rig-bgutil-pot (youtube), the laptop relay. 

## Confirmed independent (safe to retire — no night-desk dependency)
- osint-backend imports 0 rig-backend code; 0 refs to worldmonitor/mc/redis.
- night-desk global-layers = ACLED + NASA EONET (external); broadcast = self-embedded.

---

## STAGE 1 — dead rig-backend code (SAFE, reversible, do first)
Delete the 181 provably-unreachable modules (see scratch/deadcode_report.txt):
routers(18) + tasks/cm(15) + tasks/coverage(10) + tasks/newsroom(16) +
tasks/narrative(9) + social/misc(6) + adapters/dossier/nlp.cm/story_clustering/
observability.brief_*/old-collectors(106) + their ~40 tests.
- Method: on a git branch → `python -c "import backend.main, backend.celery_app"`
  + `celery inspect registered` must pass → only then sync to /root/rig.
- Risk: none (unreachable at boot, no dynamic dispatch).

## STAGE 2 — strip rig-backend HTTP API (keep workers)
The legacy domains that consumed rig-backend's API are being retired, so the
FastAPI surface (routers observe/clippings/me/admin/rbac) serves no one.
- Option A (low effort): leave the API running but unrouted (harmless once Caddy
  drops the legacy domains). Keep rig-backend container = workers + idle API.
- Option B (clean): trim start.sh to run workers only, drop uvicorn + routers.
- RECOMMEND Option A first (zero risk), Option B later.

## STAGE 3 — retire legacy frontend (old Next.js)
- Delete `frontend/src` (+ frontend app), remove `rig-frontend` from compose,
  stop+rm rig-frontend container.

## STAGE 4 — retire worldmonitor
- Delete `archive/world-monitor`, remove rig-worldmonitor + rig-wm-redis +
  rig-wm-redis-rest + rig-wm-ais-relay + rig-wm-seeder from compose, stop+rm them.

## STAGE 5 — retire mc app
- Identify mc source dir, delete it, remove mc-frontend + mc-backend from compose,
  stop+rm them.

## STAGE 6 — Caddy: collapse to one site
- Remove robin-osi.rig360media.com, 178-105-63-154.nip.io, mc.*.nip.io blocks.
- Keep only the desk.rig360media.com block. Reload Caddy.

## STAGE 7 — verify + clean compose
- desk.rig360media.com still loads + serves data; ingestion still writes public.*.
- Remove orphaned images/volumes ONLY after a soak period (rollback window).

## Execution rules
- Code deletions on a git branch first; infra teardown is separate + gated.
- After EACH infra stage: confirm desk.rig360media.com works before the next.
- Keep a rollback path (don't prune images/volumes until soak passes).
- /root/rig git index is SHARED with a concurrent newspaper session — coordinate.
