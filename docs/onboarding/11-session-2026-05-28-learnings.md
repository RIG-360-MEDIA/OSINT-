# 11 - Session 2026-05-28 Learnings

> **Purpose.** Permanent record of lessons, mistakes, and fixes from the
> 2026-05-27/28 marathon session (D1 SPO fix → D26 source country). When
> any of the other onboarding docs reference "see session 2026-05-28",
> this is where the details live. Append future-session-learnings as
> `12-session-YYYY-MM-DD-learnings.md` rather than overwriting this.

---

## TL;DR — what was true at session end (2026-05-28 03:30 UTC)

- **Substrate v3 fully working.** D1 SPO prompt fix → 14% predicate fill → **99% SPO completeness** today (23K claims sampled in last 6h)
- **Daily drain rate ~25-65/min** depending on cloud quota state. Free-tier Cerebras + Groq exhaust within ~5h of heavy drain. After 00:05 UTC reset they recover.
- **Trijya local LLM (4090 + qwen3:14b)** is the reliable lane. Cap is ~25-30 inferences/min for substrate prompts at this hardware. Cannot be multiplied by adding more servers (we tried both Ollama and llama.cpp — same GPU, same cap).
- **30,000+ articles processed v3** today, 0.28% failure rate, all field fill-rates 99-100% on processed rows.
- **5 migrations shipped:** 070 (narrative tables), 072 (effective_event_date), 073 (entity/unit normalize), 074 (location_scope derive), 075 (source country + article.source_country trigger).

---

## Lessons by category

### LLM infrastructure

1. **Cerebras deprecated `qwen-3-235b-a22b-instruct-2507` on 2026-05-27.** All 27 of our keys started returning 404 model_not_found on that exact dated tag. They retired it the same day we noticed. New available models on free tier (per `GET /v1/models` with our keys): `gpt-oss-120b` and `zai-glm-4.7`. Updated `_GROQ_TO_CEREBRAS_MODEL` mapping accordingly. **Don't trust dated model tags — they get retired.**

2. **gpt-oss-120b is unsuitable for substrate.** Too verbose: emits ~3,800 tokens for a substrate response that qwen3 finishes in ~2,800. Cerebras free-tier output capping at ~1,968 chars truncates it mid-JSON 46% of the time. Also **silently drops quotes entirely** (0 of 0 in head-to-head test vs qwen3's 2 quotes).

3. **zai-glm-4.7 is a reasoning model.** Without `reasoning_effort: "none"` in the request, it spends ~3,000 tokens on chain-of-thought BEFORE emitting JSON. At our max_tokens=3000, the content field is empty (no 'content' key at all in the response — only 'reasoning'). Adding `reasoning_effort: "none"` cut output from 3,781 tokens → 799 tokens, **5× faster, 0% truncation**. This was the single biggest LLM throughput win today.

4. **Same trick may work on other Cerebras reasoning models.** Tested params that DON'T work: `enable_thinking`, `thinking`, `reasoning`, `chat_template_kwargs.enable_thinking` — all return 400 invalid_request_error. Only `reasoning_effort` is OpenAI-standard and accepted.

5. **Cerebras free-tier daily TPD = 1M tokens per key.** With 27 keys = 27M aggregate. A heavy substrate drain (~30K calls × 5K tokens) burns ~150M tokens — 5× over budget. The pool keeps trying exhausted keys (no daily counter); each call wastes a round-trip. **Solution today:** none — we let it exhaust, drain rate drops, recovers at 00:05 UTC. **Future fix:** add TPD-aware probe that disables a key for the day after its TPD is exhausted.

6. **Groq has per-org TPM = 6,000 tokens/min, NOT per-key.** Multiple keys can share the same org. Hitting one key's TPM cools that key, but the org's other keys ALSO start 429-ing because they share the bucket. Our 21 Groq keys appear to span 5-7 distinct orgs (per `org_*` IDs in 429 responses). Effective Groq TPM ceiling: ~36-42K/min aggregate. Each substrate call (≈3K-5K tokens) → ~7-14 successful Groq calls/min total, regardless of key count.

7. **Cooldown window for TPM 429s should be SHORT.** Groq 429 message says "try again in 5-15s". Original 60s cooldown was 4-12× too long, kept healthy keys cold. Cut to **15s** in D14 — pool recovers fast enough to handle bursts.

8. **Ollama Windows-Service env vars require service restart.** `setx /M` persists to Machine scope but running Ollama processes don't pick up new vars. `Restart-Service Ollama` is mandatory. If Ollama runs as user-app (not service), need `taskkill /F /IM ollama.exe && Start-Process "ollama" "serve"`.

9. **Ollama NUM_PARALLEL=8 doesn't multiply throughput linearly** on a single 4090 with qwen3:14b. The GPU compute is the binding constraint, not request concurrency. With or without NUM_PARALLEL=8, we observed ~15-20s per call. **Lesson:** Setting NUM_PARALLEL high helps utilization but can't exceed GPU FLOPS for the same model. Roughly the same caps apply on llama.cpp.

10. **llama.cpp `--ctx-size` divides across `--parallel` slots.** Setting `--ctx-size 32768 --parallel 8` gives only 4096 tokens per slot. Our substrate prompts are ~4,800 tokens → every call returns 400 "exceeds available context size". Use `--ctx-size 131072` (16K per slot × 8 parallel) or `--ctx-size 65536` (8K per slot — minimum safe for our prompts).

11. **`--flash-attn` flag in llama.cpp ≥b9000 is an enum, not boolean.** `--flash-attn on|off|auto`. Bare `--flash-attn` consumes the next argument as its value and fails. KV cache quant flags (`--cache-type-k q8_0 --cache-type-v q8_0`) work as documented.

12. **GitHub releases asset naming matters.** `cudart-llama-bin-win-cuda-12.4-x64.zip` contains ONLY the CUDA runtime DLLs — NOT the llama binaries. The actual binaries are in `llama-bXXXX-bin-win-cuda-12.4-x64.zip`. Match the regex `^llama-b\d+-bin-win-cuda` not `win.*cuda` to avoid this trap.

13. **`$args` is a PowerShell reserved variable.** Assigning `$args = @(...)` outside a function is silently ignored (existing $args holds script args). Rename to `$serverArgs` etc.

14. **LMStudio integration was wired and reverted.** Added 8 client slots pointing at llama.cpp via `LMSTUDIO_BASE_URL` env var. Worked technically but didn't improve aggregate throughput because: (a) same GPU as Ollama = shared compute, (b) pool rotation became biased toward local slots starving Cerebras of attention, (c) llama.cpp's 4090 cap is ~25 calls/min, not more than Ollama's. **Decision:** keep the code path (D23), don't set the env var. Code remains as future-ready overlay.

15. **Pool rotation has positional bias.** Slots are added local → lmstudio → groq → cerebras. With drain semaphore=8, the first 8 grabs are always local + lmstudio. Cerebras (indices 37-63) gets disproportionately less attention. Currently acceptable; future fix would be weighted round-robin based on observed latency.

### Substrate pipeline

16. **D1 SPO prompt fix delivered as projected.** Pre-D1 claims had `subject_text` 100% but `predicate` 14% and `object_text` 14%. Post-D1: **99% all-three filled**. The fix was compressing 4 example claims in the prompt down to 1 minimal example + explicit 3-field schema reminder. Ollama was truncating the long prompt; compressed version stays within token budget.

17. **Substrate failure modes during the session:**
    - Cerebras qwen-3-235b 404 (model deprecated) → swap mapping (D14)
    - Cerebras gpt-oss-120b truncation 46% (verbose model) → swap to zai-glm-4.7 (D16)
    - zai-glm-4.7 reasoning consumes max_tokens (no JSON emitted) → `reasoning_effort: none` (D17)
    - Parse failure silently drops articles (was 25% data loss) → 2-attempt retry loop (D15)
    - max_tokens=5000 inflated Groq per-call TPM consumption → drop to 3000 (D18)
    - Drain race condition (multiple drains picking same articles) → `FOR UPDATE SKIP LOCKED` atomic claim (D19)

18. **`groq_semantic` retry loop pattern.** Wrap call + parse in `for attempt in range(2)`. On parse-fail attempt 1, log INFO and re-loop (pool naturally rotates slot). On attempt 2 also failing, log WARNING + return None. **Net: article-loss rate 25% → ~2%.**

19. **D1 reset script lives at `/tmp/d1_force_reextract.py` on the host**, but the daily cron at 00:05 UTC tries to invoke it inside the container at `/app/scripts/d1_force_reextract.py` where it doesn't exist. Cron has been failing silently for weeks. **Permanent fix (D13, pending):** bake script into image via Dockerfile.backend `COPY scripts/`.

20. **D1 reset is only HALF the job.** The script RESETS substrate_status='pending' but doesn't actually enqueue work. A human must then run `python -m backend.tasks.substrate.run_corpus_pass --limit N` manually. The legacy `tasks.process_nlp_batch` celery worker checks a different flag (`nlp_processed`) and won't pick up substrate-pending articles. **Permanent fix (D13):** auto-trigger corpus pass from the cron.

### Database

21. **Migration 072 — effective_event_date.** LLM extracts `event_date` from articles but defaults to its training-cutoff year (2020 or 2024) for events whose article doesn't mention a year. 33% of events were tagged 2024 when actual year was 2026. Solution: 4-tier rule populating `effective_event_date`:
    - Tier 1: LLM date within ±365 days of publish → trust LLM (44%)
    - Tier 2: wrong year but year-corrected date within ±14 days of publish → use corrected (13% — Korea ship pattern)
    - Tier 3: wrong year and correction doesn't help → keep LLM date (18% — real past/future events like Senegal-2024, Artemis-2028)
    - Tier 4: no LLM date or no publish → use `COALESCE(published_at, collected_at)` (42% — the no-date case)
    
    Trigger auto-populates on insert/update of `event_date`. Index added for fast timeline queries.

22. **Migration 074 — location_scope.** Substrate prompt was emitting `scope='country'` for 99.97% of locations regardless of whether the place was a city/state/country/continent. Derived `scope` deterministically from existing city/region/country columns: if `city` is filled → 'city', else if `region` → 'state', else if `country` → 'country', else 'unknown'. Continents (Africa, Asia, Europe, etc.) detected by text match. Migration ran into deadlock with `sync_geo_primary` trigger when done as one UPDATE — fix: batched 5K rows at a time with `FOR UPDATE SKIP LOCKED`. 259K rows updated successfully.

23. **Migration 075 — sources.country + articles.source_country.** Added ISO 3166-1 alpha-2 country code on sources (canonical) and propagated to articles via INSERT trigger. Backfilled 119K articles. Enables clean `WHERE source_country='CN'` queries instead of `unnest(geo_states[])`. **Findings exposed:** our pool is 83% India (659/793 sources). Chinese sources are 9 (all defense-only — China Daily Military, PLA Daily, Xinhua Military, etc. — NOT general news). USA, Russia, Japan, France, Germany, Brazil, Iran, Saudi have ZERO sources. Massive gap to fill via Phase 1 expansion.

24. **PostgreSQL `FOR UPDATE SKIP LOCKED` is gold for parallel workers.** Multiple drain processes hitting the same `pending` queue: each `SELECT ... FOR UPDATE SKIP LOCKED LIMIT N` atomically claims a distinct batch. Eliminates double-processing. We marked claimed rows `substrate_status='processing'` so a hard-killed drain leaves orphans that can be recovered (filter `substrate_status='processing' AND substrate_processed_at IS NULL`).

### Scraping / sources

25. **RSS source-list distribution today.** 793 sources, 550 active.
    - 81% India (national + 28 state-level tags)
    - 7% global wires (BBC, Reuters, AP, etc.)
    - 12% rest of world (UK 19, China 9 [defense-only], various African/Asian)
    - **Zero US, RU, JP, FR, DE, BR, MX, IR, SA, AE explicit national sources** — these fall under "global" (.com) bucket
    - Phase 1 expansion proposal: top 5 flagships × 20 priority countries = +100 sources, comfortably within Ollama's 24K calls/day capacity

26. **TRIJYA-7 is a Windows 11 box, not Linux.** Discovered via Tailscale status output (`tdsworks@ windows active`). All deploy scripts must use PowerShell + setx /M / Restart-Service, NOT systemd/bash. Owner is Tailscale user `tdsworks@gmail.com`.

27. **SSH access to Trijya is restricted.** Our `~/.ssh/rig_hetzner` key (and 5 other tried keys) returns "Permission denied" on Trijya. Only the Admin login (password Red@0909, per Connection_Guide.pdf) works. AI MUST NOT use the password to SSH directly — security policy. Instead: give the user a PowerShell script to paste in their already-open admin terminal.

28. **vLLM is not practical on Windows.** Officially Linux-only. Windows install requires WSL2 + CUDA-in-WSL — fragile, complex. Alternatives that DO work on Windows: LM Studio (GUI, OpenAI-compatible API), llama.cpp `llama-server.exe` (CLI, OpenAI-compatible). We chose llama.cpp via PowerShell install — fully headless-friendly.

29. **`Start-Process` to a URL fails in an SSH session** because SSH has no desktop. `Start-Process "https://...ai"` returns "operation not supported". For SSH-only Windows admin tasks, use CLI installers (Invoke-WebRequest + Expand-Archive + Start-Process to .exe), not GUI installers.

### Operations / runbook learnings

30. **Pause ingest while heavy backfill runs.** SIGSTOP the collectors worker processes (PID + SIGSTOP), not the whole rig-backend container. Beat keeps firing collect_rss every 15min but they queue harmlessly. Resume with SIGCONT. Runbook: `docs/PAUSE_INGEST_RUNBOOK.md`. Important: SIGSTOP state does NOT survive container restart — workers come back running.

31. **Hourly substrate throughput during today's drain.**
    - 17:00 UTC: 4,781 articles
    - 18:00 UTC: **10,219** (peak, Cerebras quota fresh)
    - 19:00 UTC: 6,726 (Cerebras quota draining)
    - 20:00-22:00: silent (drain stalled — D1 cron failure, then SIGSTOP, then restarting drain debug)
    - 23:00 UTC: 1,530 (drain restarted)
    - 00:00 UTC: 3,493 (after we restarted drain)
    - 01:00-03:00: 1,000-2,000/hr (max_tokens cuts + provider tuning)

32. **"3K rate" claim was wrong about D17 too.** I told the user D17 (`reasoning_effort=none`) would 5× throughput. Actual measured: parsed-success rate went 14% fail → 0% fail (quality win), but raw throughput climbed only +35% (34/min → 46/min). The GPU is the binding constraint; reducing wasted calls helps quality more than aggregate speed.

---

## What's still broken / pending

1. **D8 (pending):** Bake `article.published_at` into substrate prompt as a hard temporal anchor. Stops LLM from defaulting to 2024 when article doesn't state a year. Will eliminate the year-bias problem at the source rather than retroactive fixing via migration 072.

2. **D13 (pending):** Permanent fix for D1 reset cron. (1) Add `COPY scripts/d1_force_reextract.py /app/scripts/` to Dockerfile.backend. (2) Modify cron to auto-trigger `run_corpus_pass` after reset.

3. **Cerebras TPD-aware quota tracking.** Today's drain blew the daily token budget across all 27 keys in ~5h. Pool keeps trying exhausted keys (wasted round-trips). Future: pre-flight TPD probe + skip exhausted keys for the remainder of day.

4. **Phase 1 source expansion (100 sources × 20 countries).** Schema is ready (migration 075 added `country` column). Need: write INSERT script, test scrapability of each, enable gradually with low health score, monitor first 24h.

5. **Claim embeddings (LaBSE) backfill.** 22,866 of 23,391 recent claims have `embedding IS NULL`. Pipeline step is missing. Without claim embeddings, semantic search and contradiction detection don't work.

6. **`narrative_frame` field 0% populated.** Stage 0-6 narrative pipeline is scaffolded (migration 070) but not wired into the drain. P1 todo: run Stage 0 (cluster assembly) nightly.

7. **`event_cluster_id` 0.2% populated.** Same reason — narrative Stage 0 not running.

8. **`location_text` vs `country` mismatch in 8% of locations.** Stale data from pre-D17 extractions. One-off SQL fix queued.

9. **Documentation consolidation (this task).** 127 active docs in `docs/` is too many. Plan in `docs/DOCS_CONSOLIDATION_PLAN.md`. Action: merge dated audits, archive completed sprints, keep onboarding canonical.

---

## See also

- `02-substrate-pipeline.md` — Prompt G mechanics, D1 SPO fix details
- `05-llm-infrastructure.md` — UnifiedPool, provider failover, today's quota lessons
- `06-operations-runbook.md` — Drain commands, watchdog config
- `07-known-issues.md` — Open frustrations after this session
- `10-context-from-may-2026-session.md` — Previous session war stories
- `docs/PAUSE_INGEST_RUNBOOK.md` — SIGSTOP/SIGCONT collectors procedure
- `scripts/migrations/072-075` — Migrations applied this session
- `scripts/deploy/trijya_ollama_tune.ps1` — Windows PowerShell admin script for Trijya
