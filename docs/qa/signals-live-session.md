# Signals — Live Debugging Session

**Date:** 2026-04-27
**Branch:** fix/archive-phase-8
**Stack:** Docker compose, all containers `Up 9 minutes (healthy)`
**Method:** read-only probes against `rig-postgres`, `rig-backend`,
plus HTTP smoke tests against the running FastAPI service.

## TL;DR

The Signals page **renders, authenticates, and queries successfully**,
but the **collection pipeline is broken in production**:

- **Reddit data: 6 days stale** (last collected 2026-04-21, today 2026-04-27).
- **Telegram data: 4 days stale** (last 2026-04-23).
- **Twitter: zero rows ever inserted** despite `TWITTER_BEARER_TOKEN`
  being set.
- **479 messages backed up** in the `collectors` Kombu queue.
- **100% of posts have empty `matched_entities`** despite 30 entities
  registered for the active user.

Per the user's pass criteria (Reddit + Telegram E2E), **the page is FAIL**.
Root cause: queue-starvation on the shared `collectors` worker
(concurrency=1) and a write-time entity-match design that doesn't
re-tag historical rows.

## Probe results

### 1. Containers & processes

| Service | Status |
|---|---|
| `rig-backend`, `rig-frontend`, `rig-postgres`, `rig-freshrss`, `rig-searxng` | all Up, healthy. |

`docker exec rig-backend ps -ef` confirms 5 Celery workers + Beat +
uvicorn:

| pid | role | queue | concurrency |
|---|---|---|---|
| 7  | worker-collectors | `collectors` | 1 |
| 8  | worker-youtube | `youtube` | 1 |
| 9  | worker-documents | `documents` | 2 |
| 10 | worker-nlp | `nlp` | 4 |
| 11 | worker-relevance | `relevance,brief` | 4 |
| 12 | beat | — | — |

(`worker-documents` runs despite CLAUDE.md noting that gap — it has
been added since the last doc update.)

### 2. Credentials present (values masked)

```
TWITTER_BEARER_TOKEN=<SET, 110 chars>
TELEGRAM_API_ID=<SET, 8 chars>
TELEGRAM_API_HASH=<SET, 32 chars>
TELEGRAM_BOT_TOKEN=<SET, 46 chars>
TELEGRAM_SESSION_STRING=<SET, 353 chars>
REDDIT_USER_AGENT=<UNSET>
GROQ_API_KEY=<UNSET>
```

Reddit needs no auth; `REDDIT_USER_AGENT` unset means default UA, low
risk. `GROQ_API_KEY` is unrelated to signals.

### 3. Database state (probed via psql)

```
social_posts total          : 207
social_posts by platform    :
  reddit   100  first/last seen 2026-04-21 10:05:30
  telegram 107  first        2026-04-23 13:04, last 2026-04-23 15:59
  twitter    0  ❌

social_monitors             : 14 active (4 reddit / 7 telegram / 3 twitter)
last_collected_at:
  reddit   2026-04-21
  twitter  2026-04-23
  telegram 2026-04-23

social_sentiment_daily      : 25 rows, latest 2026-04-23, 11 monitors
user_entities               : 30 rows, all owned by one user
                              db4b9207-51aa-4d39-a7bf-e6fab34c3465

null sentiment_score        : 0% (good)
empty matched_entities      : 100% (BUG) — see SIG-10
duplicate platform_post_id  : 0 (good — UNIQUE constraint enforcing)
```

Indexes present on `social_posts`: `collected_at DESC`, `(monitor_id,
collected_at DESC)`, `platform`, GIN on `matched_entities`, HNSW on
`labse_embedding`, plus PK and `(platform, platform_post_id)` UNIQUE.

`social_monitors` has only PK and `(platform, identifier)` UNIQUE —
**no index on `(platform, is_active)`** (SIG-6 confirmed).

### 4. Broker queue depth (the smoking gun)

```
SELECT name, count(*) FROM kombu_queue q
  JOIN kombu_message m ON m.queue_id=q.id
  WHERE m.visible GROUP BY name;
```

| queue | pending |
|---|---|
| `celery` | 13 |
| `collectors` | **479** |
| `default` | 10 |

worker-collectors is `--concurrency=1` and shares the `collectors`
queue with RSS, HTML, social, and newspaper tasks (per
[backend/celery_app.py:51-69](backend/celery_app.py:51)). The HTML
scrapers are slow (we observed multi-second `Tier 3` adapter calls
to `communicationstoday.co.in` blocking the worker), starving the
social tasks. Beat keeps publishing them; they pile up.

### 5. API smoke tests

| Request | Result |
|---|---|
| `GET /api/signals/feed?platform=reddit` (no token) | `HTTP 401` 0.2 ms |
| `GET /api/signals/monitors` (no token) | `HTTP 401` |
| `GET /api/signals/feed?platform=all&days=7&limit=30` (with bearer, from logs) | `200 OK` |
| `GET /api/signals/sentiment?days=7` (with bearer, from logs) | `200 OK` |

Auth gating works; happy-path returns 200.

### 6. EXPLAIN on `/monitors` N+1 (SIG-4)

```
Seq Scan on social_monitors m
   SubPlan 1
     ->  Aggregate
           ->  Seq Scan on social_posts
                 Filter: monitor_id = m.id
                 Rows Removed: 192 (per loop, loops=14)
 Execution Time: 0.555 ms
```

Confirms the per-monitor sub-COUNT — fast at 14 monitors / 207 rows
but linear on monitor count and full-scan per loop. Will degrade as
the dataset grows.

### 7. Beat-vs-worker traces

`docker logs rig-backend --since 168h` filtered to `collect_reddit |
collect_twitter | collect_telegram`:

- **Beat** sends due tasks every 30 min for Reddit/Telegram and every
  hour for Twitter → many lines.
- **worker-collectors** never logs `Task received` or `Task succeeded`
  for any of those task names.
- Only `aggregate_social_sentiment_daily` runs cleanly (`succeeded in
  0.30–0.75 s`, on `worker-nlp` which routes via `nlp` queue).
- The `worker-collectors` slot is occupied by RSS / HTML scrapes (we
  see `parsed tree length: 1, wrong data type or not valid HTML`
  errors stream every 1-2 s from `ForkPoolWorker-1`).

## New defects discovered (added to register)

| ID | Sev | Defect |
|---|---|---|
| SIG-10 | HIGH | 100 % of posts have empty `matched_entities`. Two-part cause: (a) `_fetch_user_entities` ([social_task.py:30](backend/tasks/social_task.py:30)) reads `SELECT DISTINCT canonical_name FROM user_entities` *without* `user_id` filter — leaks one user's entity list to all matches; (b) historical posts collected before user added entities are never re-tagged. |
| SIG-11 | **CRITICAL** | `collectors` queue backed up by **479 messages**. worker-collectors `--concurrency=1` is shared between RSS, HTML, newspapers, and social. Slow HTML scrapers starve social collection. Beat keeps firing; messages pile up. |
| SIG-12 | HIGH | Twitter has 0 rows ever despite `TWITTER_BEARER_TOKEN` set. Effectively dark; consequence of SIG-11 (the task never runs) compounded by possible quota issues we can't observe without execution. |
| SIG-13 | MED  | Telegram posts inserted with `post_language='en'` regardless of actual language. Telugu post (`SRH Captain: సన్‌రైజర్స్‌లోకి…`) stored as `en`, VADER returns sentiment_score=0. No language-detection step in the Telegram path of [social_task.py](backend/tasks/social_task.py). Twitter has `t.get("lang") or "en"` ([social_collector.py:127](backend/collectors/social_collector.py:127)) — falls back to en silently. |
| SIG-14 | LOW  | `_fetch_user_entities` query has no `user_id` predicate — privacy/correctness: every user's signals feed is matched against the same global pool. (Mitigated for now since only one user has entities, but breaks at multi-user.) |

## What works
- Endpoints serve correctly when invoked.
- Sentiment aggregator (`worker-nlp` consumer) runs and updates
  `social_sentiment_daily` hourly.
- Schema, indexes, FKs are sound.
- Auth (Supabase Bearer + `get_current_user`) is enforced.
- No duplicate posts (UNIQUE `(platform, platform_post_id)`).
- Frontend dev server reachable, no crash.

## What doesn't work
- Reddit / Twitter / Telegram collectors do not actually run in the
  current production scheduling (queue starvation).
- Entity matching is broken for historical rows; design needs a
  re-tag pass.
- Telegram language detection is absent.
- N+1 in `/monitors` is latent.

## Verdict (per user pass criteria)

| Platform | Required | Result | Reason |
|---|---|---|---|
| Reddit | data <24 h old | ❌ 6 days stale | SIG-11 starvation |
| Telegram | data <24 h old | ❌ 4 days stale | SIG-11 starvation |
| Twitter | (not part of pass) | ❌ 0 rows | SIG-11 + SIG-12 |

**Overall: FAIL.** Remediation is in `signals-defects.md` and the fix
branch will need to address SIG-11 first (split the social tasks onto
their own queue or raise concurrency) before any other Signals work
can be validated.

## Files referenced
- [backend/routers/signals_router.py](backend/routers/signals_router.py)
- [backend/collectors/social_collector.py](backend/collectors/social_collector.py)
- [backend/tasks/social_task.py](backend/tasks/social_task.py)
- [backend/celery_app.py](backend/celery_app.py)
- [scripts/migrations/007_social_signals.sql](scripts/migrations/007_social_signals.sql)
- [infrastructure/start.sh](infrastructure/start.sh)
- [frontend/src/app/signals/page.tsx](frontend/src/app/signals/page.tsx)
