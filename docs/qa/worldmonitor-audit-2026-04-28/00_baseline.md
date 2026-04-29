# 00 — Baseline (Step 0)

**Date:** 2026-04-28
**Branch:** `feat/embed-worldmonitor`
**Auditor:** Claude (Opus 4.7)

## Verdict: PASS with notes

## Findings

### Containers up (`docker ps`)
| Container | Image | Status |
|---|---|---|
| rig-backend | infrastructure-rig-backend | Up 49m |
| rig-frontend | infrastructure-rig-frontend | Up 2h |
| rig-postgres | ankane/pgvector | Up 2h (healthy) |
| rig-freshrss | lscr.io/linuxserver/freshrss | Up 2h (healthy) |
| rig-searxng | searxng/searxng | Up 2h |
| **rig-worldmonitor** | rig-worldmonitor:latest | Up 2h (healthy) |
| **rig-wm-seeder** | rig-worldmonitor-seeder:latest | Up 2h |
| **rig-wm-redis** | redis:7-alpine | Up 2h |
| **rig-wm-redis-rest** | rig-worldmonitor-redis-rest:latest | Up 2h |
| **rig-wm-ais-relay** | rig-worldmonitor-ais-relay:latest | Up 2h (healthy) |

> **NEW finding (not in plan/CLAUDE.md):** the `rig-wm-*` sidecar
> stack (5 containers) backs the Global iframe view. CLAUDE.md
> documents only the original 5 services and lists no WM stack.
> Audit scope must extend to these — add to defects to update CLAUDE.md.

### Worker topology (`docker exec rig-backend ps -ef`)
All 6 Celery worker processes + Beat + uvicorn running:
- `worker-collectors` (concurrency=1)
- `worker-social` (concurrency=2)
- `worker-youtube` (concurrency=1)
- **`worker-documents` (concurrency=2, prefetch=1)** ✅
- `worker-nlp` (concurrency=4)
- `worker-relevance` consumes `relevance,brief` (concurrency=4)
- `celery beat`
- `uvicorn backend.main:app --reload`

> **CLAUDE.md is STALE.** It claims the `documents` queue has no
> consumer; `start.sh` lines 27–34 actually launch
> `worker-documents`. The documents-queue gap is **closed**. Update
> CLAUDE.md.

### CM tables (`\dt cm_*`)
All 10 tables present:
- cm_coalitions, cm_counter_narratives, cm_dissent_signals,
  cm_issue_evidence, cm_issues, cm_political_handles, cm_promises,
  cm_risk_calendar, cm_spokesperson_quotes, cm_stance_scores

### Migration files (`scripts/migrations/`)
- 020 → 029 present in correct order.
- ⚠️ **DUPLICATE migration prefix 030**:
  - `030_cm_source_id_uuid.sql`
  - `030_rbac_and_impersonation.sql`
  - On first-boot, postgres `docker-entrypoint-initdb.d` applies
    files in alpha order, so `cm_source_id_uuid` would run first,
    then `rbac_and_impersonation`. Behavior is currently
    deterministic but the convention is broken; file as MEDIUM.
- ⚠️ No `schema_migrations` tracking table — confirmed by
  `SELECT FROM schema_migrations` raising
  `relation "schema_migrations" does not exist`. Applied migrations
  cannot be enumerated; we infer application from table presence.

### Playwright inside rig-backend
6 `playwright/driver` node processes + chrome-headless-shell
running. This is a heavy resident memory consumer; verify which
collector launches them and whether they run idle. File as MEDIUM
(performance / hygiene).

### Recent commits
Top 10 commits all touch worldmonitor (matches feat branch). Last
commit `d820634 fix(worldmonitor): center-modal dialog`.

## Defects flagged at this stage
| ID | Sev | Description |
|---|---|---|
| B-1 | MEDIUM | Two migration files share prefix `030_*` — fix one (e.g. rename to 031). |
| B-2 | MEDIUM | No `schema_migrations` tracking table — adopt a tracker (Alembic / sqlx / app-side ledger) to know which migrations applied. |
| B-3 | LOW | CLAUDE.md claims documents queue has no consumer; start.sh disagrees — update doc. |
| B-4 | MEDIUM | Multiple Playwright/chrome processes resident in rig-backend; verify only-on-demand spawn, not always-on. |
| B-5 | INFO | rig-wm-* sidecar stack (5 containers) is undocumented in CLAUDE.md. |
