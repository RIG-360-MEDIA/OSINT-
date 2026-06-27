# RIG — Session Handoff (2026-06-18): Clustering v9 LIVE + Forward Loop Armed

**Paste this into a fresh chat to pick up where we left off. It is self-contained — no prior context assumed.**

---

## 0. What this session shipped (the headline)

The **story-clustering system went from broken (~25% precision, auto-grouping switched OFF) to live and good
(80.7% surfaced precision), and continuous auto-grouping is now armed.** Two concrete state changes on the
production Hetzner box:

1. **One-time backfill flipped LIVE** into `analytics.story_*_v8` — `run_id=1781767919` (additive, reversible).
2. **Continuous forward loop ARMED** — cron `/etc/cron.d/rig-v9-forward`, every 6h, running the validated
   pipeline; the old over-merging cosine loop was disabled.

Everything below is the detail, the numbers, the files, the rollbacks, and what's left.

---

## 1. Access / environment

- **SSH:** `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154`
- **DB:** `docker exec -i rig-postgres psql -U rig -d rig` (Postgres 16 + pgvector)
- **Code is bind-mounted:** `/root/rig` → `/app` inside `rig-backend`. Edit on host, `docker exec rig-backend python /app/...` picks it up immediately (NOT baked). Do NOT `git commit` into `/root/rig` (shared index across sessions).
- **LLM nodes:** TRIJYA-7 `qwen2.5:32b` @ `http://172.30.0.1:11434`, TRIJYA-8 `qwen2.5:14b` @ `:11435` (local, **unlimited**, ~2-4s/call). Cloud Cerebras `gpt-oss-120b` (27 keys in container env `CEREBRAS_API_KEYS`, ~fast, TPD per-model/day reset 00:00 UTC). **Rule: never assume "all keys exhausted" — probe per model; local is the unlimited oracle.**
- Keeper tables = `analytics.story_clusters_v8` / `analytics.story_cluster_members_v8` (suffix `_v8`). The front-end (night-desk) reads these.

---

## 2. The problem & root cause (proven, not guessed)

Grouping articles so each cluster = ONE real event. It failed two ways: **over-merge** (different events in one
pile) and the **auto-grouping was paused** since Jun 17 (the old loop made a 14,893-article "Iran" mega).

**Root cause (measured, twice):** embedding cosine + entity-overlap CANNOT separate same-event from
same-topic in dense news. The FIFA World Cup = a near-clique (every match article linked via high cosine +
shared "Messi/FIFA" entities). **Resolution is a DEAD lever** — precision stayed flat ~60% across Leiden
RES 1.0→2.5, biggest cluster 174→167. The over-merge is in the EDGES (dense topic-cliques), not Leiden
chaining. **Only an LLM reading the content separates "same tournament" from "same match."**

---

## 3. The pipeline that fixed it (in order)

Scripts live in `/root/rig/scripts/maintenance/`:

1. **`cluster_v9.py`** — smart sorter. Template filter → ANN candidates (cos≥0.68) → GBM same-event edge model
   (`_sameevent_gbm.pkl`; feats cos/title-trgm/gap/shared-clean-entity/jaccard/shared-numbers/IDF) →
   confident-merge / confident-no / **gray→LLM** cascade → Leiden. Gray judge runs on LOCAL nodes. Emits
   `_fwd_run.csv` + `_fwd_run_edges.csv`. **Result: biggest cluster 173 (no megas) vs the old 14,893.**

2. **`_v9_purity_split.py`** — THE fix for the dense-clique over-merge. For each cluster, anchor on the
   max-degree hub, LLM-judge every member vs hub (cloud `gpt-oss-120b`, sharp prompt with a tournament/series
   clause + article LEADS), eject different-event members to singletons. **Lifted intra-precision 25%→62%→80%.**
   Writes `analytics._v9_members_pure` + rewrites the CSVs.

3. **`_v9_recall_refine.py`** — purity ejected ~half (2,882); this recovers genuine sub-events. Re-judge ONLY
   ejected↔ejected candidate edges event-precise (cloud) → Leiden → **recovered 979 members into 238 real
   sub-clusters** (e.g. the "Norway fans escalator" trio kicked out of the FIFA pile).

4. **`_v9_recall_tighten.py`** — 2-of-2 consensus. A SECOND independent model (local qwen-32B) re-votes on the
   recovery edges; keep only where BOTH agree. Drops borderline regroupings; keeps clean ones (944 grouped).

5. **`_v9_golive.sh`** — applies the result additively to a target keeper. Rebuilds guard mappings
   (`forward_safe_target.py`: anti-mega SIZE_NET≥2000 + entity-spread ≥3 distinct clean dominants +
   attach-coherence cos≥0.85), then `additive_merge.sql` (INSERT-only, dedup on article_id, run_id-tagged,
   transactional). Prints its own rollback command.

**Orchestration / validation scripts:** `_v9_stitch_clone.sh` (clone-first validate on `_v8copy`),
`_v9_restitch_pure.sh` (re-stitch from pure CSVs + gate-c), `_v9_gatec.py` (the hard gate: intra-precision via
local-32B judge + attach over-merge proxy), `_v9_res_probe.py` (the resolution sweep that proved resolution is dead).

---

## 4. The numbers (all measured on the box)

Three operating points were measured (intra-precision = % of random within-cluster pairs that are truly same-event):

| Config | Intra-precision (ALL new clusters) | Recall (singletons) |
|---|---|---|
| A — purity only | 80.0% | 7,505 (least) |
| B — purity + 1-vote recall | 72.7% | 6,587 (most) |
| **C — purity + 2-vote recall (SHIPPED)** | 74.7% | 6,622 |

**The number that decided it = SURFACEABLE precision** (≥3 independent sources = what users actually see):
**80.7%** (121/150). The all-cluster 74.7% is dragged down by tiny 2-4 article recovered sub-clusters that
**never surface** (they fail the ≥3-source guard). So shipped = full recall + 80.7%-clean surfaced stories.

**Direct eyeball of the live page** (17 stories read, big + small): 15 clearly one-event-each; the FIFA World
Cup correctly split into per-match stories (Portugal-Congo, Messi/Argentina, England-Croatia all distinct);
no blobs (biggest surfaced = 114). Titleless-article contamination = only 3/304 clusters (1%) / 62/2,488
members (2.5%) — a separate small data-quality issue (title extraction), not a clustering flaw.

**~80% is the practical CEILING** of single-vote hub-purity. Getting to >90% needs an edge-level rebuild
(route ALL high-entity-overlap pairs through the LLM at edge-formation time) — a multi-hour build, NOT done.

---

## 5. What is LIVE right now

- **Backfill:** `run_id=1781767919` in `analytics.story_*_v8`. +10,423 members (303,733→314,156, all distinct =
  no dupes), +7,250 clusters (304 surfaceable), 0 new megas, 0 phantoms, 0 reassignments (INSERT-only).
- **Rollback the backfill:**
  ```
  docker exec -i rig-postgres psql -U rig -d rig -c "DELETE FROM analytics.story_cluster_members_v8 WHERE run_id=1781767919; DELETE FROM analytics.story_clusters_v8 WHERE run_id=1781767919;"
  ```

- **Continuous forward loop ARMED:** `/etc/cron.d/rig-v9-forward`, **every 6h at 00/06/12/18 UTC**, runs
  `/root/rig/scripts/maintenance/_v9_forward_cron.sh` = the full chain (cluster_v9→purity→recall→tighten→golive),
  additive to live `_v8`, log `/var/log/rig-v9-forward.log`.
  - **Kill-switch:** `touch /root/rig/.v9_forward_OFF` (tested — clean skip).
  - **Lock:** `/tmp/.v9_forward.lock` (no overlapping runs).
  - **Runaway tripwire:** a run producing a ≥1000-article cluster auto-engages the kill-switch.
  - Reversible per run_id (each cycle prints its run_id; delete to undo).
  - cluster_v9 gray = LOCAL; purity/recall = cloud-first + local fallback.
  - **The OLD cosine cron `/etc/cron.d/rig-forward` (every 20min) was COMMENTED OUT — do NOT re-arm it; it is the
    one that made the Iran mega.** It used a different kill-switch `.forward_OFF` (left set).
  - First manual cycle was kicked at 08:07 UTC 2026-06-18 to prove it end-to-end.

- Backstop: the nightly janitor `/etc/cron.d/rig-night-repair` (03:30) still splits piles
  (`night_repair_nightly.sh`, kill-switch `.night_repair_OFF`).

---

## 6. Other things done this session (context)

- **Uttarakhand news supply fix:** repaired ~27 dead/real district feeds + 9 Amar Ujala desks; down-tiered
  fake-local (Times Now/India TV "Uttarakhand" → tier 3); **fixed a system-wide DirectRSS bug** (httpx blocked
  by Cloudflare on small WordPress feeds → added feedparser/urllib fallback in `direct_rss_collector.py`).
  Volume ~35/day → 294/90min genuine-local.
- **Merge-back payoff sim:** folding under-merged fragments = modest gain (+79@0.90 / +298@0.85 on ~5,030 base),
  mostly wire-dup, NOT a multiplier. Needs the anti-mega + entity-spread guards.
- **Ranking-engine DB answers** (for the front-end ranking chat): future `published_at` 0.1% (clamp suggested),
  `geo_primary` 30% null, clustering lag confirmed (now fixed by this work), `topic_category` taxonomy (15
  values, NO `EDUCATION`, SOCIAL is a catch-all), `entities_extracted` shape, `source_tier` (1=best).
  File: `C:\Users\Dell\Desktop\uttrakhand-live-frontent\RANKING_ENGINE_DBCHAT_ANSWERS.md`.
- **Gray/verify LLM routing:** kept the proven cloud-strong-first (`gpt-oss-120b`) + local fallback pattern;
  `gpt-oss-120b` needs `max_tokens≥1500` + `reasoning_effort:"low"` or it returns empty.

---

## 7. What's PENDING / next (your call)

1. **First forward-loop cycle result** — was running at handoff time; check `/var/log/rig-v9-forward.log` tail
   for `v9-forward done run_id=... members_added=... biggest_new_cluster=...`.
2. **Efficiency follow-up (not urgent):** each loop run RE-clusters the whole 1-day window (LLM-costly even in
   steady state; additive dedup only ADDS new articles). A true **incremental engine** (process only newly-
   collected articles, attach to existing _v8 clusters) would cut cost ~10x. Design, don't rush.
3. **Push precision >80% (optional, big):** edge-level rebuild — 2-vote LLM at edge-formation on all
   high-entity-overlap pairs. Multi-hour. Only if 80.7% surfaced isn't enough.
4. **Titleless-article cleanup:** ~2.5% of surfaced members have no extracted title (foreign-language title
   extraction gap) — a data-quality fix in ingestion, unrelated to clustering.
5. **Content-gen** (`/etc/cron.d/rig-worldwide-gen`, every 30min → `story_generated_v8`) will pick up the new
   surfaced clusters automatically; spot-check it keeps up.

---

## 8. Foot-guns (do NOT do)

- Do NOT remove `.forward_OFF` or re-enable `/etc/cron.d/rig-forward` — that arms the OLD cosine over-merging
  loop (Iran-mega maker). The v9 loop is the replacement.
- Do NOT run two beat/forward loops at once (double-fire). The v9 loop has its own lock; respect it.
- Do NOT `git commit` into `/root/rig` (shared index). Edit files, don't commit.
- Do NOT call yt-dlp / transcript-api raw from a Hetzner shell (burns the YouTube IP reputation) — unrelated
  pillar but a standing rule.
- The big `14,893` Iran cluster in `_v8` is PRE-EXISTING (old runaway), NOT made by this work — it's a separate
  cleanup (the janitor's job). The v9 pipeline created ZERO new megas.

---

## 9. Memory pointers (this chat's auto-memory, for continuity)

`project_clustering_v9_sameevent` (LIVE + loop armed), `project_forward_loop_rearm` (old loop SUPERSEDED),
`project_uttarakhand_supply_fix`, `project_mergeback_payoff_sim`, `reference_cluster_surfaceable_schema`
(independent_source_count = min(distinct source_id, distinct reprint_key)), `project_night_detector_v8` (janitor).
