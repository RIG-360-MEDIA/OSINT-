# Archive (`/documents`) — Full Fix Plan

Translates the QA findings (`documents-defects.md`, `sources-why-broken.md`, `sources-per-source-verdict.md`) into ordered, executable phases. Each phase is independently shippable; later phases assume earlier ones landed.

## Phasing principle

1. Phase 1 = highest user-visible impact at lowest risk. Small diffs, no schema changes.
2. Phase 2 = correctness of the data going **in** (sources). Touches every adapter.
3. Phase 3 = quality / observability / refactor. Larger diffs but no behaviour regressions.
4. Phase 4 = new coverage (CAG, PIB) and stretch. Only if Phases 1-3 hold.

Estimates are person-hours, assuming the dev stack is up.

---

## Phase 1 — User-visible correctness (5 hours, no schema changes)

Goal: make the page tell the truth and let the user reach all the data.

| ID | File:line | Change | Effort |
|---|---|---|---|
| **D-4** | [page.tsx:147-150](../../frontend/src/app/documents/page.tsx) | Render an `ErrorBanner` when `!res.ok`. Preserve previous results on `loadMore` failure. | 45 m |
| **D-2** | [documents_router.py:60](../../backend/routers/documents_router.py) | Drop the `days` predicate when `cursor` is supplied — cursor itself bounds the window. | 10 m |
| **D-3** | [documents_router.py:158-175](../../backend/routers/documents_router.py) | Make `total` and `geography_counts` apply the same filters as the feed. Use `COUNT(*) OVER ()` window function so it's one query. | 30 m |
| **D-5** | [page.tsx:130-163](../../frontend/src/app/documents/page.tsx) | Wrap each `fetch` in an `AbortController`; abort on dep change; ignore `AbortError`. | 30 m |
| **D-1** | [documents_router.py:80,117-124,134](../../backend/routers/documents_router.py) | Cursor → composite of `(score_final, intrinsic_importance, collected_at, doc_id)`. Encode as base64 JSON. Update `next_cursor` derivation to match. | 3 h |
| **D-7** | [page.tsx:57-64](../../frontend/src/app/documents/page.tsx) | Add a "Window" filter row (7d / 30d / 90d / 1y / all) and forward as `?days=`. Treat `all` as `days=365`. | 30 m |

Verification:
- New router tests in `test_documents_router.py` (already scaffolded) flip from `xfail` → green.
- Frontend `it.fails` for D-4 flips → green.
- Manual: filter chips show real counts; pagination walks past 30 days; rapid filter clicks no longer race.

Rollback plan: each item is a small, independent diff. Revert per-commit if needed.

---

## Phase 2 — Source pipeline correctness (10–14 hours, code-only)

Goal: stop lying about dates and stop re-scraping history every night.

### 2A. Real `published_at` in every adapter (~6 hours)

Every adapter currently emits `"published_at": None`. The fix is per-adapter parsing of the date that's already on the listing page.

Strategy: introduce a single helper `_parse_listing_date(text, hints) -> datetime | None` in `backend/collectors/sources/_dateparse.py` that recognises:
- `dd-mm-yyyy`, `dd/mm/yyyy`, `dd.mm.yyyy`
- `dd Mon yyyy`, `Mon dd, yyyy`
- ISO `yyyy-mm-dd`
- `Notification dated ...`, `Order dated ...`, `W.P. ... / yyyy`

Then per family, update the row construction to call it on the link's surrounding `<td>`/`<li>`/`<p>` text.

Per-family touch-points (not all are equally easy):

| Family | Approach |
|---|---|
| `central_regulators` | RBI / SEBI / TRAI list dates next to the title in a sibling `<td>` — straightforward |
| `courts` | SCI / NGT / NCLT have a date column; TSHC/NCLAT use date-in-title (`"Order dated 12.03.2024"`) |
| `notifications` | Most ministries put the date inline; eGazette stays stub-only |
| `parliament` | Sansad: question/bill date is in the row; PRS bills: pub-date in the article header |
| `ip_permits` | IP India journal-tm publishes weekly with a known date; CDSCO / FSSAI use `<dt>` tags |
| `international` | World Bank / ILO use ISO; ADB / IMF / UN have date in card meta |
| `telangana_state` | GO IR / Gazette have GO numbers and dates; tenders use `closing_date` (best fallback) |

Where no date is parseable (e.g. archive pages), set `published_at = collected_at - 1 day` and log a `WARNING` so the gap is visible.

### 2B. Honor `since_days` (~2 hours)

Once 2A lands, every adapter gets a 5-line gate at the bottom:
```python
cutoff = datetime.now(UTC) - timedelta(days=since_days)
docs = [d for d in docs if d["published_at"] is None or d["published_at"] >= cutoff]
```
We keep `published_at is None` rows so we don't lose docs whose date couldn't be parsed; the warning above lets us track the gap rate.

### 2C. Playwright self-check at worker boot (~1 hour)

Add `backend/collectors/playwright_helper.py:probe()` that renders `https://example.com` and asserts non-empty HTML. Call from `backend/celery_app.py` worker startup signal. Fail loudly if Chromium isn't installed.

### 2D. Persist `dropped_junk_count` for drift detection (~2 hours)

Add a column `dropped_junk` to `govt_collection_runs`. Every adapter already computes `dropped` — just thread it back through the orchestrator and include it in the run record. Add a Slack alert when junk-rate > 50% for any source over 3 consecutive runs.

### 2E. Surface NLP failures (~1 hour)

`govt_documents.nlp_processed = FALSE` rows are currently invisible to the user (D-8). Add a `/api/documents/nlp-health` endpoint returning the unprocessed-count by source for the past 24h. Wire it to a small admin panel later (out of scope for this phase).

Verification:
- New `test_dateparse.py` with 30+ format fixtures.
- DB query `SELECT pct_with_date FROM ...` (in `sources-why-broken.md`) goes from ~0 % → > 80 %.
- After a fresh collection run, `SELECT COUNT(*) FROM govt_documents WHERE collected_at::date = today` drops sharply (no more re-scraping).

---

## Phase 3 — Code health, tests, observability (8 hours)

### 3A. Refactor `page.tsx` (1043 → ~300 lines, ~3 hours)

Extract to `frontend/src/app/documents/components/`:
- `DocumentRow.tsx`
- `DocumentDialog.tsx` (with proper `<dialog>` element, focus trap, Esc handler — closes D-10)
- `FilterRow.tsx`, `FilterPill.tsx` (with `aria-pressed` — closes D-12)
- `DeskMemo.tsx`, `LoadingState.tsx`
- `ErrorBanner.tsx` (lands as part of D-4)
- `useDocumentsFeed.ts` — custom hook owning fetch, abort, debounce.

### 3B. Accessibility cleanup (~1 hour)
- Modal: `role="dialog" aria-modal="true"`, focus trap via `react-focus-lock` (or homebrew), Esc-to-close.
- Filter pills: `aria-pressed={active}`, `role="group" aria-label="Desk filter"`.
- Decorative search glyph: `aria-hidden="true"`.
- `formatShortDate` → server-stable formatting (return `published_at_label` from API) to kill hydration warning (D-11).

### 3C. Auth-rotation handling (~30 min)
Subscribe to `supabase.auth.onAuthStateChange`; on `TOKEN_REFRESHED` update local token state. Closes D-13.

### 3D. Move Celery enqueue out of GET hot-path (~1 hour)
Today every `/feed` hit enqueues `score_govt_doc_for_all_users` for any unscored doc. Replace with: a periodic Celery beat task (every 5 min) that finds unscored docs and enqueues them — idempotent via Redis SADD. Closes D-9.

### 3E. Magic-constant lift (~30 min)
Move `_PER_PORTAL_CAP=15` and `_HTTP_TIMEOUT=30` from `govt_collector.py` to `backend/config/govt_config.py`, env-overrideable. Closes D-19.

### 3F. `govt_collection_runs` TTL (~30 min)
Add migration `008_govt_runs_ttl.sql`: scheduled cron `DELETE WHERE started_at < NOW() - INTERVAL '90 days'`. Closes D-20.

### 3G. Run all backend tests against the test DB (~1 hour)
Backend tests are scaffolded but not run yet. Provision `DATABASE_URL` for a disposable test DB; run; fix any breakage; lock in CI.

### 3H. Backfill failing fixtures, run e2e (~30 min)
Once Phase 1 lands, the 3 `it.fails` frontend tests turn green — remove `.fails`. Run Playwright e2e.

---

## Phase 4 — Coverage expansion (4–8 hours)

### 4A. Add CAG adapter (~2 hours)
Frontend already advertises a "CAG Reports" chip (D-17). Add `scrape_cag` to `notifications.py` for `cagofindia.delhi.nic.in/audit-report-list/`. httpx + selector for `/sites/default/files/audit_report_files/.*\.pdf`.

### 4B. Add PIB adapter to registry (~1 hour)
PIB exists in the legacy fallback path inside `govt_collector.py`. Promote it to a proper `@register_source("pib.gov.in")` in `notifications.py`. Closes D-16.

### 4C. Expand `DOC_TYPES` UI chips (~1 hour)
Today: 5 chips. Backend emits ~20. Two options:
1. **Static expansion** — hardcode the full list (faster).
2. **Facets endpoint** — `GET /api/documents/facets` returns the universe + counts; frontend renders dynamically (correct but more work).
Pick (1) for v1, (2) later. Closes D-6.

### 4D. (Stretch) State HC coverage
Add `bombay_hc`, `delhi_hc`, `madras_hc`, `karnataka_hc`. Each is a 1-2 hour adapter. Skip unless explicitly asked.

---

## Out of scope (deliberately, in this plan)

- Replacing Groq with another LLM provider.
- Re-architecting the relevance-scoring algorithm.
- Adding RAG-style chunked retrieval to the page (chunks already exist; UI doesn't use them yet).
- Full mobile redesign.

---

## Effort summary

| Phase | Hours | Outcome |
|---|---|---|
| Phase 1 | 5 | Page stops lying; pagination correct; users reach old docs; errors surfaced |
| Phase 2 | 10–14 | Real dates everywhere; daily delta is real; silent failures detected |
| Phase 3 | 8 | A11y green; file split; tests in CI; observability for NLP failures |
| Phase 4 | 4–8 | CAG + PIB adapters; full doc-type chips |
| **Total** | **27–35** | All 26 defects from `documents-defects.md` + `sources-why-broken.md` resolved |

## Rollout plan

- Each phase ships behind no feature flag; defects are bug fixes, not features.
- Phase 1 lands first, in a single PR per defect (6 PRs) so each can be reverted in isolation if it regresses.
- Phase 2A (date parsing) lands family-by-family (7 PRs) so a buggy parser in one family doesn't take down the others.
- Phase 3 can run in parallel with 2 (different files).
- Phase 4 only after a full Phase-2 collection run produces clean numbers.

## Recommended starting point

**Phase 1 in full, in one session.** It's 5 hours, no schema changes, immediate user-visible improvement, and unlocks honest QA of the rest.
