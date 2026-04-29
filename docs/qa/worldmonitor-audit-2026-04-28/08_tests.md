# 08 — Test coverage (Step 8)

**Verdict: FAIL — no worldmonitor tests, no e2e, no integration.**

## Backend tests
- 26 test files in `backend/tests/`.
- 6 are CM-specific: `test_cm_cache.py`, `test_cm_counter_narrative.py`,
  `test_cm_dissent.py`, `test_cm_router_smoke.py`, `test_cm_speakers.py`,
  `test_cm_stance.py`.
- All 27 unit tests pass; all 17 router-smoke tests pass.
- **`test_worldmonitor_router.py` does not exist.**
- The CM router-smoke is *structural* (paths, schemas, helper
  importability) — not integration. Endpoints are not exercised
  with auth + DB + assertions on response shape.

## Frontend tests
- Vitest configured (package.json), Playwright configured.
- 6 vitest spec files exist project-wide. **None for worldmonitor.**
- 5 Playwright e2e specs: brief, clips, coverage, cuttings, documents.
  **No worldmonitor.spec.ts.**
- No `frontend/src/app/worldmonitor/__tests__/` directory.

## Coverage summary
| Surface | Tests | Status |
|---|---|---|
| `cm_router.py` (16 endpoints) | 17 structural smoke tests | partial — no integration |
| `worldmonitor_router.py` (4 endpoints) | 0 | **none** |
| `cm_queries.py` SQL helpers | 0 (only signatures verified) | **none** |
| `nlp/cm/stance.py` | 9 unit tests | ✓ |
| `nlp/cm/speakers.py` | 5 unit tests | ✓ — but D-24 shows runtime hole |
| `nlp/cm/dissent.py` | 3 unit tests | ✓ |
| `nlp/cm/counter_narrative.py` | 4 unit tests | ✓ — but doesn't catch ungrounded cites at issue-relevance level |
| `nlp/cm/cache.py` | 5 unit tests | ✓ |
| `frontend/src/app/worldmonitor/page.tsx` | 0 | **none** |
| `frontend/src/app/worldmonitor/TelanganaBriefing.tsx` (713 LOC) | 0 | **none** |
| `frontend/src/app/worldmonitor/hooks/useTelanganaSignals.ts` | 0 | **none** |
| `frontend/src/app/worldmonitor/GlobalView.tsx` | 0 | **none** |
| Playwright e2e for `/worldmonitor` golden path | 0 | **none** |

## Defects added
| ID | Sev | Title |
|---|---|---|
| D-30 | HIGH | No backend integration tests for `worldmonitor_router.py` (4 endpoints) |
| D-31 | HIGH | No frontend tests (Vitest unit OR Playwright e2e) for the worldmonitor page |
| D-32 | MEDIUM | CM router-smoke is structural; no integration tests with seeded DB exercise the 16 endpoints |
| D-33 | MEDIUM | speakers/cluster_issues unit tests cover the parsers but not the *political-relevance* filter (D-23/D-25 root cause) |
