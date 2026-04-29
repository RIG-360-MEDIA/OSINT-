# VERDICT — Globe Page (WorldMonitor) Production Audit

**Date:** 2026-04-28
**Branch:** `feat/embed-worldmonitor`
**Auditor:** Claude (Opus 4.7)

## Decision: **HOLD — do not ship.**

10 BLOCKER defects, 8 HIGH. The page **renders without crashing**
and the *infrastructure plumbing* (auth, caching, FastAPI/Celery
topology) is sound. But the page's **value proposition — political
intelligence and a live-channel briefing — is not yet truthful.**
Shipping today would expose users to:

1. Spokesperson surfaces dominated by cricketers, actors, judges,
   and industry analysts (D-23, D-24, D-25).
2. Issue clusters showing "Indonesia train accident" and "Iran
   Russia Diplomatic Talks" instead of TG/AP politics (D-26).
3. Counter-narrative & dissent panels permanently empty until the
   Groq key is rotated (D-3, D-8).
4. Source-of-truth invariants violated: every political handle is
   unverified (D-1); every promise URL is a generic landing page
   (D-22).
5. The "Global" iframe view will be **frame-blocked by CSP** at the
   current frontend port (D-18).
6. The embedded WM dashboard itself reports 40 EMPTY feeds and
   14 STALE_SEED feeds (D-19) — its data layer is degraded.
7. A logged-in user without `worldmonitor` page access can still
   read the entire CM dataset via direct API calls (D-11).

The two LLM-backed *output* tables (counter_narratives, dissent)
are zero-row. The two LLM-backed *input* extraction tables
(stance_scores, spokesperson_quotes) are populated but with a
~30% unknown rate from Groq 401s and a wide-open speaker
extraction.

## What works
- All 20 backend endpoints respond 200 (or graceful 503).
- Defensive code in `_safe()` (dashboard) and `_safe_execute()`
  (cm_queries) prevents 500s on missing data.
- All 6 Celery workers are running (collectors, social, youtube,
  documents, nlp, relevance/brief) + Beat — CLAUDE.md is stale on
  the documents-queue gap; it is closed.
- Beat schedule wires 13 CM tasks at appropriate cadence (5 min
  → daily).
- Auth gate on `worldmonitor_router` works (`require_page`).
- WorldMonitor briefing endpoint cache works (6.9s cold → 742ms
  warm).
- 9 of 9 Telugu live channel IDs resolve to real, named channels;
  8 are currently live; backend scrapes real video IDs server-side.
- 27 unit tests + 17 router-smoke tests all pass.
- SQL is parameterized; no hardcoded secrets in routers; CORS is
  configured (modulo D-34).
- LiveChannelsDrawer has proper `AbortController` cleanup
  (correcting the Phase-1 hypothesis).

## Minimum bar to lift the HOLD

Address all BLOCKERs and HIGHs:

1. **Rotate `GROQ_API_KEY`** (D-8) and confirm stance / speakers
   stop logging 401s. Re-run dissent + counter_narrative tasks
   manually to populate cm_dissent_signals and cm_counter_narratives.
2. **Fix speaker extraction** (D-23, D-24, D-25): add a
   political-relevance filter; reject the
   "The article does not mention…" sentinel; restrict to speakers
   whose canonical name matches `cm_political_handles.person_name`
   or a curated allowlist.
3. **Fix issue clustering** (D-26): filter clustering input to
   `geo_primary IN ('TG','AP','Telangana','Andhra Pradesh',
   'Hyderabad', …)` before LaBSE embeds.
4. **Backfill state on existing cm_stance_scores + cm_spokesperson_quotes**
   (D-2): re-run the tasks with state derived from the article's
   `geo_primary`, or run a one-time `UPDATE` SQL.
5. **Backfill `cm_political_handles.verified_url`** (D-1) for all
   9 rows, manually.
6. **Add `require_page("worldmonitor")` to cm_router** (D-11).
7. **Fix middleware backend reachability** (D-17): introduce
   `INTERNAL_API_URL=http://rig-backend:8000`.
8. **Fix CSP `frame-ancestors`** in rig-worldmonitor nginx (D-18)
   to template from `FRONTEND_ORIGIN`.
9. **Fix WM seeder** (D-19): investigate why 40 feeds are EMPTY
   and 14 are STALE_SEED. Likely seeder source-adapter failures
   inside `rig-wm-seeder`.
10. **Add at least one Playwright e2e** (D-31): `/worldmonitor`
    → click "Live" → expect drawer → cycle one channel → no console
    errors.
11. **Backend integration tests for the 4 worldmonitor endpoints**
    (D-30) with mocked ACLED, Groq, YouTube.

## Conditional ship (for canary / opt-in only)

If the team wants to ship to a *small* internal-only cohort with
clear "preview" framing, the minimum set drops to:
- D-8 (Groq), D-11 (cm_router gate), D-17 (middleware), D-18 (CSP),
  D-19 (seeder).

The content-correctness BLOCKERs can be deferred *only* if every
CM-derived surface (spokespersons, voice-share, issues,
counter-narratives, dissent) is hidden in the UI behind a
"PREVIEW" feature flag that warns users not to trust the data.

## Defects deferred (post-ship)

The MEDIUM and LOW items in `DEFECTS.md` are graded as not
blocking. Track them as a backlog: many are quality-of-life
improvements (D-13, D-29) or documentation drift (B-3, B-5).

## Audit artifacts
| File | Step |
|---|---|
| `00_baseline.md` | 0 — env, containers, processes, tables |
| `01_db_seed.md` | 1 — DB schema + seed sanity |
| `02_workers.md` | 2 — Celery topology + Groq finding |
| `03_endpoints.md` | 3 — all 20 endpoints smoked |
| `04_frontend.md` | 4 — frontend route gate + iframe + sidecar health |
| `05_failure_paths.md` | 5 — graceful degradation |
| `06_content_quality.md` | 6 — content correctness samples |
| `07_caching.md` | 7 — cache + concurrency |
| `08_tests.md` | 8 — test coverage gap |
| `09_security.md` | 9 — auth + SQL + CSP + CORS + RLS |
| `DEFECTS.md` | 10 — punch list, 40 items |
| `VERDICT.md` | this file |
| `wm-anon.png` | screenshot — anon /worldmonitor → /login redirect |
