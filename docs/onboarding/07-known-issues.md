# 07 - Known Issues

> **TL;DR.** Recurring frustrations grouped as **open**, **partial
> mitigation in place**, or **resolved 2026-05-28** (today's session
> fixed several). Each entry: symptom · root cause · current state ·
> proper fix path.
>
> Read this BEFORE re-debugging a problem. Many issues here have
> deeper context in `11-session-2026-05-28-learnings.md`.

---

## 🟢 RESOLVED in session 2026-05-28

### R1. Cerebras qwen-3-235b-a22b-instruct-2507 returned 404 model_not_found

**Status:** ✅ Fixed in D14.

**Was:** All 27 Cerebras keys started returning `404 model_not_found`
on 2026-05-27 because Cerebras retired that dated tag. Substrate ran
on Groq + Ollama only, missing the Cerebras lane entirely.

**Fix:** Updated `_GROQ_TO_CEREBRAS_MODEL` map in `groq_client.py` to
point `qwen/qwen3-32b` → `zai-glm-4.7` (one of the two available
free-tier Cerebras models). Plus `reasoning_effort:"none"` (R3 below).

**Lesson preserved at:** `05-llm-infrastructure.md` critical-knowledge
section, `11-session-2026-05-28-learnings.md` lesson #1.

### R2. ~25% silent article-loss to Cerebras truncation

**Status:** ✅ Fixed in D15.

**Was:** When Cerebras returned truncated/malformed JSON, the parser
returned None and the article was silently dropped. Net ~25% of
drained articles lost.

**Fix:** Wrapped `call_groq` + JSON parse in 2-attempt loop in
`groq_semantic`. On parse fail attempt 1, log INFO and re-loop (pool
rotates to next slot, usually a different provider). Net loss rate
now ~2%.

### R3. zai-glm-4.7 returned empty content (reasoning model)

**Status:** ✅ Fixed in D17.

**Was:** zai-glm-4.7 is a chain-of-thought reasoning model. It spent
~3,000 tokens on hidden `reasoning_content` BEFORE emitting JSON. At
max_tokens=3000, the response had NO `content` key at all.

**Fix:** Added `"reasoning_effort": "none"` to Cerebras request body
when model starts with `zai-glm`. Output dropped 3,781 → 799 tokens
per call. 5× faster, 0% truncation.

### R4. Drain double-processing same articles

**Status:** ✅ Fixed in D19.

**Was:** 4 parallel drain processes each ran `SELECT id FROM articles
WHERE substrate_status='pending' LIMIT 64` — all grabbed same 64 rows,
each called LLM on each, last writer's UPDATE wins. ~30% wasted LLM
calls.

**Fix:** Replaced fetch SQL with `UPDATE ... WHERE id IN (SELECT id
... FOR UPDATE SKIP LOCKED) RETURNING ...`. Each drain atomically
claims a distinct batch marked `substrate_status='processing'`. Other
drains skip those rows.

### R5. Substrate prompt year-bias (events tagged 2024)

**Status:** ✅ Migration 072 retroactive fix. D8 prompt-anchor still
pending for proactive fix.

**Was:** LLM defaulted event years to its training-cutoff year (2024)
when articles didn't state the year. 33% of events tagged 2024 when
actual was 2026.

**Fix:** Migration 072 added `effective_event_date` column with
4-tier rule: trust LLM if within ±365d of publish; year-correct if
month/day matches publish year within ±14d; else keep LLM date; else
fallback to publish_at. Trigger auto-populates on insert.

### R6. `location_scope` defaulted to 'country' for every row

**Status:** ✅ Migration 074.

**Was:** Substrate prompt emitted `scope='country'` for 99.97% of
locations regardless of whether the place was a city/state/country.

**Fix:** Derived scope deterministically from existing city/region/
country columns. Trigger auto-populates on insert.

### R7. Entity-type and unit duplicates

**Status:** ✅ Migration 073.

**Was:** `entity_type` had `org` / `organisation` / `organization` (3
spellings). `unit` had `year`/`years`, `dollars`/`USD`, `%`/`percent`/
`per cent`, `kilometre`/`km`, etc.

**Fix:** Single SQL UPDATE normalizing 11 unit variants and 2 entity-
type spellings.

### R8. No clean country attribution for articles

**Status:** ✅ Migration 075.

**Was:** `sources.geo_states` was a text array mixing Indian states,
country names, continents, regions, and cities. No clean "country"
field. Queries had to `unnest(geo_states)` and pattern-match.

**Fix:** Added `sources.country` (ISO 3166-1 alpha-2) and
`articles.source_country` (auto-populated via trigger from FK).
Heuristic backfill caught 666 India + 19 UK + 9 China-defense
correctly. 83 sources still 'XX' (intentional global wires).

---

## 🟡 PARTIALLY MITIGATED

### P1. Cerebras free-tier daily TPD burn during long drains

**Symptom.** A drain that starts at 09:00 UTC consumes 99.5% of the
27M-token daily Cerebras budget by ~14:00 UTC. The remaining hours
stall on 429s from every Cerebras key.

**Root cause.** Drain throughput controller knows about per-minute
rate limits (RPM/TPM) but has no concept of the per-day token budget.
Even after R3 fix (5× fewer tokens/call), heavy backfills still
exhaust by mid-day.

**Current workaround (today, 2026-05-28):** Watchdog flips drain to
`LOCAL_ONLY` when Cerebras aggregate falls below ~5% remaining. The
drain continues on Ollama (slower but unlimited) until 00:05 UTC
reset.

**Proper fix (P2 — see backlog 09-todos):** TPD-aware controller.
Track rolling 24h token consumption per provider per key. Flip to
LOCAL_ONLY pre-emptively at 70% burn, not 95%.

**Tradeoff today:** ~5h of Cerebras → 8-10h of Ollama-only. Net
drain rate drops 60/min → 25/min during the LOCAL_ONLY phase.

### P2. Drain stalls when Ollama daemon dies on TRIJYA-7

**Symptom.** Drain process alive, but `v3` count not climbing.
`OllamaCallFailed` repeated in log.

**Root cause variants:**
- Ollama daemon crashed on Trijya (rare since 2026-05 reinstall)
- Tailscale connection between Hetzner and Trijya dropped

In LOCAL_ONLY mode (P1's mitigation), there's no cloud fallback, so
the drain just retries Ollama forever.

**Current workaround:** Operator notices and either restarts Ollama
on Trijya OR manually clears `LLM_LOCAL_ONLY=0` to let pool fall
back to cloud.

**Proper fix (P1):**
- Watchdog should detect "drain alive but v3 not climbing for 10+
  min" and try Ollama health-check; flip to cloud fallback if
  Ollama unreachable.
- Add Tailscale-up healthcheck to backend startup.

### P3. Worker-collectors backed-up queue accumulates stale tasks

**Symptom.** Queue depth on `collectors` climbs to 800+ messages.

**Root cause.** `worker-collectors` was `concurrency=1` originally;
bumped to 3 in D44. Still possible for a 30-60min RSS scrape to
block subsequent enqueues during the same window.

**Current workaround.** `celery purge -Q collectors -f` then re-fire
canonical tasks manually.

**Proper fix.**
- Per-source timeout caps to prevent any single scrape running
  60+ minutes.
- Beat deduplication: don't enqueue new `collect_rss` if previous
  one still running.

---

## 🔴 OPEN — no mitigation yet

### O1. `semantic_repass.py` ignores `LOCAL_LLM_PRIMARY`

**Symptom.** Setting `LOCAL_LLM_PRIMARY=1` and starting the drain.
Monitoring shows traffic going to Cerebras/Groq, not Ollama —
opposite of intent.

**Root cause.** `LOCAL_LLM_PRIMARY` wired only at unified-pool entry
point. `semantic_repass.py` constructs its own provider list manually
and never consults the flag.

**Current workaround.** Use `LLM_LOCAL_ONLY=1` instead — gated at the
layer all paths eventually reach.

**Proper fix (P1 todo).** Audit every LLM-call site; route through
unified pool OR explicitly consult flag in manual provider-list
construction.

### O2. No monitoring / alerting

Every other issue in this list is "invisible until manually checked".
Failures cascade silently. First indicator is usually a user complaint
or manual SQL spot-check days later.

**Proper fix (P2 todo).** Metrics layer + email alerts to
`heretech.shodh1@gmail.com`. Auto-restart for Celery workers.
Boot-time integrity checks.

### O3. D1 reset cron broken (script-path mismatch)

**Symptom.** Daily cron at `5 0 * * *` runs but D1 reset never
happens. Articles stay at `extraction_version=3` even after the
"new prompt deploys".

**Root cause.** Cron invokes
`docker exec rig-backend python /app/scripts/d1_force_reextract.py`
but the script lives only at `/tmp/d1_force_reextract.py` on the
Hetzner host. `No such file or directory` error logged silently.

**AND even when run manually**, the script only RESETS
`substrate_status='pending'` — it doesn't enqueue the corpus pass.
Operator must then run `python -m backend.tasks.substrate.run_corpus_pass
--limit N` manually.

**Current workaround.** Today (2026-05-28) we ran both steps
manually. Daily automation is broken.

**Proper fix (P1 — see 09-todos D13).** `COPY scripts/d1_force_reextract.py`
into image via Dockerfile. Modify cron to chain reset + corpus pass.

### O4. Pool slot positional bias

**Symptom.** With LMStudio (8 slots) added, the pool rotation
disproportionately uses local + lmstudio (slots 0-15) and starves
Cerebras (slots 37-63). Even with Cerebras keys healthy, throughput
drops because cloud capacity goes unused.

**Root cause.** Slots are added local → lmstudio → groq → cerebras.
Drain semaphore=8 grabs first 8 available slots. If those are fast
(local/lmstudio), they recycle quickly and dominate rotation.

**Current workaround (today).** Disabled LMStudio (`LMSTUDIO_BASE_URL`
unset). 56-slot pool (8 local + 21 groq + 27 cerebras) rotates more
evenly.

**Proper fix.** Weighted round-robin based on observed latency, OR
interleave slot order so each provider type is sampled per rotation.

### O5. Claim embeddings (LaBSE) not being generated

**Symptom.** Only 0.96% of recent claims have `embedding IS NOT NULL`.

**Root cause.** Pipeline step has fallen out (task unregistered or
batch worker not running). Probable cause: a refactor moved the embed
step out of the substrate path but never added a separate worker.

**Current workaround.** None — semantic claim search broken, narrative
clustering doesn't work, contradiction detection broken.

**Proper fix (P1 — see 09-todos P1.4).** Find the embedding step,
restart it, backfill 23K recent claims.

### O6. Narrative pipeline scaffolded but not running

**Symptom.** `articles.narrative_frame` is 0% populated.
`article_events.event_cluster_id` is 0.2% populated.

**Root cause.** Migration 070 created the tables (narrative_clusters,
narrative_cluster_members, narrative_drafts). Code at
`backend/tasks/narrative/` Stage 0-6 is scaffolded but never wired
into a beat schedule or invoked from substrate.

**Proper fix (P2).** Wire Stage 0 (cluster assembly) as nightly beat
task. Stage 2A → 2B → 6 chain after.

### O7. India source over-representation (81%)

**Symptom.** 659 / 793 sources tagged country=IN. Pool produces
~80% India-focused articles. Coverage of US, RU, JP, FR, DE, BR,
MX, IR, SA, AE is essentially zero (these fall under "global" .com
bucket, no national-flagship per country).

**Current workaround.** None — accepted limitation.

**Proper fix (P1 — see 09-todos P1.3).** Phase 1 expansion: top 5
flagships × 20 priority countries = +100 sources. Schema ready
(migration 075 added `country` column).

### O8. YouTube IP-reputation gating

**Symptom.** YouTube transcript fetches return 429 / blocked.

**Root cause.** A debug session called `yt-dlp` /
`youtube-transcript-api` raw from Hetzner shell bypassing
`_youtube_throttle`. Burst burnt the IP reputation. Recovery 24-72h.

**Current workaround.** Wait. No manual recovery.

**Proper fix.** Already in memory: NEVER call yt-dlp / transcript-api
raw from a debug shell on Hetzner. Always go through `_youtube_throttle`.
Consider rotating egress IPs for YouTube traffic long term.

---

## 🟠 EXISTING issues from prior sessions (still real)

### E1. FreshRSS admin user wipe (2026-05-15)

Symptom and recovery unchanged. Boot-time integrity check still
pending (will be part of O2 monitoring layer).

### E2. Bulk-disable cascade (2026-04-25)

174 of 406 bulk-disabled sources re-enabled. ~232 remain. Some
recoverable, most dead. `probe_all_disabled.py` is the tool. Backlog
item P3.9.

### E3. Old Ollama install was CPU-only (~553MB)

Resolved when re-installed May 2026 with the 2GB CUDA-enabled
installer. Cautionary tale in `10-context-from-may-2026-session.md`.

---

## See also

- `docs/mistakes.md` — full incident log, chronological.
- `docs/qa/` — defect registers per pillar.
- `08-future-plans.md` — proper fixes for several items show up as
  planned work.
- `09-todos-prioritized.md` — concrete priority order.
- `11-session-2026-05-28-learnings.md` — deep dives on R1-R8 fixes.
- `docs/PAUSE_INGEST_RUNBOOK.md` — for SIGSTOP / SIGCONT collectors.
