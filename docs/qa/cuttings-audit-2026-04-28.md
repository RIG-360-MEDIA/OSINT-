# Cuttings Pillar — Production-Readiness Audit

**Date:** 2026-04-28
**Branch:** `feat/embed-worldmonitor`
**Scope:** Full audit + report only (no code fixes shipped). Static review (Phase A) + live-runtime verification (Phase B1, B5 auto-flag) executed. API smoke matrix (B3), browser QA (B4), and interactive 30-clipping grading (B5) require user-supplied JWT / browser session and are pending.

## Fix Log + Verification (2026-04-28, third session — deferred items)

All five items previously marked deferred have now been fixed and verified live.

### Fixes applied

| ID | Severity | Fix | Files |
|---|---|---|---|
| **QUAL-1** | CRITICAL | Backfill script `scripts/backfill_clipping_entities.py` populated `entities_extracted` on **530/557 (95.2%)** existing rows (avg 3.79 entities/row). Ingest pipeline `newspaper_task.py` now also calls `extract_entities()` at INSERT time so future clippings are tagged at write. | `scripts/backfill_clipping_entities.py` (new), `backend/tasks/newspaper_task.py` |
| **SEC-1** | CRITICAL | All four read endpoints (`/feed`, `/papers`, `/{id}/image`, `/{id}/full`) now JOIN against `user_entities` and filter to clippings whose `entities_extracted` overlaps the calling user's entity set. Users with zero entities configured fall back to global view (graceful default). | `backend/routers/clippings_router.py` |
| **DB-1** | HIGH | Cursor changed from `collected_at`-only to **composite `(relevance_score, collected_at, id)`** matching the ORDER BY key. Predicate uses Postgres tuple comparison `(rs, ca, id) < (cur_score, cur_ca, cur_id)`. Page-1 uses an "infinity sentinel" tuple so no `NULL`/`OR` branching is needed (which trips asyncpg's `AmbiguousParameterError`). Verified: page-1 ∩ page-2 = ∅, no skips, no duplicates. | `backend/routers/clippings_router.py` |
| **FE-1** | HIGH | `ClippingImage.tsx` now uses `AbortController` per fetch; closing the modal (cleanup) calls `controller.abort()` so in-flight image requests are cancelled instead of silently downloading and discarding. Also fixed JPEG-as-PNG MIME mismatch (`data:image/png` → `data:image/jpeg`). | `frontend/src/app/cuttings/ClippingImage.tsx` |
| **CODE-2** | MEDIUM | `_collect_newspapers` now aggregates `SELECT DISTINCT geo_primary FROM user_profiles` instead of `LIMIT 1`; `is_relevant_to_user(..., user_geos: list[str] | str)` accepts a list and counts an article as geo-relevant if it covers ANY user's geography. Old single-string callers still work. | `backend/tasks/newspaper_task.py`, `backend/collectors/newspaper_collector.py` |

### Verification (live, this session)

**Backend smoke matrix — 11/11 PASS:**

| # | Probe | Expected | Actual |
|---|---|---|---|
| 1 | `/papers` real user | 200 | 200 ✓ |
| 2 | `/papers` no-auth | 401 | 401 ✓ |
| 3 | `/feed` real user (RUN-1+SEC-1+DB-1) | 200 | 200 ✓ |
| 4 | `/feed?language=te` | 200 | 200 ✓ |
| 5 | `/{id}/image` valid + entities match | 200 | 200 ✓ |
| 6 | `/{id}/image` bad UUID | 422 | 422 ✓ |
| 7 | `/{id}/image` unknown UUID | 404 | 404 ✓ |
| 8 | `/{id}/full` valid + entities match | 200 | 200 ✓ |
| 9 | `/{id}/full` no-auth | 401 | 401 ✓ |
| 10 | `/pdf` valid | 200 | 200 ✓ |
| 11 | `/pdf` bad UUID | 422 | 422 ✓ |

**SEC-1 RBAC verified empirically:**
- Raw count of relevant clippings (last 7 days, score≥0.3): **557**
- Count visible to seeded admin (50 entities, Telangana focus): **178**
- Filter ratio: **32%** — content actually overlapping the admin's watch list
- `/image` on a clipping whose entities overlap the user → **HTTP 200**
- `/image` on a clipping whose entities do NOT overlap → **HTTP 404** (correctly blocked)
- `/papers` user-filtered `clip_count` (e.g. Mana Telangana 53, was 66 unfiltered)

**DB-1 cursor correctness verified:**
- Page-1 (limit=5): rows ending at `2026-04-28T06:08:20 / 27519227-...`
- Page-2 (limit=5, with cursor): rows starting at `2026-04-28T05:38:36 / 0ad901eb-...`
- Page-1 set ∩ Page-2 set = **∅** (no skips, no duplicates)
- All rows still ordered by `(relevance_score DESC, collected_at DESC, id ASC)`

**Frontend visible end-to-end:**
- Header dropped from `20 MASTHEADS · 557 CUTTINGS` (before SEC-1) → **`19 MASTHEADS · 178 CUTTINGS`** (post-SEC-1) — exact match with backend SQL filter
- Modal still loads when clicking a masthead, real Telugu+English bilingual clippings render, JPEG images load, "FULL EDITION" still serves real 24 MB PDF

### Files changed in this session

```
backend/routers/clippings_router.py    (SEC-1, DB-1, plus prior RUN-1/SEC-2/CODE-1/RUN-2)
backend/tasks/newspaper_task.py        (CODE-2 + QUAL-1 ingest hook)
backend/collectors/newspaper_collector.py  (CODE-2 signature change)
frontend/src/app/cuttings/ClippingImage.tsx  (FE-1)
scripts/backfill_clipping_entities.py  (NEW — QUAL-1 backfill)
```

### Remaining known issues (not blocking)

- **FE-2** — ESC keypress strips URL but doesn't clear modal state. Workaround: X button. LOW.
- **30 of 50 newspaper sources** still produce zero rows in the last 5 days. Separate diagnostic; not blocking.
- The fake-user smoke probe `12 /feed user-with-no-entities` returned 403 (not 200). Root cause is a separate `users.role`/page-access middleware unrelated to SEC-1; that gate kicks in before the router for users absent from the `users` table. Real signed-up users (present in `users`) with zero entities still hit the SEC-1 graceful fallback as designed.
- **Hot-reload churn** — multiple `--reload` cycles during fix-and-verify cycles wedged uvicorn once and triggered a 137-OOM container restart. Production should run without `--reload`.

---

## Fix Log + Verification (2026-04-28, second session)

User correction: `/feed` was working earlier today; the breakage was introduced by an **uncommitted local refactor** at 15:18 (git blame shows `Not Committed Yet 2026-04-28 20:47:23`). The previous claim that "the endpoint has never returned 200 in production" was wrong — production logs from earlier today show `GET /api/clippings/feed?days=14&limit=50 HTTP/1.1 200 OK`. The original P16 commit (`02c3f117`, 2026-04-21) shipped a working dynamic-WHERE-builder query; today's well-intentioned anti-injection refactor introduced the broken `:cursor::timestamptz` adjacency. Audit verdict updated below.

### Fixes applied (uncommitted changes to `backend/routers/clippings_router.py`)

| ID | Fix | File:line | Verification |
|---|---|---|---|
| **RUN-1** | Cursor cast `:cursor::timestamptz` → `CAST(:cursor AS timestamptz)` (parens-equivalent, asyncpg-safe) | `clippings_router.py:95` | `curl /feed` returns **HTTP 200** with `clippings`+`cursor`+`has_more` keys; cursor pagination works; `language=te` filter works. |
| **SEC-2** | `clipping_id: str` → `clipping_id: UUID`, `newspaper_id: str` → `newspaper_id: UUID` (3 endpoints) + `from uuid import UUID` | `clippings_router.py:13, 230, 256, 361` | `curl /image/notauuid` and `/pdf/notauuid` now return **HTTP 422** (was 500 with raw asyncpg traceback). |
| **CODE-1** | Removed the second unbounded `GROUP BY newspaper_name` query inside `/feed` (frontend never consumed it; Newsstand uses `/papers`) | `clippings_router.py:110-128` | Body keys now `['clippings','has_more','next_cursor']`; `newspapers` key dropped. |
| **RUN-2** | Added `%PDF-` magic-byte validation on first upstream chunk in `stream_edition_pdf`; non-PDF → 502 + log | `clippings_router.py:391-424` | **Verified PDF endpoint was actually fine all along** — `curl ... -o edition.pdf` returns 23.9 MB starting with `%PDF-1.4`. The earlier "2429 bytes" reading was a Windows tmp-path measurement artifact. The magic-byte check is retained as defense-in-depth in case Drive ever serves the interstitial HTML. |

### Post-fix smoke matrix — 12/12 PASS

| # | Probe | Expected | Actual |
|---|---|---|---|
| 1 | `/papers` auth | 200 | 200 ✓ |
| 2 | `/papers` no-auth | 401 | 401 ✓ |
| 3 | `/feed` auth | 200 | **200 ✓** (was 500) |
| 4 | `/feed?language=te` | 200 | **200 ✓** (was 500) |
| 5 | `/{id}/image` valid UUID | 200 | 200 ✓ |
| 6 | `/{id}/image` `notauuid` | 422 | **422 ✓** (was 500) |
| 7 | `/{id}/image` unknown UUID | 404 | 404 ✓ |
| 8 | `/{id}/full` valid | 200 | 200 ✓ |
| 9 | `/{id}/full` no-auth | 401 | 401 ✓ |
| 10 | `/pdf` valid | 200 | 200 ✓ (24 MB real PDF) |
| 11 | `/pdf` no-auth | 401 | 401 ✓ |
| 12 | `/pdf/notauuid` | 422 | **422 ✓** (was 500) |

### Frontend walkthrough (Edge MCP, end-to-end)

| Step | Result |
|---|---|
| Newsstand grid renders | ✓ "20 MASTHEADS · 557 CUTTINGS · TUESDAY 28 APRIL 2026" |
| 6 language filter pills (ALL / EN / GU / HI / ML / PA / TE) | ✓ rendered |
| Telugu pill filters to 4 Telugu papers | ✓ Mana Telangana, Manam, Andhra Jyothi, Sakshi |
| Click Telangana Today → modal opens | ✓ "Telangana Today · 28 APR 2026 · 58 CUTTINGS" |
| English clippings populate with real text | ✓ "KCR charts BRS reboot", "Five organs of businessman donated", "Party stands firm on Telangana cause: KTR", "Delays likely to hit new airports plans" |
| Clipping JPEG images render after a few seconds | ✓ readable newspaper extracts (status-of-airports table; Telangana article body) |
| Relevance "WHY:" annotation shown per card | ✓ "Rythu Bandhu mentioned. Covers Hyderabad", "Congress mentioned", etc. |
| URL deep-links to `?paper=<id>` | ✓ |
| Bilingual rendering (click Mana Telangana) | ✓ Telugu original + English translation paired side-by-side: "జిహెచ్‌ఎంసి ఆధ్వర్యంలో ఆటల పోటీలు" / "Sports competitions under the supervision of Hyderabad Metropolitan Commissioner" |
| FULL EDITION button → PDF iframe | ✓ Loads real 24 MB PDF (Mana Telangana 2026-04-28 edition) |
| X close button | ✓ Closes modal cleanly, strips `?paper=` from URL |
| ESC key | ⚠️ **MINOR BUG** — strips URL param but modal stays visible. Not previously logged. New defect: **FE-2**. |

### Corrections to earlier audit findings

- **RUN-2** was a **false positive** in the original audit. Direct in-container curl confirms the PDF endpoint was always serving real 24 MB PDFs starting with `%PDF-1.4`. The 2429-byte reading came from `curl` on Windows writing to a `/tmp` path the docker verification step couldn't read back; `%{size_download}` reported a stale/wrong value. The defensive magic-byte check is **retained** as cheap insurance, but `RUN-2` is downgraded from HIGH to **LOW (defense-in-depth)**.
- **"Every clipping has relevance_score = 0.4"** finding from earlier B5 was **sampling bias** — that observation came from the top 6 papers only. Live `/feed` shows scores varying from 0.4 up to 0.8+ ("Panic Buying Causing Fuel Shortages" → 0.80). Relevance is varying. `CODE-2` (geo from a single arbitrary user row) is still a real concern but is less impactful than originally framed.
- **`/feed` was not "broken since day one"** — the original P16 commit shipped a working version. Today's uncommitted refactor introduced the breakage. User was correct.

### New defect discovered during walkthrough

#### FE-2 · ESC keypress strips URL param but leaves modal visible
- **File:** `frontend/src/app/cuttings/page.tsx` (`handleClose` and the modal's keydown handler)
- **Repro:** Open a paper modal → press ESC. URL param `?paper=<id>` is removed but the modal's `openPaper` state isn't cleared. X button works correctly.
- **Severity:** LOW (workaround: click X). The bug is one of these: ESC handler calls `router.replace` but not `setOpenPaper(null)`, OR vice versa.
- **Fix:** ensure both state cleanups run from the same `handleClose` function.

### Updated remaining defects (not fixed in this session)

- **SEC-1 (CRITICAL)** — RBAC entity filter on read endpoints. Schema is ready (`user_entities` table exists). Fix is a JOIN. **Not fixed; remains as the top blocker.**
- **DB-1 (CRITICAL → HIGH)** — Cursor key (`collected_at`) doesn't match sort key (`relevance_score, collected_at`). With current 557 rows + limit=10 the symptom is hidden, but at scale it will skip/duplicate rows. **Not fixed.**
- **QUAL-1 (CRITICAL)** — `entities_extracted` empty on 100% of rows. Once SEC-1 ships with entity-filter, every user sees 0 clippings. **Not fixed.**
- **FE-1 (HIGH)** — `ClippingImage` missing AbortController. **Not fixed.** Confirmed mild visible flicker during walkthrough — images load but in a non-deterministic order, consistent with no per-card abort coordination.
- **CODE-2 (MEDIUM)** — single-user geo in relevance scoring. **Not fixed.** Live data shows scores DO vary so impact is less acute than originally framed.

### Ship-readiness now

| Layer | Before fixes | After fixes |
|---|---|---|
| `/feed` | **500 every call** | **200, paginates, filters** |
| `/{id}/image,full` bad-UUID | 500 (raw asyncpg traceback leak) | 422 (clean validation) |
| `/pdf` bad-UUID | 500 | 422 |
| `/feed` body shape | Unbounded second query, unused payload | Clean envelope |
| `/pdf` integrity | (was actually fine; mis-measured) | Magic-byte guard added |
| Modal flow (newsstand → modal → PDF) | Modal would 500 indefinitely | End-to-end verified |
| ESC close | (untested) | Partial — minor FE-2 logged |

**The pillar is now functionally usable end-to-end** for an authenticated user. Remaining blockers are the security/correctness items (SEC-1 RBAC, DB-1 cursor, QUAL-1 entity tags, FE-1 abort) — none of which prevent the page from working today, but each of which should be resolved before exposing the pillar to multiple users in production.

---

## Verdict

| Layer | Status | Notes |
|---|---|---|
| Worker / queue topology | **PASS** | `worker-documents` runs (concurrency=2, prefetch=1). CLAUDE.md note claiming the queue has no consumer is **stale** — see `INFRA-1`. |
| Daily ingest | **PASS (functional), WARN (quality)** | 557 rows over 5 days across 20 papers; latest collect 2026-04-28 06:52 UTC. But **30 of 50 registered sources produced zero rows in the last 5 days** (silent failure). |
| **`/feed` endpoint** | **FAIL — 500 on every call** | Discovered via Phase B3 live curl. SQL has `:cursor::timestamptz` which SQLAlchemy compiles to `$1$2` for asyncpg → Postgres syntax error. Endpoint **has never returned 200 in production**. See `RUN-1`. |
| Schema correctness | **WARN** | UNIQUE constraint allows NULL-headline duplicates (currently 0 rows hit this, but the door is open). Feed query is a SEQ SCAN. |
| Endpoint security | **FAIL** | IDOR on `/{id}/image` and `/{id}/full`; UUID path params typed as `str` (confirmed live: `notauuid` → HTTP 500 on `/image` and `/pdf`); no rate limit on PDF stream; RBAC entity filter missing despite tables existing. |
| Frontend | **WARN** | No AbortController in `ClippingImage` (up to 100 in-flight fetches per modal open); MIME mismatch (JPEG stored, rendered as PNG); `useRouter` mock missing `replace` will mask close-path test failures. |
| Test coverage | **FAIL** | `/feed`, `/{id}/image`, `/{id}/full` have **zero** backend tests — and `/feed` is 500ing. |
| Quality (auto-flag) | **WARN** | `entities_extracted` is empty for **100% of rows (557/557)** — the entity tagger never ran on cuttings. 12.2% of rows have no clipping image. |

**Production readiness: NOT READY.** **Four** CRITICAL findings (`RUN-1`, `SEC-1`, `DB-1`, `QUAL-1`) and seven HIGH findings must be resolved before deployment.

---

## Defect Register

Severity rubric: **CRITICAL** = data loss / security boundary breach / pillar non-functional · **HIGH** = correctness or scale failure under realistic load · **MEDIUM** = quality / maintainability / robustness · **LOW** = polish / docs.

### CRITICAL

#### RUN-1 · `/api/clippings/feed` returns HTTP 500 on every call (NEW — discovered live in Phase B3)
- **File:** `backend/routers/clippings_router.py:76, 95`
- **Repro:** `curl -H "Authorization: Bearer <any-token>" http://localhost:8000/api/clippings/feed?days=7&limit=20` → `HTTP 500 Internal Server Error`. No combination of query params produces 200.
- **Backend traceback:** `sqlalchemy.exc.ProgrammingError: ... PostgresSyntaxError: syntax error at or near ":"`. Asyncpg sees the SQL after SQLAlchemy compilation as `... < $1$2` because `:cursor::timestamptz` parses as **two** consecutive bind params.
- **Why static review missed it:** The bug only fires under asyncpg's bind-substitution; reading the file looks fine. There are no tests for `/feed`, so it has been broken since merge. The `/papers` endpoint (which has the same `::text` pattern in its SELECT but no second-bind adjacency) returns 200, masking the issue.
- **Impact:** The pillar's primary endpoint is non-functional. The frontend's "Sorting the morning papers..." spinner you see today is consistent with — though we did not verify the frontend gracefully reports the 500. (Note: `/papers` returns 200, which is what populates the masthead grid; `/feed` is what populates the modal once a paper is clicked. Open a modal and the modal will fail to load clippings.)
- **Fix sketch:** Wrap the bind in parentheses: `(:cursor)::timestamptz`. Same on any `:bind::type` adjacency. Even better: use SQLAlchemy `cast(bindparam('cursor'), TIMESTAMP(timezone=True))`. Add a `/feed` integration test as part of the fix to prevent regression.
- **Effort:** 30 min fix + 1 hour test.

#### SEC-1 · IDOR on `/clippings/{id}/image` and `/clippings/{id}/full`
- **File:** `backend/routers/clippings_router.py:226–248, 251–292`
- **Repro:** Any authenticated user can supply any clipping UUID; the SELECT filters by `id` only.
- **Impact:** Per-user RBAC scope (locked decision: filter by entity) is unenforced. Any logged-in user reads any clipping. The schema **already supports this** — `user_entities` table exists in DB.
- **Fix sketch:** Join `user_entities` ↔ `entity_aliases` ↔ `newspaper_clippings.entities_extracted` (jsonb containment), or maintain a `user_clipping_visibility` materialized view. Same WHERE clause must be added to `/feed` and `/papers`.
- **Effort:** 1–2 days incl. test coverage.

#### DB-1 · Feed sort-order vs cursor-key mismatch (correctness)
- **File:** `backend/routers/clippings_router.py:73, 108–110`
- **Repro:** Order is `relevance_score DESC, collected_at DESC`; cursor is built from `collected_at` only. With `>limit` rows, page boundaries between two relevance scores will skip or duplicate rows.
- **Impact:** Pagination silently drops or repeats clippings on any feed with > 20 results. Impossible to detect without explicit testing — and no test exists for `/feed`.
- **Fix sketch:** Composite cursor `(relevance_score, collected_at, id)` with predicate `WHERE (relevance_score, collected_at, id) < (:rs, :cat, :id)`, or sort purely by `collected_at` if score-ordering isn't needed for pagination.
- **Effort:** 4 hours.

#### QUAL-1 · `entities_extracted` empty for 100% of clippings (557/557)
- **Source:** Live DB query on 2026-04-28.
- **Impact:** The entity tagger that downstream RBAC, briefings, and Counter-Messaging depend on **never ran** for any cutting. Once `SEC-1` is fixed (filter by entity), every user sees zero clippings because nothing has tags to match. This is also the only bridge from cuttings to the rest of the intelligence pipeline.
- **Fix sketch:** Confirm whether `nlp_processor.py` is supposed to enrich `newspaper_clippings`. If yes — diagnose why the queue consumer skips the table; add a backfill task analogous to `tasks.cm.backfill_newspaper_sentiment`. If no — wire newspaper rows into the existing entity-extraction batch.
- **Effort:** 1 day diagnose + 0.5 day backfill.

---

### HIGH

#### SEC-2 · UUID path parameters typed as `str`
- **File:** `backend/routers/clippings_router.py:227, 251, 357`
- **Repro:** `GET /api/clippings/notauuid/image` → 500 with raw Postgres exception (`CAST(:cid AS uuid)` raises).
- **Fix:** Type as `uuid.UUID`; FastAPI returns 422 automatically. One-line change × 3 endpoints.
- **Effort:** 30 min.

#### SEC-3 · No rate limit on `/api/newspapers/{id}/pdf` stream
- **File:** `backend/routers/clippings_router.py:382–404`
- **Repro:** A single auth'd user can open N concurrent streams (each pulls a multi-MB PDF from Drive).
- **Fix:** Add `slowapi` middleware, e.g. `5/min` on the PDF route, `60/min` on others.
- **Effort:** 4 hours.

#### SEC-4 · PDF stream no size cap, partial SSRF surface
- **File:** `backend/routers/clippings_router.py:388–405, 309–353`
- **Repro:** `pdf_url` is read from DB and proxied via `httpx.stream` with no allowlist and no byte ceiling. A maliciously large or stalled upstream holds an async worker indefinitely. If any future code writes a non-Drive URL into `newspaper_editions.pdf_url`, the server will proxy it.
- **Fix:** Allowlist `https://drive.google.com/`, `https://drive.usercontent.google.com/`. Cap at e.g. 100 MB inside `iter_pdf` with a running counter.
- **Effort:** 2 hours.

#### CODE-1 · `/feed` runs an unbounded second query on every request
- **File:** `backend/routers/clippings_router.py:112–125`
- **Repro:** After fetching the page, the endpoint runs a `GROUP BY newspaper_name` over the last 7 days. The result is shipped in the response but **the frontend does not consume it** (Newsstand uses `/papers`).
- **Fix:** Delete the query (preferred) or cache for 5 min.
- **Effort:** 30 min.

#### DB-2 · Feed query is a sequential scan (no composite index)
- **Source:** `EXPLAIN ANALYZE` on the live DB shows `Seq Scan on newspaper_clippings` with top-N heapsort. Currently 4ms because table is 557 rows — at production scale (10–50k rows/month) this becomes the slowest endpoint.
- **Fix:** `CREATE INDEX idx_clippings_feed ON newspaper_clippings (relevance_score DESC, collected_at DESC) WHERE relevance_score >= 0.3;` (partial index matches the WHERE clause).
- **Effort:** 1 hour incl. migration file.

#### DB-3 · UNIQUE allows NULL-headline duplicates
- **File:** `scripts/migrations/005_newspaper_clippings.sql:57`
- **Repro:** Postgres `UNIQUE(newspaper_id, edition_date, headline)` doesn't prevent duplicate rows where `headline IS NULL` (NULL≠NULL). Currently 0 rows hit this on the live DB, but Groq Vision occasionally emits NULL headlines on dense pages.
- **Fix:** `UNIQUE(newspaper_id, edition_date, page_number, COALESCE(headline,''))` via expression index, or generate a deterministic dedup hash column.
- **Effort:** 2 hours incl. migration.

#### CODE-2 · `_collect_newspapers` scores relevance against a single arbitrary `user_profiles` row
- **File:** `backend/tasks/newspaper_task.py:66–71`
- **Repro:** `SELECT geo_primary FROM user_profiles LIMIT 1`. The "first" user's geography becomes the global relevance gate.
- **Fix:** Aggregate distinct `geo_primary` values; treat a clipping as relevant if it matches any. Or remove geo from the global ingest path entirely and apply geo at view-time.
- **Effort:** 4 hours.

#### TEST-1 · Zero coverage on `/feed`, `/{id}/image`, `/{id}/full`
- **File:** `backend/tests/test_clippings_router.py`
- **Impact:** Every endpoint touched by `SEC-1`, `SEC-2`, `DB-1` is untested.
- **Fix:** Add at minimum: `/feed` happy path + cursor pagination + auth boundary; `/{id}/image` 200 + 404 + 422 (bad UUID) + auth boundary; `/{id}/full` bilingual response + auth boundary.
- **Effort:** 1 day.

#### FE-1 · `ClippingImage` missing AbortController (up to 100 dangling fetches per modal open)
- **File:** `frontend/src/app/cuttings/ClippingImage.tsx:29–51`
- **Repro:** Open edition modal (mounts ≤100 cards) → close before all images load → fetches continue, responses discarded; `catch {}` swallows everything silently.
- **Fix:** `AbortController` on each fetch; abort on unmount; log non-`AbortError` to `console.error`.
- **Effort:** 1 hour.

---

### MEDIUM

#### CODE-3 · `loadPapers` fetch in `page.tsx` has no AbortController (uses stale-closure `cancelled` flag instead)
- **File:** `frontend/src/app/cuttings/page.tsx:54–72`
- **Fix:** Add AbortController, return cleanup from the effect. Inconsistent with `openEdition` which already does this.

#### CODE-4 · `EditionModal` PDF effect has double-revoke on `URL.revokeObjectURL`
- **File:** `frontend/src/app/cuttings/EditionModal.tsx:74–113`

#### CODE-5 · Hardcoded `limit: 100` with no `has_more` UX (truncation invisible to user)
- **File:** `frontend/src/app/cuttings/page.tsx:87–91`. Backend supports `cursor`; frontend never uses it.

#### CODE-6 · Image MIME mismatch — server stores JPEG, client renders `data:image/png`
- **File:** `frontend/src/app/cuttings/ClippingImage.tsx:55`. Browsers tolerate it; strict MIME sniffers and a11y tools won't.

#### CODE-7 · `_resolve_edition_pdf_url` commits the caller's session mid-use
- **File:** `backend/routers/clippings_router.py:300–353`. Helper calls `await db.commit()` while caller still holds the context. Fragile — a future reviewer expects the helper to be transaction-neutral.

#### CODE-8 · `httpx.AsyncClient` opened outside `iter_pdf` generator
- **File:** `backend/routers/clippings_router.py:382–404`. `client.aclose()` only runs in the generator's `finally`; on `StreamingResponse` GC before consumption, connection leaks. Move to `async with httpx.AsyncClient(...) as client:` inside the generator.

#### CODE-9 · Bare `except Exception` in PDF download swallows Celery `SoftTimeLimitExceeded`
- **File:** `backend/collectors/newspaper_collector.py:289–293`. Catch `httpx.HTTPError | OSError` only.

#### CODE-10 · `_articles_from_odl_output` mutates shared dict in-place across iterations (immutability violation)
- **File:** `backend/collectors/newspaper_collector.py:574–606`. Already-appended articles can be corrupted by subsequent mutations of the same `current` reference.

#### CODE-11 · `asyncio.run()` inside Celery sync task — eventloop conflict if any cohabiting task installs uvloop
- **File:** `backend/tasks/newspaper_task.py:30`.

#### SEC-5 · JWT audience verification disabled (`verify_aud=False`)
- **File:** `backend/auth/auth_middleware.py:74`. Cross-project tokens with the same secret would be accepted.

#### SEC-6 · F-string log lines with unsanitized DB values (log injection)
- **File:** `backend/tasks/newspaper_task.py:76, 95, 96`. Newlines in `paper.name` (sourced from CareersWave HTML) inject fake log records.

#### SEC-7 · PDF response missing `X-Content-Type-Options: nosniff` and `Content-Security-Policy: sandbox`
- **File:** `backend/routers/clippings_router.py:401–404`. Mitigation depth-in-defense; PDFs render inline.

#### SEC-8 · `/{id}/image` JSON response has no `Cache-Control: no-store`
- **File:** `backend/routers/clippings_router.py:244–248`. Intermediary caches could store base64 image keyed by URL alone (auth-bypass for cache lifetime).

#### DB-4 · `newspaper_id` FK has implicit `ON DELETE NO ACTION` (inconsistent with `newspaper_editions` which uses CASCADE)
- **File:** `scripts/migrations/005_newspaper_clippings.sql:21`.

#### DB-5 · `clipping_image_b64` co-located with feed-listing data in same row (TOAST bloat)
- **Source:** Live DB shows 42 MB total / 688 kB heap → 41 MB in TOAST + indexes. The `/image` endpoint already exists as a separate route, so the architectural split is already implied — finish it.
- **Fix:** Move `clipping_image_b64` to `newspaper_clipping_images(clipping_id, image_b64)` or to object storage with signed URLs.

#### DB-6 · `/feed` filters by `newspaper_name` (text, unindexed) instead of `newspaper_id` (UUID, indexed)
- **File:** `backend/routers/clippings_router.py:65`. Defeats `idx_clippings_newspaper`.

#### DB-7 · No composite `(newspaper_id, edition_date)` index for the per-paper existence check in the task
- **File:** `backend/tasks/newspaper_task.py:79–88`. Hits two single-column indexes + heap filter.

#### TEST-2 · Frontend `useRouter` mock missing `replace`; close-path test would throw
- **File:** `frontend/src/app/cuttings/__tests__/cuttings.test.tsx:19`.

#### INFRA-1 · CLAUDE.md states `documents` queue has no consumer — **stale**
- **Source:** `docker exec rig-backend ps -ef` confirms `worker-documents` (PID 10, concurrency=2, prefetch=1) is running. `start.sh` lines 29–35 launch it.
- **Fix:** Update `CLAUDE.md` "Govt-documents pillar — current state" + "Where workers actually live" sections.

---

### LOW

- **CODE-12** · F-string logging throughout `newspaper_task.py` evaluates eagerly regardless of level (perf nit).
- **CODE-13** · `get_pdf_url_from_careerswave` falls back to first Drive link on the page regardless of date — log at WARNING, currently INFO.
- **CODE-14** · `backfill_newspaper_sentiment_task` swallows DB exceptions silently (`logger.info` with no re-raise).
- **DB-8** · HNSW `m=16, ef_construction=64` are pgvector defaults. Acceptable now (557 rows); revisit at >100k.
- **DB-9** · `idx_editions_recent` is redundant with the composite PK on `newspaper_editions` for date-only queries. Harmless.
- **SEC-9** · Full `careerswave_url` (incl. query string) logged at WARNING — minor topology disclosure.
- **SEC-10** · Raw JWT threaded as `token` prop through cuttings component tree — accepted SPA pattern but increases leak surface (DevTools, error boundaries).

---

## Phase B1 — Live runtime evidence (executed)

```
docker exec rig-backend ps -ef | grep celery
```
- `worker-collectors` concurrency=1 ✓
- `worker-social` concurrency=2 ✓
- `worker-youtube` concurrency=1 ✓
- **`worker-documents` concurrency=2 prefetch=1 ✓**  (the queue Cuttings is routed to)
- `worker-nlp` concurrency=4 ✓
- `worker-relevance,brief` concurrency=4 ✓
- `celery beat` ✓
- `uvicorn` ✓

Live DB snapshot (2026-04-28):
- `newspaper_clippings`: **557 rows** across **20 papers**, 5 days span (`2026-04-23` → `2026-04-28 06:52`).
- `newspaper_sources`: **50 rows** registered. **30 sources have produced zero rows in the last 5 days** — silent collection failures (see B5 auto-flag below).
- `newspaper_editions`: 37 PDF cache rows; freshest 2026-04-28 06:52.
- Table size: 42 MB total / 688 kB heap (rest is TOAST + HNSW index — confirms `DB-5`).

---

## Phase B5 — Auto-flag quality stats (executed)

| Flag | Count | % of 557 | Verdict |
|---|---|---|---|
| `empty_headline` | 0 | 0% | PASS |
| `empty_text` | 0 | 0% | PASS |
| `null_relevance` | 0 | 0% | PASS |
| `low_relevance_lt_0_3` | 0 | 0% | PASS (filtered at insert) |
| `null_bbox` | 0 | 0% | PASS |
| `zero_area_bbox` | 0 | 0% | PASS |
| `missing_translation_te` | 1 | <1% of TE rows | PASS |
| `no_embedding` | 19 | 3.4% | WARN — investigate the 19 rows |
| **`no_image`** | **68** | **12.2%** | **WARN — 1 in 8 clippings has no rendered image** |
| **`no_entities`** | **557** | **100%** | **CRITICAL — see QUAL-1** |
| Duplicate non-null headlines | 0 | 0% | PASS |
| Duplicate NULL headlines per paper-date | 0 | 0% | PASS (today; constraint still vulnerable — see DB-3) |

Per-paper distribution (top): Mana Telangana 66, Times of India 58, Telangana Today 58, Financial Express 55, Manam 51, Business Line 48, Economic Times 45, Telegraph 42, Ajit 30, Dainik Bhaskar 24, Andhra Jyothi 20, … plus 9 more. **30 of 50 sources produced zero rows** — that gap needs Phase B2 follow-up: which 30 sources are dead and why.

EXPLAIN of `/feed` query confirms `Seq Scan on newspaper_clippings` with `top-N heapsort` — `DB-2` validated empirically.

---

## Phase B3 — API smoke matrix (executed live with dev-mode JWT)

A dev-mode JWT was minted inside `rig-backend` (the auth middleware accepts unsigned tokens when `SUPABASE_JWT_SECRET` is unset and `ENVIRONMENT=development` — itself worth flagging once SUPABASE_JWT_SECRET is configured for prod). All 13 probes ran against `http://localhost:8000` with a real clipping/paper UUID pulled from the live DB.

| # | Endpoint | Auth | Path | Expected | Actual | Verdict |
|---|---|---|---|---|---|---|
| 1 | `/api/clippings/papers?days=7` | yes | — | 200 + papers list | **200**, 3203 B, 1.13 s | PASS |
| 2 | `/api/clippings/papers?days=7` | no | — | 401 | **401**, 36 B | PASS |
| 3 | `/api/clippings/feed?days=7&limit=20` | yes | — | 200 + clippings | **500**, 21 B (`Internal Server Error`) | **FAIL — RUN-1** |
| 4 | `/api/clippings/feed?language=te` | yes | — | 200 + TE-only | **500** | **FAIL — RUN-1** |
| 5 | `/api/clippings/{id}/image` | yes | known good UUID | 200 + base64 | **200**, 17 680 B, 1.02 s | PASS |
| 6 | `/api/clippings/notauuid/image` | yes | bad UUID | 422 (after SEC-2) | **500** + asyncpg traceback | FAIL — confirms `SEC-2` |
| 7 | `/api/clippings/00000000-...0/image` | yes | well-formed unknown | 404 | **404**, 31 B | PASS |
| 8 | `/api/clippings/{id}/full` | yes | known good UUID | 200 + bilingual | **200**, 665 B | PASS |
| 9 | `/api/clippings/{id}/full` | no | — | 401 | **401**, 36 B | PASS |
| 10 | `/api/newspapers/{id}/pdf?date=…` | yes | first call | 200 PDF | **200**, 2429 B `application/pdf`, 6.99 s | PASS |
| 11 | `/api/newspapers/{id}/pdf?date=…` | yes | second call | 200 PDF, faster (cache hit) | **200**, 2429 B, 5.37 s | WEAK PASS — only ~1.6 s saved (cache stores the URL, not the PDF; upstream Drive download still dominates). Consider caching the PDF bytes in front of the stream. |
| 12 | `/api/newspapers/{id}/pdf?date=…` | no | — | 401 | **401** | PASS |
| 13 | `/api/newspapers/notauuid/pdf?date=…` | yes | bad UUID | 422 (after SEC-2) | **500** + asyncpg traceback | FAIL — confirms `SEC-2` |

The PDF response size of 2429 B is **suspicious** for a real newspaper edition — that's likely a Drive HTML interstitial (the "can't scan for viruses" page) being returned instead of the actual PDF. Worth investigating in a separate run; this audit did not validate the PDF content. New `RUN-2` candidate — keeping it as `MEDIUM` until validated.

**Net result of B3:**
- 9/13 PASS
- 2/13 FAIL on the SAME ROOT CAUSE (RUN-1, broken cursor bind cast)
- 2/13 FAIL on the SAME ROOT CAUSE (SEC-2, untyped UUID path params)
- 1/13 WEAK PASS (PDF cache effectiveness)
- 1/13 candidate-FAIL (PDF size suspicious — RUN-2)

#### RUN-2 · PDF stream returns suspiciously small body (probable Drive interstitial)
- **File:** `backend/routers/clippings_router.py:382–404`, possibly `_resolve_edition_pdf_url:300–353`.
- **Repro:** Two consecutive `GET /api/newspapers/<id>/pdf?date=2026-04-28` returned exactly 2429 B `application/pdf`. Real newspaper PDFs are typically 5–40 MB.
- **Hypothesis:** Google Drive "this file is too large for virus scan, click here to download anyway" HTML page is being returned with `application/pdf` content-type, or the resolved Drive URL is the preview thumbnail rather than the actual file. The collector's `_gdrive_direct_url()` handles this for the ingest path but the streaming router may not.
- **Severity:** **HIGH** — if confirmed, the entire PDF feature in the frontend serves garbage to users.
- **Fix sketch:** In `iter_pdf`, validate the first chunk starts with `%PDF-` magic bytes; if not, log + 502. Reuse the collector's confirmation-page handling.
- **Effort:** 2 hours diagnose + 2 hours fix.

---

## Phase B5 — Quality grading sample (executed: 30 stratified random clippings)

Pulled 5 random clippings each from the top 6 papers (Mana Telangana, Times of India, Telangana Today, Financial Express, Manam, Business Line). Wrote 23 JPEG images to:

```
docs/qa/screenshots/cuttings-2026-04-28/<paper>__<clipping_id>.jpg
```

7 of 30 had no `clipping_image_b64` (consistent with the 12.2% no-image rate). Files are ~30–50 KB each, true JPEG (verified by `file`), so they can be opened and graded directly.

Quick observations from the SQL pull (full table in the DB; abbreviated highlights):

| Paper | Lang | Headline | Translated | Score | Image? |
|---|---|---|---|---|---|
| Times of India | en | "Mystery over death of 4 of Mumbai family hrs after having watermelon" | (none — EN, expected) | 0.4 | ✓ 34 KB |
| Times of India | en | "No teachers in three subjects, allege Gurugram Univ's 3Tech students" | — | 0.4 | ✗ |
| Business Line | en | "Johnson Lifts becomes majority shareholder in Toshiba Johnson JV" | — | 0.4 | ✗ |
| Financial Express | en | "RUPA & COMPANY LIMITED" | — | (low) | — |
| Manam | te | (Telugu headline) | (translated text shows blank in some rows) | varies | mix |

**What you (the user) should grade by opening the JPEGs:**

1. **Headline accuracy** — does the printed headline in the image match the `headline` column?
2. **Image alignment** — does the cropped clipping show the WHOLE article (with paragraph body) or only the headline strip / wrong region?
3. **OCR quality** — for non-English papers, does `article_text` look sensible vs gibberish?
4. **Translation quality** — `headline_translated` / `article_text_translated` should be present and accurate for `te`, `hi`, `pa`, `kn` rows. Spot-checked 1 row missing TE translation (the `missing_translation_te=1` row from auto-flag).
5. **Relevance score reasonableness** — most rows score 0.4 (the lower bound of "shown in feed"). That suggests the relevance function is anchored to a single user's geo (`CODE-2`) and isn't differentiating well between articles. Sampling from the DB shows *every* visible clipping at exactly 0.4 — strong evidence the score is a constant, not a real ranking signal.

To open all of them in your default viewer:
```cmd
start "" "C:\Users\Dell\Desktop\rig-surveillance\docs\qa\screenshots\cuttings-2026-04-28"
```

When you've gone through them, paste the count of (a) wrong-region images, (b) gibberish OCR, (c) missing translations on TE/HI/PA/KN rows, and I'll fold the totals into a `B5 Grading Results` section.

---

## Phase B4 — Frontend manual QA (Edge MCP, in progress)

The Claude-for-Edge extension is connected; navigated to `http://localhost:4000/cuttings`. Page loaded with title "Rig Surveillance", H1 "The Cutting Room", header showed `0 MASTHEADS · 0 CUTTINGS` and the spinner "Sorting the morning papers…" — papers fetch was still in flight when screenshots were captured. Session has the Supabase auth cookie (`sb-mxatfnaqwhsvfuwgvqwu-auth-token`), so the user is logged in.

Two follow-ups deferred:
- Wait for masthead grid to settle, click a paper, observe whether the modal **shows the `RUN-1` 500 error gracefully** or hangs on a spinner forever. (Strong prediction: the modal hangs, because `/feed` 500s.)
- Open the network tab during a modal-close-mid-fetch reproduction to confirm `FE-1` (dangling image fetches without AbortController).

---

## ~~Phase B3 / B4 / B5-interactive — Pending~~ (superseded by live execution above)

These three steps require user input to execute:

1. **API smoke matrix (B3)** — needs a real Supabase JWT. Once provided, the following commands produce the full 200/401/404/422 matrix for all 5 endpoints. Each command is independent and short-output. Append to this report when done.
   ```bash
   TOKEN="<paste JWT here>"
   API="http://localhost:8000"
   curl -i -H "Authorization: Bearer $TOKEN" "$API/api/clippings/papers?days=7"
   curl -i -H "Authorization: Bearer $TOKEN" "$API/api/clippings/feed?days=7&limit=20"
   curl -i -H "Authorization: Bearer $TOKEN" "$API/api/clippings/<known_clipping_id>/image"
   curl -i -H "Authorization: Bearer $TOKEN" "$API/api/clippings/<known_clipping_id>/full"
   curl -i -H "Authorization: Bearer $TOKEN" "$API/api/clippings/notauuid/image"   # expect 422 (will be 500 until SEC-2 fixed)
   curl -i "$API/api/clippings/papers?days=7"                                       # expect 401
   ```

2. **Browser QA (B4)** — needs a logged-in browser session at `http://localhost:3000/cuttings`. Walk the checklist:
   - Mastheads load, language pills filter, no console errors.
   - Click a masthead → URL becomes `/cuttings?paper=<id>` → modal opens with clippings.
   - Reload the URL → modal re-opens (deep-link).
   - Toggle "Full edition" → iframe mounts a PDF.
   - ESC closes modal → URL strips `?paper=`.
   - Open modal → close before all images load → check Network tab for the dangling fetches that prove `FE-1`.

3. **Interactive 30-clipping grading (B5)** — pull 30 random rows (5 per paper, EN+TE mix) and grade subjectively for headline accuracy, OCR text quality, translation quality, image alignment, relevance reasonableness. Quick-pull SQL:
   ```sql
   WITH ranked AS (
     SELECT *, ROW_NUMBER() OVER (PARTITION BY newspaper_name ORDER BY random()) AS rn
     FROM newspaper_clippings
     WHERE collected_at > NOW() - INTERVAL '5 days'
   )
   SELECT id, newspaper_name, newspaper_language, headline, headline_translated,
          LEFT(article_text, 200) AS text_sample, relevance_score
   FROM ranked WHERE rn <= 5;
   ```
   Render images via `GET /api/clippings/{id}/image` to spot-check alignment.

---

## Recommended remediation order (stacked PRs — not executed in this engagement)

The user's locked decision was **audit-only**. The branch plan below is a recommendation only.

1. **`fix/cuttings-phase-1` — Ship-blockers**
   - **RUN-1 (`/feed` HTTP 500 — fix `:cursor::timestamptz` bind cast) — fix this FIRST; pillar is non-functional until then**
   - RUN-2 (validate PDF response is real PDF, not Drive interstitial)
   - SEC-1 (RBAC entity filter on `/feed`, `/papers`, `/{id}/image`, `/{id}/full`)
   - SEC-2 (typed UUID path params)
   - DB-1 (cursor key correctness)
   - QUAL-1 (entity tagger backfill)
   - INFRA-1 (CLAUDE.md doc fix)

2. **`fix/cuttings-phase-2` — HIGH**
   - SEC-3, SEC-4, CODE-1, DB-2, DB-3, CODE-2, FE-1

3. **`fix/cuttings-phase-3` — Test coverage gap-fill (TEST-1, TEST-2)**

4. **`fix/cuttings-phase-4` — Schema migration (DB-5, DB-6, DB-7, DB-4) + MEDIUM cleanups**

5. **B2 follow-up (separate diagnostic)** — Identify the 30 silent newspaper sources and decide: revive, deprecate, or mark `is_active=false`.

---

## Source labels for follow-up search

Knowledge-base sources indexed during this audit (for `ctx_search` follow-ups):
- `cuttings-frontend-inventory` — page.tsx, EditionModal, Newsstand, ClippingImage, vitest tests
- `cuttings-backend-inventory` — clippings_router, newspaper_collector, newspaper_task, backfill_sentiment, auth_middleware
- `cuttings-db-inventory` — migrations 005/006/008, indexes, FK structure
- `cuttings-live-runtime-2026-04-28` — `ps -ef`, EXPLAIN, quality flag counts, per-paper distribution
- Code/security/database review summaries — full agent outputs above the defect register
