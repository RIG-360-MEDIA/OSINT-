# Full incident chain — 2026-06-04 (and health-check fix 06-05)

This is the consolidated record of everything diagnosed and fixed across
the long 2026-06-04 session, plus the `health_history` fix that landed
just after midnight UTC (06-05). Read `06-feed-wedge-incident-2026-06-04.md`
first for the NLP-wedge deep dive; this file is the wider chain.

## The chain of distinct problems (each masked the next)

| # | Problem | Root cause | Fix | Status |
|---|---|---|---|---|
| 1 | Ollama probed despite being off a week | `LOCAL_LLM_ENABLED=0` set in `.env.prod` + osint-backend but **not** wired into `rig-backend.environment:` | added passthrough at compose line 100 | ✅ live |
| 2 | Transcript fetches failing | stale `YOUTUBE_PROXY_URL=socks5h://172.30.0.1:1081` left in `.env.prod` from a reverted SOCKS experiment | commented out line 46 | ✅ live |
| 3 | Feed stuck 2h behind | NLP batch wedged: `check_semantic_duplicate` shared the caller's SQLAlchemy session; a DNS blip threw, corrupted the session, every subsequent UPDATE failed, poison row re-pulled every 30s | `await db_conn.rollback()` in the dedup except block | ✅ live |
| 4 | (recovery) 1,486 backlog rows | downstream of #3 | bulk `UPDATE nlp_processed=true WHERE substrate_status='ok'` | ✅ done |
| 5 | Collectors stopped inserting | Postgres restarted ~2 min after each `rig-backend` recreate; asyncpg pool held dead connections → `connection is closed` on every INSERT | `setup=SELECT 1` checkout-validator + `max_inactive_connection_lifetime=60` on the pool, plus retry-on-stale-conn in single-conn paths | ✅ live |
| 6 | `fetch_og_images_batch` crash-looping every 10 min for a month | `thumbnail_task.py` queried non-existent column `inserted_at` | → `collected_at` (2 refs) | ✅ live |
| 7 | Dashboard stuck red (1/34 failing) | `health_history` check is self-referential — counts itself in the failure total, so once any real failure trips it, it latches red forever | exclude own key in `_health_history_ok` | ✅ live (06-05) |

## Deployed code changes

**rig repo (`/root/rig`, mirrored to local `rig-surveillance`):**
- `backend/nlp/nlp_embedding.py` — dedup rollback (#3)
- `backend/collectors/direct_rss_collector.py` — pool `setup` + idle lifetime (#5)
- `backend/collectors/rss_collector.py` — retry-on-stale-conn (#5)
- `backend/collectors/html_collector.py` — retry-on-stale-conn (#5)
- `backend/tasks/thumbnail_task.py` — `inserted_at`→`collected_at` (#6)

**rig-mc repo (`/root/rig-mc`, NOT a git repo — host-only):**
- `backend/app/metrics/system.py` — `_health_history_ok` self-exclusion (#7)
  - backup: `system.py.bak-20260605-health-history-latch`

**Config (`/root/rig/infrastructure`):**
- `docker-compose.yml` line 100 — `LOCAL_LLM_ENABLED` passthrough (#1)
- `.env.prod` line 46 — stale proxy commented (#2)

Both rig-backend and mc-backend images were rebuilt and recreated.

## Verified-healthy state at end of session (2026-06-05 ~00:15 UTC)

- Articles: newest 0 min ago, 308/hour
- NLP: 19 batches/10min, backlog ~5 (normal in-flight)
- Dashboard: **34/34 checks pass** (data 8, entity 3, extraction 7, sources 8, system 8)
- Embedding coverage: 98.4% · Substrate OK: 78.7% (both above floor)
- Data quality last 24h: title 98.7%, lead_translated 98.8%, topic 99.9%,
  nlp_processed 99.9%, thumbnail 89.3%, entities 84%, geo_primary 67%
- All containers up; all worker queues present; zero error signatures in 15 min
- Postgres-restart resilience proven: a restart occurred during the #5 deploy
  and the pool absorbed it with zero dropped articles

## KNOWN-STALE pillars (pre-existing, NOT caused today, flagged for triage)

These are real but predate this session and were never the user's
immediate concern (the Feed/articles pipeline). No health check monitors
pillar freshness, which is why they went unnoticed:

| Pillar | Newest data | Dead for | Likely cause |
|---|---|---|---|
| Clips (youtube_clips) | 2026-05-25 17:49 | ~10 days | Hetzner IP blocked at YouTube captions endpoint (confirmed); plus the wedge. Bypass infra deployed but not wired (host-network sidecar needed). |
| Signals/social — telegram | 2026-05-25 17:39 | ~10 days | social collection task not dispatched by beat |
| Signals/social — reddit | 2026-04-29 15:00 | ~5 weeks | social collection task not dispatched by beat |

The social worker IS alive (3 procs) but beat dispatches **no** social
collection task — 12 min of beat ticks showed NLP/RSS/enrich/og-images
and zero social/reddit/telegram. Root cause likely a missing/disabled
beat-schedule entry (grep for social schedule in `celery_app.py` found
nothing). **Needs its own investigation — not started.**

## Recommended follow-ups (not done)

1. **Pillar-freshness alerts** — add checks to mc-backend's REGISTRY for
   clips/social/articles "newest < N hours". Would have surfaced the
   weeks-dead pillars immediately. The single biggest monitoring gap.
2. **NLP-throughput alert** — page if `nlp_processed/collected` over the
   last hour < 80%. Would have caught the #3 wedge in minutes.
3. **Investigate why Postgres restarts on rig-backend recreate** —
   `docker events` around the recreate; likely a healthcheck flap or
   memory spike from 4 simultaneous LaBSE loads. Set memory limits.
4. **Backfill 3,095 old `labse_embedding IS NULL` rows** — static
   pre-existing gap (not growing; recent flow is 95.9%). Pushes coverage
   toward 99%+.
5. **Social pillar revival** — diagnose the missing beat schedule;
   separately, Reddit (5wk) and Telegram (10d) may also have auth/API
   issues on top of the scheduling gap.
6. **Capture the real dedup exception** — `check_semantic_duplicate`'s
   `except Exception` swallows the cause (we saw "DNS name resolution"
   once). Log `exc_info=True` for one batch to confirm and fix upstream.
