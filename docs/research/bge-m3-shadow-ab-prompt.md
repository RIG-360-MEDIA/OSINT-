# Prompt — BGE-M3 vs LaBSE shadow A/B (de-risk before full re-embed)

> Paste into a session that has **WRITE access to the ingestion side** (`/root/rig` backend,
> the embed harness, a GPU node). This is the corpus team's track — NOT the read-only
> Ask-RIG app. Goal: decide go/no-go on re-embedding all 354K articles with BGE-M3, by
> proving it beats LaBSE **on our Telugu/Hindi corpus**, on a small sample, in ~1–2 days.

---

```
ROLE & GOAL
Our article corpus is embedded with LaBSE (column articles.labse_embedding_v4, recipe
"v4-tr-title-1024" = LaBSE on the English-translated TITLE, ~256-token cap). We are
considering upgrading to BGE-M3 (BAAI/bge-m3): natively multilingual, 8192-token context,
1024-dim dense + sparse. Re-embedding all ~354K docs is a multi-day run, so FIRST prove
BGE-M3 actually wins on OUR data with a small shadow A/B. Do NOT run the full re-embed.
Produce a go/no-go recommendation with numbers.

HARD CONSTRAINTS
- SHADOW ONLY: write to a NEW side table/column. NEVER touch labse_embedding_v4 or any live
  column. (Reuse the existing analytics.embed_ab* scaffold if it fits.)
- Idempotent + resumable. Run BGE-M3 on a GPU node (TRIJYA 4090), not the CPU box.
- Apples-to-apples: BOTH models must search the SAME fixed document pool (see Step 1).

STEP 1 — Build a self-contained A/B set (fair haystack + queries)
  1a. QUERY SET: sample ~60 story clusters from analytics.story_clusters_v8 with
      article_count BETWEEN 4 AND 12 AND independent_source_count >= 3, representative_title
      NOT NULL, is_template_family=false, suppression_reason IS NULL. DELIBERATELY oversample
      Telugu/Hindi: aim for ~40% of clusters where the representative or members are te/hi
      (the moat is cross-lingual, so weight the test toward it). Each cluster's
      representative_title = one query; its member article_ids = the relevant set.
  1b. HAYSTACK: the union of all those clusters' members + ~8,000 random DISTRACTOR articles
      from the clean set (substrate_status='ok' AND NOT is_duplicate AND
      labse_embedding_v4 IS NOT NULL), mixed languages. Freeze this ~10K id list — both
      models embed exactly these, and retrieval is ONLY within this pool (so the comparison
      is embedding-quality, not corpus-size).
  1c. Persist the query set (query, relevant_ids, lang) and the haystack id list.

STEP 2 — Compute BGE-M3 embeddings for the haystack (shadow)
  - Model: BAAI/bge-m3 via FlagEmbedding (or sentence-transformers). Dense output = 1024-dim.
    Normalize embeddings. NO instruction prefix needed for BGE-M3 (unlike E5).
  - RECIPE (this is the real test — BGE-M3's edge is reading more, natively): embed the
    NATIVE-language text = title + lead (lead_text_original; fall back to a body truncation),
    NOT the English translation, NOT title-only. Truncate to ~1024 tokens.
  - Also embed a second variant = native TITLE-only, so we can separate "model gain" from
    "more-text gain".
  - Store into a shadow column/table keyed by article_id, e.g. vector(1024). Batch on GPU;
    log throughput (docs/sec) so we can extrapolate the full-run ETA accurately.

STEP 3 — Head-to-head retrieval eval (same metrics as products/ask-rig/eval/run_eval.py)
  For EACH query, retrieve top-20 from the 10K haystack by COSINE in each model's space
  (10K is small → brute-force cosine, no HNSW needed):
    - LaBSE arm: query embedded with LaBSE (same recipe as v4); search labse_embedding_v4.
    - BGE-M3 arm (x2 recipes): query embedded with BGE-M3 (raw query text); search the
      bge native-title+lead column, and the bge title-only column.
  Compute, per arm: hit@10, recall@10, recall@20, MRR. Break out a CROSS-LINGUAL slice
  (non-English queries, and English queries whose relevant docs are te/hi). Report a
  per-language table (en / te / hi).

STEP 4 — Decision gate (be strict; the full run costs 1–2 weeks)
  GREEN-LIGHT the full BGE-M3 re-embed ONLY if, vs LaBSE:
    - cross-lingual recall@10 improves by >= +5 points (this is the whole point), AND
    - overall MRR or recall@10 improves meaningfully with NO regression on English.
  If BGE-M3 wins only on English, or ties cross-lingual → STAY ON LaBSE (not worth it).
  Also state which RECIPE won (native title+lead vs title-only) — that becomes the production
  recipe, and the query embedder in Ask-RIG must match it exactly.

STEP 5 — Deliverable (write to docs/research/bge-m3-ab-results.md)
  - The numbers table (LaBSE vs BGE-M3 x2), with the per-language breakdown.
  - Measured GPU throughput (docs/sec) → extrapolated full-354K-run ETA.
  - A clear GO / NO-GO recommendation + the winning recipe + storage delta
    (354K x 1024 x 4 bytes ≈ 1.4 GB vectors + HNSW).
  - If GO: the migration plan (new vector(1024) column, shadow backfill, HNSW
    m=16/ef_construction=200, then cutover + tell Ask-RIG to switch its query embedder).

GOTCHAS
- The query embedder MUST match the doc recipe/model, or cosine is meaningless.
- BGE-M3 is natively multilingual → embed ORIGINAL text; do not translate first (that was a
  LaBSE-era workaround).
- Don't build a full HNSW for the A/B — brute-force cosine over 10K is fine and exact.
- Keep the live pipeline untouched; this is purely additive/shadow.
```
