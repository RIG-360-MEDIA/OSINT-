# Defects Register — `/documents` page

Severity: **P0** = data correctness / 5xx storm | **P1** = broken feature / wrong UX | **P2** = a11y / observability / silent failure | **P3** = code health / polish.

> **Status (2026-04-28 audit pass):** All 21 defects closed across phases 1–9.
> The Phase 9 audit (this pass) ground-truthed the register against current code,
> closed the four remaining items (D-8, D-11, D-13, D-14) and tightened D-15
> exception logging. See "Closing notes" at the bottom for evidence.

| ID | Sev | Layer | File:line | Symptom | Status |
|---|---|---|---|---|---|
| D-1 | P0 | backend | [documents_router.py:117-155](../../backend/routers/documents_router.py) | Cursor predicate filters by `collected_at` only, but ORDER BY is dominated by `score_final`. Pages produce **duplicates and skips** depending on score distribution. | ✅ **CLOSED** (phase 6) — composite cursor over `(score_null, score, intrinsic, collected_at, doc_id)` with strict-less-than predicate. |
| D-2 | P0 | backend | [documents_router.py:98-106](../../backend/routers/documents_router.py) | `days=30` clause re-applies on every cursor page → user can never reach docs older than 30 days even though `total` advertises thousands. | ✅ **CLOSED** (phase 6) — `days` predicate dropped once `cursor_state is not None`. |
| D-3 | P1 | backend | [documents_router.py:189, 235-265](../../backend/routers/documents_router.py) | `total` and `geography_counts` ignore active filters → UI shows misleading "X of 12,345" while filtered set has only 50. | ✅ **CLOSED** (phase 6) — `COUNT(*) OVER ()` window in feed query; geo-counts share base WHERE. |
| D-4 | P1 | frontend | [page.tsx:264-272](../../frontend/src/app/documents/page.tsx) | `!res.ok` silently sets `documents=[]` and returns. API outage / 401 / 500 indistinguishable from "no matches". | ✅ **CLOSED** (phase 5) — `ErrorBanner` rendered with retry; previous documents preserved on append failure. |
| D-5 | P1 | frontend | [page.tsx:51, 80-82, 102, 139-143](../../frontend/src/app/documents/page.tsx) | No `AbortController` on filter-change refetch — older slow response can clobber newer fast one (stale-result race). | ✅ **CLOSED** (phase 5) — single AbortController ref, aborted on every refetch + on unmount. |
| D-6 | P1 | frontend | [lib/constants.ts:18-49](../../frontend/src/app/documents/lib/constants.ts) | `DOC_TYPES` exposes 5 of ~20 emitted types → most data unreachable via filters. | ✅ **CLOSED** (phase 5) — list expanded to 28 entries covering every adapter-emitted type. |
| D-7 | P1 | frontend | [page.tsx:220-229](../../frontend/src/app/documents/page.tsx) | No date-range UI — `days` is silently capped at backend default 30. | ✅ **CLOSED** (phase 5) — Window FilterRow with 7/30/90/365 day pills; forwarded as `?days=`. |
| D-8 | P2 | backend | [tasks/govt_task.py](../../backend/tasks/govt_task.py) | `nlp_processed = TRUE` hardcoded → docs that fail Groq / language detect are invisible forever (silent data loss). | ✅ **CLOSED** (phase 9) — per-source `nlp_degraded` counter; degradation rate logged at INFO, escalated to WARNING above 30%. |
| D-9 | P2 | backend | [documents_router.py:218-233](../../backend/routers/documents_router.py) | GET enqueues Celery tasks on every page hit; no dedup; bare `except Exception`. | ✅ **CLOSED** (phase 6) — gated on `cursor_state is None`; warning-level logging. |
| D-10 | P2 | frontend | [components/DocumentDialog.tsx:35-51, 88-93](../../frontend/src/app/documents/components/DocumentDialog.tsx) | `DocumentDialog` lacks `role="dialog"`, `aria-modal`, focus trap, Escape-to-close. | ✅ **CLOSED** (phase 5) — role/aria-modal/Esc/focus-restore all present. |
| D-11 | P2 | frontend | [lib/constants.ts:71-83](../../frontend/src/app/documents/lib/constants.ts) | `formatShortDate` uses `undefined` locale → potential SSR/CSR hydration mismatch on non-`en-US`. | ✅ **CLOSED** (phase 9) — locale pinned to `'en-US'` so SSR (Node) and CSR (browser) agree regardless of client locale. |
| D-12 | P2 | frontend | [components/FilterPill.tsx:11-13](../../frontend/src/app/documents/components/FilterPill.tsx) | `FilterPill` lacks `aria-pressed`; chips not keyboard-navigable as a group. | ✅ **CLOSED** (phase 5) — `role="radio"` + `aria-checked` + `aria-pressed`. |
| D-13 | P2 | frontend | [page.tsx:53-79](../../frontend/src/app/documents/page.tsx) | Auth effect doesn't subscribe to `onAuthStateChange` → silent 401s after token rotation. | ✅ **CLOSED** (phase 9) — subscription added; SIGNED_OUT bounces to `/login`, TOKEN_REFRESHED swaps in the new token and the existing fetch effect re-runs. |
| D-14 | P2 | collector | [tasks/govt_task.py:209-216](../../backend/tasks/govt_task.py) | `geo_primary` left NULL with no fallback when geocoder fails → frontend renders blank chip. | ✅ **CLOSED** (phase 9) — falls back to `source.source_geography` when `tag_geography` returns falsy. |
| D-15 | P2 | tasks | [tasks/govt_task.py](../../backend/tasks/govt_task.py) (multiple) | Broad `except Exception` per source isolates failures but hides bug categories. | ✅ **CLOSED** (phase 9) — per-step `except Exception` blocks now use `logger.exception` so stack traces reach the operator. The catch-all retains broad scope intentionally for fail-soft degradation; categorising would re-introduce the brittleness phase 5 fixed. |
| D-16 | P2 | sources | [collectors/sources/notifications.py:432-483](../../backend/collectors/sources/notifications.py) | No PIB adapter in registry, but UI exposes `press_release` filter. | ✅ **CLOSED** (phase 7) — `@register_source("pib.gov.in")` `scrape_pib` lives in `notifications.py`. |
| D-17 | P2 | sources | [collectors/sources/notifications.py:392-426](../../backend/collectors/sources/notifications.py) | No CAG adapter — UI exposes `audit_report → CAG Reports` chip. | ✅ **CLOSED** (phase 7) — `@register_source("cag.gov.in")` `scrape_cag` lives in `notifications.py`. |
| D-18 | P3 | frontend | [frontend/src/app/documents/](../../frontend/src/app/documents/) | 1043-line page.tsx — mixed data/layout/sub-components. | ✅ **CLOSED** (phase 5) — page.tsx now 374 lines; DocumentDialog, DocumentRow, FilterRow, FilterPill, ErrorBanner, DeskMemo, LoadingState, TagChip extracted to `./components/`. |
| D-19 | P3 | tasks | [backend/config/govt_config.py](../../backend/config/govt_config.py) | Magic constants `_PER_PORTAL_CAP=15`, `_HTTP_TIMEOUT=30` inlined. | ✅ **CLOSED** (phase 5) — lifted to `govt_config.py` with env-var overrides. |
| D-20 | P3 | schema | [scripts/migrations/009_govt_runs_ttl.sql](../../scripts/migrations/009_govt_runs_ttl.sql) | `govt_collection_runs` has no TTL → grows unbounded. | ✅ **CLOSED** (phase 5) — TTL migration shipped. |
| D-21 | P3 | tests | [backend/tests/test_govt_*](../../backend/tests/) | Only 1 test file covers the 47-adapter, 3-endpoint, 8-step-pipeline feature. | ✅ **CLOSED** (phases 5/8) — five govt-related test files now exist (`test_govt_collector`, `test_govt_intel`, `test_govt_intel_pipeline`, `test_govt_task`, `test_documents_router`). |

## Pre-fix → post-fix delta (achieved)

| Metric | Pre | Post |
|---|---|---|
| User can paginate beyond 30 days | ❌ | ✅ |
| Pagination has no dups/skips | ❌ | ✅ (composite cursor) |
| `total` matches filter | ❌ | ✅ (`COUNT(*) OVER ()`) |
| API failure shows error UI | ❌ | ✅ (ErrorBanner + retry) |
| Adapter test coverage | 1/47 | 5 govt test files (router, collector, intel, intel-pipeline, task) |
| Page a11y on dialog + chips | ❌ | ✅ (role/aria-modal/Esc, aria-pressed) |
| Filter chips reach all doc types | 5/~20 | 28/28 |
| SSR/CSR hydration on date | mismatch | ✅ (locale pinned) |
| Auth-token rotation handling | silent 401 | ✅ (onAuthStateChange) |
| `geo_primary` blank chip on geo-fail | shown | ✅ (source_geography fallback) |
| NLP-degradation visibility | invisible | ✅ (per-source % logged, WARN >30%) |

## Closing notes (phase 9 audit)

- The register's "fixes out of scope for this QA pass" disclaimer is no longer
  accurate — phases 5–8 closed 17 of the 21 items, and this phase 9 pass
  closed the remaining four (D-8, D-11, D-13, D-14) plus tightened D-15.
- CLAUDE.md's "documents queue has no consumer" note is also stale: the
  worker is forked at `backend/start.sh:30-35`. CLAUDE.md should be updated
  on its next pass.
- 47 source adapters are registered (not 53 as CLAUDE.md states).
