# Brief — Defect Register

**Owner:** QA / RIG
**Date opened:** 2026-04-26
**Branch at audit:** `fix/archive-phase-8`
**Scope:** `/brief` page — backend (router + generator + Celery), frontend (page.tsx), schema, data-quality.

Severity scale: **P1** = blocker / data-correctness, **P2** = significant defect, **P3** = polish / DX, **P4** = cosmetic.

---

## Pillar Coverage Matrix (summary — full version in [brief-coverage-matrix.md](./brief-coverage-matrix.md))

| Pillar | In brief? |
|---|---|
| Articles | ✅ |
| Clips, Cuttings, Threads, Govt-docs, Cross-day briefs | ❌ |

Brief uses 1 of 6 pillars. Govt-docs: 17/50 sources producing rows in last 7d, but **0 reach the brief**.

---

## Defects

### D-BRIEF-1 — Brief omits 5 of 6 pillars (P1, design)

**Where:** [backend/routers/brief_router.py:99–127](../../backend/routers/brief_router.py), [backend/nlp/brief_generator.py](../../backend/nlp/brief_generator.py).
**What:** Brief query only joins `articles` via `user_article_relevance`. `govt_documents` (with its own per-user relevance table `user_govt_doc_relevance`), `clips`, `clippings`, `story_threads`, and prior-day `briefs` are not read.
**Impact:** A user with monitored entities sees zero govt-doc, zero YouTube-clip, zero newspaper, zero social signal in their daily brief — even though the data is in Postgres and being scored per user. SOURCE COVERAGE section reports only RSS domains.
**Fix sketch:** add a parallel query for top-N govt docs (`user_govt_doc_relevance`, tier 1–2), feed into a new `GOVT ACTIONS` section in the prompt fan-out. Repeat for clips/threads. Multi-week feature, not a one-line fix.

### D-BRIEF-2 — `tasks.generate_all_briefs` is a no-op stub (P1, blocker)

**Where:** [backend/tasks/collector_tasks.py:84–88](../../backend/tasks/collector_tasks.py).
**What:** Task body is `return {"status": "not_implemented", "prompt": "P10"}`. Beat publishes `tasks.generate_all_briefs` daily at 00:30 UTC ([backend/celery_app.py:91–95](../../backend/celery_app.py)) and the `worker-relevance` consumer drains it instantly with no work.
**Impact:** Every user must manually click "Generate" to get a brief. The `briefs` table currently has only 4 rows — all from a single user — confirming this. The `brief_time` / `brief_timezone` columns on `user_profiles` are unused.
**Fix sketch:** iterate `user_profiles` for users whose local `brief_time` matches the current Beat tick, call the same code path as `POST /generate`, log per-user errors but never fail the whole batch.

### D-BRIEF-3 — Zero brief tests (P2)

**Where:** none — there is no `backend/tests/test_brief_*.py` and no `frontend/e2e/brief.spec.ts` and no `frontend/src/app/brief/__tests__/`.
**What:** Brief is the user-facing flagship of the product and has no automated coverage of router, generator, page, or e2e flow.
**Impact:** Any regression in section parsing, in `parseBrief()`, in the upsert path, or in the 6-fanout asyncio.gather is invisible until a user complains. CI cannot signal brief breakage.
**Fix:** the four test files this audit creates — `test_brief_router.py`, `test_brief_generator.py`, `brief.spec.ts`, `parseBrief.test.ts` — establish a baseline. Aim for ≥80% line coverage on router and generator.

### D-BRIEF-4 — Per-section Groq calls have no timeout / retry (P2)

**Where:** [backend/nlp/brief_generator.py:131–190](../../backend/nlp/brief_generator.py).
**What:** Six concurrent `generate(...)` calls fanned out via `asyncio.gather(*tasks, return_exceptions=True)`. There is no `asyncio.wait_for`, no per-call timeout, no retry. If Groq stalls on one section, the brief returns 5 good sections + one `[Generation failed: ...]` placeholder.
**Impact:** Confirmed by code path at line 202–207 — failures are logged and stringified into the markdown. User sees `[Generation failed: ...]` text in their brief.
**Fix:** wrap each call in `asyncio.wait_for(..., timeout=20)` and retry once with backoff before falling back to placeholder.

### D-BRIEF-5 — No recency filter on article query (P2)

**Where:** [backend/routers/brief_router.py:99–124](../../backend/routers/brief_router.py).
**What:** `WHERE uar.relevance_tier IN (1,2) AND a.nlp_confidence != 'error' ORDER BY uar.relevance_tier ASC, uar.score_final DESC LIMIT 30`. No `a.published_at >= NOW() - INTERVAL 'X hours'` filter.
**Impact:** A 4-day-old high-scored article can dominate today's "DAILY INTELLIGENCE BRIEF". The page literally renders `## {today_str}` ([brief_generator.py:209–212](../../backend/nlp/brief_generator.py)) above stale content.
**Fix:** add `AND a.published_at >= NOW() - INTERVAL '36 hours'` (or an env-controlled window) to the query.

### D-BRIEF-6 — `is_duplicate` articles not filtered (P3)

**Where:** [backend/routers/brief_router.py:99–124](../../backend/routers/brief_router.py).
**What:** No `AND a.is_duplicate = FALSE` clause. Dedup pipeline runs but its output is ignored here.
**Impact:** Same story can occupy two of the top-30 slots, inflating one cluster at the expense of diversity.
**Fix:** add `AND COALESCE(a.is_duplicate, FALSE) = FALSE`.

### D-BRIEF-7 — UNIQUE-violation race on POST /generate (downgrade P3)

**Where:** [backend/routers/brief_router.py:166–187](../../backend/routers/brief_router.py).
**What:** Originally suspected a UNIQUE-key race; on closer read, the upsert *does* have `ON CONFLICT (user_id, brief_date) DO UPDATE`. **However**, two concurrent generates still both run the full Groq fan-out (~15–30s × 6 calls × Groq tokens) before one wins the upsert. No request-level lock.
**Impact:** Wasted Groq spend; the loser's section text is silently discarded.
**Fix:** advisory lock per `(user_id, brief_date)` at the top of the handler, or cache an in-flight Future keyed by the same tuple.

### D-BRIEF-8 — Frontend Generate button has no debounce (P3)

**Where:** [frontend/src/app/brief/page.tsx](../../frontend/src/app/brief/page.tsx) — `handleGenerate()` and the regenerate button in `BriefContent`.
**What:** No `disabled` flag tied to in-flight POST, no double-click guard. Pairs with D-BRIEF-7.
**Impact:** Rapid double-click fires two POSTs.
**Fix:** disable the button while `pageState === 'generating'`.

### D-BRIEF-9 — 965-line single-file page.tsx (P3, maintainability)

**Where:** [frontend/src/app/brief/page.tsx](../../frontend/src/app/brief/page.tsx).
**What:** Twelve internal components, parser, state machine, fetch logic in one client file. Violates project rule "200–400 lines typical, 800 max" ([CLAUDE.md / coding-style](../../CLAUDE.md)).
**Fix:** split into `components/{Movement,SituationSection,DevelopmentsSection,EntitiesSection,SignalsSection,FinancialSection,SourcesSection,LoadingState,EmptyState,HistoryStrip}.tsx` and `lib/parseBrief.ts`.

### D-BRIEF-10 — No error boundary (P3)

**Where:** [frontend/src/app/brief/page.tsx](../../frontend/src/app/brief/page.tsx).
**What:** Reliance on state-machine `'error'` branch only; a render-time exception in any section component crashes the whole page.
**Fix:** wrap `BriefContent` in a Next.js `error.tsx` boundary or React `ErrorBoundary`.

### D-BRIEF-11 — Frontend `fetch` has no caching strategy (P3)

**Where:** [frontend/src/app/brief/page.tsx](../../frontend/src/app/brief/page.tsx).
**What:** Plain `fetch(url, { headers })` everywhere — no `cache`, no SWR/React Query. Every navigation re-hits the API.
**Impact:** When the user toggles between dates, history list refetches each time. Auth-token refresh mid-flight will silently 401.
**Fix:** introduce a thin `useApi` hook with SWR; centralize Bearer-token refresh.

### D-BRIEF-12 — 22-adapter drift between code and seed table (P2, ingestion)

**Where:** `backend/collectors/sources/*.py` (72 `@register_source` decorations) vs. `govt_document_sources` table (50 rows).
**What:** 22 adapters compiled-in but never seeded → Beat never schedules them.
**Impact:** Even if the brief *did* read govt docs, those 22 sources would silently contribute zero rows.
**Fix:** add a startup check in `start.sh` (or an idempotent migration) that inserts a `govt_document_sources` row for every registered slug.

### D-BRIEF-13 — Section-name parser is brittle (P3)

**Where:** [frontend/src/app/brief/page.tsx:31–43](../../frontend/src/app/brief/page.tsx).
**What:** Regex `/^## ([A-Z ]+)\n\n([\s\S]*)/` only accepts uppercase-letters-and-spaces and requires exactly two newlines. The LLM occasionally returns ` ## Situation Status` or `## SITUATION STATUS:` or single-newline blocks. Any drift drops the section.
**Impact:** Silent UI dropouts of whole sections with no error state.
**Fix:** uppercase-normalise + tolerate 1+ newlines + strip trailing punctuation. Covered by `parseBrief.test.ts` cases added in this audit.

### D-BRIEF-14 — `[Generation failed: ...]` placeholder leaks to user (P3)

**Where:** [backend/nlp/brief_generator.py:202–207](../../backend/nlp/brief_generator.py).
**What:** When a Groq call raises, the section text becomes the literal string `[Generation failed: <stringified exception slice>]` and is rendered as user-facing prose by `parseBrief()` → `<blockquote>` etc.
**Fix:** route to a friendly fallback string per section, log the exception server-side only.

### D-BRIEF-15 — Loading-phase animation is fake progress (P4, UX honesty)

**Where:** [frontend/src/app/brief/page.tsx](../../frontend/src/app/brief/page.tsx) — `LoadingState` cycles `LOADING_PHASES` on a fixed timer.
**What:** Phases ("Reading the wires…", "Marking the developments…", "Filing the brief…") are time-based, not bound to actual backend progress. If Groq stalls, the animation still completes and then the page sits.
**Fix:** EITHER stream progress events from a server-sent stream OR mark the animation as decorative-only and add a real "still working…" indicator after T+30s.

### D-BRIEF-16 — `GET /api/brief/{date}` returns 400 on invalid date, but FastAPI route order may shadow it (P3)

**Where:** [backend/routers/brief_router.py:200, 233, 272](../../backend/routers/brief_router.py).
**What:** `/today`, `/{brief_date}`, `/history/list` are declared in that order. FastAPI matches `/today` before the `/{brief_date}` placeholder, but `/history/list` is a sub-path under `/{brief_date}` if the placeholder isn't constrained. In practice it works because `/history` becomes the `brief_date` arg → `fromisoformat('history')` → 400. **But:** the 400 message reaches users who visited `/history/list` from old links → confusing.
**Fix:** add `path: str = Path(..., regex=r"^\d{4}-\d{2}-\d{2}$")` to constrain.

---

## Priority remediation queue (top 3 P1/P2)

1. **D-BRIEF-1** — wire govt-docs (and at least clips) into the brief. Without this, the user's perception of "the brief is empty / shallow" will not change.
2. **D-BRIEF-2** — implement `tasks.generate_all_briefs` so users actually get a daily push, not a manual click.
3. **D-BRIEF-5** — add a recency filter so "today's brief" can no longer be 4-day-old articles.

D-BRIEF-3 (no tests) is being closed by this audit's test-authoring pass.

---

## Cross-references

- Coverage numbers and source matrix: [brief-coverage-matrix.md](./brief-coverage-matrix.md)
- Manual UX walkthrough: [brief-live-session.md](./brief-live-session.md)
- Output quality scoring: [brief-quality-scorecard.md](./brief-quality-scorecard.md)
- Govt-source verdict (pre-existing): [sources-per-source-verdict.md](./sources-per-source-verdict.md)
