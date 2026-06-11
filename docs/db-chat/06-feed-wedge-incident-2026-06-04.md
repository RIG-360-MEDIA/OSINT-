# Incident — Feed wedged on stale NLP backlog (2026-06-04)

## Timeline (UTC)

| Time | Event |
|---|---|
| 14:48 | `rig-backend` recreated via `docker compose --env-file .env.prod up -d --force-recreate rig-backend` (recovering from the earlier 10-min outage). |
| 15:01 | Workers boot. LaBSE loads cleanly on 4 NLP fork-pool workers. |
| ~15:03 | First `tasks.process_nlp_batch` tick pulls a freshly-collected article. Its semantic-dedup pgvector query throws (unknown root error from inside `check_semantic_duplicate`). The helper logs `"Semantic dedup check failed: ..."` and returns `None` — but **does not roll back the SQLAlchemy session**. |
| 15:03 → 17:30 | Every subsequent `await db.execute(...)` on that session raises `Can't reconnect until invalid transaction is rolled back`. Both the success-path UPDATE *and* the error-recovery UPDATE in `_process_single` are rejected. The batch wedges before reaching `logger.info("NLP batch complete: ...")`. Celery sees the task as still running; the next 30s tick dispatches a new batch that pulls the same DESC-ordered article and re-wedges. |
| 17:30 | User reports Feed showing 2h-old. Investigation. Backlog = 1,717 unprocessed; 0 "NLP batch complete" log lines in 2.5h. |
| 17:32 | **Step 1**: bulk `UPDATE articles SET nlp_processed=TRUE, nlp_confidence='substrate_v3_only' WHERE substrate_status='ok' AND nlp_processed=FALSE AND collected_at > '2026-06-04 14:50+00'`. 1,486 rows flipped. Feed-eligible-2h jumped 0 → 1,105. Newest feed-eligible: 17:27 UTC. |
| 17:33 | **Step 2**: source patch to `check_semantic_duplicate` (see below). Local + Hetzner source updated. Not yet deployed. |

## Root cause

`/root/rig/backend/nlp/nlp_embedding.py` — `check_semantic_duplicate`
shared the caller's SQLAlchemy session for its pgvector query. On any
internal exception it logged and returned `None` without
`await db_conn.rollback()`. That left the caller's session in
"InvalidTransaction" state, and every subsequent statement in
`_process_single` was rejected by SQLAlchemy with the rollback-required
error.

The poison article was at the top of the `collected_at DESC` queue, so
every fresh batch (LIMIT 50, ordered DESC) pulled the same row first
and re-wedged. The whole NLP pipeline was effectively stopped at 15:03
UTC.

## Why it wasn't caught

- The outer Celery task wraps `asyncio.run(_process_batch())` in
  `try/except` that re-raises on Exception. But the corrupted-session
  errors were caught by an INNER try/except in `_process_single` and
  logged as `Article ... failed`. So Celery never saw a "task failed"
  signal; just "task still running".
- `logger.info("NLP batch complete: ...")` was the only normal-path
  log line — and it never fired, because the batch never reached the
  return statement. Anyone looking at log volume saw it go quiet but
  no errors.
- Health checks (`/api/checks` returning 34/34 failing) were a
  downstream symptom but the dashboard didn't tie them to NLP-pipeline
  health.

## Step 1 — the unblock SQL (already run)

```sql
BEGIN;
UPDATE articles
   SET nlp_processed = TRUE,
       nlp_confidence = 'substrate_v3_only',
       topic_category = COALESCE(topic_category, 'OTHER'),
       updated_at = now()
 WHERE nlp_processed = FALSE
   AND substrate_status = 'ok'
   AND collected_at > '2026-06-04 14:50+00';
COMMIT;
```

Affected rows: **1,486**. Reverse with
`UPDATE articles SET nlp_processed=FALSE WHERE nlp_confidence='substrate_v3_only'`.

These rows still have `entities_extracted`, `register_*`,
`geo_primary`, lead text — all set by the substrate-v3 pipeline. The
fields they lack are `topic_category` (set to `'OTHER'` as fallback)
and `labse_embedding` (NULL — will be backfilled by next embed sweep).

## Step 2 — the source patch (deploys tomorrow)

`backend/nlp/nlp_embedding.py`, `check_semantic_duplicate` except block:

```python
except Exception as exc:
    logger.warning("Semantic dedup check failed: %s", exc)
    # CRITICAL: rollback the caller's session before returning. The pgvector
    # query above shares the SQLAlchemy session with _process_single in
    # nlp_processor.py; on failure SQLAlchemy marks the transaction
    # invalid, and every subsequent `await db.execute(...)` on the same
    # session raises "Can't reconnect until invalid transaction is rolled
    # back". That wedged the entire NLP batch on 2026-06-04.
    try:
        await db_conn.rollback()
    except Exception:
        pass
    return None
```

Backup on Hetzner: `nlp_embedding.py.bak-20260604-dedup-rollback`.

## What about the 267 rows still `nlp_processed=false`?

These have `substrate_status != 'ok'` so they were excluded by the
unblock SQL by design. They'll flow normally once substrate completes
them — and the NLP wedge has self-resolved as a side-effect of the
flip (the queue head is now a different, non-poison article).

## Follow-ups

1. **Tomorrow**: rebuild rig-backend image + recreate (with cold-start
   ping-warm per `05-operational-rules-banked.md`) to land the source
   patch.
2. **Investigate**: what specifically threw inside the pgvector query?
   The dedup helper's `except Exception` swallows it. Tighten to log
   `exc_info=True` for one batch to see the underlying error. Likely
   candidates: vector dimension mismatch, NaN in embedding, HNSW index
   transient.
3. **Add a Mission Control alert**: if `nlp_processed=true / collected_at`
   ratio for the last hour drops below 80%, page. Would have caught
   today's incident in minutes instead of hours.
4. **Backfill the 1,486 rows' `labse_embedding`** once the dedup patch
   is live, so they appear in semantic search / dedup downstream. A
   one-shot embedding job over `WHERE labse_embedding IS NULL AND
   nlp_confidence = 'substrate_v3_only'`.

## Why this happened "today and not yesterday"

The bug was always there. The pre-restart NLP worker had been chugging
along on a clean DESC-ordered queue where the head article happened
not to trigger the dedup exception. The 14:48 recreate gave a clean
session whose first eligible article was the one that throws. Once
that article was at the head, every batch wedged on it.

Same reason the Feed showed "2h ago" specifically: 2h is roughly the
distance between the restart at 15:01 and the moment the user opened
Mission Control.
