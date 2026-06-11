# Operational rules — surviving the `/clear`

These are the rules that have been banked across many sessions and
**must** be honoured by anyone touching `rig-backend` / YouTube /
production DB. If a fresh session can't find them anywhere else, this
is the offline copy.

## Access

- **Hetzner SSH**: `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154`
  (use exact `-i` flag; no other key).
- **Caddy is dockerized** — `rig-caddy`, Caddyfile at
  `/root/rig/infrastructure/Caddyfile`. Not a host service.
- **DB writes** go via:
  `docker exec rig-postgres psql -U rig -d rig -c "<sql>"`.

## Restart hygiene

- **NEVER** plain `docker compose up -d rig-backend`. Always pass
  `--env-file .env.prod`, or you silently empty every `${VAR}` reference
  in compose. This was the 14:48 incident on 2026-06-04.
- **NEVER** restart `rig-backend` without warming Celery workers
  first — `process_broadcast` reliably deadlocks as the first task
  after restart (asyncio Lock + Celery prefork; root cause suspected
  in `groq_manager` module-level Lock). Warm via ping tasks before
  invoking substrate.
- **NEVER** issue a destructive git op (`reset --hard`, `push --force`,
  `clean -f`) without explicit user instruction.

## YouTube / yt-dlp / IP reputation

- **NEVER** call `yt-dlp` or `youtube_transcript_api` raw from a debug
  shell on Hetzner. Always go through `backend.tasks.newsroom._youtube_throttle`
  (`throttle_async()` / `throttle_sync()`).
- The production `youtube_collector.fetch_transcript` is safe — it has
  its own polite 1.5–3.5s delay and an `_ip_block_streak` short-circuit.
- The captions endpoint is currently IP-blocked at Hetzner. Recovery
  after a burn is 24–72h. **Do not test recovery by repeatedly probing
  yt-dlp** — that resets the clock.
- If you need a transcript urgently, use the metadata-fallback
  (`analyze_video_metadata_with_groq`) — runs on title+description only,
  no IP burn.

## Substrate / NLP pipeline

- LLM pool composition: 8 local (Ollama/Trijya) + 21 Groq + 27 Cerebras
  = 56 slots nominal. With Trijya offline + `LOCAL_LLM_ENABLED=0` set,
  effective pool is 48 (cloud only).
- `tasks.process_nlp_batch` runs every 30s.
- If substrate is stalling, check in this order:
  1. `docker exec rig-backend ps -ef | grep worker-nlp` — is the worker up?
  2. Last batch timestamp in `articles` table — `MAX(processed_at)`.
  3. Backlog count — `WHERE processed_at IS NULL`.
  4. Container logs: `docker logs rig-backend --since 5m | grep -i nlp`.
  5. LLM pool health probe.

## Concurrent sessions

- A **parallel session** is editing OSINT brief files
  (`products/osint/**`). Do NOT touch those files from this chat.
  Cross-talk from that session sometimes leaks into the SessionStart
  hook payload (filenames like `WarRoom.jsx`, `Analytics.jsx`,
  `brief_prefs.py`). If you see those in injected context, that's
  the other window — ignore them.

## Data correctness

- Every seed row must be source-verified; no fabricated handles,
  pledges, or quotes. LLM outputs need cite-ID guardrails.
- Emotion ≠ stance for measurement. Use `article_stances` for any
  negativity/bias metric; `register_emotion`'s "alarm" is event-emotion
  and skews everything negative.

## Resource discipline

- Off the 12 GiB cgroup for `rig-backend`.
- Off-peak for any bulk migrations.
- Host >600 MiB free before kicking off heavy refits (Louvain, LaBSE
  re-embed, etc.).

## Editorial / story layer

- Story-layer keeper swapped live 2026-06-03: `story_*` (34,599-story
  keeper). `story_*_old` (37,982) retained as rollback for ~1 week.
  Product tables (`public.event_clusters`, `story_threads`) untouched.
- igraph + leidenalg are baked into `requirements.txt` with a
  `_require_igraph` fail-loud guard.

## When in doubt

- `docker exec rig-backend ps -ef` — what's *actually* running.
- `docker exec rig-postgres psql -U rig -d rig -c "<sql>"` — DB state.
- `docs/qa/` — every audit and defect register from the QA pass.
- `docs/onboarding/00-README.md` — the canonical entry point for any
  session.

## Where this lives

Full memory: `~/.claude/projects/C--Users-Dell-Desktop-rig-surveillance/memory/MEMORY.md`.
This file (`05-operational-rules-banked.md`) is the in-repo mirror so
the rules survive a `/clear` even when memory isn't reloaded.
