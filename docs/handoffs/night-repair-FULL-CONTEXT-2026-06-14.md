# RIG Surveillance — Night-Repair Janitor: FULL CONTEXT & HANDOFF

**Audience:** any chat picking up this work cold. Read top-to-bottom once; after that use it as a reference.
**Last updated:** 2026-06-14. **Author:** DB/engine chat (Claude Code on the Hetzner box).
**One-line status:** the nightly LLM story-repair "janitor" + its quality gate are BUILT, CALIBRATED,
and a confirming cross-family dry-run is GREEN; the janitor is currently **DISABLED** (kill-switch on),
awaiting the final arm/no-arm call + a schedule change (03:30 → 23:15 UTC).

---

## 0. TL;DR — what's done, what's pending

**Done & live (build-dark):** the first real repair batch is applied to the `_v8` keeper — **9 clean
splits → 52 `night-repair-v8` clusters** (9 parents + 43 children). Fully reversible. Product is
unaffected (it reads OLD).

**Done & validated:** detector (Step 1b), action layer (Step 2), writer (Step 3, reversible),
quality gate (Gate B/C), the nightly orchestrator, cross-family direct-vote (gpt-oss + local qwen2.5),
single-vote-defer, embedding eject pre-gate. Confirming dry-run (NSUS=120) GREEN.

**Pending decisions (the open work):**
1. **ARM call** — flip the kill-switch to go live nightly (analytics' final call).
2. **Reschedule** the cron 03:30 → **23:15 UTC** (ingestion trough; avoids matview/e2scrub collisions).
3. **Gate A** (golden/recall backstop) — harness is in `rig-news`, not on the box → analytics runs it
   after the first armed night; auto-wire later.
4. **do-not-resplit list** — `3d6422b7` (football fixtures) repeatedly lands a marginal partition →
   caught + rolled back nightly (safe but wasteful).
5. **Re-enrich scoping** — orchestrator runs `story_enrich_v8 PHASE=all` (heavy) → scope to touched.

---

## 1. The system (context)

**RIG Surveillance** = multi-pillar OSINT intelligence aggregator, **India/Telangana political focus**.
FastAPI + Celery backend, Postgres 16 + pgvector. Pillars: Articles, Clips (YouTube), Cuttings
(newspapers), Threads/Signals (social), Documents, Brief, Analyst.

**Two backends on Hetzner:** `osint-backend` (the night-desk product, desk.rig360media.com) and
`rig-backend` (ingestion + ALL the clustering/NLP work described here).

**The `_v8` story-clustering keeper** (what this work mutates):
- Tables: `analytics.story_clusters_v8`, `analytics.story_cluster_members_v8`, `analytics.story_edges_v8`.
- `run_id = 1781406460`.
- Built by `cluster_job_7` (igraph-Leiden over `labse_embedding_v4`, CAND_COS=0.80, θ=0.668, refit
  scorer `edge-fit-report-2026-06-03-refit.json`) → `story_loader` → giant-split discriminator
  (θ_jaccard=0.195, GENERIC_DF_MIN=54).
- **BUILD-DARK:** the product reads OLD (`public.event_clusters`/`story_threads` or `story_*_old`) via
  the `OSINT_STORY_SOURCE` kill-switch. So **every `_v8` write is invisible to users** until a separate
  product-side flip. This is why the janitor can run on `_v8` with no user impact.
- **Parachutes (do not drop):** `story_*_job7`, `story_*_old`.

---

## 2. Access & infrastructure (how to operate)

- **SSH:** `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154`
- **Code is bind-mounted:** `/root/rig/scripts` → `/app/scripts` and `/root/rig/backend` →
  `/app/backend` inside `rig-backend`. Edits to `/root/rig/...` are live immediately (no rebuild).
  **Do NOT `git commit` into `/root/rig`** — the git index is shared across concurrent sessions.
- **Run a script:** `docker exec [-e VAR=val ...] rig-backend python /app/scripts/maintenance/<x>.py`
- **DB (psql):** `docker exec rig-postgres psql -U rig -d rig -c "<sql>"`
- **DB (python in container):** `psycopg2.connect(host='rig-postgres',dbname='rig',user='rig',password='')`
- **All janitor scripts:** `/root/rig/scripts/maintenance/` (= `/app/scripts/maintenance/`).
- **Logs:** `/root/rig/logs/night_repair_*.log`

### The LLM pool (`backend/nlp/groq_client.py`) — important subtleties
- Unified pool is **LOCAL-PRIMARY**. `FAST_MODEL = QUALITY_MODEL = "qwen/qwen3-32b"` (cloud default).
- **Local Ollama** `qwen2.5:32b` at `http://172.30.0.1:11434` is the PRIMARY slot, **shared with live
  ingestion NLP**, `LOCAL_MAX_CONCURRENT=4`. CRITICAL: a local slot **always runs `_OLLAMA_MODEL`,
  ignoring the requested `model`** (~line 813). So you CANNOT get a clean per-vote gpt-oss/local split
  through the pool — both votes collapse onto local. → use **direct calls** (see §4.3).
- Keys: 21 groq (`gsk_...` plain strings in `groq_manager.keys`), 27 cerebras.
- **`gpt-oss-120b` = the headroom workhorse** (zero throttling, proven). `llama-3.3-70b-versatile`
  has the LOWEST TPD (100k/key). **Never conclude "all keys exhausted" from a 70b 429 storm** — that's
  one model. Probe per-model with `probe_llm_quota.py`.
- Direct-call endpoints: groq `https://api.groq.com/openai/v1/chat/completions` (Bearer key); Ollama
  `{base}/api/chat`.

---

## 3. Workstream A — Forward-loop hardening (DONE, UNARMED)

`forward_cluster.py` (dry-run). The hourly loop that drains the embedded-but-unclustered backlog into
`_v8` stories (JOIN existing / start NEW / WAIT). Hardened with:
- **Join corroboration** (`JOIN_MIN_CORROB=2`): a JOIN needs ≥2 edges ≥θ to the SAME story (killed the
  single-spurious-edge false joins).
- **Junk filter**: drops null/short/pure-digit/scraper-slug titles.

Validated 6/8 sample joins clean. Residual = same-sport-different-event (bi-encoder limitation) → that
is exactly what the janitor (Workstream B) cleans up. **Stays UNARMED until the janitor is its net.**
Arming = wire live writes + hourly beat (a separate go, not done).

---

## 4. Workstream B — The night-repair janitor (THE MAIN WORK)

**Specs:** `docs/plans/nightly-story-repair-pass-2026-06-14.md` (the janitor),
`docs/plans/night-repair-quality-gate-spec-2026-06-14.md` (the gate).
**Idea:** the cheap hourly bi-encoder can't fix two residual defects — false-merge (junk-glued
articles) and over-merge (one cluster = N events). An LLM reading the articles *jointly* can. The
nightly pass detects + splits/ejects, with hard safety rails, then a **deterministic** gate verifies
the LLM (not LLM-checking-LLM).

### 4.1 The pipeline (orchestrator `night_repair_nightly.sh`)
```
detect+plan → apply → quality-gate(B/C) → per-story rollback of failures → Gate A backstop → re-enrich
```
- Default cross-family votes: `VOTE_MODELS=groq:openai/gpt-oss-120b,ollama:qwen2.5:32b` (quota-free).
- **Kill-switch:** `touch /root/rig/.night_repair_OFF` (present now = disabled).
- **Auto-halt sentinel:** `/root/rig/.night_repair_HALTED` (set if Gate A regresses or >20% of a batch
  fails B/C). Resume: review/rollback, then `rm` the sentinel.
- Env: `GATE_LOG_ONLY=1` (run gate, log, no rollback — the review cycle), `SKIP_ENRICH=1`, `NSUS`,
  `VOTE_MODELS`.

### 4.2 Components (all `/root/rig/scripts/maintenance/`)
| Script | Role |
|---|---|
| `triage_v8.py` | **Step 1a** read-only suspect selection by **dominant-entity share** (max members sharing one entity / size). 1,542 stories ≥8 articles → **140 suspects** (share<0.5). Gap: suspects 0.17–0.49 vs coherent giants 0.82–0.95. |
| `night_detector_1b.py` | **Step 1b** read-only detector: Leiden sub-split (res 3.0) + cross-model 2-vote LLM judge (KEEP/SPLIT), concordant-only. Validated: every decisive verdict correct; the LLM corrects the dom-share triage BOTH ways. |
| `night_action_2.py` | **Step 2** dry-run planner (HARD-GUARDED: refuses `ACTION_ARM=1`; SELECT + JSONL only). SPLIT → children = Leiden communities @ `PARTITION_RES=1.0` (largest keeps parent id) + **embedding-gated** dust eject + caps. Emits `_action_plan_full.json` (clean, non-high-blast, 2-vote suspect splits only). Holds the **direct-vote dispatch** (§4.3) + **single-vote-defer** + **embedding eject pre-gate**. |
| `night_action_writer.py` | **Step 3** the writer. Modes: DRY-RUN / `ACTION_ARM=1` / `ROLLBACK=<batch_id>` / `ONLY_STORY` / `MAX_SPLITS`. Reversible via snapshot side-table `story_repair_undo_members_v8` + log `story_repair_log_v8`. Children stamped `algo_version='night-repair-v8'`. Rollback = **exact byte-restore** (proven). Sanitizes NUL/surrogate chars. |
| `night_repair_gate.py` | **The quality gate** (§5). |
| `verify_batch.py` | Structural self-consistency (conservation/orphans/min-child/dust → `EVAL_GATE=PASS/FAIL`). |
| `night_repair_nightly.sh` | The orchestrator (§4.1). |
| `probe_llm_quota.py`, `probe_local_vote.py`, `ingestion_by_hour.py` | Diagnostics. |

**Key planner params:** `PARTITION_RES=1.0`, `MIN_CHILD=3`, `MAX_CHILDREN=8` (>8 children = `high_blast`
→ flagged for review, NOT auto-applied), `CAND_COS=0.80` (eject gate), `MAX_SPLITS`.

### 4.3 Cross-family direct-vote (the arm-gate workhorse)
Because the pool is local-primary and overrides the model on local slots, the detector dispatches by
**prefix** in `night_action_2.py`'s `judge()`:
- `groq:<model>` → direct groq REST (uses `groq_manager.keys[0]`, a `gsk_` string).
- `ollama:<model>` → direct `{_OLLAMA_BASE}/api/chat` (172.30.0.1:11434, qwen2.5:32b).
- plain name → the pool.
Nightly default `groq:openai/gpt-oss-120b,ollama:qwen2.5:32b` = genuine **cross-FAMILY 2-vote, ZERO
cloud TPD** (dodges qwen3 exhaustion entirely).

### 4.4 Safety rails (all real, all tested)
- **Single-vote-defer:** a split reaches the writer plan only if ≥2 models actually voted (under quota
  throttle, no corroboration → defer, don't act).
- **Embedding eject pre-gate:** "dust" = structural isolation (no ≥MIN_CHILD graph community) ≠ semantic
  outlier. Dust with cosine-sim ≥ 0.80 to the keep-child is **reattached, not ejected** (kills false
  ejects at the source).
- **high_blast deferral:** >8-child splits flagged for review, not auto-applied.
- **Per-story rollback + whole-batch auto-halt + reversible undo + caps.**

---

## 5. The quality gate (`night_repair_gate.py`) — calibrated, the missing rail

Independent **deterministic** verification of the LLM's actions (the discriminator run *as a verifier*):
- **Gate B (PRIMARY):** mean pairwise cross-child top-5 entity Jaccard **< θ_keep (0.195)** → children
  genuinely distinct → split valid. **≥ 0.195** → children still share a core → over-split → roll back.
- **Gate C:** ejected article cosine-sim to post-eject parent centroid **< CAND_COS (0.80)** → valid
  eject; **≥ 0.80** → it belonged → false eject → roll back.
- **Gate A (BACKSTOP):** golden(134)/recall(20) via `eval-clustering.cjs` (in **rig-news**, NOT on this
  box) — recall drop >1pt = fail → whole-batch halt. Run externally by analytics.
- **UNVERIFIABLE** (J=None, entity-sparse children): roll back (can't confirm) but **NOT counted toward
  the halt-rate** (avoids spurious halts).
- Modes: default = calibrate on `BATCH_ID`; `FORCE_SPLIT=<sid>` = bad-case test; `SWEEP=1` =
  PARTITION_RES sweep; `GATE_EVAL=1` = emit `ROLLBACK_STORY <id>` lines + `GATE_RESULT PASS|FAIL_SOME|HALT`.

**Calibration result (measure-first, batch 1781442293):**
- θ=0.195 **validated by a clean gap:** real piles 0.022–0.138; force-split coherent controls 0.23–0.30.
  Both-ways proven (passes piles, fails force-split coherent stories).
- Gate C caught 2 false dust-ejects (bf9ea20b, sim 0.82) → root-caused → embedding pre-gate added.
- **PARTITION_RES locked at 1.0** (sweep: 0.8/1.0 tied at J≈0.07 / 0 dust; ≥1.2 degrades).

---

## 6. Current state (exact)

- **`_v8` keeper:** batch `1781442293` applied = **9 clean splits → 52 `night-repair-v8` clusters**
  (9 parents + 43 children). All pass Gate B. Live in `_v8`, build-dark.
- **2 historical false-ejects** (bf9ea20b) sit in backlog; self-heal via the forward loop. Left as-is
  (didn't nuke a good split for 2 articles).
- **Janitor DISABLED:** `/root/rig/.night_repair_OFF` present. Cron installed but no-ops.
- **Confirming cross-family dry-run (NSUS=120) GREEN:** 8 splits → 6 PASS / 1 FAIL (`3d6422b7` marginal
  0.226) / 1 UNVERIFIABLE; fail_rate 12% < 20% = `FAIL_SOME` (per-story rollback, no halt); 0 ejects;
  no crash; full batch byte-rolled-back.
- **Undo tables:** `analytics.story_repair_log_v8` (+ `story_repair_undo_members_v8` snapshot). 9 open
  log rows = the live good splits.

---

## 7. Open work / what to do next

1. **ARM (analytics' call):** if go → `rm /root/rig/.night_repair_OFF`. Runs nightly via cron.
2. **Reschedule 03:30 → 23:15 UTC.** WHY: 03:30 was arbitrary AND congested — the `*/30` matview
   refresh fires at every :00/:30 (two cron lines), `e2scrub` runs 03:10 daily / 03:30 Sundays, and
   03:30 UTC = 09:00 IST = morning news PEAK (the 4090 + DB are busiest, contending with live NLP).
   Data (processing/hr, 3d): trough **23:00 UTC (419) = 04:30 IST**; 03:00 UTC = 1176 (~3× busier);
   peak 12:00 UTC = 2444. `:15` dodges the matview `:00`/`:30` slots. → change `/etc/cron.d/rig-night-repair`
   to `15 23 * * *`.
3. **Gate A wiring:** port/wire `eval-clustering.cjs` (rig-news) to dump `_v8` membership pre/post and
   halt on recall-drop >1pt. Until then analytics runs it manually after the first armed night.
4. **do-not-resplit list:** stories that repeatedly fail Gate B (e.g., `3d6422b7` football) → stop
   re-proposing them each night (avoid churn). Small addition to the planner.
5. **Scope re-enrich:** orchestrator runs `story_enrich_v8.py PHASE=all` (all stories, heavy) → scope to
   the night's touched stories (writer already marks them stale by deleting their
   `story_enrichment_status_v8` rows).
6. (Separate) **Arm the forward loop** — it now has its net (this janitor).

---

## 8. Commands cheat-sheet

```bash
SSH:           ssh -i ~/.ssh/rig_hetzner root@178.105.63.154
Disable:       touch /root/rig/.night_repair_OFF
Arm:           rm   /root/rig/.night_repair_OFF        # cron then runs nightly
Reschedule:    printf '...\n15 23 * * * root /root/rig/scripts/maintenance/night_repair_nightly.sh\n' > /etc/cron.d/rig-night-repair

# Manual confirming dry-run (gate logs, no rollback), then it self-rolls-back at the end of YOUR session:
mv /root/rig/.night_repair_OFF /root/rig/.night_repair_OFF.bak
GATE_LOG_ONLY=1 NSUS=120 SKIP_ENRICH=1 /root/rig/scripts/maintenance/night_repair_nightly.sh
mv /root/rig/.night_repair_OFF.bak /root/rig/.night_repair_OFF
# then roll back the dry-run batch (get batch_id from the log line "batch_id=..."):
docker exec -e ROLLBACK=<batch_id> rig-backend python /app/scripts/maintenance/night_action_writer.py

# Roll back ONE story:        add  -e ONLY_STORY=<story_uuid>
# Run the gate on a batch:    docker exec -e BATCH_ID=<id> rig-backend python /app/scripts/maintenance/night_repair_gate.py
# Force-split bad-case test:  docker exec -e FORCE_SPLIT=<coherent_story_uuid> rig-backend python /app/scripts/maintenance/night_repair_gate.py
# PARTITION_RES sweep:        docker exec -e SWEEP=1 rig-backend python /app/scripts/maintenance/night_repair_gate.py
# Per-model LLM headroom:     docker exec rig-backend python /app/scripts/maintenance/probe_llm_quota.py
# Logs:                       /root/rig/logs/night_repair_*.log
```

---

## 9. Gotchas / rules (will bite you otherwise)

- **`_v8` writes are build-dark** (product on OLD) and fully reversible. Parachutes `story_*_job7` /
  `story_*_old` intact. Don't drop them.
- **Don't `git commit` into `/root/rig`** (shared index across sessions).
- **`uuid[]` reads back as a STRING** with the default psycopg2 cursor — use `unnest()` in SQL or parse
  the `{...}` string. (Caused cosmetic count artifacts before; data was always correct.)
- **Leiden partition is node-order-sensitive** (seed=42 but order-dependent): a split that's clean in
  one ordering can be marginal in another. That's WHY the gate evaluates the **actual applied children**,
  and why the planner emits the exact member→child assignment (`_action_plan_full.json`) for the writer.
- **LLM pool is local-primary and overrides the model on local slots** → for a deterministic per-vote
  model, use the `groq:` / `ollama:` direct-call prefixes (§4.3).
- **Never infer "all LLM keys exhausted" from a `llama-3.3-70b` 429 storm** — it's the lowest-TPD model;
  probe per-model.
- The janitor uses the **local 4090 (shared with live ingestion NLP)** for the qwen2.5 vote + the
  re-enrich DB load → schedule at the ingestion trough (§7.2).

---

## 10. Memory pointer
The durable session memory lives in the project memory file `project_night_detector_v8.md` (indexed in
`MEMORY.md`). It mirrors this doc's facts in condensed form for cross-session recall.
