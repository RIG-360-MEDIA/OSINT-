# Quality Scorecard — `/documents` page

Scores are filled where a static-only audit allows. Cells marked **TBD** require Phase D (live session against the dev DB / running server) — placeholders kept so the scorecard is reusable across runs.

Scoring scale: 1 (broken) … 5 (excellent).

| # | Dimension | Score | Evidence |
|---|---|---|---|
| 1 | **Source coverage** | 3 / 5 | 47 adapters across 7 families. Solid central-regulator and Telangana coverage; **gaps**: no CAG, no PIB, no state HCs outside Telangana, no other state govts. UI advertises a "CAG Reports" chip with no backing adapter. See [govt-sources-inventory.md](govt-sources-inventory.md). |
| 2 | **Relevance to user** | TBD | Needs DB query against `user_govt_doc_relevance.score_final` distribution per user (Phase D, query in `documents-live-session.md`). |
| 3 | **Freshness** | TBD | Needs `SELECT median(NOW() - collected_at) FROM govt_documents WHERE nlp_processed`. |
| 4 | **Pagination correctness** | 1 / 5 | **Broken** — D-1 (cursor mismatch with ORDER BY) + D-2 (`days` floor blocks deep pagination). User can never reach old data; can see duplicates within current window. |
| 5 | **Error visibility (user)** | 1 / 5 | API failure renders the same empty-state as "no matches" (D-4). No retry UI. |
| 6 | **Filter coverage (user)** | 2 / 5 | Geography: 4 / 4 ✓. Doc type: 5 / ~20 ✗ (D-6). Date window: 0 / 1 (no UI; capped at 30d, D-7). Search: present, no boolean operators, no field-targeted search. |
| 7 | **Type safety (FE↔BE)** | 5 / 5 | Feed shape matches `DocumentItem` interface field-for-field. ✓ |
| 8 | **Accessibility** | 2 / 5 | Modal lacks `role`, `aria-modal`, focus trap, Esc-to-close (D-10). Chips lack `aria-pressed` (D-12). Decorative icon not `aria-hidden`. Date locale risks hydration mismatch (D-11). axe scan deferred to C2 e2e. |
| 9 | **Comprehension aids** | TBD | % of feed rows with `summary_preview != null AND why_it_matters != null` — DB query. |
| 10 | **Trust (link integrity)** | TBD | % of `document_url` returning HTTP 2xx — Playwright probe in C2. |
| 11 | **Latency p50 / p95** | TBD | Benchmark: 100 cold + 100 warm `/feed` calls; capture in Phase D. |
| 12 | **Resilience (adapter health)** | TBD | Needs `--with-db` re-run of `list_govt_sources.py`. % adapters with `last_success_at < 7d`. |
| 13 | **Observability** | 2 / 5 | `logger` used; `govt_collection_runs` audit table exists. **Gaps**: no metrics on Groq quota burn, no alert on adapter failure rate, lazy-fanout failures swallowed (D-9), unprocessed-doc backlog invisible (D-8). |
| 14 | **Code health (page.tsx)** | 2 / 5 | 1043 lines, 7 inline components, no extraction (D-18). Else: clean state, debouncing correct, no `console.log`. |
| 15 | **Code health (router)** | 3 / 5 | Bound parameters throughout, clean auth, narrow exception mapping. **Minus**: GET endpoint enqueues Celery work (D-9), bare `except Exception`. |
| 16 | **Test coverage** | 1 / 5 | One test file (`test_govt_intel.py`) for the entire 47-adapter / 3-endpoint feature (D-21). Phase B/C scaffolding raises this. |

## Aggregate

- **Pre-fix overall:** ~2.2 / 5 weighted across the 16 dimensions where a number is available.
- **Score-able now (10 dims):** 25 / 50.
- **Blockers to ship-readiness:** D-1, D-2, D-4, D-5 (the four P0/P1s). Everything else is incremental.

## Quick-win ladder

If only 1 day of fixes is available, take in this order — each unblocks the next:

1. **D-4** error UI (1 hour) — at least the user knows when the system is broken.
2. **D-2** drop `days` when cursor present (15 minutes) — users can browse the archive.
3. **D-3** filter-aware `total` (30 minutes) — chip counts stop lying.
4. **D-5** AbortController on refetch (30 minutes) — kills the stale-result race.
5. **D-1** cursor composite key (3 hours) — fixes pagination correctness end-to-end.

Total: ~5 hours to move from 2.2 → ~3.5.
