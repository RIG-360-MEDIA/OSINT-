# DEFECTS — Globe Page (WorldMonitor) Production Audit

**Date:** 2026-04-28
**Branch:** `feat/embed-worldmonitor`
**Scope:** WorldMonitor (globe) page end-to-end + the new CM
political-intelligence stack it depends on for the eventual
"go-deep" surface.

Defects are graded:
- **BLOCKER** — must fix before any production traffic.
- **HIGH** — fix before broader rollout.
- **MEDIUM** — fix in next sprint.
- **LOW / INFO** — track but optional.

## BLOCKER — content correctness (per `feedback_cm_content_correctness.md`)

| ID | Title | Where | Repro |
|---|---|---|---|
| **D-1** | All 9 cm_political_handles rows have NULL `verified_url` | `scripts/migrations/029_seed_opposition_handles.sql`, table `cm_political_handles` | `SELECT count(*) FROM cm_political_handles WHERE verified_url IS NULL` → 9 |
| **D-2** | 99% of cm_stance_scores + 82% of cm_spokesperson_quotes have empty state — state-scoped CM endpoints return near-empty | `backend/tasks/cm/stance_task.py`, `speakers_task.py` | stance state distribution: 5536/5582 unscoped |
| **D-3** | cm_counter_narratives + cm_dissent_signals both empty (LLM tasks no-op) | `backend/tasks/cm/{counter_narrative,dissent}_task.py` | `SELECT count(*) FROM cm_counter_narratives` → 0 |
| **D-23** | 100% of cm_spokesperson_quotes for state='TG' come from a single logistics article (Vamshi Karangula × 10) | `backend/nlp/cm/speakers.py` extraction filter | sample query in `06_content_quality.md` |
| **D-24** | Literal string "The article does not mention a specific named person" stored as `speaker` 7 times | `backend/nlp/cm/speakers.py` LLM-output validation | `SELECT speaker, count(*) FROM cm_spokesperson_quotes` |
| **D-25** | Top speakers pool dominated by cricketers (Piyush Chawla), actors (Sylvester Stallone), judges, agencies | `backend/nlp/cm/speakers.py` political-relevance filter missing | top-15 query in 06 |
| **D-26** | cm_issues clusters are world-news with NULL state; "Indonesia train accident scene" appears twice | `backend/tasks/cm/issues_task.py` clustering input filter | `SELECT * FROM cm_issues` — 5 rows, 0 TG/AP |

## BLOCKER — infrastructure / runtime

| ID | Title | Where | Impact |
|---|---|---|---|
| **D-8** | Groq API key returns 401 on every CM LLM task — stance/speakers/counter_narrative all silently no-op | env var `GROQ_API_KEY` | Backend logs: "Invalid API Key" continuous; counter_narratives stay empty until rotated |
| **D-18** | rig-worldmonitor CSP `frame-ancestors` only allows `localhost:3000`; frontend runs on `localhost:4000` → Global iframe blocked | nginx config inside `rig-worldmonitor:latest` image | User toggles to "Global" → empty iframe |
| **D-19** | WM dashboard `/api/health` UNHEALTHY: 40 EMPTY feeds, 14 STALE_SEED — seeder not refreshing | `rig-wm-seeder` sidecar | Embedded dashboard shows blank for 40 feed categories |

## HIGH — security

| ID | Title | Where | Fix |
|---|---|---|---|
| **D-11** | `cm_router.py` does not gate endpoints with `require_page("worldmonitor")` — any authenticated user can hit `/api/cm/*` | `backend/routers/cm_router.py:54` (router init) | `cm_router = APIRouter(..., dependencies=[Depends(require_page("worldmonitor"))])` |
| **D-17** | Frontend middleware can't reach backend in container — page-allowlist gate silently bypasses | `rig-frontend` env: `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` | Set a separate `INTERNAL_API_URL=http://rig-backend:8000` for SSR/middleware |

## HIGH — content / LLM

| ID | Title | Where | Fix |
|---|---|---|---|
| **D-9** | No surface signal when CM data is degraded (Groq down) — page silently shows defaults | `backend/routers/cm_router.py` + frontend | Add `data_health` field to dashboard response; render banner if degraded |
| **D-12** | Speaker / quote extraction permissive — returns sportspeople, judges, executives as political voices | `backend/nlp/cm/speakers.py` | Add political-relevance classifier or whitelist on `cm_political_handles` |
| **D-14** | Briefing LLM prompt conflates "ACLED token missing" with "no incidents"; produces falsely reassuring summary | `worldmonitor_router._generate_summary` | Pass `data_complete: bool` flag into prompt; suppress "stable" phrasing on missing data |
| **D-22** | cm_promises rows have generic landing-page source_urls; last_evidence_url 100% null | `cm_promises` seed | Per-pledge specific URLs + populate `last_evidence_url` from promise-status task |

## HIGH — testing

| ID | Title | Where |
|---|---|---|
| **D-30** | No backend integration tests for `worldmonitor_router.py` (4 endpoints) | `backend/tests/` |
| **D-31** | No frontend tests (Vitest unit OR Playwright e2e) for `/worldmonitor` | `frontend/src/app/worldmonitor/__tests__/`, `frontend/e2e/` |

## MEDIUM

| ID | Title |
|---|---|
| **D-4** | Quote `party` column not canonicalized (BJP vs Bharatiya Janata Party; 5 literal "null") |
| **D-5** | `cm_promises.source_url` should be NOT NULL once seed is finalized |
| **D-6** | No person-level handles seeded (only 9 party-level twitter accounts) |
| **D-7** | Only twitter platform represented; press_rss/html/youtube/telegram unused |
| **D-15** | `/api/cm/heatmap` solo latency 12s — exceeds single-call budget |
| **D-20** | No way to e2e-test worldmonitor page without real Supabase login; missing test harness |
| **D-28** | Process-local cache won't scale across uvicorn workers; switch to Redis (`rig-wm-redis` already running) |
| **D-32** | CM router-smoke is structural; no integration tests with seeded DB |
| **D-33** | Speakers/cluster_issues unit tests don't cover political-relevance filter (root cause of D-23/D-25) |
| **B-1** | Two migration files share prefix `030_*` (rbac + cm_source_id_uuid) — rename one to 031 |
| **B-2** | No `schema_migrations` tracking table — adopt Alembic / app-side ledger |
| **B-4** | Multiple Playwright/chrome processes resident in rig-backend; verify only-on-demand spawn |

## LOW

| ID | Title |
|---|---|
| **D-13** | LaBSE warmup blocks uvicorn startup ~3 minutes; move to background task |
| **D-21** | Phase-1 plan claim of "no AbortController" was wrong — cleanup IS present |
| **D-27** | RLS disabled on cm_* tables (acceptable for current architecture) |
| **D-29** | No cache-stampede protection on miss — add per-key asyncio.Lock |
| **D-34** | CORS `allow_origins` lists localhost-only entries; prod origin must be added via env |
| **B-3** | CLAUDE.md claims documents queue has no consumer; start.sh disagrees — update doc |
| **B-5** | rig-wm-* sidecar stack (5 containers) is undocumented in CLAUDE.md |

## INFO

| ID | Title |
|---|---|
| **D-10** | `celery -A backend.celery_app inspect active/registered` returns "no nodes replied" — sqla broker doesn't support broadcast |
| **D-16** | "Indonesia train accident" leaking into TG/AP issue clusters — confirms D-2 end-to-end |
| **D-35** | Prod must set `SUPABASE_JWT_SECRET` (already enforced — refuses to start without it in production) |

## Total
- **BLOCKER**: 10
- **HIGH**: 8
- **MEDIUM**: 12
- **LOW**: 7
- **INFO**: 3
