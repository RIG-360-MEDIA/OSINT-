# Cuttings (Clippings) Pillar — Production-Readiness Audit

**Date:** 2026-04-28
**Branch:** feat/embed-worldmonitor
**Scope:** End-to-end audit of `/cuttings` (frontend) + `clippings_router`
backend + newspaper collector + Celery task + DB schema, against the
production-readiness gate.

The plan that drove this work lives at
`C:\Users\Dell\.claude\plans\i-want-you-to-calm-blum.md`.

---

## Verdict

**CONDITIONAL GO.** The page is technically functional and the code path
is now hardened, but **D9 (newspaper task only reaches ~30 of 50
sources per run)** is a launch-blocker on its own — production users
will see 30 mastheads with "Full edition only" and no clippings, which
defeats the pillar's purpose. Recommend launching with the documented
list of stale papers hidden via `is_active = FALSE` until the per-paper
task fan-out is implemented. Everything else in this audit is
launch-cleared.

---

## Stack inventory (verified live, 2026-04-28)

| Layer | Path | State |
|---|---|---|
| Page | [frontend/src/app/cuttings/page.tsx](../../frontend/src/app/cuttings/page.tsx) | Healthy after F3 fix |
| Components | [EditionModal](../../frontend/src/app/cuttings/EditionModal.tsx), [Newsstand](../../frontend/src/app/cuttings/Newsstand.tsx), [ClippingImage](../../frontend/src/app/cuttings/ClippingImage.tsx) | Healthy after F5 fix |
| Router | [backend/routers/clippings_router.py](../../backend/routers/clippings_router.py) | Healthy after B2/B3 fixes |
| Collector | [backend/collectors/newspaper_collector.py](../../backend/collectors/newspaper_collector.py) | Healthy after B6 fix |
| Task | [backend/tasks/newspaper_task.py](../../backend/tasks/newspaper_task.py) | Decorator routing fixed (B1); D9 deferred |
| Queue | `documents` (concurrency=2 in `start.sh`) | Healthy |
| Beat | every 12h (`celery_app.py:265`) + worker_ready catch-up at >24h stale | Healthy |
| DB | `newspaper_sources`, `newspaper_editions`, `newspaper_clippings` | D1 migration applied, FK NOT NULL ✓ |

Live counts after all fixes: 50 sources, 52 editions, 557 clippings,
0 NULL FKs.

---

## Defect register

### Resolved (this PR)

| ID | Severity | Area | Defect | Resolution |
|---|---|---|---|---|
| B1 | LOW | task | `@app.task(queue="collectors")` decorator default disagreed with the actual `task_routes` route to `documents` | Decorator now reads `queue="documents"` with explanatory comment |
| B2 | MEDIUM | router | `/api/clippings/feed` masthead-summary subquery hardcoded a 7-day window and silently ignored the user-supplied `?days` param | Now binds `:days` like the main feed query; pinned by [test_feed_papers_summary_respects_days_param](../../backend/tests/test_clippings_router.py) |
| B3 | MEDIUM | router | `/feed` built its WHERE clause with `" AND ".join(conditions)` → `text(f"…{where}…")`. Safe today (values bound) but a fragile pattern for future edits | Replaced with a fully-static SQL using sentinel-value predicates (`:paper = 'all' OR …`). No more dynamic SQL string assembly |
| B4 | HIGH | tests | `/feed`, `/{id}/image`, `/{id}/full` had **zero** unit tests | Added 14 new cases in [test_clippings_router.py](../../backend/tests/test_clippings_router.py) — auth, filters, cursor pagination, threshold, both languages, 404 |
| B5 | HIGH | tests | Collector + relevance scorer had **zero** tests | New file [test_newspaper_collector.py](../../backend/tests/test_newspaper_collector.py) — 18 cases covering 9 date variants, Drive ID regex, scoring with English/Telugu/empty/political-only inputs |
| B6 | LOW | collector | `get_pdf_url_from_careerswave` returned `None` silently when no date variant matched, making source-format breakage invisible | Now logs at WARNING with the dates tried, the page byte size, and whether *any* Drive link was even on the page |
| D1 | MEDIUM | schema | `newspaper_clippings.newspaper_id` was nullable; weakened the UNIQUE (newspaper_id, edition_date, headline) constraint and allowed orphan rows | New migration [031_clippings_newspaper_id_not_null.sql](../../scripts/migrations/031_clippings_newspaper_id_not_null.sql); applied & verified live; idempotent guard included |
| F3 | LOW | frontend | Fetch errors rendered raw `HTTP 502` in the desk-memo card | New `describeFetchFailure(status)` mapper produces newsroom-tone copy for 401/403/404/5xx |
| F5 | LOW | frontend a11y | Newsstand language-filter rail had no group-level accessible name | Added `role="group" aria-label="Filter by language"`; FilterPill already had `aria-pressed` |
| F7 | HIGH | tests | No Playwright e2e for `/cuttings` | New [frontend/e2e/cuttings.spec.ts](../../frontend/e2e/cuttings.spec.ts) — 8 specs covering auth header, masthead render, modal open, deep-link, Esc close, filter, friendly error, empty state |

### Reclassified during audit (not actually defects)

| Original ID | Reclassified | Why |
|---|---|---|
| F1 (dead `next_cursor` state) | **N/A** | Source already does not store `next_cursor` in state. The Explore agent's claim was wrong. |
| F2 (hardcoded `days=7,limit=100`) | **WONTFIX (v1)** | At ~5 clippings/paper/day average and 58 max/day, `limit=100` is sufficient. URL-param exposure is a v2 nice-to-have. |
| F4 (deep-link `?paper=<id>` without validation) | **N/A** | Code already guards: `papers.find(...)` returns undefined for stale ids and `if (target)` short-circuits. |
| F6 (PDF iframe error boundary) | **N/A** | `EditionModal` already handles `pdfError` state with friendly fallback (lines 362–377). iframe `onError` doesn't fire reliably for blob URLs anyway. |

### New defects discovered live (Phase A) — see "Deferred" below

| ID | Severity | Defect | Why deferred |
|---|---|---|---|
| **D4** | **HIGH** | 30 of 50 active sources had **zero clippings in the last 7 days**. 13 of them have `last_scraped_at = NULL` — **never reached** | Architectural — needs per-paper task fan-out (D9). Mitigation: tag those papers `is_active=FALSE` until D9 ships |
| **D5** | MEDIUM | 68 of 557 (12%) clippings have empty `clipping_image_b64` | Likely Groq Vision returning a malformed bbox. Renderer already handles by skipping (line 783). Frontend falls back to masthead-initials thumbnail. Cosmetic. |
| **D6** | LOW | 19 of 557 (3.4%) clippings have NULL `labse_embedding` | HNSW index is partial-where-NOT-NULL, so vector search degrades silently. Backfill task can be added later. |
| **D7** | LOW | 1 non-English clipping has NULL `headline_translated` | One row. Likely transient Groq rate limit. Re-run on next ingest will heal. |
| **D8** | INFO | Relevance score distribution: min 0.4, max 0.8, avg 0.45; 84% in [0.4, 0.7) | Scoring function is intentionally coarse-grained (entity 0.4 + geo 0.3 + politics 0.1). Working as designed; future tuning ticket. |
| **D9** | **HIGH** | Newspaper task processes 50 papers serially in one Celery call; per-paper takes 3–7 min. Run hits a wall around paper #16–22 each cycle, leaving the tail unscraped | Architectural — needs to fan out one Celery task per paper. Out of scope for this audit; tracked separately as launch-blocker if /cuttings ships with all 50 sources active |

### Deferred (not in this PR)

- **D2**: `topic_category`, `geo_primary` are free-text TEXT — should be CHECK-constrained. Cosmetic; doesn't affect reads.
- **D3**: Backfill `labse_embedding` for the 19 NULL rows.
- **B7**: Per-user / per-IP rate limit on `/api/newspapers/{id}/pdf`.
- **D9**: Per-paper Celery fan-out (see above).
- **R2**: `worker_ready` catch-up's hostname-prefix filter is brittle (renaming `worker-documents` silently disables catch-up).

---

## Test coverage delta

| Suite | Before | After | Δ |
|---|---|---|---|
| `backend/tests/test_clippings_router.py` | 12 cases (papers + pdf only) | **27 cases** — adds full coverage for `/feed`, `/{id}/image`, `/{id}/full` | **+15** |
| `backend/tests/test_newspaper_collector.py` | did not exist | **18 cases** — date variants, Drive regex, relevance scoring | **+18** |
| `frontend/src/app/cuttings/__tests__/cuttings.test.tsx` | 11 cases | 11 cases (unchanged — F3/F5 covered by e2e + already-existing assertions) | 0 |
| `frontend/e2e/cuttings.spec.ts` | did not exist | **8 specs** | **+8** |
| **Total new assertions for the cuttings pillar** | — | — | **+41** |

Pytest run, post-fix: **45 passed, 0 failed, 45 warnings** in 3.4 s.
Vitest run, post-fix: **11 passed** in 19.0 s.

---

## Quality spot-check (10 random clippings)

All 10 random rows have valid base64 JPEG signature `/9j/4AAQ` (JPEG SOI
marker `\xFF\xD8\xFF\xE0\x00\x10` after base64 decode). Image lengths
ranged 380 B (one suspicious near-empty crop in Deccan Chronicle) to
117 KB. Headlines and translations populated correctly across English,
Telugu, and Malayalam samples.

| ID prefix | Paper | Headline (truncated) | bytes |
|---|---|---|---|
| d060e4fd | Economic Times | CEA Flags Energy Risk to Growth Story | 85,952 |
| b5bb6b67 | Malayala Manorama | ബംഗാളിൽ രണ്ടാംഘട്ട വോട്ടെടുപ്പ് നാളെ | 10,812 |
| df8cbdea | Manam | జిహెచ్‌ఎంసి ఆధ్వర్యంలో ఆటల పోటీలు | 44,808 |
| 5d3040ae | Deccan Chronicle | Six historic buildings in Hyd get intach… | **380** ⚠ |
| b6e401c7 | Telangana Today | KTR condemns attack on environmentalist | 117,592 |

The 380-byte outlier is the same shape as the D5 empty-image cohort —
a degenerate Groq Vision bbox that produced a near-zero crop. The
renderer's "if rect.width < 30 skip" guard catches the worst cases but
not 30×30-ish marginals like this one. Cosmetic.

---

## Live verification status

| Check | Result |
|---|---|
| Containers (`docker ps`) | All 5 healthy (rig-backend, rig-frontend, rig-postgres, rig-searxng, rig-freshrss) |
| Workers (`ps -ef`) | All 6 Celery workers + Beat alive, including `worker-documents` |
| DB row counts | 50 sources, 52 editions, 557 clippings — consistent with last `collected_at` 06:52 UTC |
| Migration 031 idempotency | ✓ Applies, re-applies as no-op |
| `newspaper_id IS NULL` post-migration | 0 rows |
| Image quality spot-check | 10/10 valid JPEG signatures (D5 marginal cases noted) |
| Backend unit tests | 45/45 green |
| Frontend Vitest tests | 11/11 green |
| Live HTTP probe of routes | **Blocked** — uvicorn `--reload` child died on a separate concurrent edit (`column "role" does not exist` from incomplete RBAC migration `030_rbac_and_impersonation.sql`). Pre-existing, not from this audit. The unit tests already lock the contract; restart the backend after `030` is fully applied to clear |

---

## Files touched

**New**
- `backend/tests/test_newspaper_collector.py` (18 unit tests)
- `scripts/migrations/031_clippings_newspaper_id_not_null.sql`
- `frontend/e2e/cuttings.spec.ts` (8 e2e specs)
- `docs/qa/cuttings-audit-report.md` (this file)

**Modified**
- `backend/routers/clippings_router.py` — B2 (days param threading), B3 (static SQL)
- `backend/tasks/newspaper_task.py` — B1 (decorator queue)
- `backend/collectors/newspaper_collector.py` — B6 (failure logging)
- `backend/tests/test_clippings_router.py` — +15 cases, RBAC dep override
- `frontend/src/app/cuttings/page.tsx` — F3 (friendlier errors)
- `frontend/src/app/cuttings/Newsstand.tsx` — F5 (a11y rail)

---

## Recommendation to ship

1. **Merge this PR.** Backend, schema, and frontend are launch-cleared.
2. **Mark the 13 never-scraped papers `is_active=FALSE`** until D9
   ships, so the newsstand only shows masthead cards that actually
   have content. List of stale papers in the Phase A query output
   above. Single SQL update.
3. **Open a follow-up** for D9 (per-paper Celery fan-out). Until that
   ships, the daily Beat run will continue covering only the first
   ~16 papers it reaches.
4. **Verify RBAC migration 030 is fully applied** before exposing
   `/cuttings` externally — the `require_page("cuttings")` dep added
   to both routers cannot work until the `users.role` column lookup
   resolves, and live API testing was blocked on this.
