# Handoff — Clustering rebuild + Uttarakhand supply (2026-06-18)

Paste this into the new chat. It is self-contained: access, what was built, measured results, current
live state, and the exact remaining build. Everything below is on the Hetzner ingestion box.

## 0. Access & environment
- SSH: `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154`
- DB: `docker exec -i rig-postgres psql -U rig -d rig` (db/user `rig`). Keeper tables live in schema `analytics`.
- Code is **bind-mounted**: host `/root/rig` → container `/app` (`rig-backend`). Edit on host, run via
  `docker exec rig-backend python /app/scripts/...`. **Running celery workers cache code — `docker restart
  rig-backend` to deploy to the live workers.** A fresh `docker exec python ...` always picks up new code.
- LLM nodes (no token limit): **TRIJYA-7 `qwen2.5:32b` @ http://172.30.0.1:11434** (also has
  `qwen2.5-coder:32b`), **TRIJYA-8 `qwen2.5:14b` @ :11435**. Cloud (Groq/Cerebras) keys exist but TPD is
  PER-MODEL/day (resets 00:00 UTC) — `scripts/maintenance/probe_all_keys2.py` probes them; `_llm_state.py`
  probes local+cloud. **The local 32B is the unlimited judge — use it for any in-loop AI judging.**

---

## 1. THE CORE PROBLEM (measured, not assumed)
The story-clustering (folders) over-merges AND under-merges. Root cause, proven on 1,081 LLM-judged pairs
(`analytics._eval_pairs`): **embedding cosine cannot separate same-event from different-event at the
boundary — same-event median cos 0.867 vs different-event 0.860.** One cosine threshold therefore fails both
ways. The discriminating signals are: shared CLEAN entities (same≈1 vs diff≈0), time gap (same≈0.5d vs diff≈3d),
shared specific numbers, title trigram.

---

## 2. WHAT WAS BUILT (all in `/root/rig/scripts/maintenance/` unless noted)

### A. Ground-truth eval harness
- `_clust_eval_build.py` / `_eval_expand.py` — LLM-judge same-event pairs (intra/cross/wild). Output:
  `analytics._eval_pairs` (a_id,b_id,kind,same_event), `analytics._eval_tpl` (template labels).
- `_eval_fit.py` — fits the same-event model + reports held-out P/R + the LLM-gray cascade analysis.

### B. The smart "same-event" model — `_sameevent_gbm.pkl`
GradientBoosting on 9 features: `cos, title_trgm(tt), gap_days, shared_clean_entities(shent), jaccard(jac),
shared_numbers(shnum), shared_entity_IDF(shidf), max_IDF(maxidf), min_entity_count(minent)`. CLEAN entity =
exclude global hubs (DF≥1200 in 45d). Feature importance: **gap 0.46 / cos 0.23 / title 0.16** (entities help
most when IDF-weighted). Saved `/app/scripts/_sameevent_gbm.pkl`.

### C. The new clusterer — `cluster_v9.py`
Pipeline: TEMPLATE filter → ANN candidate pairs (cos≥0.68) → **EDGE CASCADE** (GBM proba ≥HI=0.80 merge /
<LO=0.25 no / gray→LLM judge on local qwen2.5:32b) → Leiden. Writes `analytics._v9_members(article_id,
cluster_id)`. Env: WINDOW_DAYS, CAND, LO, HI, LLM_GRAY, GRAY_CONC.

### D. Template classifier — `_tpl_classifier.py` → `_tpl_clf.pkl`
Char-ngram TF-IDF + LogisticRegression on titles (no LLM at inference). **NOTE: weak (P0.80/R0.22) because
templates are only ~4.7% of the corpus — a MINOR lever, not the big win the original plan assumed.** cluster_v9
currently uses a regex `TPL` heuristic, not the .pkl — integrating the .pkl is optional/low priority.

### E. Splitter (over-merge safety net) — `night_repair_nightly.sh` + `night_action_2.py` (detect/plan) +
`night_action_writer.py` (apply, reversible) + `night_repair_gate.py` (Gate B/C). **Two fixes shipped this
session:** (a) `night_action_writer.apply_story` now `if len(children)<2: skip` (was IndexError-crashing on
edgeless clusters like the 14.9k Iran mega); (b) use **budget-free local votes** `VOTE_MODELS=
ollama:qwen2.5:32b,ollama:qwen2.5-coder:32b` (the default `groq:gpt-oss-120b` DEFERs everything when cloud is
TPD-tight). **ARMED nightly via crontab 03:30.**

### F. Forward-loop guards (for when the loop is re-armed)
- `forward_safe_target.py` — builds the guarded shadow→keeper merge map: **anti-mega** (skip target if
  `is_multi_event` OR `article_count≥2000`) + **entity-spread** (skip merged groups with ≥3 distinct CLEAN
  dominant entities).
- `additive_merge.sql` — now dedups (NOT EXISTS on article_id) + `BEGIN/COMMIT` atomic.
- `worldwide_forward_cron.sh` — `story_loader` now stamped `ALGO_VERSION=cluster_job_7/v4/leiden-res1.0/
  rescue-v1/_v8` (was the phantom `pf-v1/tg-v3`); calls `forward_safe_target.py` before the merge.
- `worldwide_forward_stitch.py` recompute — reprint_key input fixed to `left(lead_text_original,200)`
  (byte-exact to `story_loader.py:92`).

### G. Uttarakhand supply (separate task, DONE) — `public.sources`
12 dead feeds repaired; 9 Amar Ujala district desks added (domain-suffix convention `amarujala.com/<city>`:
uttarakhand/haridwar/nainital/rishikesh/roorkee/pithoragarh/almora/kotdwar/chamoli); 3 TASK-2 feeds (Devbhoomi
Khabar, Hill Vani, Mussoorie Times); fake-local (Times Now/India TV/News Nation Uttarakhand) → `source_tier=3`.
**System-wide collector fix:** `backend/collectors/direct_rss_collector.py` now has a **feedparser/urllib
fallback** when httpx 403/0-items (Cloudflare blocks httpx but not urllib) — feed failures 13→1. Backup:
`public._uk_sources_bak_20260618`. Schema gotchas: `geo_states` is `text[]` (use `array_to_string(..,',') ILIKE`),
`domain` is UNIQUE, tier 1=best..3=worst.

### H. Content generator — `scripts/worldwide_gen_live.py`
`--aligned` mode = the front-page/candidate set (3-tier: shown→full article, single-source→stub,
long-tail→on-demand). **ARMED via crontab every 30 min.** `--backlog` (writes everything) RETIRED as wasteful.
Writes `analytics.story_generated_v8`.

---

## 3. MEASURED RESULTS
- **Same-event model (held-out test, 1081 pairs):** current cosine sorter P0.52/R0.51 → **GBM-only P0.78/R0.73
  → GBM+LLM-gray cascade P0.92/R0.89.** This is the proof the design works.
- **cluster_v9 end-to-end on a real window:** intra-cluster precision (over-merge) **v8 ~25-28% → v9 ~56-62%**
  (judged by local qwen2.5; the cheap judge caps it below the 0.92 held-out — a stronger gray judge closes the gap).
- **Splitter (batch 1781748896, reversible):** 17 piles split → Gate B/C rolled back 7 (12% < 20% halt ceiling,
  incl. correctly catching a coherent j=0.528 over-flag) → **10 kept = 64 coherent child clusters** (verified
  single-event: Putin-forum / UFC-White-House / Quetta-bombing / WorldCup-squads / Iran-sanctions).
- **UK supply:** ~35 genuine-local/day → **294 in 90 min from 21 desks** (one-time backlog catch-up; steady
  capacity now hundreds/day).
- **Gen:** 289 PUBLISHABLE, **capped by ~517 multi-event "Guard-C held" piles** (gen refuses to write one
  article for an over-merged pile → the splitter lifting this ceiling is why it matters).

---

## 4. CURRENT LIVE STATE (what is armed / running / off)
- ✅ Splitter cleanup — crontab 03:30 nightly (gated, reversible).
- ✅ Article-writer — crontab `*/30` `--aligned 500` (candidate-only).
- ✅ UK supply — fixed + DirectRSS fallback deployed (`docker restart rig-backend` done).
- ⛔ **Forward loop OFF** (`/root/rig/.forward_OFF` present, no cron) → **13,360 recent articles are queued
  UNSORTED** (embedded, recoverable — NOT lost). Deliberately NOT re-armed with the old cosine sorter (would
  re-create the over-merge).

---

## 5. THE ONE REMAINING BUILD (the real completion) — smart sorter → live keeper

**Goal:** cluster the 13,360 queued backlog (and all new news going forward) with the *smart sorter*, merged
into the live keeper `analytics.story_clusters_v8` / `story_cluster_members_v8`, reversibly.

**Plan (do on a clone first, then live):**
1. **Run `cluster_v9.py` on the backlog window** (LLM_GRAY=1, GRAY model = local qwen2.5:32b — unlimited;
   ~5/sec, so 13,360 → a few hours one-time; per-daily-window ~25 min ongoing). Output `analytics._v9_members`.
2. **Convert `_v9_members` → the forward-stitch shadow format**: populate `story_cluster_members_fwdrun` +
   mint `story_clusters_fwdrun` rows (rep title, source/indep counts via the verified reprint_key
   `LEAST(distinct source_id, distinct reprint_key)`), `algo_version=cluster_job_7/v4/leiden-res1.0/rescue-v1/_v8`.
3. **`forward_safe_target.py`** (SRC_SUFFIX=_fwdrun, TGT_SUFFIX=**_v8copy** first) — builds the guarded
   shadow→target map (anti-mega + entity-spread).
4. **`additive_merge.sql`** into the **_v8copy clone** (sed _v8shadow4→_fwdrun, keep _v8copy) → run_id-tagged.
5. **Verify on the clone:** new clusters stamped v4/_v8; max article_count unchanged (no mega re-inflation);
   0 member reassignment; 0 phantom (member-less) clusters; spot-read new clusters are single-event.
6. **If clean → repeat into live `_v8`** (sed _v8copy→_v8), reversible by `run_id` (`worldwide_forward_cron.sh
   undo <run_id>`). Then **arm a `*/30` cron** so new news clusters with the smart sorter continuously.
7. The nightly splitter + the entity-spread guard catch any residual over-merge; the gen `--aligned` cron then
   publishes the new coherent folders.

**Known caveat:** the forward dry-run earlier passed gates a/b/d but showed **gate-c ~15% over-merge on
attaches** for short/no-entity content (regional briefs, sports squad-lists). cluster_v9's edge cascade
reduces this vs the old cosine loop; the splitter is the net for the remainder. Re-measure gate-c on the
cluster_v9-fed stitch before arming live.

### Secondary / optional
- **Cross-window stitch (under-merge):** `analytics._mergeback_edges` + the cos≥0.90 + guards recipe
  (`project_mergeback_payoff_sim` memory) — modest payoff (+79–298 surfaceable), reversible. Do after #5.
- **Template classifier:** wire `_tpl_clf.pkl` into cluster_v9 (currently regex). Low priority (4.7% of corpus).
- **Throughput note:** "near-perfect end-to-end on the *entire* archive in one pass" is local-LLM-throughput
  bound (days). The practical path = the smart sorter on the live stream (above) + the nightly splitter chipping
  the old back-archive. Don't attempt a single full-corpus LLM re-cluster.

## 6. Safety rules (carried from this session)
- Every production-cluster write must be **reversible** (backup table or run_id undo) and **dry-run on a clone
  first**. Never blind-write `story_*_v8`.
- Box is **15 GB RAM** — never batch many big piles through one `docker exec` (OOM-killed rig-backend once);
  one-pile-per-process or size-aware chunking.
- Report measured numbers only; verify each feed/cluster actually produced output (no fabricated "done").
