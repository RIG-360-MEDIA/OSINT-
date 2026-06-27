# Ask-RIG (rig chat) — corpus / data update (2026-06-21)

Paste into the Ask-RIG session. Summarises what changed in the underlying data so retrieval
can "see further", plus the contracts for the new layers. READ-ONLY consumer (`analytics_user`).

## What changed (so you can see further)

- **Retrievable article corpus: 347,992** articles with `labse_embedding_v4` (your current hybrid base — unchanged recipe).
- **NEW synth layer — 2,713 published worldwide stories** in `analytics.story_generated_v8` (status `LIKE 'PUBLISHABLE%'`): one cited, deduped, multi-source article per news cluster (250–1,500w, sentence-case, faithfulness-verified). Best for "what's the latest on X / summarise the X situation" — a tier above raw articles.
- **NEW structured facts — 43,810 facts over 7,721 clusters** in `analytics.story_facts_v8`: corroborated numeric facts with `citing_article_ids`. Ground numeric answers here.
- **Freshness + integrity:** clusters are now (a) **de-fragmented** — ongoing stories stay ONE pile (cross-window re-join every 6h), (b) **fresh-first generated**, and (c) **2-source clusters now have facts** (surfacing bar lowered 3→2). **556 fresh (<48h) clusters.** So "latest" queries return current, non-duplicated results.

## Data contracts (all in `analytics`)

**`story_generated_v8`** — synth stories: `story_id` (uuid, → `story_clusters_v8`), `headline`, `deck`,
`body` (full prose), `topic`, `tags` (text[]), `claim_provenance` (jsonb `{claim -> [source ids]}` for cites),
`word_count`, `strategy` (`source-grounded` = the richest), `status`, `updated_at`.
Join `story_clusters_v8 USING(story_id)` for `last_seen_at` (recency), `independent_source_count`,
`primary_entities` (jsonb), `languages`, `subject_country/region`, `representative_article_id`.

**`story_facts_v8`** — `story_id`, `fact_key`, `unit`, `value_latest`, `member_count`,
`citing_article_ids` (uuid[]), `single_source` (bool), `sample_claim`.

**Dedup guard (IMPORTANT):** merged/duplicate clusters have `story_clusters_v8.redirected_to IS NOT NULL`
and/or `suppression_reason='rejoin-merged'`. **Exclude `redirected_to IS NOT NULL` and `suppression_reason IS NOT NULL`** when surfacing, or you'll show stale duplicate piles.

## To actually "see further" — options
1. Add a **second retrieval lane over `story_generated_v8.body`** (the synth layer) alongside `articles`, fused via your existing RRF → far better "summary/latest/what-happened-with-X" answers.
2. For numeric questions, **cite `story_facts_v8`** (value + `citing_article_ids`).
3. For "latest" intent, **rank by `story_clusters_v8.last_seen_at`** and respect the dedup guard above.

## Things you asked
> (I don't have the Ask-RIG session's specific questions in front of me — paste them and I'll
> answer each precisely. Known open build items from the last review: wire `ASKRIG_LLM_API_KEY`
> [point at local 32b on `:11434` or a fresh key], run the eval gate, containerize+deploy, build UI.)
