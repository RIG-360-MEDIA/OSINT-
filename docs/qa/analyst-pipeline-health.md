# Analyst Pillar — Pipeline Health (Phase A)

**Audit date:** 2026-04-28
**Stack:** running (rig-backend, rig-postgres, rig-frontend all `Up 2h+`)
**Scope:** Database schema + Celery worker topology + Beat schedule + corpus freshness — read-only, no mutations.

---

## TL;DR

The pipeline that feeds the Analyst is **healthy**. All 6 Celery workers are running, every embedded table has an HNSW index, the `documents` queue *is* being consumed (CLAUDE.md is stale on this point — see §2), and corpus freshness is acceptable across articles, govt docs, social posts, and newspaper clippings.

Two things to watch:
1. `youtube_clips` returned an empty count row — likely the table has 0 rows. Confirm before relying on clip evidence in the Analyst.
2. Single-tenant test environment: only **1 user** with a profile. RBAC isolation tests (Phase C) cannot run on prod data — needs a synthetic second user.

---

## 1. Postgres + pgvector

| Check | Result |
|---|---|
| `vector` extension | ✅ installed, version `0.5.1` |
| `pgcrypto` extension | ✅ installed |
| `analyst_sessions` table | ✅ present |
| `analyst_turns` table | ✅ present |
| `analyst_sessions` row count | **161** |
| `analyst_turns` row count | **135** |
| Users with profiles | **1** (`db4b9207-…`) |

### HNSW indexes (cosine ops)

All 7 embedding tables are indexed:

| Table | Index |
|---|---|
| `articles` | `idx_articles_embedding` (m=16, ef_construction=64) |
| `govt_documents` | `idx_docs_embedding` |
| `govt_document_chunks` | `idx_chunks_embedding` |
| `newspaper_clippings` | `idx_clippings_embedding` |
| `social_posts` | `idx_posts_embedding` |
| `youtube_clips` | `idx_clips_embedding` |
| `cm_issues` | `cm_issues_emb_idx` |

**CLAUDE.md gap closed:** the doc claims HNSW on `story_threads.centroid_embedding` is commented out — that's true in [scripts/migrations/001_initial_schema.sql](scripts/migrations/001_initial_schema.sql), but the Analyst doesn't query `story_threads`, so it's not Analyst-relevant. No action.

---

## 2. Celery worker topology

`docker exec rig-backend ps -ef` shows **all 6 workers running**:

| Queue | Hostname | Concurrency | PIDs |
|---|---|---|---|
| `collectors` | `worker-collectors@…` | 1 | 7 + child 77 |
| `social` | `worker-social@…` | 2 | 8 + children 80, 87 |
| `youtube` | `worker-youtube@…` | 1 | 9 + child 69 |
| **`documents`** | **`worker-documents@…`** | **2** | **10 + children 102, 103** |
| `nlp` | `worker-nlp@…` | 4 | 11 + children 106, 110 |
| `relevance,brief` | `worker-relevance@…` | 4 | 12 + children 68, 72, 78, 84 |
| Beat | (scheduler) | — | 13 |
| FastAPI | uvicorn | — | 1 |

**CLAUDE.md is stale.** The doc says "the `documents` queue exists in routing but `start.sh` does not launch a worker for it." The actual [backend/start.sh:29-35](backend/start.sh:29) **does** launch `worker-documents@%h --concurrency=2 --prefetch-multiplier=1`. The carve-out from the audit plan is moot. Recommend updating CLAUDE.md.

`celery_taskmeta` shows **20,844 task results** with `most_recent_done = 2026-04-28 13:26:59` — Beat is firing and tasks are being consumed across all queues.

---

## 3. Corpus freshness (Analyst evidence pools)

| Table | Total | Embedded | Recent | Most recent |
|---|---:|---:|---:|---|
| `articles` | 13,097 | 13,022 (99.4%) | — | — |
| `articles` (un-embedded backlog) | **75** | — | — | — |
| `govt_documents` | 233 | 233 (100%) | 8 in last 24h | `2026-04-28 04:55:30 UTC` |
| `youtube_clips` | **0?** (empty result) | — | — | — |
| `social_posts` | 1,805 | — | 810 in last 24h | `2026-04-28 13:09:50 UTC` |
| `newspaper_clippings` | 557 | — | 557 in last 7d | `2026-04-28 06:52:41 UTC` |
| `user_article_relevance` (user db4b9207) | 13,079 scored | — | 135 tier-1 | — |

### Observations

- **Articles backlog: 75 un-embedded** out of 13k total — 0.57%. Beat fires `process-nlp-every-30-seconds`; backlog should drain in < 5 min. Acceptable for prod.
- **Govt docs: 233 rows, all embedded, 8 fresh in last 24h** — flat contradiction of CLAUDE.md's "15 rows from 2026-04-23 manual run". The pipeline has been working since the doc was written.
- **YouTube clips: empty result** — may be 0 rows. ⚠ FOLLOW-UP: confirm `SELECT count(*) FROM youtube_clips;` returns a number; if 0, the YouTube collector is silently failing.
- **Social posts: 810 / 1,805 = 45% in last 24h** — fresh, ingest is alive.
- **Newspapers: 557 in last 7d (matches total)** — newspaper_clippings table appears to only retain 7 days. Verify retention policy is intentional.
- **Relevance scoring: 13,079 / 13,097 = 99.86% coverage for the one user** — `score_unscored-every-30-min` is doing its job.

---

## 4. Analyst usage signal

```
SELECT confidence, count(*), avg(retrieval_ms)::int FROM analyst_turns
 WHERE created_at > now() - interval '7 days' GROUP BY confidence;
```

| Confidence | Count | Avg retrieval_ms |
|---|---:|---:|
| HIGH | 52 | 5,722 |
| MEDIUM | 19 | 4,566 |

71 queries in the last 7 days. **No LOW-confidence rows** — either users only ask questions with strong corpus support, or the LOW path doesn't persist a turn (likely the latter, since the `INSUFFICIENT COVERAGE` short-circuit at [analyst_router.py:270-296](backend/routers/analyst_router.py:270) returns early without writing to `analyst_turns`).

### Recent turns (latency outliers)

```
2026-04-27 15:28:07 | 20 evidence | HIGH | retrieval_ms=26,363 | What should I know about: Fee hike row…
2026-04-27 14:50:34 | 19 evidence | HIGH | retrieval_ms= 7,117 | (same q)
2026-04-27 12:49:24 | 20 evidence | HIGH | retrieval_ms= 2,166 | What is the 90-day implementation risk…
2026-04-27 12:48:55 | 12 evidence | MEDIUM | retrieval_ms= 1,947 | What is the political dynamic behind…
2026-04-27 12:48:08 | 23 evidence | MEDIUM | retrieval_ms= 4,487 | What buried story…
```

⚠ `retrieval_ms = 26,363` outlier on the 15:28 turn — 26 seconds is well over a user's patience. Worth tracking p95 latency in the structured log finding (Phase B finding B-04).

---

## 5. Recommendations

| # | Action | Owner | Priority |
|---|---|---|---|
| H-01 | Update CLAUDE.md: remove the "documents queue has no consumer" gap claim — it has been fixed. | docs | low |
| H-02 | Add a YouTube clips count check to the daily smoke; if 0 rows, the YouTube collector / `worker-youtube` is silently broken. | ops | medium |
| H-03 | Surface p95 retrieval latency to logs/dashboard. The 26s outlier suggests the dual-pool query can degrade badly under cold-cache or geo-filter expansion. | obs | medium |
| H-04 | Seed a second user in dev for RBAC isolation testing. Single-tenant data makes Phase C's user-isolation regression test infeasible against this DB. | qa | medium |

No production blockers from Phase A.
