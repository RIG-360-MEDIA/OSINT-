# Analyst Pillar — Scraper / Pipeline Sweep (Phase F)

**Audit date:** 2026-04-28
**Method:** read-only DB queries against the running stack + cross-reference against [backend/celery_app.py](backend/celery_app.py) Beat schedule and [backend/start.sh](backend/start.sh) worker definitions.

The Analyst RAG endpoint pulls from five evidence pools: **articles**, **govt_documents**, **youtube_clips**, **social_posts**, **newspaper_clippings**. This sweep checks each one's collector + freshness.

---

## Per-source verdict

| Pool | Source code | Beat schedule | Worker queue | Freshness | Verdict |
|---|---|---|---|---|---|
| Articles (RSS / HTML) | [backend/collectors/newspaper_collector.py](backend/collectors/newspaper_collector.py) (misnamed; actually does RSS) + `tasks.collect_rss`, `tasks.collect_html` | every 15 min / 30 min / 6 h | `collectors` (concurrency=1) | 13,022 / 13,097 embedded; 75 backlog | ✅ healthy |
| Govt documents | [backend/collectors/sources/*.py](backend/collectors/sources/) (53 adapters) → `tasks.collect_govt_documents` | every 12 h + on-boot catch-up | `documents` (concurrency=2, prefetch=1) | 233 rows, 8 in last 24 h, all embedded | ✅ healthy (CLAUDE.md is stale) |
| YouTube clips | [backend/collectors/youtube_collector.py](backend/collectors/youtube_collector.py) → `tasks.collect_youtube` | every 2 h | `youtube` (concurrency=1) | **0 / empty result** | ⚠ **degraded** |
| Social posts | [backend/collectors/social_collector.py](backend/collectors/social_collector.py) → `tasks.collect_reddit`, `tasks.collect_telegram`, `tasks.collect_twitter` | tiered hot/warm/cold (15 m / 1 h / 6 h) | `social` (concurrency=2) | 1,805 total, 810 in last 24 h | ✅ healthy |
| Newspaper clippings | `tasks.collect_newspapers` | every 12 h | `documents` (shared with govt) | 557 in last 7 d, last collected 06:52 today | ✅ healthy |

---

## 1. Articles (RSS / HTML)

[backend/collectors/newspaper_collector.py](backend/collectors/newspaper_collector.py) — note the misleading name; this file is for RSS articles, not newspaper *clippings* (those live in `tasks.collect_newspapers`).

- **Beat:** `collect-rss-every-15-min`, `collect-rss-direct-every-30-min`, `collect-html-every-6-hours` ([celery_app.py:111-125](backend/celery_app.py:111))
- **Pipeline:** collect → (un-embedded row written) → `process-nlp-every-30-seconds` runs LaBSE embedding + entity extraction → `score_relevance_batch` per user → queryable in Analyst.
- **End-to-end freshness:** ~ 1–10 minutes from publish to Analyst.
- **Backlog:** 75 articles un-embedded (0.57%). At 30-second beat intervals with concurrency 4 on `nlp`, the backlog drains in seconds.
- **Risk:** the `collectors` queue has concurrency=1 and shares with HTML scraping; long RSS scrapes (30–60 min per CLAUDE.md) can starve newer collections. Acceptable for current load.

**Verdict: healthy.**

---

## 2. Govt documents

53 source adapters under [backend/collectors/sources/](backend/collectors/sources/) — registered via `@register_source`.

- **Beat:** `collect-govt-docs-every-12h` (changed from once-daily for self-healing per the comment at [celery_app.py:171-176](backend/celery_app.py:171)) + the `worker_ready` catch-up handler at [celery_app.py:383-429](backend/celery_app.py:383) that fires immediately on worker boot if last collection > 24 h ago.
- **Worker:** `worker-documents@%h --concurrency=2 --prefetch-multiplier=1` ([start.sh:30-35](backend/start.sh:30)). **The CLAUDE.md "no consumer" gap is closed.**
- **Doctor:** `tasks.govt_collection_doctor` ([celery_app.py:182-186](backend/celery_app.py:182)) — runs every 12 h to probe sources.
- **Freshness:** 233 rows total, **8 in the last 24 h**, most recent at 04:55 UTC today. Embedding rate 100%.
- **Risk:** of the 53 adapters, 9 are JS-rendered and depend on Playwright (SEBI, SCI, NGT, MCA, ADB, IMF, UN, CERC, PNGRB — see [celery_app.py:359-367](backend/celery_app.py:359)). If Playwright fails to boot, those adapters silently return zero rows. The `_govt_collector_self_check` warns on failure but doesn't crash the worker. **Recommendation:** wire `assert_available_sync` failure into a metric so the silent degradation surfaces.

**Verdict: healthy.**

---

## 3. YouTube clips ⚠ DEGRADED

[backend/collectors/youtube_collector.py](backend/collectors/youtube_collector.py) → `tasks.collect_youtube`.

- **Beat:** `collect-youtube-every-2h` ([celery_app.py:161-170](backend/celery_app.py:161)) — bumped from 6 h to 2 h per the comment.
- **Worker:** `worker-youtube@%h --concurrency=1`. Running (PIDs 9 + 69 with significant CPU time).
- **Freshness:** the count query `SELECT count(*) … FROM youtube_clips` returned an **empty result row** (no row at all) — likely 0 rows in the table.

This means **every Analyst query is paying for a YouTube retrieval round-trip that returns nothing**, and the user's "Clips" evidence pool is permanently empty.

**Triage steps for the YouTube task (separate ticket):**
1. `docker exec rig-postgres psql -U rig -d rig -c "SELECT count(*) FROM youtube_clips;"` — confirm whether 0 or table missing.
2. If table exists with 0 rows: check worker logs for `tasks.collect_youtube` exceptions over the last 24 h.
3. Likely culprits: YouTube API quota, channel-feed config missing, `yt-dlp` binary absent, transcript-fetch failing.
4. Reactivate by either fixing the collector or **removing** `retrieve_relevant_clips` from the Analyst query path until clips are flowing again (avoids paying for the wasted DB hit — see backend finding **B-07**).

**Verdict: degraded — Analyst's Clips evidence is silently empty. Not a launch blocker, but the page advertises clips support that doesn't currently materialize.**

---

## 4. Social posts (Reddit / Telegram, Twitter hidden)

`tasks.collect_reddit`, `tasks.collect_telegram`, `tasks.collect_twitter` on the dedicated `social` queue (concurrency=2).

- **Beat:** Tiered cadence per platform — hot=15 min, warm=1 h, cold=6 h ([celery_app.py:188-229](backend/celery_app.py:188)). Twitter is `warm`-only since the UI is hidden per CLAUDE.md.
- **Pipeline:** collect → translate (every 10 min) → cluster (every 15 min) → sentiment aggregation (hourly) → analyst-queryable.
- **Freshness:** 1,805 total posts, **810 in last 24 h** (45% — very fresh). Most recent 13:09 UTC today.
- **Embedding:** column `labse_embedding` is indexed (`idx_posts_embedding`) but the count query did not separate embedded vs un-embedded — Phase A skipped the embedded sub-count for social. Add to the daily smoke.

**Verdict: healthy.**

---

## 5. Newspaper clippings

`tasks.collect_newspapers` — moved off `collectors` queue to `documents` queue per [celery_app.py:265-272](backend/celery_app.py:265). The catch-up handler at [celery_app.py:404](backend/celery_app.py:404) also probes `newspaper_clippings.collected_at`.

- **Beat:** `collect-newspapers-every-12h`.
- **Freshness:** 557 rows total, **all 557 in the last 7 days** (which means the table likely has a 7-day retention window — verify intent), most recent at 06:52 UTC today.
- **Embedding index:** `idx_clippings_embedding` exists ✅.

**Verdict: healthy. Confirm 7-day retention is intentional (separate ticket).**

---

## CM Page tasks (not directly Analyst)

[celery_app.py:97-108, 273-343](backend/celery_app.py:97) — heavy LLM work for the CM (Chief Minister) page. None of this feeds the Analyst directly, but the `nlp` and `social` queues are shared, so a CM-task burst can starve Analyst-relevant NLP. Worth a note for capacity planning, not Analyst sign-off.

---

## Summary

| Source | Verdict | Action needed before Analyst prod |
|---|---|---|
| Articles | ✅ healthy | None |
| Govt documents | ✅ healthy | None (CLAUDE.md edit) |
| YouTube clips | ⚠ degraded | Decide: fix YouTube collector OR remove the retrieval round-trip from `analyst_router.py` (B-07). Either is acceptable for launch. |
| Social posts | ✅ healthy | Add embedded-vs-unembedded sub-count to daily smoke |
| Newspapers | ✅ healthy | Confirm 7-day retention is intentional |

**Production verdict for Analyst evidence pipelines:** four out of five are healthy and fresh. YouTube clips is the only degraded source and is the cheapest to either fix or feature-flag off until fixed.
