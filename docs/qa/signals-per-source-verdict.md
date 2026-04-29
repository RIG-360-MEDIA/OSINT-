# Signals — Per-Source Verdict

**Probed:** 2026-04-27. **Pass criteria** (set by user):
data <24 h fresh AND `/feed?platform=<x>` returns rows AND collector
logged success in last 24 h. Reddit + Telegram are the required-pass
platforms; Twitter is documented but not part of pass.

## Verdict matrix

| Platform | Required | Rows ever | Latest `collected_at` | Last successful task in last 24 h | Verdict | Root cause |
|---|---|---|---|---|---|---|
| **Reddit**   | ✓ pass | 100 | 2026-04-21 10:05 | ❌ none | **❌ FAIL** | SIG-11 starvation |
| **Telegram** | ✓ pass | 107 | 2026-04-23 15:59 | ❌ none | **❌ FAIL** | SIG-11 starvation |
| **Twitter**  | document | 0   | — | ❌ none | **❌ DARK** | SIG-11 starvation, possibly compounded by quota |

**Overall page verdict: ❌ FAIL.**

## Test-suite verdict (this QA pass)

| Suite | Result |
|---|---|
| Backend pytest (router + collector + task) | **57 passed, 2 skipped, 1 xfailed, 2 xpassed** |
| Backend coverage on `signals_router.py` | **100 %** |
| Backend coverage on `social_collector.py` | 44 % (deep async fetchers uncovered without live broker) |
| Backend coverage on `social_task.py` | 45 % |
| Frontend Vitest (signals page) | **11 passed** including SIG-1 + SIG-2 demonstrations via `it.fails` |
| Playwright spec discovery | **9 tests** registered (skip without `E2E_SUPABASE_TOKEN`) |
| Hypothesis property tests | 4 properties × ~80 examples each — green |

The single `xfailed` in pytest is `test_fetch_user_entities_filters_by_user_id` (SIG-14 confirmed).
The two `xpassed` results are intentional — `test_sentiment_includes_unmonitored_posts` (SIG-5) and `test_monitors_no_n_plus_one` (SIG-4) are limited by FakeSession fidelity; the production behaviour is captured by the live EXPLAIN trace in [signals-data-quality-report.md](signals-data-quality-report.md).

## Reddit — ❌ FAIL

**Symptom.** `social_posts WHERE platform='reddit'` is 6 days stale.
All 100 rows share the timestamp `2026-04-21 10:05:30.656` — single
batch run, then nothing.

**Evidence.**
- `kombu_queue` shows 479 backed-up messages on `collectors`.
- `docker logs rig-backend --since 168h | grep collect_reddit` shows
  Beat firing every 30 min but **zero** `Task received` lines for
  `tasks.collect_reddit` on `worker-collectors`.
- `worker-collectors` is busy parsing HTML (`parsed tree length: 1,
  wrong data type or not valid HTML` errors stream every 1-2 s).
- 4 active Reddit monitors are configured (`hyderabad`, `india`,
  `telangana`, `unitedstatesofindia`) — config is fine; pipeline is
  blocked.

**Root cause.** SIG-11: shared `collectors` queue with `--concurrency=1`,
slow HTML scrapers monopolise the slot.

**Path to PASS.** Fix SIG-11 (split social to dedicated queue or raise
concurrency). Optionally also SIG-8 (429 backoff + metric) so future
freshness drops alert.

## Telegram — ❌ FAIL

**Symptom.** Telegram is 4 days stale (last 2026-04-23 15:59).

**Evidence.**
- All 5 Telegram credentials present (`TELEGRAM_API_ID`,
  `_API_HASH`, `_BOT_TOKEN`, `_SESSION_STRING`).
- 7 active Telegram channel monitors configured.
- Same starvation pattern as Reddit; tasks queued, never received.
- 107 rows from a 2-hour window on 2026-04-23 — single successful
  Beat-cycle landed before the queue locked up.

**Root cause.** SIG-11.

**Quality concerns even if SIG-11 is fixed.**
- SIG-13: language stuck at `en` — Telugu posts get sentiment_score=0.
- SIG-10: `matched_entities` empty for all 107 rows (entity tagging
  applied at write-time but query is global, not user-scoped, plus
  user added entities post-collection).

**Path to PASS.** SIG-11 first. SIG-13 (langdetect) and SIG-10
(per-user entity match) for quality bar.

## Twitter — ❌ DARK (informational)

**Symptom.** Zero rows in `social_posts WHERE platform='twitter'`.

**Evidence.**
- `TWITTER_BEARER_TOKEN` set (110 chars).
- 3 active Twitter account monitors (`KTRTRS`, `revanth_anumula`,
  `trspartyonline`).
- Beat has fired `tasks.collect_twitter` hourly since at least
  2026-04-26 08:33 — never received.
- We cannot verify whether the bearer is on free tier or what its
  rate-limit posture is, because the collector never executed.

**Possible compounding causes.**
- Twitter free-tier search window is 7 days; backfill may be limited.
- Bearer-only auth may not have `tweet.read` scope.

**Path to PASS** (not required by user spec, but for completeness).
SIG-11 first → run `tasks.collect_twitter` once manually with verbose
logging → inspect for 401 / 403 / 429.

## Sentiment aggregator — ✓ WORKING

`tasks.aggregate_social_sentiment_daily` runs **on the `nlp` queue**
(not `collectors`), consumed by `worker-nlp` (concurrency=4). It is
not affected by SIG-11. We see clean executions every hour:

```
[2026-04-26 14:32:15,939] social_sentiment_daily aggregation done — 23 buckets upserted
[2026-04-26 14:32:16,055] succeeded in 0.75s
```

`social_sentiment_daily` has 25 rows for 11 monitors, latest date
2026-04-23. The aggregator is correct; its inputs are stale because
no fresh posts arrive.

## Frontend rendering — ✓ WORKING (modulo defects)

`/api/signals/feed` and `/api/signals/sentiment` return 200 to
authenticated requests; the page renders, tabs switch, pagination
advances when there are >30 posts, sentiment ledger displays.

But the page silently presents stale data to the user with no "data
freshness" indicator — users currently have no way to tell that what
they're seeing is 4-6 days old. This is itself a UX defect (informal
SIG-18 candidate; not registered to keep the list tight).

## Required to flip this page to ✓ PASS

1. **SIG-11** — split social tasks onto a dedicated worker (CRITICAL,
   blocks everything).
2. **SIG-12** — once SIG-11 is fixed, manually invoke
   `tasks.collect_twitter` with verbose logging to surface auth /
   quota errors, fix as needed.
3. **SIG-10 + SIG-14** — restructure entity matching to be per-user
   and re-tag historical rows.
4. **SIG-13** — language detection on the Telegram path.
5. (Optional UX) — surface "last updated" timestamp on the page so
   stale-data scenarios are visible to the user.
