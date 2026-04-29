# 07 — Caching + concurrency (Step 7)

**Verdict: PASS for current single-worker dev. RISK for multi-worker prod.**

## WorldMonitor router cache
- File: `backend/routers/worldmonitor_router.py:90-115` (approx).
- Pattern: process-local dict + monotonic timestamp.
- TTL: `WM_TG_CACHE_TTL_S` env (default 1800s = 30 min).
- Keys: `"telangana:briefing"`, `"telangana:news"`, `"telangana:events"`,
  `"telangana:live-channels"`. Note: route-only — **no per-user
  variation** (acceptable for these endpoints — same data for all
  authorized users).
- Verified: first `/briefing` call 6.9s `cached:false`, second
  call 742ms `cached:true`.

## CM router cache
- File: `backend/nlp/cm/cache.py`.
- Pattern: section-keyed dict, per-tuple value, TTL per section.
- TTL: `CM_TTL_<SECTION>_S` env override per section
  (pulse/issues/silence/etc.). Default 300s typical.
- Keys: `(user_id, state_code, window)` etc. — **per-user**, so
  cache hit only for the same user re-requesting.
- Backed by 27 unit tests (all green).

## Concurrency risk
- Both caches are **process-local** (Python dict). Single uvicorn
  worker today (`--reload` runs one process) → cache shared across
  requests, hit rate good.
- If prod scales uvicorn to N workers behind a load balancer,
  cache becomes per-worker → thundering-herd on the upstreams
  (Groq, ACLED, YouTube, RSS) every TTL boundary × N workers.
- **D-28 (MEDIUM)**: in production, swap to Redis. The
  `rig-wm-redis` container is already running, but unused by
  rig-backend.

## Cache stampede
- No request-coalescing on miss. If 50 users hit `/briefing` in the
  same millisecond on cold cache, 50 outbound parallel calls fire.
  Acceptable for current low-traffic dev; will need
  request-coalescing (per-key lock) at scale.
- **D-29 (LOW)**: add a per-key `asyncio.Lock` so only one fetch
  is in flight per cache key.

## Defects added
| ID | Sev | Title |
|---|---|---|
| D-28 | MEDIUM | Process-local cache won't scale across uvicorn workers; switch to Redis (`rig-wm-redis` already running) |
| D-29 | LOW | No cache-stampede protection on miss; add per-key asyncio.Lock |
