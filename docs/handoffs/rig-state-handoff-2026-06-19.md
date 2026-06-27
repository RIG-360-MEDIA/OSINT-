# RIG — Full State Handoff (2026-06-19) for the next chat

**Paste into a fresh chat. Self-contained. Covers: clustering (rebuilt this session, with measured quality),
the live system, content-generation state (the NEXT focus), and the roadmap.**

---

## 0. Access / environment

- **SSH:** `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154`
- **DB:** `docker exec -i rig-postgres psql -U rig -d rig` (Postgres 16 + pgvector)
- **Code:** bind-mounted `/root/rig` → `/app` in container `rig-backend` (edit on host, runs live; do NOT `git commit` into `/root/rig` — shared index).
- **LLM:** local (unlimited) TRIJYA-7 `qwen2.5:32b` @172.30.0.1:11434 + TRIJYA-8 `qwen2.5:14b` @:11435; cloud Cerebras `gpt-oss-120b` (27 keys, env `CEREBRAS_API_KEYS`). Rule: never assume "all keys dead" — local is the unlimited oracle.
- **Corpus:** 332,263 embedded articles, 64 days (2026-04-16 → 06-19), ~5,191/day. Keeper = `analytics.story_clusters_v8` / `story_cluster_members_v8` (~314k members). Edge graph = `analytics.story_edges_v8` (434,088 edges).

---

## 1. CLUSTERING — what was rebuilt this session (the big work)

**Problem at start:** story-clustering was broken — giant blobs (one 14,893-article "Iran" mega) + auto-grouping was off. Quality ~25% (3 of 4 co-grouped articles were NOT the same event).

**Root causes (measured, not guessed):**
- Embedding cosine + entity overlap CANNOT separate same-event from same-topic (dense topic-cliques, e.g. all FIFA matches link).
- **Resolution is a dead lever** (precision flat ~60% across Leiden RES 1.0–2.5).
- The over-merge is in the EDGES, not Leiden chaining. **Only an LLM reading content separates "same tournament" from "same match."**

**The pipeline built (`/root/rig/scripts/maintenance/`):**
1. `cluster_v9.py` — smart sorter: template filter → ANN candidates (cos≥0.68) → GBM same-event edge model (`_sameevent_gbm.pkl`) → confident/gray/no cascade (gray → LLM judge) → Leiden. Has `NEW_ONLY` mode (incremental).
2. `_v9_purity_split.py` — **THE quality lever:** per cluster, anchor on the hub, LLM-judge each member vs hub, eject different-event ones. Lifted precision **45%→73%** (and the windowed pipeline 62%→80%). Without it, clustering is ~45–62%.
3. `_v9_recall_refine.py` + `_v9_recall_tighten.py` — recover ejected real sub-events (2-of-2 model consensus).
4. `_v9_golive.sh` — additive live write (INSERT-only, run_id-tagged, reversible).
5. `_v9_graph_incr.py` + `_v9_graph_loop.sh` — **the live incremental engine** (see §2).
6. Measurement: `_v9_gatec.py`, `_gi_prec_set.py`, `_gi_precision.py`.

**MEASURED QUALITY (all on real DB, LLM-judged intra-cluster precision = "are two co-grouped articles the same event"):**
| Config | Precision | Note |
|---|---|---|
| Old baseline (`cluster_job_7`) | **~25%** | the broken state |
| Backfill (cluster_v9+purity+recall), surfaced ≥3-src | **80.7%** | shipped live, run_id 1781767919 |
| Graph loop, last-day live | **85.7%** | 0 articles in megas |
| Graph placement (with purity) | 73–75% | all-placements |
| Multi-cycle drift sim | 79→81→81% | **NO DRIFT** (cyc1 improved to 84.5%) |

**Eyeball check (8 random live graph clusters, read by hand):** 7/8 clean one-event clusters (Ebola outbreak, ED liquor-scam arrest, Russian-artist murder, Uttarakhand cabinet, Cocktail-2 review, etc.) — **multi-source AND cross-language** (English+Hindi+Telugu+Tamil correctly co-grouped). 1 had blank-title articles (a data-quality/title-extraction issue, NOT a clustering flaw). **85% holds up under inspection — good enough to build on.**

---

## 2. WHAT IS LIVE NOW (clustering)

- **Backfill:** run_id `1781767919` in `_v8` (+10,423 members, 80.7% surfaced, additive). Rollback: `DELETE FROM analytics.story_cluster_members_v8 WHERE run_id=1781767919; DELETE FROM analytics.story_clusters_v8 WHERE run_id=1781767919;`
- **Graph loop (incremental, LIVE):** `/etc/cron.d/rig-v9-graph` every 30 min → `_v9_graph_loop.sh` → `_v9_graph_incr.py` on live `_v8`. NEW unclustered articles → edges (ANN+GBM+LLM gray on LOCAL) → affected subgraph (EXCLUDES ≥2000 megas) → Leiden re-carve → anchor-ID inheritance (attach to existing clean cluster, or new id) → **purity net** → additive write. Kill `touch /root/rig/.v9_graph_OFF`; lock `/tmp/.v9_forward.lock`; runaway tripwire (≥1000 → auto-kill); MAXN=800/run (bounds backlog drain). Attaches ~150/run; reversible per run_id.
- **Nightly reconcile:** `/etc/cron.d/rig-v9-forward` (the old windowed pipeline) demoted to **23:00 daily**.
- **Janitor:** `/etc/cron.d/rig-night-repair` 03:30 (splits piles, `night_repair_nightly.sh`).
- **OLD cosine loop `/etc/cron.d/rig-forward` is DISABLED** (commented). Do NOT re-arm — it made the megas.

**Cluster makeup (who made the live clusters):** `cluster_job_7` (OLD) ~185k clusters (94%) + both megas (14,893 + 13,824); `cluster_v9` (backfill) 10,624; `graph-incr` (loop) 2,340; `night-repair` 455. **Old algo stopped ~June 17** (last cluster Jun 17 10:04); graph loop took over Jun 18–19.

---

## 3. KEY FINDINGS / LESSONS (so the next chat doesn't relearn them)

- **Purity net is the quality lever** (not resolution, not the size cap). The ≥2000 anti-mega cap is just a SAFETY RAIL — quality = the LLM same-event judge + purity, measured by intra-precision (~85%).
- **Graph engine routes AROUND megas** (excludes ≥2000) → new articles form clean clusters, never join the mega. That's why last-day = 0 in megas.
- **Clustering a WIDE window OVER-MERGES.** cluster_v9 is tuned for ~1-day same-event density. A 3-day window → biggest cluster 721, precision 50%. **Always cluster/reconcile in ~1-day slices.**
- **4-day window = gap/dormancy rule, not an age cap.** An event active every ≤4 days chains for weeks (cluster keeps full history); >4 days quiet → new article starts fresh.
- **Graph is ~2× cheaper than windowed at scale** (skips re-confirming old articles + 5× less purity), NOT 7× — recent batches are dense (near-dups).
- **Two asyncio.run() in one script → recreate the Semaphore inside the 2nd coroutine** (binds to its loop).
- **MEGA POLLUTION (the remaining cleanup):** before the graph loop, 52% of recent (3-day) articles were stuck in legacy megas → live grouping of recent news measured only 17%. The graph loop fixed FORWARD (last-day now 0% megas) but can't rescue the ALREADY-stuck ones (it only touches unclustered articles). The 185k old clusters + megas remain untouched.

**Re-assigning reconcile (built, clone-validated, NOT applied):** `_v9_reconcile_apply.py` + `_v9_reconcile.sh` — snapshot→delete→re-insert window articles into fresh clusters; anchor-ID-stable; reversible (`_reconcile_snap_<run_id>`). Pulled 5,621 articles OUT of megas on a clone, BUT only 50% precision because the 3-day window over-merges. **Rejected by its own clone-gate.** Fix = day-by-day (1-day slices). Not yet built.

---

## 4. CONTENT GENERATION — the NEXT focus (current state)

**Live and producing:** `analytics.story_generated_v8` = **3,884 generated stories, 3,458 refreshed in last 2 days** (newest today).
- Cron: `/etc/cron.d/rig-worldwide-gen` */30 → `docker exec rig-backend python /app/scripts/worldwide_gen_live.py --aligned 500` → `story_generated_v8` (flock `/tmp/rig-gen.lock`).
- Generator: `scripts/_worldwide_gen_sample.py::run_story` (gen_hybrid: A-first prose → verify → B → extractive; `gpt-oss-120b` prose, `qwen3-32b` verify/Guard-C). Live wiring: `scripts/worldwide_gen_live.py`.
- Cache table `story_generated_v8` fields: headline, deck, body, topic, tags[], strategy, status, guard_c (jsonb), verify (jsonb), claim_provenance (jsonb), fact_version, updated_at, run_id.
- Design intent (from the work order): NYT/Atlantic-style headline (verified as a claim) + 1-line deck + article + topic/tags; 3-tier cache (headline+deck for surfaced set; full article when a story ENTERS the shown set; on-demand long-tail); single-source → NO synth (stub); regenerate only on MATERIAL change (fact_version); per-claim provenance trace; Guard-C reject metric.

**What the next chat should do for content-gen** (verify first, then build):
1. **Inspect actual generated output** (read 5–10 `story_generated_v8` rows: headline/deck/body) — judge publish-quality by eye, like we did for clusters. Don't trust status flags.
2. Measure the **Guard-C reject rate** on the now-clean `_v8` clusters (expected to drop vs the old 58% now that giants are split).
3. Confirm the **3-tier cache** + single-source-stub + fact-version regen logic are actually wired (not just intended).
4. Note: content-gen now sits on the **clean graph clusters** (~85%) — so its inputs are far better than when the megas dominated. Re-generate for the new clean clusters.

---

## 5. ROADMAP (user's chosen order)

1. **Content generation** ← NEXT (this is what the user wants now). Verify + improve the gen pipeline on the clean clusters. See §4.
2. **Saga / story-thread layer** — "show me the whole Iran war, start to end." `public.story_threads` (7,409 rows) EXISTS but is **stale (last updated 2026-05-25) and blobby (biggest thread 29,798 articles, built old centroid way)** — needs rebuilding on the clean event clusters with entity + LLM gating + a freshness loop. EVENT clusters = atoms (done); SAGA = chains atoms across time (to build).
3. **Full 64-day forward replay** → rebuild ALL history clean into a new keeper `_v10` (day-by-day, ~2–2.5 days resumable background compute, ~700k LLM calls), validate (zero megas, ~80%), swap `_v8→_v10` (reversible), retire old. This is the proper way to clean the 94% old-algo base + megas — NOT "one giant graph" (over-merges) and NOT "combine old+new" (inherits megas).

---

## 6. FOOT-GUNS

- Do NOT re-enable `/etc/cron.d/rig-forward` or remove `.forward_OFF` — that's the old cosine blob-maker.
- Do NOT cluster/reconcile a wide (>~1 day) window — it over-merges.
- Do NOT "combine" old clusters into new — rebuild clean (replay) instead.
- Do NOT `git commit` into `/root/rig` (shared index).
- The 14,893 / 13,824 megas are PRE-EXISTING old-algo output — the new pipeline created ZERO megas.
- Memory: see `project_clustering_v9_sameevent` (full detail), `project_forward_loop_rearm` (superseded), `project_substrate_llm_starvation` + `project_worldwide_build` (content-gen background).
