# 30 — Clustering & Stories (_v8 keeper) + Enrichment + Generation + Chronicle

**Last verified:** 2026-06-19

## Overview

The **live keeper** is the `analytics.story_clusters_v8` / `story_cluster_members_v8` / `story_edges_v8` triple, rebuilt by `cluster_v9` (Louvain/igraph, run_id-stamped) and extended incrementally by `_v9_graph_incr`. Every enrichment table (`story_facts_v8`, `story_quotes_v8`, `story_timeline_v8`, `story_geo_v8`, `story_sources_v8`, `story_stance_v8`, `story_stance_by_source_v8`, `story_facts_series_v8`, `story_enrichment_status_v8`) hangs off `story_id` from that keeper. `story_generated_v8` stores LLM-generated headlines/decks/bodies with a `member_hash` regen-skip guard and a `guard_c` faithfulness JSONB. The nightly janitor writes reversible split operations to `story_repair_log_v8` + `story_repair_undo_members_v8`. **Critical Chronicle caveat:** `analytics.chronicle_cache` and `analytics.user_story_assignments` foreign-key to `analytics.story_clusters_archive` (the frozen 2026-06-03 keeper with 34,599 stories), **not** to `_v8`; meanwhile `chronicle_router.py` queries the unsuffixed names `analytics.story_clusters`, `analytics.story_facts`, etc., which **do not exist** — this is an unresolved naming mismatch that causes Chronicle reads to fail at runtime.

---

## Table Index

| Table | Schema | Status | Rows | Size |
|---|---|---|---|---|
| story_clusters_v8 | analytics | LIVE | 200,823 | 285 MB |
| story_cluster_members_v8 | analytics | LIVE | 325,077 | 62 MB |
| story_edges_v8 | analytics | LIVE | 449,344 | 89 MB |
| story_enrichment_status_v8 | analytics | LIVE | 5,447 | 8.2 MB |
| story_facts_v8 | analytics | LIVE | 33,076 | 8.6 MB |
| story_facts_series_v8 | analytics | LIVE | 42,418 | 6.0 MB |
| story_quotes_v8 | analytics | LIVE | 98,677 | (see tables) |
| story_sources_v8 | analytics | LIVE | 36,370 | (see tables) |
| story_timeline_v8 | analytics | LIVE | 5,447 | (see tables) |
| story_geo_v8 | analytics | LIVE | 5,304 | 1.7 MB |
| story_stance_v8 | analytics | LIVE | 4,942 | (see tables) |
| story_stance_by_source_v8 | analytics | LIVE | 48,263 | (see tables) |
| story_generated_v8 | analytics | LIVE | 6,963 | 6.1 MB |
| story_repair_log_v8 | analytics | LIVE | 55 | (small) |
| story_repair_undo_members_v8 | analytics | LIVE | 30,692 | (see tables) |
| suppression_audit | analytics | LIVE | 6 | (small) |
| story_clusters_archive | analytics | FROZEN since 2026-06-03 | 34,599 | 23 MB |
| chronicle_cache | analytics | LIVE (1 row) | 1 | 96 KB |
| event_clusters_archive | public | FROZEN (legacy product layer) | 6,859 | (see tables) |

---

### analytics.story_clusters_v8 — [LIVE] (~200,823 rows, 285 MB)

**Purpose:** Master story/cluster registry. One row per cluster produced by the graph-based clustering pipeline. The `story_id` (UUID) is the stable cluster identity used everywhere else.  
**Populated by:** `cluster_v9` batch (Louvain igraph, `_v8` algo tag), `_v9_graph_incr` (incremental edge additions, `graph-incr` algo tag), and `night-repair-v8` janitor (split children).  
**Read by:** Night-desk front-end, enrichment pipeline, generation pipeline, relevance scorer, surfaceability queries.  
**Freshness:** Updated continuously; `MAX(updated_at)` = 2026-06-19 13:41 UTC.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| story_id | uuid | NO | — | PK. Stable cluster identity. Generated at cluster creation. |
| created_at | timestamptz | NO | now() | First time this cluster row was written. |
| updated_at | timestamptz | NO | now() | Last time any cluster metadata was refreshed (trigger or explicit update). |
| status | text | NO | 'active' | Lifecycle state. Only observed value: `active` (200,823 rows). `redirected` is supported in schema via `redirected_to`. |
| redirected_to | uuid | YES | — | If this cluster was merged into another, points to the surviving `story_id`. FK → `story_clusters_archive.story_id` (via migration). |
| provisional | boolean | NO | false | True for clusters held back from surfacing pending confirmation. |
| run_id | bigint | NO | — | Clustering job run identifier. Links to the batch that produced/last touched this cluster. Examples: `1781767919` (v9 live batch). |
| algo_version | text | NO | — | Full algorithm lineage string. Observed values: `cluster_job_7/v4/leiden-res1.0/rescue-v1/_v8` (178,213 rows), `cluster_v9/pure+recall/v4/leiden-res1.0/_v8` (10,624), `graph-incr/v4/_v8` (4,860), `night-repair-v8` (455), `cluster_job_7/pf-v1/tg-v3/leiden-res1.0/rescue-v1` (6,671 — old recipe). |
| first_seen_at | timestamptz | NO | — | Timestamp of the earliest member article's `published_at`. Represents real event start, not scrape time. |
| last_seen_at | timestamptz | NO | — | Timestamp of the most recent member article's `published_at`. |
| as_of | timestamptz | NO | — | Snapshot timestamp when cluster metadata was last recomputed. |
| article_count | integer | NO | 0 | Total member articles in this cluster at last recompute. |
| source_count | integer | NO | 0 | Distinct `source_id` values across members. |
| independent_source_count | integer | YES | — | `MIN(distinct source_id, distinct reprint_key)` — deduplicates wire-copy reprints. Key surfaceability lever: ≥3 = surfaceable. |
| subject_country | text | YES | — | Primary country of coverage (ISO or full name). E.g. `India`, `Pakistan`. |
| subject_region | text | YES | — | Broader region. E.g. `South Asia`. |
| subject_locations | jsonb | YES | — | Array of location strings. E.g. `["New Delhi","Mumbai"]`. |
| topic | text | YES | — | Top-level topic classification. E.g. `POLITICS`, `ECONOMY`. |
| event_type | text | YES | — | Fine-grained event type string. E.g. `ELECTION`, `MILITARY_CONFLICT`. |
| primary_entities | jsonb | YES | — | Top entity names and types extracted from members. E.g. `[{"name":"Narendra Modi","type":"PERSON"}]`. |
| languages | jsonb | YES | — | Language distribution across member articles. E.g. `{"en":12,"hi":3}`. |
| stance_distribution | jsonb | YES | — | Aggregated framing counts. E.g. `{"neutral":8,"critical":2}`. |
| sentiment | jsonb | YES | — | Aggregated sentiment scores. E.g. `{"positive":0.3,"negative":0.5,"neutral":0.2}`. |
| representative_quote | jsonb | YES | — | Best representative quote object from member articles. |
| importance_score | numeric | YES | — | Computed prominence/importance score used for ranking. |
| representative_article_id | uuid | YES | — | FK → `articles.id`. The single article chosen to represent this cluster (on-core + tier-1 + recency picker). |
| representative_title | text | YES | — | Headline of the representative article (denormalized for fast display). |
| entity_core_cov | numeric | YES | — | Fraction of member articles that mention the cluster's primary entity (0.0–1.0). Used in suppression decisions. |
| is_template_family | boolean | YES | — | True if the cluster was identified as a recurring-template pile (e.g. daily weather, sports scores) rather than a real event. |
| title_cohesion | numeric | YES | — | Mean pairwise title similarity within the cluster. Used by discriminator. |
| rescued_from_story_id | uuid | YES | — | If this cluster was created by splitting a parent, the parent's `story_id`. Provenance chain for janitor undo. |
| suppression_reason | text | YES | — | If set, cluster is suppressed from surfacing. Observed value: `actor-pile-handflag`. Set together with `suppressed_at`; both cleared on revert. |
| suppressed_at | timestamptz | YES | — | When suppression was applied. NULL for surfaced stories. |
| prev_representative_article_id_f1 | uuid | YES | — | Migration 098 provenance field. Stores the old `representative_article_id` only when it was replaced by the on-core/tier-1/recency picker. NULL otherwise. Used for revert. |
| prev_representative_title_f1 | text | YES | — | Denormalized title for `prev_representative_article_id_f1`. |
| is_multi_event | boolean | YES | — | True when Guard C classifies the cluster as containing multiple distinct events. Trigger for janitor split. |

**Joins:**
- `story_cluster_members_v8` on `story_id` → member articles
- `story_edges_v8` on `article_a` / `article_b` → pairwise similarity graph
- All `story_*_v8` enrichment tables on `story_id`
- `story_generated_v8` on `story_id` → LLM output
- `articles` on `representative_article_id` → representative article

**Notes:**
- All 200,823 rows are `status='active'`; `redirected` status is schema-supported but not observed in live data.
- The discriminator uses `is_template_family`, `title_cohesion`, `entity_core_cov`, and `independent_source_count` for surfaceability decisions.
- `is_multi_event` is set by the generation pipeline's Guard C pass; the nightly janitor reads it to schedule splits.

---

### analytics.story_cluster_members_v8 — [LIVE] (~325,077 rows, 62 MB)

**Purpose:** Many-to-one join between articles and clusters. Each row says "article X belongs to cluster Y with this scoring metadata."  
**Populated by:** `cluster_v9` batch and `_v9_graph_incr` incremental attachment.  
**Read by:** Enrichment pipeline (pulls all member `article_id`s per story), generation pipeline, surfaceability queries.  
**Freshness:** Written with each clustering run; most recent `added_at` tracks the live run.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| article_id | uuid | NO | — | FK → `articles.id`. The member article. |
| story_id | uuid | NO | — | FK → `story_clusters_v8.story_id`. The owning cluster. |
| source_id | uuid | YES | — | FK → `sources.id`. Denormalized for fast source-diversity queries. |
| is_representative | boolean | NO | false | True for the single article chosen as the cluster representative. |
| is_canonical | boolean | NO | true | True for on-core articles (high attach score, not peripheral). |
| attach_score | numeric | YES | — | Cosine similarity or graph-edge weight between this article and the cluster centroid/hub. |
| provisional | boolean | NO | false | Mirrors `story_clusters_v8.provisional` for this membership. |
| added_at | timestamptz | NO | now() | When this membership row was inserted. |
| run_id | bigint | NO | — | The clustering run_id that created this membership. |

**Joins:**
- `story_clusters_v8` on `story_id`
- `articles` on `article_id`
- `sources` on `source_id`

**Notes:**
- No explicit UNIQUE constraint on `(article_id, story_id)` observed, but `article_id` should appear once per cluster in practice.
- Large table (325k rows, 62 MB) — use `story_id` index when pulling all members for a single cluster.

---

### analytics.story_edges_v8 — [LIVE] (~449,344 rows, 89 MB)

**Purpose:** Pairwise article similarity graph underlying the clustering. Each row is a directed or undirected edge between two articles that exceed the cosine threshold used by the Leiden algorithm.  
**Populated by:** `cluster_v9` batch (`scorer-high` edges, 434,088 rows) and `_v9_graph_incr` (`graph-incr` edges, 15,256 rows).  
**Read by:** Clustering pipeline for incremental graph extension; not typically read by product queries.  
**Freshness:** Grows with each incremental run.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| article_a | uuid | NO | — | FK → `articles.id`. First article in the pair (lower UUID by convention, inferred). |
| article_b | uuid | NO | — | FK → `articles.id`. Second article in the pair. |
| score | numeric | NO | — | Cosine similarity between the two article embeddings (V4 LaBSE recipe). |
| decided_by | text | NO | — | How the edge was created. Observed: `scorer-high` (main batch, 434,088), `graph-incr` (incremental, 15,256). |
| run_id | bigint | NO | — | Clustering run that inserted this edge. |
| created_at | timestamptz | NO | now() | Insertion timestamp. |

**Joins:**
- `articles` on `article_a`, `article_b`
- `story_clusters_v8` indirectly (via member lookup)

**Notes:**
- PK is implicitly `(article_a, article_b)` — no duplicate edges expected per pair.
- The operative CAND_COS threshold is ≈0.81; edges below that are not inserted.
- `story_edges_v8copy` (440,307 rows, 87 MB) is a validation snapshot — do not use for production queries.

---

### analytics.story_enrichment_status_v8 — [LIVE] (~5,447 rows, 8.2 MB)

**Purpose:** Per-story coverage tracker for the enrichment pipeline. Records which components have been populated and at what depth. "Empty" means enriched-but-genuinely-none, not unprocessed — this distinction is critical.  
**Populated by:** Enrichment pipeline after each story enrichment pass.  
**Read by:** Generation pipeline (decides whether to attempt LLM generation), ops monitoring.  
**Freshness:** 5,447 rows = matches `story_timeline_v8` count; enrichment covers a subset of all clusters.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| story_id | uuid | NO | — | PK. FK → `story_clusters_v8.story_id`. |
| members_total | integer | YES | — | Total member article count at enrichment time. |
| claims_coverage | numeric | YES | — | Fraction of members that have extractable claims (0.0–1.0). |
| quotes_coverage | numeric | YES | — | Fraction of members that yielded at least one quote. |
| stances_coverage | numeric | YES | — | Fraction of members with stance annotations. |
| geo_coverage | numeric | YES | — | Fraction of members with geo data. |
| facts_count | integer | YES | — | Count of `story_facts_v8` rows for this story. |
| quotes_count | integer | YES | — | Count of `story_quotes_v8` rows for this story. |
| stance_count | integer | YES | — | Count of `story_stance_by_source_v8` rows for this story. |
| run_id | bigint | YES | — | Enrichment run that last wrote this row. |
| enriched_at | timestamptz | YES | now() | When enrichment completed for this story. |

**Notes:**
- `coverage_tag` column referenced in some older code does **not exist** in the live table (confirmed: `ERROR: column ses.coverage_tag does not exist`). Use `claims_coverage`/`quotes_count` etc. instead.
- A row present with all-zero counts means enriched with genuinely no data; a missing row means not yet enriched.

**Joins:**
- `story_clusters_v8` on `story_id`

---

### analytics.story_facts_v8 — [LIVE] (~33,076 rows, 8.6 MB)

**Purpose:** Entity-anchored quantitative claims extracted from member articles. One row per unique `(story_id, fact_key)` aggregated across all members.  
**Populated by:** Enrichment pipeline (LLM claim extraction + aggregation).  
**Read by:** Generation pipeline (fact ledger for Guard C faithfulness check), night-desk story detail page.  
**Freshness:** Populated for enriched stories.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | bigint | NO | nextval(seq) | Surrogate PK. |
| story_id | uuid | YES | — | FK → `story_clusters_v8.story_id`. |
| fact_key | text | YES | — | Entity/metric name. E.g. `port arthur`, `the dockyard`. |
| unit | text | YES | — | Unit of the value. E.g. `people`, `USD`, `km`. |
| value_min | numeric | YES | — | Minimum reported value across citing articles. |
| value_max | numeric | YES | — | Maximum reported value across citing articles. |
| value_latest | numeric | YES | — | Most recent value reported (by `published_at`). |
| member_count | integer | YES | — | Number of member articles that mention this fact. |
| citing_article_ids | uuid[] | YES | — | Array of `article_id`s that cite this fact. |
| single_source | boolean | YES | — | True if only one source reported this fact (low corroboration signal). |
| sample_claim | text | YES | — | Verbatim sample claim text from one of the citing articles. |
| run_id | bigint | YES | — | Enrichment run that wrote this row. |

**Joins:**
- `story_clusters_v8` on `story_id`
- `articles` on any element of `citing_article_ids`

---

### analytics.story_facts_series_v8 — [LIVE] (~42,418 rows, 6.0 MB)

**Purpose:** Time-series expansion of story facts — one row per `(story_id, fact_key, published_at)` data point, enabling trend/change-over-time queries.  
**Populated by:** Enrichment pipeline alongside `story_facts_v8`.  
**Read by:** Generation pipeline for temporal trend context; analytics dashboards (inferred).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| story_id | uuid | NO | — | FK → `story_clusters_v8.story_id`. Composite PK component. |
| fact_key | text | NO | — | Entity/metric name matching `story_facts_v8.fact_key`. Composite PK component. |
| unit | text | YES | — | Unit of measurement. |
| value | double precision | NO | — | Single data-point value at this timestamp. |
| published_at | timestamptz | YES | — | Article publication time for this data point. Composite PK component. |
| source_id | uuid | YES | — | FK → `sources.id`. Which source reported this value. |
| source_tier | integer | YES | — | Numeric tier of the source (1 = top-tier). |
| article_id | uuid | YES | — | FK → `articles.id`. The article that provided this data point. |
| run_id | bigint | YES | — | Enrichment run. |

**Joins:**
- `story_facts_v8` on `(story_id, fact_key)` for aggregated view
- `sources` on `source_id`

---

### analytics.story_quotes_v8 — [LIVE] (~98,677 rows)

**Purpose:** Verbatim quotes extracted from member articles, attributed to named speakers.  
**Populated by:** Enrichment pipeline (LLM quote extraction).  
**Read by:** Night-desk story detail page (top 18 quotes ordered by `is_direct DESC, length DESC`).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| story_id | uuid | YES | — | FK → `story_clusters_v8.story_id`. |
| quote_text | text | YES | — | Original-language verbatim quote. |
| quote_text_en | text | YES | — | English translation of the quote (may equal `quote_text` if already English). |
| speaker | text | YES | — | Named speaker. E.g. `Francesca Albanese`, `Viktor Hovland`. |
| speaker_entity_id | uuid | YES | — | FK → entity table (if speaker was resolved to a known entity). |
| article_id | uuid | YES | — | FK → `articles.id`. Source article. |
| is_direct | boolean | YES | — | True for verbatim direct quotes; false for paraphrases. |
| run_id | bigint | YES | — | Enrichment run. |
| published_at | timestamptz | YES | — | `published_at` of the source article (denormalized). |

**Joins:**
- `story_clusters_v8` on `story_id`
- `articles` on `article_id`

**Notes:**
- 98,677 rows is the largest enrichment table. Product query uses `COALESCE(quote_text_en, quote_text)` and filters `length > 15`.

---

### analytics.story_sources_v8 — [LIVE] (~36,370 rows)

**Purpose:** Per-source contribution summary for each story. One row per `(story_id, source_id)`.  
**Populated by:** Enrichment pipeline.  
**Read by:** Night-desk (source tier breakdown); surfaceability queries (`independent_source_count` cross-check).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| story_id | uuid | NO | — | FK → `story_clusters_v8.story_id`. Composite PK component. |
| source_id | uuid | NO | — | FK → `sources.id`. Composite PK component. |
| articles_from_source | integer | YES | — | Count of member articles from this source. |
| first_seen_at | timestamptz | YES | — | Earliest `published_at` among this source's articles in the cluster. |
| source_tier | text | YES | — | Tier label for the source. All 36,370 rows have NULL tier (inferred: tier field not yet backfilled). |
| source_country | text | YES | — | Country of the source outlet. |
| is_canonical_origin | boolean | YES | — | True if this source is deemed the originating source of the story event. |
| run_id | bigint | YES | — | Enrichment run. |

**Notes:**
- `source_tier` is fully NULL in production (36,370 / 36,370). Use `sources.tier` via join instead.

---

### analytics.story_timeline_v8 — [LIVE] (~5,447 rows)

**Purpose:** Aggregate publication velocity and temporal span for each story. One row per story.  
**Populated by:** Enrichment pipeline.  
**Read by:** Night-desk story detail page; breaking-news detection.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| story_id | uuid | NO | — | PK. FK → `story_clusters_v8.story_id`. |
| first_seen_at | timestamptz | YES | — | Earliest article `published_at` in the cluster. |
| last_seen_at | timestamptz | YES | — | Latest article `published_at`. |
| peak_at | timestamptz | YES | — | Hour of maximum publication velocity. |
| peak_articles_per_hour | integer | YES | — | Article count in the peak hour. |
| velocity | numeric | YES | — | Articles per hour over the active span. |
| span_hours | numeric | YES | — | Hours between `first_seen_at` and `last_seen_at`. |
| is_breaking | boolean | YES | — | True if velocity exceeds the breaking-news threshold. |
| dormant_since | timestamptz | YES | — | If no new articles for >N hours, the cutoff timestamp. |
| run_id | bigint | YES | — | Enrichment run. |
| computed_at | timestamptz | YES | now() | When this row was last (re)computed. |

---

### analytics.story_geo_v8 — [LIVE] (~5,304 rows, 1.7 MB)

**Purpose:** Geographic footprint of each story. One row per story.  
**Populated by:** Enrichment pipeline.  
**Read by:** Night-desk story detail page; geo-filter queries.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| story_id | uuid | NO | — | PK. FK → `story_clusters_v8.story_id`. |
| subject_countries | jsonb | YES | — | Array of country strings mentioned across members. E.g. `["India","Pakistan"]`. |
| primary_country | text | YES | — | Single dominant country. |
| continent | text | YES | — | Continent of `primary_country`. E.g. `Asia`. |
| country_spread | integer | YES | — | Number of distinct countries mentioned. |
| run_id | bigint | YES | — | Enrichment run. |

---

### analytics.story_stance_v8 — [LIVE] (~4,942 rows)

**Purpose:** Aggregated stance/framing and sentiment distribution for each story. One row per story.  
**Populated by:** Enrichment pipeline (aggregates from `article_stances`).  
**Read by:** Night-desk story detail page.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| story_id | uuid | NO | — | PK. FK → `story_clusters_v8.story_id`. |
| stance_distribution | jsonb | YES | — | Framing counts by label. E.g. `{"neutral":8,"critical":2,"supportive":1}`. |
| sentiment | jsonb | YES | — | Sentiment score distribution. E.g. `{"positive":0.3,"negative":0.5,"neutral":0.2}`. |
| n_stances | integer | YES | — | Total stance annotations aggregated. |
| run_id | bigint | YES | — | Enrichment run. |

---

### analytics.story_stance_by_source_v8 — [LIVE] (~48,263 rows)

**Purpose:** Per-source stance breakdown for each story — one row per `(story_id, source_id, stance)`. Enables per-outlet framing analysis.  
**Populated by:** Enrichment pipeline.  
**Read by:** Analytics queries (source framing comparison).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| story_id | uuid | NO | — | FK → `story_clusters_v8.story_id`. Composite PK component. |
| source_id | uuid | YES | — | FK → `sources.id`. |
| source_tier | integer | YES | — | Numeric tier of the source. |
| source_country | text | YES | — | Country of the source outlet. |
| stance | text | YES | — | Stance label. E.g. `neutral`, `critical`, `supportive`. |
| n | integer | NO | — | Count of articles from this source with this stance for this story. |
| run_id | bigint | YES | — | Enrichment run. |

---

### analytics.story_generated_v8 — [LIVE] (~6,963 rows, 6.1 MB)

**Purpose:** LLM-generated editorial content (headline, deck, body) per story. `member_hash` prevents redundant regeneration; `guard_c` records the faithfulness verdict from the Guard C verifier pass.  
**Populated by:** Content generation pipeline (`gen_hybrid` / `_worldwide_gen_sample.py` recipe).  
**Read by:** Night-desk (published stories); generation pipeline (skip-regen check via `member_hash`).  
**Freshness:** 6,963 rows; 584 fully PUBLISHABLE, majority STUBs (4,324).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| story_id | uuid | NO | — | PK. FK → `story_clusters_v8.story_id`. |
| headline | text | YES | — | LLM-generated headline. |
| deck | text | YES | — | Subheadline / summary sentence. |
| body | text | YES | — | Full generated article body. |
| topic | text | YES | — | Topic label assigned at generation time. |
| tags | text[] | YES | — | Array of topic/entity tags. |
| strategy | text | YES | — | Which generation strategy won. E.g. `narrative`, `extractive`. |
| status | text | YES | — | Pipeline verdict. Pipe-delimited compound strings observed: `PUBLISHABLE`, `STUB`, `HELD (no facts: empty ledger)`, `HELD (no facts: backfill 2026-06-17)`, `PUBLISHABLE \| HELD (Guard C: multi-event — needs _v8 split)`, `EXTRACTIVE-FALLBACK (all gens failed verify)`, `EXTRACTIVE-FALLBACK (all gens failed verify) \| HELD (Guard C: multi-event — needs _v8 split)`. |
| tier | integer | YES | 0 | Generation quality tier (higher = better). |
| guard_c | jsonb | YES | — | Guard C faithfulness result. Keys: `verdict` (`ONE`, `SEVERAL`), `dominant` (which event dominates). |
| verify | jsonb | YES | — | Verifier output. Keys: `computed_verdict`, `failing` (array of high-risk units). |
| claim_provenance | jsonb | YES | — | Mapping of generated claims back to source article IDs. |
| fact_version | text | YES | — | Version tag of the fact ledger used at generation time. |
| word_count | integer | YES | — | Word count of the generated body. |
| run_id | bigint | YES | — | Generation run. |
| updated_at | timestamptz | YES | now() | Last time this row was regenerated. |
| member_hash | text | YES | — | Hash of the cluster membership at generation time. If membership has not changed, generation is skipped. NULL on old rows (pre-hash). |

**Joins:**
- `story_clusters_v8` on `story_id`
- `story_enrichment_status_v8` on `story_id` (check enrichment completeness before regenerating)

**Notes:**
- `guard_c->>'verdict'` = `ONE` → single event, publishable. `SEVERAL` → multi-event, triggers janitor split and `HELD` status suffix.
- The `member_hash` regen-skip was added later; older rows have `member_hash IS NULL` and will always be regenerated on the next pass.
- `STUB` status = cluster exists but lacks sufficient facts/quotes for full generation.

---

### analytics.story_repair_log_v8 — [LIVE] (~55 rows)

**Purpose:** Append-only ledger of janitor repair operations (splits and merges applied to `_v8` clusters). Each row records one parent cluster being split into children.  
**Populated by:** Nightly janitor (`night-repair-v8`).  
**Read by:** Ops/audit queries; undo pipeline.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | bigint | NO | nextval(seq) | Surrogate PK. |
| batch_id | bigint | NO | — | Groups all operations from one janitor nightly run. |
| applied_at | timestamptz | NO | now() | When the repair was applied. |
| parent_story_id | uuid | NO | — | The cluster that was split. FK → `story_clusters_v8.story_id`. |
| action | text | NO | — | Operation type. Only observed value: `SPLIT` (55 rows). |
| new_child_ids | uuid[] | NO | '{}' | Array of new child cluster `story_id`s created by the split. E.g. 5–6 children per operation. |
| ejected | uuid[] | NO | '{}' | Article UUIDs that were removed from the parent during the split. |
| parent_before | jsonb | NO | — | Full snapshot of the parent cluster row at the time of repair (for rollback). |
| reasons | jsonb | YES | — | Structured reasons for the repair. E.g. Guard C verdict, entity spread signal. |

**Joins:**
- `story_repair_undo_members_v8` on `batch_id` → full undo payload

---

### analytics.story_repair_undo_members_v8 — [LIVE] (~30,692 rows)

**Purpose:** Companion to `story_repair_log_v8`. Stores the pre-split member state so any split can be fully reversed by replaying these rows back into `story_cluster_members_v8`.  
**Populated by:** Nightly janitor (written atomically with `story_repair_log_v8`).  
**Read by:** Undo pipeline.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| batch_id | bigint | NO | — | Links to `story_repair_log_v8.batch_id`. |
| article_id | uuid | NO | — | FK → `articles.id`. Member article pre-split. |
| story_id | uuid | NO | — | Parent cluster `story_id` before split. |
| source_id | uuid | YES | — | Denormalized source. |
| is_representative | boolean | NO | — | Pre-split representative flag. |
| is_canonical | boolean | NO | — | Pre-split canonical flag. |
| attach_score | numeric | YES | — | Pre-split attach score. |
| provisional | boolean | NO | — | Pre-split provisional flag. |
| added_at | timestamptz | NO | — | Original `added_at` from the member row. |

**Joins:**
- `story_repair_log_v8` on `batch_id`

---

### analytics.suppression_audit — [LIVE] (~6 rows)

**Purpose:** Append-only audit trail for cluster suppression events. Captures the at-flag snapshot (article count, entity coverage, etc.) so the cluster can continue evolving without losing the suppression rationale.  
**Populated by:** Suppression pipeline (manual or automated flag).  
**Read by:** Ops audit queries.  
**Freshness:** 6 rows; all `suppression_reason = 'actor-pile-handflag'`.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | bigint | NO | nextval(seq) | Surrogate PK. |
| story_id | uuid | NO | — | The suppressed cluster. Not a strict FK (cluster can evolve after suppression). |
| suppression_reason | text | NO | — | Reason code. Observed: `actor-pile-handflag`. |
| suppressed_at | timestamptz | NO | now() | When suppression was applied. |
| article_count_at_flag | integer | YES | — | `article_count` at suppression time. |
| independent_source_count_at_flag | integer | YES | — | `independent_source_count` at suppression time. |
| entity_core_cov_at_flag | numeric | YES | — | `entity_core_cov` at suppression time. |
| top_entity_at_flag | text | YES | — | Primary entity name at suppression time. |
| representative_title_at_flag | text | YES | — | Representative title at suppression time. |
| spec_doc | text | YES | — | Reference to the spec or decision document that mandated this suppression. |
| applied_by | text | YES | — | Who or what applied the suppression (`admin`, pipeline name, etc.). |
| notes | text | YES | — | Free-text notes. |

**Joins:**
- `story_clusters_v8` on `story_id` (not a hard FK — cluster state may have changed since flag)

---

### analytics.story_clusters_archive — [FROZEN since 2026-06-03] (~34,599 rows, 23 MB)

**Purpose:** The previous live keeper produced by `cluster_job_7` (igraph-Louvain, 2026-06-03 swap). Now frozen as the Chronicle feature's target table — both `chronicle_cache` and `user_story_assignments` FK to it.  
**Populated by:** Final `cluster_job_7` run (2026-06-03). No new rows since.  
**Read by:** `chronicle_router.py` — **BUT** `chronicle_router.py` actually queries `analytics.story_clusters` (unsuffixed), which **does not exist**. This is an unresolved naming bug that causes all Chronicle reads to fail.  
**Freshness:** Frozen. Do not write to it.

Schema is identical to `story_clusters_v8` (same columns, same types, same defaults). See `story_clusters_v8` column table above for full field definitions. Key difference: `algo_version` values are `cluster_job_7/*` lineage strings; no `graph-incr` or `cluster_v9` rows.

**Joins:**
- `chronicle_cache` on `story_id` (hard FK)
- `user_story_assignments` on `story_id` (hard FK)
- `story_clusters_v8.redirected_to` → `story_clusters_archive.story_id` (hard FK — the _v8 redirected_to column points here, not to _v8 itself)

**CRITICAL BUG:** `chronicle_router.py` reads `analytics.story_clusters`, `analytics.story_timeline`, `analytics.story_facts`, `analytics.story_quotes`, `analytics.story_stance` (all unsuffixed). None of these tables exist — the tables are named `*_archive` (for the Chronicle-targeted keeper) and `*_v8` (for the live keeper). Chronicle is non-functional until the router is updated to query `*_archive` tables (or until the Chronicle feature is repointed to `_v8`).

---

### analytics.chronicle_cache — [LIVE] (1 row, 96 KB)

**Purpose:** LLM output cache for the Chronicle feature. Stores the full rendered narrative payload per `story_id`, keyed for TTL-based regeneration (>24h → regenerate, enforced at read time in `chronicle_router.py`).  
**Populated by:** `chronicle_router.py` on first request per story (or after cache expiry).  
**Read by:** Chronicle sidebar in night-desk UI.  
**Freshness:** 1 row (story_id `e8a5d010-d67e-407b-a528-ab89e5a39bc2`, generated 2026-06-07 11:01 UTC, model `qwen3-32b-v2`).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| story_id | uuid | NO | — | PK. FK → `story_clusters_archive.story_id`. |
| payload | jsonb | NO | — | Full Chronicle narrative output from the LLM. Structure includes timeline, key actors, significance, etc. |
| generated_at | timestamptz | NO | now() | When the payload was generated. Used for 24h TTL check. |
| model_version | text | YES | — | LLM model used. Observed: `qwen3-32b-v2`. |

**Joins:**
- `story_clusters_archive` on `story_id`
- `user_story_assignments` on `story_id` (indirectly — assignments determine which stories get Chronicle pages)

**Notes:**
- Only 1 row in production — Chronicle is effectively non-functional due to the router naming bug described under `story_clusters_archive`.
- TTL is enforced in application code, not by a DB trigger.

---

### analytics.user_story_assignments — [LIVE] (2 rows)

**Purpose:** Admin-managed assignments of stories to specific users for the Chronicle feature. No automatic matching — all rows are manually created by admins.  
**Populated by:** Admin API or manual SQL insert.  
**Read by:** `chronicle_router.py` to determine which stories a user sees in their Chronicle tab.  
**Freshness:** 2 rows (2 assignments).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK. |
| user_id | uuid | NO | — | FK → `analytics.users.id`. The user receiving the assignment. |
| story_id | uuid | NO | — | FK → `analytics.story_clusters_archive.story_id`. The assigned story. |
| assigned_at | timestamptz | NO | now() | When the assignment was created. |
| assigned_by | text | YES | 'admin' | Who created the assignment. |
| label | text | YES | — | Optional label for the assignment (e.g. `PRIORITY`, `WATCH`). |

**Constraint:** UNIQUE `(user_id, story_id)` — a user cannot be assigned the same story twice.

**Joins:**
- `analytics.users` on `user_id`
- `analytics.story_clusters_archive` on `story_id`

---

### public.event_clusters_archive — [FROZEN legacy] (~6,859 rows)

**Purpose:** Older product-layer event cluster table, predating the `_v8` keeper. Still referenced by `article_events.event_cluster_id` via a hard FK. The `canonical_date` has wild values (max `2060-01-01`) suggesting test data was never cleaned.  
**Populated by:** Legacy event clustering pipeline (before `cluster_job_7`). No new writes.  
**Read by:** `article_events` (FK) — any query joining `article_events` to event detail must hit this table.  
**Freshness:** Frozen. `MAX(canonical_date)` = 2060-01-01 (test artifact).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK. |
| canonical_description | text | NO | — | Human-readable event description (not LLM-generated, assembled by legacy pipeline). |
| canonical_actors | text[] | NO | '{}' | Deduplicated union of actors across all `article_events` in this cluster. |
| canonical_event_type | text | YES | — | Event type label. |
| canonical_date | date | YES | — | Representative date for the event. Note: max value is `2060-01-01` — test artifact, not real. |
| is_future | boolean | YES | false | True if the event was predicted/scheduled at ingest time. |
| article_count | integer | NO | 0 | Count of `article_events` rows pointing here at last update. |
| source_count | integer | YES | — | (inferred) Distinct source count. |
| confidence_score | real | YES | — | Clustering confidence. |
| first_seen_at | timestamptz | NO | — | Earliest article publication among members. |
| last_updated_at | timestamptz | NO | — | Last time this cluster row was touched. |
| is_active | boolean | NO | — | Whether this cluster is considered current/active. |
| importance_score | real | YES | — | Legacy importance rank. |
| importance_updated_at | timestamptz | YES | — | When `importance_score` was last recomputed. |

**Joins:**
- `article_events` on `event_cluster_id → id` (hard FK; `article_events` also FKs `articles.id`)

**Notes:**
- Do not confuse with `analytics.story_clusters_archive` (which is the Chronicle keeper). This table is in `public` schema, not `analytics`.
- The `_v8` keeper does NOT replace this table for `article_events` — that link is unchanged.

---

## Leftover scratch (do not use)

These are disposable validation tables from clustering experiments. No production code reads them. No full column docs.

- **`analytics._v9_cand`** (53,673 rows, 4.0 MB) — candidate edge pairs `(a_id, b_id, cos, tt)` from the _v9 CAND_COS sweep. Temporary working table.
- **`analytics._v9_members`** (32,646 rows, 2.0 MB) — `(article_id, cluster_id)` from the _v9 pure-Leiden pass. Intermediate result.
- **`analytics._v9_members_pure`** (32,646 rows, 2.0 MB) — identical schema to `_v9_members`; second validation snapshot of the same run.
- **`analytics.story_cluster_members_v8shadow`** (17,790 rows, 3.4 MB) — shadow copy of `story_cluster_members_v8` from an earlier shadow-re-embed validation pass.
- **`analytics.story_cluster_members_v8shadow4`** (33,487 rows, 6.0 MB) — later shadow copy; same schema as `_v8shadow`.
- **`analytics.story_edges_v8copy`** (440,307 rows, 87 MB) — point-in-time copy of `story_edges_v8` for pre-_v9 validation.
- **`analytics.story_edges_v8shadow`** (46,588 rows, 9.3 MB) — partial edge shadow from the shadow re-embed experiment.
- **`analytics.story_edges_v8shadow4`** (108,447 rows, 21 MB) — later shadow edge set from the _v9 validation harness.
