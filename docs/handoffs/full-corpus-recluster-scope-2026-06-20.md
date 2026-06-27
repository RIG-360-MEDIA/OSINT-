# Scope: full-corpus `cluster_v9` re-cluster (2026-06-20)

**Question:** what would it take to re-cluster the *entire* corpus with `cluster_v9` (the best algo,
~80.7% surfaceable precision) instead of leaving ~89% of the keeper on old `cluster_job_7` (~25%)?

**Headline:** the clustering *compute* is cheap (~1–2 h, no LLM). The real cost is (1) the **gray-LLM
recall band** and (2) the **downstream enrichment + content rebuild** that a new cluster set forces.
The clustering is the easy 10%; the cascade behind it is the 90%.

## Measured inputs (live, 2026-06-20)
| Input | Value |
|---|---|
| Clusterable articles (v4 embeddings) | **338,412** (95% of 356,216) |
| Ingestion span (`collected_at`) | 2026-04-16 → 2026-06-19 = **64 days** |
| Daily ingest | ~6,600–12,100/day (avg ~9,400) |
| ANN method | **pgvector HNSW kNN-14** (`<=>`, `idx_articles_embedding_v4`, ef_search=120) → **linear in N**, not all-pairs |
| Models on box | `_sameevent_gbm.pkl` (GBM same-event), `_tpl_clf.pkl` (template filter) |
| Box | **4 cores, 15 GB RAM** (~8 GB free) — shared with the live pipeline |

## The four cost components

### 1. Clustering compute — CHEAP, feasible ✅  MEASURED + DONE 2026-06-20
Because ANN is kNN-14 (linear), candidate gen via HNSW, then GBM scoring, Leiden, purity-split.
- **MEASURED (run `b3sh60f4s`, full corpus, LLM_GRAY=0): ~55 minutes, zero LLM/quota.**
  338,412 articles → 1,649,561 candidate pairs → confident-merge **190,674** edges (gray band
  **733,661** skipped, confident-no 725,226) → **228,277 clusters** (199,582 singletons, biggest 982).
- Materialised into a SHADOW keeper: `analytics.story_clusters_v9shadow` (228,277 rows, with
  article_count + source_count) + `analytics.story_cluster_members_v9shadow` (329,113 rows).
  **Live `_v8` keeper untouched.**
- **VALIDATION (same-event judge, surfaceable ≥3 src, same 150 pairs):** qwen2.5:32b **76%** (114/150);
  **INDEPENDENT llama-3.3-70b (Meta) 69%** (103/150) → qwen ~7pts generous, trustworthy **~70%**, still
  ~3× the ~25% v7 floor. Surfaceable clusters: **6,930** (shadow, distinct-source≥3) vs **5,563** in v8.
- 🔑 **KEY FINDING: the 733,661-edge gray-LLM band buys only ~5 precision points (76→81%).**
  Confident-only delivers ~94% of the quality at ~0% of the LLM cost → the multi-day gray pass is NOT
  worth it; skip it or trickle incrementally (revises Phase 2 below).

### 2. Gray-LLM recall band — the EXPENSIVE, rate-limited part ⚠️
Only the ambiguous (MIDM–LO) candidate pairs go to the LLM same-event judge. This is what made the
1-day marathon run 66+ min on the local 32B before I killed it.
- Full-corpus gray ≈ 64× a 1-day window's gray edges → **~tens-to-hundreds of thousands of LLM judgments**
  (exact count from `b3sh60f4s`).
- Cost: **~tens of hours on the local 32B** (serial-ish at 12 concurrency, and it *hogs the node the live
  pipeline shares*), OR **multiple days of cloud TPD** (gpt-oss-120b/Cerebras — currently exhausted).
- **Do NOT batch it all.** Options:
  - **(a) Skip gray now** (`LLM_GRAY=0`) → confident-merge backbone: higher precision, lower recall
    (more fragments). Then let the **night-repair janitor + `graph-incr` forward loop** apply gray merges
    incrementally on a sustainable daily LLM budget.
  - **(b) Gray only on surfaceable clusters** (≥3 sources — the ones actually shown/generated) → bounds
    the LLM workload to ~tens of thousands, feasible in a budgeted cloud batch.

### 3. Downstream enrichment rebuild — the HIDDEN 10× cost 🔴
A re-cluster produces **new `story_id`s**. Every enrichment table is keyed by `story_id`:
`story_facts_v8`, `story_quotes_v8`, `story_timeline_v8`, `story_geo_v8`, `story_stance_v8`,
`story_sources_v8`, `story_enrichment_status_v8`. All of it must be **rebuilt** for ~200k new clusters
(`story_enrich_v8.py`, PHASE=structural + extraction). Facts come from `article_claims` (cheap, SQL/local),
but it's ~200k clusters of work — **hours-to-days**, and far larger than the clustering itself.

### 4. Content regeneration — story_generated_v8 🔴
Every generated article is keyed by `story_id` + `member_hash`; new clusters ⇒ **regenerate all surfaced
content**. With the *current* ledger generator that's ~LLM-bound; with the new **source-grounded** generator
(the prototype) it's heavier still. This is gated by the same LLM quota as #2. Bound it to the surfaceable
set (~5–15k clusters), not all 200k.

## Live-swap risk & reversibility
- The keeper swap is a big operation: FKs already point at `story_clusters_archive`
  (`user_story_assignments`, `chronicle_cache` — see the Chronicle mismatch), enrichment must be rebuilt,
  content regenerated. **Must be additive + reversible** (build into `*_v9shadow`, validate with the
  gate-c harness, swap behind a kill-switch with a rollback) — the same pattern the prior v9 ship used.

## Recommended phased plan (lowest risk, fastest value)
1. **Phase 1 — confident backbone (this week, ~1–2 h, no quota):** full-corpus `cluster_v9 LLM_GRAY=0`
   into a shadow keeper. Validate surfaceable precision vs the current v7-dominated keeper. This alone
   should lift most of the corpus from ~25% toward v9-confident precision.
2. **Phase 2 — surfaceable gray pass (budgeted):** run gray-LLM only on ≥3-source clusters when cloud
   quota is available (or trickle via the janitor/forward loop). Don't grind all 300k gray edges.
3. **Phase 3 — enrichment + (source-grounded) content rebuild** on the surfaceable set only.
4. **Phase 4 — reversible swap** behind a kill-switch, with the old keeper retained as rollback.

**Bottom line:** the *clustering re-run* is a 1–2 hour, no-quota job. Treating it as "the work" is the trap
— the real programme is the gray-LLM recall + the enrichment/content rebuild it forces downstream. Scope it
as a **surfaceable-first pipeline**, not a big-bang full-corpus regen.
