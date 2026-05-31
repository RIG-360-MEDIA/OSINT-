# 0a — Embed-at-ingest (decoupled embed lane)

**Date:** 2026-05-31 · **Owner:** database chat · **Status:** design + scaffold (NOT deployed)
**Serves:** the production clusterer (needs the vector within seconds of ingest) and
0c (re-embed must be runnable independent of the full NLP pass).

## Current state (the coupling we're removing)
- Collectors insert an article (`nlp_processed=FALSE`, `labse_embedding NULL`).
- Beat `process-nlp-every-30-seconds` → `tasks.process_nlp_batch` (queue `nlp`)
  batch-encodes LaBSE **inside the full NLP pass** (entities, topic, stance, …).
- ⇒ The vector waits behind the entire heavy NLP backlog. Re-embedding (0c) would
  mean re-running NLP. That's the coupling 0a breaks.

## Target lane
A dedicated **`embedding` queue** whose only job is: text → vector → write
`labse_embedding` + provenance. NLP no longer owns embedding.

### Options considered
- **A. Per-article task at ingest** — collector enqueues `embed_article(id)`.
  Lowest latency; most queue chatter; +1.8 GB (second LaBSE).
- **B. Dedicated high-frequency batch drain (RECOMMENDED)** — `embed_pending_batch`
  on a `worker-embedding` (concurrency=1, one LaBSE), Beat every ~15 s, drains
  `labse_embedding IS NULL AND lead present`. Batches for CPU efficiency, truly
  decoupled from NLP, ~15 s worst-case latency. +1.8 GB (box has 5 GB+ headroom;
  reaper + cgroup cap protect Postgres regardless).
- **C. Split embedding into its own fast task on the existing nlp worker** — no
  extra model copy, but embedding still competes with NLP slots ⇒ not truly
  decoupled. Rejected.

→ **Recommend B.** One open call for you: accept the **+1.8 GB** dedicated
embedding worker, or prefer C (no extra RAM, weaker decoupling)?

## Change set
1. `backend/nlp/embedding_recipe.py` — ✅ DONE. Single source of truth: `RECIPE`
   (currently V0/prod) + `build_embedding_text()`. 0a and 0c both import it.
2. `backend/tasks/embed_task.py` — ✅ DONE. `tasks.embed.embed_pending_batch`:
   select missing-vector rows → `build_embedding_text(RECIPE)` → `encode_text()` →
   UPDATE `labse_embedding`, `embedded_at`, `embedding_model`,
   `embedding_revision = RECIPE.recipe_version` (guarded `labse_embedding IS NULL`
   so it never overwrites a vector NLP wrote in the same window).
3. `backend/nlp/nlp_embedding.py` — ✅ DONE. `encode_text()` (recipe-windowed, no
   re-truncation) + `max_seq_length` set from RECIPE in `get_labse_model()`.
   Legacy `generate_embedding()` left untouched (other callers depend on it).
4. `backend/celery_app.py` — ✅ DONE. include `embed_task`; route `tasks.embed.*`
   → `embedding`; Beat `embed-pending-every-15-seconds`. (Inert until a worker
   consumes the queue — see #6.)
5. `backend/tasks/nlp_processor.py` — ⏳ AT DEPLOY (with locked recipe + test).
   Route its batch + fallback embedding through `build_embedding_text(RECIPE)` so
   NLP can't overwrite lane vectors with a different recipe post-lock; optionally
   skip re-embed when a vector already exists. Deferred because it's hot-path and
   should be verified against the *actual* locked (original-language) recipe.
6. `start.sh` — ⏳ AT DEPLOY. Add `worker-embedding` (queue=embedding,
   concurrency=1, `--max-memory-per-child=2500000`). **Edit the canonical Hetzner
   start.sh** (which has whisper + `--max-memory-per-child`), NOT the stale repo
   copy — origin↔Hetzner divergence: deploying the repo's start.sh would drop the
   whisper worker and the memory caps. Reconcile at deploy.

Block to add to start.sh at deploy:
```bash
# Dedicated embedding worker — 0a embed-at-ingest lane (one LaBSE, ~1.8 GB)
celery -A backend.celery_app worker \
  --queues=embedding \
  --concurrency=1 \
  --hostname=worker-embedding@%h \
  --max-memory-per-child=2500000 \
  --loglevel=info &
```

## Provenance / 0c linkage
`embedding_revision` stores `RECIPE.recipe_version`. 0c = one-shot re-embed of all
rows where `embedding_revision <> RECIPE.recipe_version`. Every vector is traceable
to the exact recipe that produced it.

## DEPLOY GATE (hard)
Deploying 0a rebuilds the baked `rig-backend` image. **Do NOT deploy until BOTH:**
1. **A/B embed job has finished** — a redeploy/restart now kills the running job
   inside `rig-backend`.
2. **Recipe is locked** — analytics picks the A/B winner; flip `RECIPE` in
   `embedding_recipe.py`, bump `recipe_version`. Then deploy 0a **and** run 0c with
   the identical recipe.

Until then: code is written and reviewable; nothing ships.
