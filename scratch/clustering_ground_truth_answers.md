# Clustering Engine — Data Ground-Truth ANSWERS
**From:** database/pipeline chat · **Date:** 2026-05-30
All numbers are **live from the Hetzner DB** unless marked `[CODE]` (verified in
source this session) or `[FOLLOW-UP]` (not yet queried — do NOT assume).
Corpus total = **124,603 articles**.

---

## ⭐ HIGHEST-STAKES FIVE

### H1 — What is the LaBSE vector computed over? `[CODE, verified]`
- Input = **`lead_text_translated`, first 512 CHARACTERS** (not tokens), head-only,
  truncated. For text-less articles it falls back to **title**. **The title is NOT
  prepended** for full-text articles — the vector is lead-only.
- Language = **machine-translated (English)**, not original.
- One vector/article, **not** chunked. 768-dim. Pinned model rev `836121a`.
- **Implication:** recall ceiling = *first 512 chars of the translated lead*. Same-
  source collapse is real but **fixable** — the body exists (H2); the embedding just
  doesn't use it, and distance alone can't separate same-event (see review doc).
- **Q1.5 L2-normalized? [FOLLOW-UP]** — pgvector `<=>` is cosine regardless, but
  confirm before assuming dot==cosine. **Q1.6 HNSW m/ef/recall@20 [FOLLOW-UP]** —
  not yet pulled from the index DDL.

### H2 — Body availability. **GOOD.**
- Columns exist: **`full_text_scraped`, `full_text_translated`, `lead_text_original`
  (cap ~2000 chars), `word_count`, `reading_minutes`, `body_quality`.**
- `lead_text_original` length: **p10=465, p50=2000, p90=2000 chars**. Buckets:
  **>1000 ch = 98,740 (79%)**, 500–1000 = 9,554, 150–500 = 11,510, <150/null = 4,843.
- So **~79% have real body**, not snippet-only → the multi-signal scorer + LLM judge
  have plenty to read. `[FOLLOW-UP]` exact `full_text_scraped` coverage % (I measured
  `lead_text_original`; full_text is the richer column).

### H3 — Entity canonicalization + cross-lingual. **Surface strings + a lookup table.**
- `entities_extracted` = JSONB array of `{name(SURFACE string), type(person/org/
  location), label(DICT_MATCH/…), confidence, prominence}`. **NOT canonical IDs.**
- **BUT** a resolution table exists: **`entity_lookup` (55,406 rows)** = canonical +
  alias/transliteration → entity_id. So Modi=Narendra Modi=మోదీ linking is **possible
  via lookup**, not via the raw jsonb. `prominence` gives **salience** (Q4.5 — yes).
- Caveat: raw NER has noise (sample had `"Yes"` tagged as a location). Resolve through
  `entity_lookup`, drop unmatched/low-prominence. **Cross-lingual quality [FOLLOW-UP]:
  measure what % of non-English NER surface forms actually resolve via lookup.**

### H4 — Source independence. **ABSENT — flag it.**
- `sources.source_type` = ingest method only (**rss=574, scrape=176, api=43**), NOT
  ownership/wire. **No parent-company or PTI/ANI/Reuters syndication map exists.**
- Partial substitute: **30% of articles are `is_duplicate=TRUE`** + `analytics.
  pair_scores` has `canonical_url_match`, `trgm_title` → you can collapse *copies*.
  But copy-dedup ≠ ownership-independence. **You will need a stopgap** (infer
  parent from domain, or a manual wire/owner map).

### H5 — Compute. **🚨 RED FLAG.**
- **4 CPU cores · 15 GiB RAM · ~123 MiB free · NO GPU · disk 150 GB @ 68%.**
- RAM is effectively **exhausted** (LLM workers + Postgres + FastAPI consume it).
- **Hourly Leiden/community-detection on 140–280K nodes + an on-box embed job is NOT
  feasible as-is** — no spare RAM, no GPU. Options: stream/edge-list on disk, run
  community detection less often / on a subgraph, move it off-box, or upgrade. **This
  constrains the architecture more than anything else here.**

---

## 1. Embeddings
- Q1.1–1.4: see **H1**. Q1.5/1.6: `[FOLLOW-UP]`.
- Q1.7 coverage **123,196 / 124,603 = 98.9%** embedded. Publish→embedded latency:
  currently NLP-coupled; Phase 0 (embed-at-ingest) targets <5 min p50 `[CODE — not
  yet deployed]`.
- Q1.8 Provenance columns `embedded_at/embedding_model/embedding_revision` now exist
  (migration 085) and are stamped **going forward**; **historical 122K are NOT yet
  back-stamped** → mixed-revision *cannot currently be proven*. Re-embed (Phase 0c)
  will unify. Pin (`836121a`) is live, so new vectors are single-revision.

## 2. Text fields
- Q2.1 per-article text cols + coverage: title 100%, lead_text_original 98.1%,
  lead_text_translated 98.8%, full_text_scraped/translated (exist; `[FOLLOW-UP]` %),
  summary_executive 75.1%, summary_preview/snippet (exist), `fts` (tsvector) present.
- Q2.2: see **H2**.
- Q2.3 cleaned vs raw: `body_quality` column exists → `[FOLLOW-UP]` its distribution.
- Q2.4 `summary_executive`: **93,611 (75%)**; abstractive LLM summary from the
  substrate pass `[CODE — verify extractive/abstractive + prompt]`.
- Q2.5 FTS language config `[FOLLOW-UP]` — `fts` column exists; confirm whether it
  indexes Telugu/Hindi or only English/translated.

## 3. Wire / syndication dedup
- Q3.1 **30% (`is_duplicate=TRUE` = 37,558)** already flagged; `duplicate_of` points
  to the kept row. trgm-based.
- Q3.5 **`analytics.pair_scores` EXISTS (28,300 rows)** with a **rich, reusable
  feature schema:** `trgm_subject, trgm_title, shared_actors, shared_speakers,
  shared_locations, shared_primary_loc, idf_loc_score, canonical_url_match,
  event_date_match, length_ratio, time_diff_hours, same_source, same_language,
  computed_at, algo_version`. Also `pair_scores_watermark` (incremental) +
  **`dup_golden` / `dup_golden_v2`** (labeled sets!) + `dup_overrides`. **The pair-
  scorer you want is half-built here — reuse the formula even if rows are stale.**
- Q3.2/3.3/3.4 fan-out, canonical marker, best signal: `canonical_url_match` +
  `trgm_title` are your trustworthy copy signals; `[FOLLOW-UP]` for fan-out
  distribution.

## 4. Entities — see **H3**.
- Q4.1 `entities_extracted` jsonb is the populated path (sample confirms). FK link
  tables are the sparse ones (drop). Coverage `[FOLLOW-UP]` exact %.
- Q4.5 yes — `prominence` field is the salience rank.

## 5. `primary_subject`
- Q5.1 free-text per-article English subject line, LLM-generated (substrate),
  **93,617 (75%)**.
- Q5.2 **Cardinality = 92,782 distinct of 93,617 → ~99% UNIQUE = FREE TEXT, NOT a
  controlled vocabulary.** No meaningful top-15 (near-unique).
- Q5.3 one per article. Q5.4 **→ it is NOT a join key.** Use it as fuzzy/lexical
  signal only (`trgm_subject` in pair_scores already does this).

## 6. `article_events`
- Q6.1 ~1 event/article (88,841 articles, 218,209 event rows → ~2.5/article).
- Q6.2 **`event_type` is a CONTROLLED VOCAB and granular** — top: announcement
  45,689 · statement 29,073 · release 27,394 · meeting 21,499 · accident 20,752 ·
  other 12,170 · legal 10,972 · sports_result 10,494 · filing 10,394 · election
  7,788 · market_event 7,281 · protest 3,503. **"other" is only ~6% → usable signal.**
- Q6.3 `effective_event_date`: **only ~5% (11,026/218,209) equal the created date →
  mostly REAL derived event dates, not publish-fallback.** Good.
- Q6.4 `actors` is a separate column from `entities_extracted` (overlapping but
  independent); `event_cluster_id` exists (the old event-cluster, degenerate 3.11).

## 7. `article_locations`
- Q7.1 schema: location_text, **country, region, city, lat/lng, is_primary,
  location_scope, mention_count**. **91,500 articles (73%)**, 260,191 rows (~2.8/art).
- Q7.2 `country` = **free-text English names** (e.g. "United States"), NOT ISO codes;
  has some non-normalized values (saw a Devanagari "Taiwan") → **needs canonicalizing**.
- Q7.3 `is_primary` + `location_scope` exist → subject location, not dateline `[CODE-
  intent; spot-verify]`.
- Q7.6 **Around-the-World reality (14d, primary subject-country, non-India):** US
  2,478 · Nigeria 1,744 · UK 1,375 · Australia 1,334 · Ghana 686 · China 590 · Russia
  418 · Iran 369 · Pakistan 348 · France 333 · DR Congo 238 · Singapore 225. **The
  country grid has real data for ~12+ countries** (note: Nigeria/Ghana high → African
  sources in the mix).

## 8. Quotes
- Q8.1 `article_quotes`: speaker_name(+_en), `speaker_entity_id`, **`quote_text`
  (verbatim) + `quote_text_en`**, char offsets, is_direct, model. Coverage **26,710
  articles (21%)** — weak. Verbatim → good for exact-match dedup.
- Q8.2 confirmed weak (speaker linking sparse).

## 9. Timestamps
- Q9.1 `published_at` **98%** = feed pubdate (can be wrong/back-dated). Q9.2 we DO
  control **`collected_at`** (use it for window ordering/freshness). `[CODE]`
- Q9.3 in-place updates / re-enrichment on update: **`[FOLLOW-UP]`** — `updated_at`
  exists; confirm whether embeddings/entities re-run on update (matters for a live
  graph). Q9.4 `url_hash` + `canonical_url` → stable de-dup key on re-ingest.

## 10. Sources
- Q10.1 sources: rss_url, source_type, **source_tier, language, geo_states, topics,
  country, health_score, is_active**. ~793 sources (574 rss+176 scrape+43 api).
- Q10.2: see **H4** (no ownership/wire map). Q10.3 dup source rows `[FOLLOW-UP]`.

## 11. article_type & language
- Q11.1 **vocab + dist:** news 67,511 · other 25,714 · null 19,014 · analysis 5,664 ·
  opinion 2,631 · explainer 1,744 · sports_result 1,022 · interview 297 · live_blog
  295 · press_release 286 · listicle 278 · recipe 90 · **photo_essay ≈17 (degenerate,
  confirmed)**. ~36% other/null → moderate reliability.
- Q11.3 **language mix (14d):** **en 32,803 (~78%)** · te 4,269 · null 1,968 · kn 864
  · hi 839 · ne 641 · hr 286 · bn 266. **Recent corpus is ENGLISH-dominant**, not
  Telugu — revise that assumption. (`hr`/`ne` are likely mis-detections.)

## 12. Scale & compute
- Q12.1 corpus 124,603; ~3,900–4,200/day currently. Q12.3 7–14d window at 20K/day =
  140–280K nodes — confirmed working set. Q12.4/12.5: see **H5** (the binding
  constraint) + ANN latency `[FOLLOW-UP]`.

## 13. Existing clustering state
- Q13.1 Output lives in **`public.story_threads`** (7,409 rows; v1 5,338 / v2 2,071);
  the **29,798-article blob is a v2 row there** (single-source runaway). `analytics`
  has NO `story_clusters` table yet → **greenfield on the analytics side**.
- Q13.2 Keep: the `entity_lookup`, `analytics.pair_scores` feature formula, the
  `dup_golden` labels, and the (good) LLM-judge prompt. Replace: the seed-anchored
  v2 assignment logic (see review doc — it's the source of the runaways).

## 14. LLM judge `[CODE]`
- Q14.1 Harness EXISTS: `groq_client` unified pool — ~22 Groq + 27 Cerebras keys,
  `call_groq(task_type, json_response, max_tokens_override)`. Fast model qwen3-32b;
  Cerebras maps to zai-glm-4.7.
- Q14.2 Budget: probed healthy — **~16.8K Groq req/day + ~27M Cerebras tokens/day
  spare** (free tier). Q14.3 batchable. Q14.4 can feed title+summary+body (H2).

## 15. Pipeline integration `[CODE]`
- Q15.1 DAG: collect → NLP (translate/entities/topic/geo/**embed**) → substrate
  (primary_subject/events/locations/quotes/summary). **Cluster AFTER embed+entities+
  events.** Q15.2 status flags: `nlp_processed`, `substrate_status`.
- Q15.3 Scheduling: Celery Beat + a 10-min drain tick; idempotent batch pattern
  exists. Q15.4 **Roles:** `analytics_user` (migration 076, read public.* + RW
  analytics) and `rigwire_app` (080, SELECT public+analytics) are **deployed** — one
  role can read `public.*`+`analytics.*` and write `analytics.*`. (Confirm
  `analytics_user` RW grant is intact before relying on it.)

## 16. Landmines
- Q16.1 **degenerate-but-populated:** `event_cluster_id` importance = 3.11 default;
  `photo_essay`≈17; `primary_subject` is unique free-text (not a key); `narrative_
  frame` ~0%; raw NER noise (`"Yes"`=location).
- Q16.4 **Backfill:** Phase-0 re-embed is planned but **not run** → historical 7–14d
  window is NOT uniformly enriched on day one; new-forward is cleaner than history.
- Q16.5 **Golden sets:** `analytics.dup_golden` + `dup_golden_v2` already exist — mine
  them to expand your 134+20 labeled set.

---
## Items I refuse to guess — pull these before locking the spec
Q1.5 (L2-norm), Q1.6 (HNSW params + recall@20), Q2.1/Q2.4 (full_text_scraped % +
summary extractive/abstractive), Q2.5 (FTS language config), Q4 (entity coverage % +
cross-lingual resolve rate), Q7.3 (subject-vs-dateline spot check), Q9.3 (re-enrich on
update?), Q12.5 (ANN p50/p95). Say which matter most and I'll pull them next.
