# Defects Register — `/signals` page (The Signal Room)

Severity: **P0** = data correctness / 5xx storm | **P1** = broken
feature / wrong UX | **P2** = a11y / observability / silent failure |
**P3** = code health / polish.

| ID | Sev | Layer | File:line | Symptom | Fix sketch |
|---|---|---|---|---|---|
| SIG-1  | P1 | frontend | [page.tsx:108-134](../../frontend/src/app/signals/page.tsx) | No `AbortController` on `fetchFeed`. Rapid tab clicks fire overlapping requests; older response can clobber newer (stale-result race). | Wrap each fetch in `AbortController`; abort on `tab` change; ignore `AbortError`. Mirror documents D-5. |
| SIG-2  | P1 | frontend | [page.tsx:136-147](../../frontend/src/app/signals/page.tsx) | `fetchSentiment` swallows `!res.ok` — 401 on token expiry becomes a silent no-op; user thinks data is fresh. | On `res.status === 401`, call `router.push('/login')`. Distinguish 4xx vs 5xx in the error path. Subscribe to `onAuthStateChange`. |
| SIG-3  | P2 | frontend | [page.tsx:120-126](../../frontend/src/app/signals/page.tsx) | Error message is `"feed ${res.status}"` — no user-friendly text, no retry button, error state not dismissible. | DeskMemo error variant with status, retry handler, dismiss; preserve previous posts on `loadMore` failure. |
| SIG-4  | P2 | backend | [signals_router.py:225-244](../../backend/routers/signals_router.py) | N+1: `/monitors` issues `(SELECT COUNT(*) FROM social_posts WHERE monitor_id=m.id)` per row. EXPLAIN shows Seq Scan on social_posts inside SubPlan, loops=14. | Single `GROUP BY monitor_id` aggregate joined LEFT to `social_monitors`. |
| SIG-5  | P2 | backend | [signals_router.py:182-184](../../backend/routers/signals_router.py) | `/sentiment` JOIN enforces `sm.id IS NOT NULL` → unmonitored / keyword-only posts vanish from sentiment dashboard even though they appear in `/feed`. | LEFT JOIN; bucket null monitor as "Untracked"; OR document the exclusion. |
| SIG-6  | P2 | schema | [007_social_signals.sql:4-18](../../scripts/migrations/007_social_signals.sql) | No index on `social_monitors(platform, is_active)` — Beat-time monitor query (`WHERE platform=:p AND is_active`) full-scans. Latent until 100+ monitors. | Add migration `009_social_monitors_active_idx.sql`: `CREATE INDEX … ON social_monitors(platform, is_active) WHERE is_active`. |
| SIG-7  | P2 | frontend | [page.tsx:293-344](../../frontend/src/app/signals/page.tsx) | Tab buttons missing `role="tab"` / `aria-selected` / arrow-key handler / `tablist` group. Screen readers can't identify active tab. | Wrap in `<div role="tablist">`; each button `role="tab" aria-selected={…} tabIndex={active?0:-1}`; add `onKeyDown` for ←/→/Home/End. |
| SIG-8  | P2 | collector | [social_collector.py:62-72](../../backend/collectors/social_collector.py) | Reddit 429 returns empty list with only a warning log. No metric, no alert, no backoff. Bursty subreddits silently blackhole. | Backoff with `tenacity`; emit metric `reddit_429_count`; raise after N consecutive 429 to surface in Beat error log. |
| SIG-9  | P3 | docs | [CLAUDE.md](../../CLAUDE.md) | Pillars list omits Signals — future sessions misread it as orphaned (we almost did). | Add `Signals` row to the pillars table with `/signals` and pipeline summary. |
| SIG-10 | **P0** | tasks | [social_task.py:26-35, 164](../../backend/tasks/social_task.py) | 100 % of inserted posts have empty `matched_entities` (probed: 207/207 rows). Two causes: (a) historical posts inserted before user added entities are never re-tagged; (b) `_fetch_user_entities` returns ALL users' canonical names, so matched_entities is the global pool — not user-scoped. | (a) Add a backfill task that re-tags rows; (b) restructure: store per-user matches in a side-table `social_post_entity_matches(post_id, user_id, entity_name)` so adding a user doesn't require re-tagging the world. |
| SIG-11 | **P0** | infra | [start.sh:8-12](../../infrastructure/start.sh), [celery_app.py:51-69](../../backend/celery_app.py) | **Production blocker.** `collectors` queue currently holds **479 backed-up messages**. `worker-collectors --concurrency=1` is shared by RSS / HTML / newspaper / social tasks. Slow HTML tier-3 scrapes monopolise the slot; social tasks never run. Last successful Reddit collection: 2026-04-21 (6 days). | Two options: (a) split social tasks onto a dedicated `social` queue with its own worker (`celery … --queues=social --concurrency=2`); or (b) raise concurrency on the collectors worker to ≥4 with `--prefetch-multiplier=1`. Option (a) preferred: isolates failure modes. |
| SIG-12 | P1 | collector | [social_collector.py:106-227](../../backend/collectors/social_collector.py) | Twitter has **0 rows ever** despite valid `TWITTER_BEARER_TOKEN`. Compound of SIG-11 (task never executes) + we cannot observe quota state. May also hit free-tier 7-day-window limitation on backfill. | Resolve SIG-11 first; then add `--max-results=10` smoke run; surface 401/429 explicitly; document the 7-day window in `signals-per-source-verdict.md`. |
| SIG-13 | P2 | tasks | [social_task.py](../../backend/tasks/social_task.py) (telegram path), [social_collector.py:127](../../backend/collectors/social_collector.py) | Telegram and Twitter posts inserted with `post_language='en'` regardless of actual language. Telugu telegram post stored as `en` → VADER returns 0.0 sentiment. Twitter uses `t.get("lang") or "en"` — silent en fallback. | Plug `langdetect` (already a dep) on the Telegram path; respect provider-supplied lang for Twitter; gate `compute_sentiment` strictly on `language=='en'`, fallback to TextBlob otherwise. |
| SIG-14 | P2 | tasks | [social_task.py:30](../../backend/tasks/social_task.py) | `_fetch_user_entities` query: `SELECT DISTINCT canonical_name FROM user_entities` — no `user_id` predicate. Cross-user entity bleed: User A's "BRS" entity will tag posts shown to User B. Mitigated only because there is one user today; breaks at multi-user. | Per-user matching: see SIG-10 fix; in interim, document and add a feature flag. |
| SIG-15 | P3 | frontend | [page.tsx](../../frontend/src/app/signals/page.tsx) (whole file) | 726 lines, 8 inline sub-components (PostCard, SentimentLedger, SentimentRow, PlatformStat, LoadingState, DeskMemo, …). Exceeds 400-line ideal / 800-line max. | Extract sub-components to `frontend/src/app/signals/components/`; data fetching to a `useSignalsFeed` hook. |
| SIG-16 | P3 | frontend | [page.tsx:149-158](../../frontend/src/app/signals/page.tsx) | Auth effect doesn't subscribe to `supabase.auth.onAuthStateChange` → silent 401 after token rotation. | Subscribe; update `token`; retry active request once. |
| SIG-17 | P3 | tests | (entire feature) | Zero tests across collector, task, router, page, e2e. | This QA pass adds 3 backend + 1 vitest + 1 playwright suite; tests intentionally tag SIG-1, SIG-2, SIG-4 regressions as `xfail` until the fix branch flips them. |

## Pre-fix → post-fix delta (target)

| Metric | Pre (probed 2026-04-27) | Post (target) |
|---|---|---|
| Reddit data freshness | 6 days | <1 h |
| Telegram data freshness | 4 days | <1 h |
| Twitter rows ever | 0 | >0 |
| `collectors` queue depth | 479 | <50 sustained |
| Posts with non-empty `matched_entities` | 0 / 207 | >70 % per fresh post |
| `/monitors` query plan loops | 14 (=monitor count) | 1 (single GROUP BY) |
| `social_monitors` indexed for active filter | ❌ | ✓ |
| Tab a11y violations (axe) | TBD | 0 critical |
| Frontend 401 handling | silent | redirect + toast |
| Test coverage on the 3 backend modules | 0 % | ≥80 % |

Fixes are **out of scope for this QA pass** (per user direction) —
queued for a follow-up `fix/signals-phase-1` branch informed by this
register. Tests written here lock current behaviour; xfail markers on
SIG-1/2/4 flip to passing in the fix branch.
