# Substrate / LLM throughput investigation — handoff (2026-06-26)

> Paste the kickoff prompt (bottom) into a fresh chat. This doc is the full context.

## 🔴 THE CENTRAL QUESTION (start here — everything else is secondary)

**The operator (Pranav) previously processed ~12,000 articles/day WITH EASE using
FEWER Groq/Cerebras keys than are configured now.** Today, summary coverage has
cratered (44% → 18% → 0%) and substrate is barely producing. **So the working
theory that "cloud TPD / keys are exhausted" is almost certainly WRONG or
incomplete — if fewer keys handled 12k before, keys/TPD are not the new bottleneck.**

**DO NOT assume TPD. Find what ACTUALLY CHANGED.** This is a regression hunt, not a
capacity-planning exercise. The prior assistant (me) kept reaching for "add more AI
capacity / it's the 4090 / it's TPD" and the operator correctly distrusts that.

### Hypotheses to investigate (rank by evidence, don't assume)
1. **A retry/dead-node storm is burning the budget on FAILED calls.** Observed:
   `1,140 "All connection attempts failed" in 10 min` — the pool was hammering the
   **dead 4090 endpoint** (`172.30.0.1:5001`). Each failed attempt may still count
   against rate windows / waste wall-clock, AND the retry loop may re-send the giant
   prompt. The dead-4090 entry was removed from `LMSTUDIO_BASE_URL` late in the
   session — re-measure whether that alone restored throughput.
2. **Calls-per-article ballooned.** Today an article can trigger: big extraction
   call + a 2-attempt retry (on ~46% truncation) + a dedicated-summary call +
   inline translation. That's 2–4× the calls vs a leaner past pipeline. Did the
   pipeline used to be 1 call/article? `git log` / `git blame` on
   `backend/tasks/substrate/run_corpus_pass.py` to see what changed.
3. **A NEW consumer started eating the pool.** Content-gen (`worldwide_gen`),
   broadcast, sagas, CM tasks, night-detector, etc. all share the same
   `groq_client` pool. Did one of these turn on recently and starve substrate?
   Check `groq_client` request distribution by `pillar`/`task_type` in logs.
4. **Working key count actually dropped** (keys expired/rotated/banned), so "fewer
   keys" today ≠ "fewer keys then." Count ACTUALLY-WORKING keys vs configured.
5. **The local nodes used to carry it and silently stopped.** 4090 is DOWN now;
   maybe substrate used to run almost entirely local (cloud as spillover) and the
   regression is purely "4090 died," not anything cloud. But 12k-with-fewer-keys
   suggests cloud alone *used* to suffice — so what made cloud sufficient then?
6. **Inflow grew** (50k/day before the cut) so per-article budget shrank — but the
   operator says 12k was easy, so compare the THEN inflow vs now.
7. **The giant system prompt** (`GROQ_SYS`, ~2–2.5k tokens, re-sent every call) —
   real cost, but it was presumably always large, so it explains steady-state cost,
   not a sudden regression. Verify with actual token counts from logs.

**Method:** get the GROUND TRUTH first — actual tokens/call, calls/article,
provider success vs failure rate, and the per-task pool distribution — from the
LIVE logs. Don't theorise before measuring.

---

## Product / system overview
- **RIG Surveillance** — multi-pillar OSINT intelligence aggregator. Customer-facing
  product = **night-desk** at `https://desk.rig360media.com` (React SPA). Persona in
  use: `maverick092005+telangana@gmail.com` (Telangana / CM **Revanth Reddy** desk;
  72-entity watchlist). Pages: Home, War Room, Analytics, Dossier, Map, Dispatch, Ask.
- **Pipeline:** collect (RSS/HTML/YouTube) → **substrate extraction** (the LLM 10-field
  JSON: article_type, primary_subject, summaries{preview,snippet,executive},
  locations, events, quotes, actor_stances, claims, numbers, register, +
  english_translation for non-English) → NLP (spaCy NER + topic LLM) → LaBSE embedding
  → clustering → relevance scoring → brief/pages.

## Infrastructure & access
- **Hetzner host:** `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154`.
  - SSH was **rate-limiting/throttling** under rapid connections this session — space
    out calls; prefer ONE ssh with a bash heredoc (`ssh ... bash <<'EOF' ... EOF`)
    over many small ssh calls. `curl`/`wget` in the Bash tool are blocked by a hook —
    use `docker exec rig-backend python3 -c "import httpx; ..."` instead.
- **Containers:** `rig-backend` (FastAPI + ALL celery workers + Beat — the ingestion
  side; code BIND-MOUNTED from `/root/rig/backend`, edits live on restart),
  `osint-backend` (night-desk API; **BAKED** image `infrastructure-osint-backend`,
  deploy = edit in-container + `docker commit` + restart), `rig-postgres`
  (`docker exec rig-postgres psql -U rig -d rig`), `rig-caddy`, `rig-askrig`.
- **LLM pool** = `backend/nlp/groq_client.py` `_UnifiedPool`. Providers: `lmstudio`
  (TabbyAPI on the TRIJYA GPUs), `groq` (qwen3-32b, multiple org keys), `cerebras`,
  `local` (Ollama, disabled). Config via `infrastructure/.env`:
  `LMSTUDIO_BASE_URL`, `GROQ_API_KEYS`, etc.
- **GPU nodes (Tailscale):**
  - **TRIJYA-7 / RTX 4090** (`100.96.25.59`, sshuser, key `/root/.ssh/trijya4090_ed25519`):
    **CURRENTLY DOWN — operator says it can't come back right now.** Was 8 TabbyAPI
    slots via autossh `172.30.0.1:5001 -> :5000`.
  - **TRIJYA-8 / RTX 4070** (`100.105.228.103`): **UP**, 2 TabbyAPI slots via
    `172.30.0.1:5000`. Qwen3-14B-exl3.

## What this session changed (so you know current state)
- **Embedding:** fixed (dedicated CPU `worker-embed` on `embeddings` queue + a 4090
  GPU LaBSE backfill server — backfill DONE; embed coverage 52%→~87%). See memory
  `project_embedding_throughput_fix`.
- **Source cut** ~50k→~27k/day (`sources.is_active=false`, snapshot table
  `sources_deactivated_20260625`, reversible).
- **Dropped dead `youtube_clips` v1 table** (backup `/root/backups/youtube_clips_v1_drop_20260626.sql.gz`). Live clips table = `youtube_clips_v2` (healthy, 253/24h).
- **night-desk frontend** (bundle deployed to `/root/rig/night-desk-dist`): error
  boundary, picsum→branded placeholder, Analytics guards, map labels, dead War-Room
  buttons removed.
- **Caddy** (`/root/rig/infrastructure/Caddyfile`, backup `.bak-pre-cache`): HTML
  `no-cache` + assets `immutable` (no hard-refresh needed).
- **osint-backend (baked, committed):** `/report/send` open-relay closed (always self),
  district gate fail-closed (404), **ticker persona-filtered** (primary-subject-first,
  `routers/ticker_router.py`).
- **CURRENT OPEN ISSUE — substrate/summary regression:**
  - Tried removing `summaries` from `GROQ_SYS` to force a dedicated summary call →
    **BACKFIRED** (0% summaries + throughput crash) → **REVERTED** (backup
    `/root/rig/backend/tasks/substrate/run_corpus_pass.py.bak-pre-summarysplit`).
  - Dropped dead 4090 from `LMSTUDIO_BASE_URL` (backup `infrastructure/.env.bak-pre-4090drop`)
    + recreated rig-backend → dead-node 429/connection-failures dropped (442→40), but
    **substrate then showed `processed=0`** (drain fires but finds nothing / nothing
    reaching substrate stage; last processed 17:19 UTC). **Verify the pipeline isn't
    actually stalled.**

## Validated facts (don't re-test)
- **Google Translate via `deep_translator.GoogleTranslator` WORKS from Hetzner** for
  Telugu, Hindi, Italian, Turkish, Russian. It already populates `lead_text_translated`
  (`backend/nlp/nlp_language.py:detect_and_translate`, `TRANSLATION_MAX_CHARS=4500`).
  (Earlier confusion: the IP-block is YouTube-specific, NOT Google Translate.)
- **Cloudflare Workers AI is NOT viable for this corpus:** m2m100 has **no Telugu
  support**; `llama-3.1-8b` **hallucinated fabricated content** on Telugu. Account id
  `8003bce1e0cf1823c69001b0100d239a` exists; token was created but is unused — drop it.
- **Summary root cause (confirmed):** of articles missing a summary, **100% still have
  their topic** → the extraction call succeeds but the long summary field is
  **truncated out** of the big JSON (the model hits its output cap). It's an
  extraction/prompt issue, NOT a backlog. Coverage swings with LLM availability.
- **Designs discussed (NOT yet shipped):** translation→Google (off the LLM); 2-call
  substrate split (extraction / summaries); relevance-gate (only enrich India/targets);
  prompt-caching / prompt-trim. The 2-call split and the summary-split both ADD LLM
  calls — risky while the pool is the bottleneck. The translation-off-LLM REMOVES work.

## Other known issues (background, not the focus)
- **District tagger DEAD since 2026-06-11** (`article_districts` frozen,
  `mv_district_news_volume_24h` empty) → Dispatch "DISTRICTS: 0", Map coloring stale.
- LLM-bound field coverage is thin (geo 42%, summary ~44% baseline, stance 32%, quotes
  24%) — all capacity/extraction-bound.
- ~73% of substrate AI spend goes to **non-India** articles that don't surface for the
  Telangana customer (relevance-gate candidate).

## Key files
- `backend/tasks/substrate/run_corpus_pass.py` — substrate extraction. `GROQ_SYS`
  (~L590), `GROQ_SYS_NON_ENGLISH` (~L641, adds english_translation),
  `groq_semantic` (~L727, 2-attempt retry loop), `process_one` (~L864), the
  dedicated-summary block (~L982), `_dedicated_summary` (~L97).
- `backend/nlp/groq_client.py` — `_UnifiedPool`, `get_slot`, provider routing, key mgmt.
- `backend/nlp/nlp_language.py` — Google translate path.
- `backend/celery_app.py` — task routes + Beat schedules (incl. `substrate_drain`).
- Memory dir: `C:\Users\Dell\.claude\projects\C--Users-Dell-Desktop-rig-surveillance\memory\`
  — read `MEMORY.md`; relevant: `project_tabby_local_llm`,
  `project_trijya7_4090_hardware_fault`, `project_substrate_llm_starvation`,
  `project_embedding_throughput_fix`.

## First moves for the new chat
1. **Measure ground truth** (one ssh heredoc): tokens/call + calls/article + per-task
   pool distribution + provider success-vs-fail rate, from `rig-backend` logs (last
   30–60m). Confirm or kill the TPD theory with numbers.
2. **Verify substrate isn't stalled** (`processed=0` — is it caught up or broken?).
3. **`git log -p`** on `run_corpus_pass.py` + `groq_client.py` to see what changed
   since the "12k was easy" era.
4. Only then decide the fix. Bias toward changes that REMOVE work (translation→Google),
   not ADD calls.
