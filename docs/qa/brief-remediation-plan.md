# Brief Pillar — Production Remediation Plan

Companion to [brief-audit-2026-04-28.md](./brief-audit-2026-04-28.md).
Each item is a self-contained commit. Branch: `fix/brief-prod-readiness`.
Target: green on every checklist item below before tag.

---

## Phase 1 — Correctness (P0/P1, must close before prod)

### 1. RBAC bypass — wire `require_page("brief")`
**File:** `backend/routers/brief_router.py` (5 endpoints, lines 27/326/372/421/645)
**Change:** swap `Depends(get_current_user)` → `Depends(require_page("brief"))`
**Test:** new `test_brief_router.py::test_endpoints_403_without_page_access`
**Accept:** valid JWT for a user *without* `user_page_access(slug='brief')` → 403 on all 5 endpoints.

### 2. Recency + dedup filter on article query
**File:** `backend/routers/brief_router.py:99-133`
**Change:** add to WHERE clause:
```sql
AND a.published_at >= NOW() - INTERVAL :recency_hours
AND COALESCE(a.is_duplicate, FALSE) = FALSE
```
`recency_hours` from `BRIEF_ARTICLE_RECENCY_HOURS` env, default `36`.
Fallback: if < 10 fresh tier-1/2 articles, widen to 72h once, log a warning. Only 425 if still < 10.
**Accept:** `avg(days_old)` of articles in next-generated brief ≤ 1.5; 0 duplicates.

### 3. Per-section LLM timeout + retry
**File:** `backend/nlp/brief_generator.py:312-336, 412`
**Change:** wrap each `generate(...)` in `asyncio.wait_for(timeout=BRIEF_SECTION_TIMEOUT_S, default 25)`. On `TimeoutError` or `GroqError`, retry once with `max_tokens // 2` and FAST_MODEL. On second failure, return a **structured fallback** (a short prose summary built from the evidence, not the raw `[Generation failed: ...]` string).
**Accept:** zero `[Generation failed` substring in any new brief; section length ≥ 80 words even on retry path.

### 4. Idempotency lock on POST /generate
**File:** `backend/routers/brief_router.py` (top of `generate_today_brief`)
**Change:** before LLM fan-out, take an advisory lock:
```python
await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
                 {"k": f"brief:{user_id}:{today}"})
existing = await db.execute(text(
    "SELECT content, evidence, source_counts FROM briefs "
    "WHERE user_id=:u AND brief_date=:d"), ...)
if existing and existing.generated_at > now() - interval '5 minutes':
    return existing  # idempotent return, no second LLM run
```
**Accept:** double-click test (`e2e/brief.spec.ts:201`) passes — exactly 1 POST round-trip generates work, the second returns cached.

### 5. Implement `tasks.generate_all_briefs`
**Files:** `backend/tasks/brief_task.py` (new), `backend/tasks/collector_tasks.py` (delete stub), `backend/celery_app.py` (route stays)
**Logic:**
```python
@app.task(name="tasks.generate_all_briefs", bind=True, max_retries=0)
def generate_all_briefs(self):
    rows = db.execute("SELECT user_id FROM user_page_access WHERE page_slug='brief'")
    for (user_id,) in rows:
        try:
            generate_brief_for_user.apply_async(args=[str(user_id)], queue="brief")
        except Exception as exc:
            logger.exception("brief enqueue failed for %s", user_id)
```
Per-user task respects `user_profiles.brief_timezone` for date boundary. Errors logged, never raised.
**Accept:** at 00:30 UTC the queue drains 1 message per opted-in user; `briefs` table has one row per user per day for 3 consecutive days.

### 6. Constrain `/{brief_date}` route
**File:** `brief_router.py:372`
**Change:** `brief_date: str = Path(..., regex=r"^\d{4}-\d{2}-\d{2}$")`. Reject future dates with 422.
**Accept:** `/api/brief/2099-01-01` → 422; `/api/brief/junk` → 422 not 400.

---

## Phase 2 — Quality (top-notch content)

### 7. Citation validator (post-LLM, pre-save)
**File:** `backend/nlp/brief_validator.py` (new)
**Logic:** parse the generated markdown for every `[N]`, `Doc:<id>`, `Paper:<id>`, `Social:<id>`, `Video:<id>` reference. For each: assert it resolves to an item in the evidence dict that was passed to the LLM. Unknown IDs → reject the brief, retry once with stricter prompt that lists allowed IDs explicitly. After two rejections, strip the offending sentence rather than ship a hallucinated cite.
**Accept:** `test_brief_validator.py` covers (a) valid cites pass, (b) hallucinated `[99]` triggers retry, (c) 2nd failure strips sentence.

### 8. Per-pillar freshness gate
**File:** `backend/nlp/rag_engine.py` (newspaper, social, video retrieval)
**Change:** prefer rows from the last 24h; fall back to 48h only if <3 results. Today's data shows the pool has 433 newspaper rows in 24h yet the brief picked 8 from a 3-day-old edition — the retrieval ranker is biased. Add an ORDER BY `(edition_date DESC, similarity DESC)` two-stage sort.
**Accept:** for a brief with `brief_date = D`, ≥ 80% of newspaper clippings have `edition_date >= D - 1`.

### 9. Section-length minimums
**File:** `brief_generator.py` (after gather)
**Change:** if any section < 80 words, regenerate just that section once with a higher `min_tokens` hint and the same evidence.
**Accept:** every section ≥ 80 words in new briefs.

### 10. Quality scorecard cron
**File:** `backend/tasks/brief_quality_task.py` (new), Beat 01:00 UTC
**Logic:** for yesterday's briefs, compute the rubric (citation density, citation validity, recency avg/max, per-section word count, failure markers). Insert into a new `brief_quality_scores` table. Surface in `/api/brief/quality/recent` for an internal dashboard.
**Accept:** new table populated daily; dashboard renders last 14 days.

### 11. Prompt hardening
**File:** `brief_generator.py` (CITATION_GUIDANCE block)
**Change:** add explicit allow-list of IDs in the prompt (`Available article IDs: [1,2,…,30]; gov doc IDs: [<uuid>,…]`). Forbid inventing entities not in the evidence. Add a self-check instruction: "Before answering, verify every bracketed ID matches the allow-list; if not, omit it."
**Accept:** hallucinated-ID rate (measured by validator from #7) drops below 1% across 30 sample briefs.

---

## Phase 3 — Resilience + UX (P2/P3)

### 12. Frontend AbortController + error boundary
**Files:** `frontend/src/app/brief/page.tsx`
**Change:** carry `AbortController` per fetch (`/today`, `/history`, `/generate`, `/{date}`); cancel on view change / unmount. Wrap page in error boundary that logs to console + shows retry CTA.
**Accept:** rapid Intel↔Monitor↔CM toggle with throttled 3G never flips state from a stale response; error boundary catches runtime errors.

### 13. UNIQUE on `(user_id, brief_date, model_used)`
**Migration:** `scripts/migrations/036_briefs_unique_with_model.sql`
**Change:** drop `briefs_user_id_brief_date_key`, add `UNIQUE(user_id, brief_date, model_used)`. Update upsert ON CONFLICT clause.
**Accept:** model A/B comparison briefs don't overwrite each other.

### 14. Timezone-correct brief_date
**File:** `brief_router.py` upsert + Beat task
**Change:** compute `brief_date = (now() AT TIME ZONE COALESCE(user_profiles.brief_timezone, 'UTC'))::date` everywhere. Add migration to backfill existing rows where `brief_timezone` is non-UTC.
**Accept:** an IST user's brief_date never collides with a UTC-midnight boundary.

### 15. Pagination on `/history/list` + `BriefWizard`
**File:** `brief_router.py:645`, `BriefWizard.tsx`
**Change:** `?limit=&offset=` on history; virtualized list for evidence arrays > 20.

### 16. Pytest in container
**File:** `infrastructure/Dockerfile.backend` — add a `dev` stage that installs `pytest`, `pytest-asyncio`, `httpx`. CI runs `docker compose run --rm rig-backend pytest -q`.

### 17. Playwright on CI
**File:** `.github/workflows/frontend-e2e.yml` — `npx playwright install --with-deps` step before test run.

---

## Verification gate (pre-prod tag)

```
[ ] All Phase 1 commits merged on main
[ ] avg(article days_old) ≤ 1.5 measured on 3 consecutive auto-generated briefs
[ ] zero `[Generation failed` substring across last 14 briefs
[ ] zero hallucinated cites across 30 sample briefs (validator-proven)
[ ] every section ≥ 80 words across 30 samples
[ ] auth: 401 no token / 403 no page-access / 200 happy path
[ ] pytest backend/tests/test_brief_*.py green in CI
[ ] playwright e2e/brief.spec.ts green in CI (incl. D-BRIEF-8 double-click)
[ ] daily Beat at 00:30 UTC produces 1 brief per opted-in user, 3 days running
[ ] Lighthouse a11y ≥ 90 on /brief
```

---

## Reassessment notes (vs original audit)

- **F2 / D-BRIEF-1 stays closed** — pillar wiring already shipped; covered by quality gates here, not by re-implementation.
- **F7 frontend setInterval cleanup** — withdrawn, code is correct.
- **Memory note about super_admin** — orthogonal to brief; flag in a separate session.
- **CLAUDE.md `worker-documents` note** — orthogonal to brief; flag in a separate session.
- The connected Supabase MCP project (`nwqstdfoqfygyifrjtcw`) is **not** the rig-surveillance backend (`mxatfnaqwhsvfuwgvqwu`). Lints from that other project are out-of-scope here.

Estimated effort: 3–4 dev-days for Phase 1, 2–3 days for Phase 2, 1–2 days for Phase 3.
