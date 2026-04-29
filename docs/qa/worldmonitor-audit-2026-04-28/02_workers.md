# 02 — Worker + queue topology (Step 2)

**Verdict: FAIL — BLOCKER (Groq API key invalid; CM LLM tasks no-op).**

## Worker fleet (confirmed running)
6 Celery workers + Beat + uvicorn:

| Worker | Queues | Concurrency | Status |
|---|---|---:|---|
| worker-collectors | collectors | 1 | active |
| worker-social | social | 2 | active |
| worker-youtube | youtube | 1 | active |
| worker-documents | documents | 2 (prefetch=1) | active ✓ |
| worker-nlp | nlp | 4 | active |
| worker-relevance | relevance, brief | 4 | active |
| beat | — | 1 | active |

## Broker topology
- Broker: PostgreSQL via `sqla+postgresql` (no Redis dependency).
- Result backend: `db+postgresql` → `celery_taskmeta` table.
- Backed by `kombu_message` + `kombu_queue` tables in postgres.

## Beat schedule — CM tasks (all wired, contradicting Phase-1 hypothesis)
| Task | Cadence | Queue |
|---|---|---|
| `tasks.cm.tag_stance` | every 5 min | nlp |
| `tasks.cm.extract_speakers` | every 10 min | nlp |
| `tasks.cm.cluster_issues` | every 2h + daily 03:00 | nlp |
| `tasks.cm.score_dissent` | daily 04:00 | nlp |
| `tasks.cm.generate_counter_narratives` | daily 05:00 | nlp |
| `tasks.cm.score_promise_status` | daily 06:00 | nlp |
| `tasks.cm.refresh_risk_window` | every 6h | nlp |
| `tasks.cm.backfill_newspaper_sentiment` | daily 01:30 | nlp |
| `tasks.cm.refresh_issue_hourly` | every 30 min | social |
| `tasks.cm.refresh_voice_share` | every 6h | social |
| `tasks.cm.compute_exploitation_index` | every 2h | social |
| `tasks.cm.refresh_constituency_heatmap` | daily | social |

**Plan was wrong** about no CM Beat schedule. Schedule is wired and
firing — see logs sample at 11:30:39 — but tasks are no-op'ing
because of the upstream Groq failure (below).

## CRITICAL — Groq API key invalid (D-8)

From `docker logs rig-backend --since 2h`:
```
2026-04-28 11:30:40,812 stance classify failed (Groq connection error on all attempts) — recording unknown
2026-04-28 11:30:44,931 speakers extract failed (Groq API error: Error code: 401
   - {'error': {'message': 'Invalid API Key', 'type': 'invalid_request_error',
                'code': 'invalid_api_key'}})
2026-04-28 11:30:48,517 stance classify failed (Groq API error: Error code: 401 - …)
2026-04-28 11:31:00,680 stance classify failed (Groq API error: Error code: 401 - …)
2026-04-28 11:31:02,601 Task tasks.cm.tag_stance[...] succeeded in 21.9s: {'articles': 60, 'posts': 60}
```

**Implications:**
- `tasks.cm.tag_stance` "succeeds" (returns counts) but every internal
  scoring call gets a 401, so the upsert writes `stance='unknown'`,
  `party_kind=NULL`. This matches DB state: 99% of stance rows
  un-state-scoped, party_kind=neutral default.
- `tasks.cm.extract_speakers` "succeeds" but produces near-zero
  quotes (`{'quotes': 1}` in the visible log line).
- `tasks.cm.score_dissent` reads from `cm_spokesperson_quotes` joined
  to `cm_issues` — sparse data → no candidate pairs → 0 dissent rows.
- `tasks.cm.generate_counter_narratives` calls Groq for each of the
  top 5 hostile issues → every call fails → 0 rows. (See
  `backend/tasks/cm/counter_narrative_task.py` lines 30+: relies on
  `generate_for_issue()` from `nlp/cm/counter_narrative.py`.)
- `worldmonitor_router._generate_summary()` for the briefing also
  calls Groq → telangana briefing summary will be `null`.

**Root cause:** `GROQ_API_KEY` env var is invalid or expired. The
`tasks.reset_groq_keys` daily Beat task at 00:05 didn't help —
suggests no fallback keys are configured, or the rotation list is
empty.

**Fix (out of scope):** rotate the key. `groq_client.py` was
modified in this branch — verify it still reads `GROQ_API_KEY` from
env and that the env is set in `infrastructure/docker-compose.yml`
or `.env`.

## Task error tolerance (graceful degradation works)
Logs show stance failures don't crash the task — they record
`'unknown'` and continue. That's good defensive coding (the task
won't backlog), but it means the CM page silently shows degraded
content with no user-facing signal. **D-9 (HIGH):** add a health
endpoint or banner that surfaces when LLM-backed CM data is stale.

## celery_taskmeta inspection
`SELECT FROM celery_taskmeta WHERE name LIKE 'tasks.cm.%'` returns
0 rows. Either:
- task `ignore_result=True` is set on CM tasks (likely — they're
  fire-and-forget batch jobs)
- result backend is db+postgresql but tasks set
  `task_ignore_result=True` globally

This isn't a defect — just means we can't use `celery_taskmeta` to
verify CM task history; rely on logs.

## Defects
| ID | Sev | Title |
|---|---|---|
| D-8 | **BLOCKER** | Groq API key returning 401 — every CM LLM task no-ops |
| D-9 | HIGH | No surface signal for stale/failed CM data — page silently shows defaults |
| D-10 | LOW | `celery -A backend.celery_app inspect active/registered` "no nodes replied" — sqla broker doesn't support broadcast; document workaround |
