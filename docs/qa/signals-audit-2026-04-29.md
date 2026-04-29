# Signals Page — Final Audit & Fix Report

**Date:** 2026-04-29 (continuation of 2026-04-28 audit)
**Auditor:** Claude (Opus 4.7)
**Scope:** Apply all P0/P1/P2 fixes identified in the prior audit, **completely remove the Twitter pillar**, and verify the system end-to-end.
**Predecessor:** [docs/qa/signals-audit-2026-04-28.md](./signals-audit-2026-04-28.md)

---

## What this report adds vs. the 2026-04-28 audit

The prior report identified 22 defects and shipped 6 P0/P1 frontend/backend fixes. This pass **closes the remaining items** and **removes Twitter completely** from code + DB.

| Defect | 2026-04-28 status | 2026-04-29 status |
|---|---|---|
| F1, F2 — frontend silent fetches + API_BASE prod guard | ✅ fixed | ✅ (verified) |
| A2, A3 — backend platform/UUID/kind guards | ✅ fixed | ✅ (verified) |
| D1 — Twitter 402 short-circuit | ✅ fixed (mitigation) | ✅ **superseded by full removal** |
| D6 — `/api/health/social` registered | ✅ fixed | ✅ (Twitter section now reports `removed`) |
| **D1b — Twitter monitors still in DB** | ❌ open | ✅ **migration 035** ships the DELETE |
| **Q1 — pytest fixtures don't satisfy RBAC** | ❌ open | ✅ **fixed** — `make_app()` overrides router-level `require_page` deps |
| **P1 — cluster Groq call has no timeout** | ❌ open | ✅ **fixed** — `soft_time_limit=240, time_limit=270` on `cluster_recent_social_posts` |
| **P5 — `worker-social --prefetch-multiplier` unset** | ❌ open | ✅ **fixed** — `--prefetch-multiplier=1` added in `start.sh` |
| **F4 — TS1501 errors on `parseBody()` `/s` flag** | ❌ open | ✅ **fixed** — `tsconfig.target` bumped ES2017 → ES2018 |
| **F6 — edition rail buttons missing aria-label** | ❌ open | ✅ **fixed** — `aria-label` + `aria-current="page"` on selected |
| **F7 — translated text missing `lang` attribute** | ❌ open | ✅ **fixed** — both visible + reveal `<p>` get `lang={...}` |
| D2 — entity-match coverage 20-32% | open | open (deferred — needs entity-dict expansion) |
| D3 — 3 of 6 event rules dormant | open | open (re-evaluate after 14-day corpus) |

---

## Twitter Removal — full inventory of changes

### Code
| File | Change |
|---|---|
| `backend/celery_app.py` | Removed `tasks.collect_twitter` route + beat schedule entry `collect-twitter-warm-every-1-hour` |
| `backend/tasks/social_task.py` | Removed `collect_twitter` task + `_collect_twitter` async helper. Updated module docstring. Replaced section with a tombstone comment pointing at git tag `pre-twitter-removal` |
| `backend/collectors/social_collector.py` | Removed `_twitter_tweet_to_post`, `collect_twitter_user_tweets`, `search_twitter_keyword`, `_twitter_402_total`, `_twitter_402_short_circuit`, `twitter_health_metrics()`, `_TWITTER_API` constant. Updated module docstring |
| `backend/main.py` | `/api/health/social` no longer imports `twitter_health_metrics`; returns `{"twitter": {"status": "removed", "since": "2026-04-29"}}` |
| `backend/routers/signals_router.py` | (already had defense-in-depth Twitter exclusions — kept) |
| `backend/tests/test_signals_router.py` | Dropped `"twitter"` from the success-case parametrize; added new `test_feed_rejects_invalid_platform` covering `["twitter", "x", "instagram", "garbage"]` → 422 |
| `frontend/src/app/signals/page.tsx` | (already excluded Twitter from `TopicPost.platform` union; runtime guard preserved as belt-and-suspenders) |

### Database
| File | Effect |
|---|---|
| `scripts/migrations/035_remove_twitter_signals.sql` | Deletes any `social_posts` with `platform='twitter'` (cascading via `social_cluster_posts`); deletes the 3 Twitter rows from `social_monitors` (KTRTRS, trspartyonline, revanth_anumula); fails loudly via `RAISE EXCEPTION` if any rows remain |

### Restoration path
If a paid X tier is procured, restore via:
```
git revert <merge-commit-of-this-PR>
# OR cherry-pick the deleted helpers from git tag pre-twitter-removal
```

---

## All Fixes Applied This Session

| ID | Severity | File(s) | Change |
|---|---|---|---|
| Q1 | P0 | `backend/tests/test_signals_router.py` | `make_app()` now iterates `signals_router.dependencies` and registers a `dependency_overrides` entry for the `require_page("signals")` inner closure — bypasses RBAC in unit tests |
| Q1b | P0 | same | New `test_feed_rejects_invalid_platform` ensures A2 stays green |
| P1 | P1 | `backend/tasks/social_briefing_task.py` | `cluster_recent_social_posts` decorator: `soft_time_limit=240, time_limit=270` |
| P5 | P2 | `backend/start.sh` | `worker-social` line gains `--prefetch-multiplier=1` |
| F4 | P2 | `frontend/tsconfig.json` | `target: "ES2017"` → `"ES2018"` (lets `parseBody` regex `/s` flag compile) |
| F6 | P3 | `frontend/src/app/signals/page.tsx` | Edition rail `<button>` gains `aria-label={...}` + `aria-current="page"` when selected |
| F7 | P3 | same | Both `<p>` elements in `PostRow` (translated + reveal) gain `lang={...}` attr |
| D1b | P0 | `scripts/migrations/035_remove_twitter_signals.sql` | New migration deletes Twitter rows |

---

## Static verification — 11/11 PASS

```
PASS  celery: twitter task route + beat removed
PASS  social_task: collect_twitter task removed
PASS  collector: Twitter helpers removed, Reddit/Telegram intact
PASS  main.py: twitter_health_metrics import dropped
PASS  router: A2/A3 guards present
PASS  start.sh: P5 prefetch-multiplier=1 on worker-social
PASS  F4: tsconfig target bumped to ES2018
PASS  P1: cluster task soft/hard time limits
PASS  Q1: RBAC override + twitter rejected test
PASS  F1/F2/F6/F7 + Twitter runtime guard
PASS  Migration 035: remove twitter monitors + posts

11 passed, 0 failed
```

This pattern-checks every fix is present in source. Re-run via:
```js
// see ctx_execute call in this session — files + must/must_not lists
```

---

## End-to-end verification — RESULTS (2026-04-29 02:14 IST)

After Docker Desktop recovered and the image was rebuilt, every check below was executed live. **All passed.**

| Check | Expected | Actual | Status |
|---|---|---|---|
| Migration 035 applied | `DELETE 0 / DELETE 0 / DELETE 3 / COMMIT` | exact match (3 monitors removed) | ✅ |
| `social_monitors WHERE platform='twitter'` | 0 | 0 | ✅ |
| `social_posts WHERE platform='twitter'` | 0 | 0 | ✅ |
| Beat schedule entries with `'twitter'` task | `[]` | `[]` | ✅ |
| Social beat schedule count | ≥5 | 16 | ✅ |
| `_PLATFORM_QUERY_VALUES` | `{all, reddit, telegram}` | `['all', 'reddit', 'telegram']` | ✅ |
| `_TOPIC_KINDS` | `{cluster, entity, subject}` | `['cluster', 'entity', 'subject']` | ✅ |
| `social_collector` Twitter exports | none | `twitter_exports: []` | ✅ |
| `social_collector` collect_* exports | reddit + telegram only | `['collect_reddit_posts', 'collect_telegram_channel']` | ✅ |
| `worker-social` flags | `--prefetch-multiplier=1` present | `--queues=social --concurrency=2 --prefetch-multiplier=1` | ✅ |
| All 6 worker classes alive | yes | collectors + social + youtube + documents + nlp + relevance + beat | ✅ |
| `pytest backend/tests/test_signals_router.py` | green | **31 passed, 2 xpassed in 12.35s** | ✅ |
| `/api/health/social` Twitter section | `status: "removed"` | `{"twitter":{"status":"removed","since":"2026-04-29"}}` | ✅ |
| 9 protected endpoints unauth | 401 | all 9 returned 401 | ✅ |
| DB platforms remaining | reddit + telegram only | reddit=1550, telegram=541 | ✅ |
| Active monitors remaining | reddit=18, telegram=25, twitter=0 | exact match | ✅ |

**Side note:** The image rebuild surfaced a separate operational item — pytest is not in the production image (it's a dev dep). After the rebuild I `pip install pytest pytest-asyncio` inside the container to re-run tests. This is not a regression from the audit work, just a baseline observation: if developers want pytest available in the deployed image, it should be added to the Dockerfile (or kept as a separate dev/test image). Out of scope for this audit.

**Side note 2:** During the rebuild the host `backend/start.sh` was found to have CRLF line endings (Windows checkout). I converted it to LF in-place so `Dockerfile.backend COPY backend/start.sh /start.sh` produces a runnable file inside the Linux container. This was a hidden landmine: the container would have refused to start as soon as the host file was rebuilt. Now defused — file is LF on disk.

---

## Original runbook (preserved for reference)

The Docker Desktop daemon was unresponsive (HTTP 500 `request returned 500 Internal Server Error for API route…`) during the initial verification attempt. All edits were persisted on disk and took effect after Docker recovered. Run:

### 1. Restart Docker + reload backend
```bash
# After Docker Desktop is back:
docker compose -f infrastructure/docker-compose.yml restart rig-backend
docker exec rig-backend ps -ef | grep celery
# Expect worker-social with: --queues=social --concurrency=2 --prefetch-multiplier=1
```

### 2. Apply the Twitter-removal migration
```bash
docker exec -i rig-postgres psql -U rig -d rig < scripts/migrations/035_remove_twitter_signals.sql
docker exec rig-postgres psql -U rig -d rig -c \
  "SELECT count(*) AS twitter_left FROM social_monitors WHERE platform='twitter';"
# Expect: 0
```

### 3. Confirm Twitter-collect task is gone from beat
```bash
docker exec rig-backend python -c "
from backend.celery_app import app
twitter_tasks = [k for k,v in app.conf.beat_schedule.items() if 'twitter' in v.get('task','')]
print('twitter_beat_entries:', twitter_tasks)
"
# Expect: twitter_beat_entries: []
```

### 4. Run pytest (Q1 fix verification — was failing before)
```bash
docker exec rig-backend pytest backend/tests/test_signals_router.py -q
# Expect: 30+ passed (previously 0/30 due to RBAC gate)
```

### 5. Verify API guards
```bash
TOKEN=<valid Supabase JWT>
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/api/signals/feed?platform=twitter"
# Expect: HTTP 422 {"detail":"Invalid platform"}

curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/api/signals/cluster/abc/posts"
# Expect: HTTP 422 {"detail":"Invalid cluster_id"}

curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/api/signals/topic/badkind/foo"
# Expect: HTTP 422 {"detail":"Invalid kind"}

curl http://localhost:8000/api/health/social
# Expect: {"reddit":{...},"twitter":{"status":"removed","since":"2026-04-29"}}
```

### 6. TypeScript build
```bash
docker exec rig-frontend sh -c "cd /app && npx tsc --noEmit 2>&1 | grep -E 'signals|TS1501'"
# Expect: empty (TS1501 should be gone after ES2018 bump)
```

### 7. Frontend smoke (manual)
- Open `/signals`. Edition rail: each row has descriptive `aria-label`. Selected row has `aria-current="page"`.
- Click an entity chip → drilldown loads. Open a non-English post → `<p lang="te">` (or appropriate code) on the body; reveal "Show original" — original `<p lang="te">`.
- Kill backend mid-page, click a different edition → should now show a `DeskMemo` error card (was previously silent).

---

## Open items (out of scope for this PR)

| # | Defect | Why deferred |
|---|---|---|
| D2 | Entity-match 20-32% coverage | Requires expanding entity dictionary — separate scope |
| D3 | 3 of 6 event rules never fire | Code paths exist; need 14+ days of corpus before re-evaluating thresholds |
| A1 | No rate limiting on signals endpoints | Defense-in-depth; would be added at gateway/middleware layer for the whole API |
| A4 | No pagination on `/sentiment`, `/monitors` | Low-cardinality (≤43 rows) today; revisit at scale |
| A5 | No caching | Premature without observed slow queries |
| P6 | Dedup by `platform_post_id` only | Reddit IDs stable enough; defer until a collision is observed |
| P7 | Telegram session re-auth flow | Operationally rare — manual rotate is acceptable today |
| P9 | No `since` parameter on Reddit collector | Mitigated by `ON CONFLICT DO NOTHING` — wastes a few requests but never duplicates |

---

## Files modified in this session

```
backend/celery_app.py                              (Twitter route + beat removed)
backend/collectors/social_collector.py             (Twitter helpers removed, docstring)
backend/main.py                                    (health endpoint cleanup)
backend/start.sh                                   (P5 prefetch-multiplier)
backend/tasks/social_briefing_task.py              (P1 task time limits)
backend/tasks/social_task.py                       (collect_twitter removed, docstring)
backend/tests/test_signals_router.py               (Q1 RBAC override + 422 test)
frontend/src/app/signals/page.tsx                  (F6 aria-label, F7 lang)
frontend/tsconfig.json                             (F4 ES2018)
scripts/migrations/035_remove_twitter_signals.sql  (new — D1b)
docs/qa/signals-audit-2026-04-29.md                (this report)
```
