# RIG — Hetzner + Database Operations (kickoff prompt)

You operate the RIG production server (Hetzner) and its Postgres database directly. Everything
below is verified. Prefer read-only first; for writes, dry-run + make it reversible.

## Server access (Hetzner)
- SSH: `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154`
- It's a Docker host. Key containers: `rig-postgres` (Postgres 16 + pgvector), `rig-backend`
  (FastAPI + all Celery workers + Beat), `rig-caddy` (reverse proxy).

## Database access
- Quick SQL: `docker exec rig-postgres psql -U rig -d rig -c "<sql>"`  (add `-t` for tuples-only)
- From a script (inside rig-backend): DSN `postgresql://rig:rig@rig-postgres:5432/rig`
  (pass as `-e DATABASE_URL_SYNC=...`).
- Serving/read-only role is `analytics_user` (read on public.*, RW only on the `analytics` schema).
  Use the `rig` superuser only for ops, never wire it into a serving app.

## Code & deploy model (IMPORTANT)
- `rig-backend` **bind-mounts** `/root/rig/backend -> /app/backend` and `/root/rig/scripts -> /app/scripts`.
  So editing files under `/root/rig/...` changes the running code (no image rebuild). `/app/docs` is
  NOT mounted (write outputs under `/app/scripts/...` to persist on the host).
- A fresh `docker exec python ...` process picks up edits immediately; long-running Celery workers
  need a restart to reload a module.
- The `/root/rig` **git index is SHARED** across sessions — edit working files, but do NOT `git commit`.
- **Safe deploy pattern for any edited .py:**
  1. `scp` the new file to a candidate path (e.g. `/root/rig/scripts/foo_cand.py`)
  2. `docker exec rig-backend python -m py_compile /app/scripts/foo_cand.py` (syntax check)
  3. back up the original (`cp foo.py foo.py.bak-YYYYMMDD`), then `mv` the candidate over it.

## Data model (the live "v9" clusters live in `_v8`-suffixed tables — naming quirk)
- `analytics.story_clusters_v8` — one row per story cluster (the v9 same-event algorithm fills these).
  Useful cols: `story_id`, `representative_title`, `representative_article_id`, `last_seen_at`,
  `independent_source_count`, `article_count`, `primary_entities` (jsonb {entity:count}),
  `is_template_family`, `suppression_reason`, `redirected_to`, `is_multi_event`.
- `analytics.story_cluster_members_v8` — (story_id, article_id) membership.
- `analytics.story_facts_v8` — numeric facts per cluster (SQL-extracted; `single_source`, `citing_article_ids`).
- `analytics.story_generated_v8` — the generated ARTICLE per cluster: `headline, deck, body, topic,
  tags, strategy, status, claim_provenance, verify, word_count, fact_version`. PUBLISHABLE filter:
  `status LIKE 'PUBLISHABLE%'`; the good full articles are `strategy='source-grounded'`.
- `public.articles` — source articles (`labse_embedding_v4` vector(1024), `full_text_translated`, etc.).
- "Surfaceable" = `NOT is_template_family AND (independent_source_count>=2 OR rescued_from_story_id IS NOT NULL) AND suppression_reason IS NULL`.

## Generation pipeline
- Drain/gen: `/app/scripts/worldwide_gen_live.py` (`--surfaced N` fresh-first, `--aligned 500` front page).
  Run under the gen flock so the cron can't double-fire:
  `flock /tmp/rig-gen.lock docker exec -e USE_SOURCE_GEN=1 -e GEN_MODEL=qwen2.5:32b -e VERIFY_MODEL=llama-3.3-70b-versatile -e AB_SRC_CHARS=2200 -e 'OLLAMA_ENDPOINTS=http://172.30.0.1:11434|qwen2.5:32b' rig-backend python /app/scripts/worldwide_gen_live.py --surfaced 5000`
- Enrichment (facts): `/app/scripts/maintenance/story_enrich_v8.py` (`PHASE=all`). It TRUNCATEs the
  `story_*_v8` enrichment tables and rebuilds — pause the drain first (it reads `story_facts_v8`).
- Crons: `/etc/cron.d/rig-*` (gen every 30m, v9-forward/graph clustering, matview refresh, night-repair).

## LLM pool (shared)
- `backend/nlp/groq_client.py` — `call_groq(...)`. `GROQ_API_KEYS` (~21) + `CEREBRAS_API_KEYS` (~27),
  round-robin + cooldown + Cerebras failover. Models: writers stay LOCAL (`qwen2.5:32b`) because cloud
  free-tier TPM (6–8k) 413s the big multi-source prompts; verifier = `llama-3.3-70b-versatile` (cloud,
  has headroom; NOT `gpt-oss-120b` which sits near its 200k Groq TPD). Correct Groq Qwen id is
  `qwen/qwen3-32b` (namespaced). A single model's TPD 429 ≠ all cloud exhausted.

## Safety rails (do not skip)
- The local LLM boxes behind the pool: `:11434 -> 100.96.25.59` (32b) and `:11435 -> 100.105.228.103`
  (14b, an **in-use human workstation**). Keep load + visible-window/scheduled-task ops OFF `:11435`.
- For destructive DB ops (merges, deletes): dry-run + eyeball first, log every change to an undo table,
  and commit per-row so a failure rolls back cleanly. Recent example: `analytics.rejoin_log_v8` +
  `_rejoin_apply.py` (`APPLY=1` / `UNDO=<run_id>`).
- Don't modify the **RIG Wire** product (separate; it only reads `story_generated_v8 ⋈ story_clusters_v8`).
- `pkill -f '<pattern>'` over SSH can self-match your own command line — kill by PID or use `docker exec
  rig-backend pkill` (pkill excludes itself).

## Start by confirming
Run `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154 "docker ps --format '{{.Names}}'"` and a trivial
`psql ... -c 'select 1'` to confirm access, then tell me the task.
