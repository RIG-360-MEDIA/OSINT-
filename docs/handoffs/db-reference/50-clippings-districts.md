# DB Reference — Clippings/Newspapers + Districts/CM-Atlas

**Domain overview (5 lines):**
The Cuttings pillar stores newspaper articles in two generations: `clippings` (migration 105, substrate-upgraded in migration 107) is the LIVE table riding the article substrate — every clipping gets child rows in `clipping_claims/events/locations/numbers/quotes/stances` and an entity-link matview (`clipping_entity_mentions`). The older `newspaper_clippings` / `newspaper_editions` / `newspaper_sources` tables are FROZEN (last row 2026-05-26); data collection halted when the live system moved to `clippings`. The Districts/CM-Atlas layer is a Telangana-first, multi-tenant gazetteer: `districts` (59 rows, TG + AP) underpins `article_districts` (49k links), five collector sink tables (all 0 rows = EMPTY/PLANNED, with live health tracking in `source_run_health`), and seven `mv_district_*` matviews; only `mv_district_stability_composite` (59 rows) has live data — the rest await active collectors.

---

## public.clippings — [LIVE] (~12,180 rows, ~varies)

**Purpose:** Primary cuttings table. Each row is one newspaper article extracted from a PDF edition via OCR or vision pipeline. Carries the full article substrate (same columns as `articles`): extraction provenance, enrichment (summary, topic, entities), and geo tagging.
**Populated by:** `backend/tasks/clipping_enrich.py` (Beat task `clipping_enrich`); extraction via PaddleOCR + vision fallback; enrichment via `GROQ_SYS_NEWSPAPER` prompt.
**Read by:** Night-desk `/api/osint/cuttings` endpoints; RAG engine (`retrieve_relevant_newspaper_clippings`); relevance scorer.
**Freshness:** Last `enriched_at` = 2026-06-18 03:43:55 UTC.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| newspaper_source_id | uuid | NO | | FK → newspaper_sources(id) ON DELETE CASCADE |
| headline | text | NO | | Article headline, e.g. "BigBasket names ex-Amazon exec as CEO" |
| body_text | text | YES | | Raw extracted text (OCR or vision) |
| section | varchar(100) | YES | | Newspaper section, e.g. "BUSINESS", "OPINION" |
| language | varchar | YES | | ISO code of source language, e.g. "en", "te" |
| relevance_score | float8 | YES | | Per-user relevance score (0–1) from relevance scorer |
| page_number | int | YES | 1 | Page in the PDF edition |
| bbox | text | YES | | JSON string `[x0,y0,x1,y1]` — pixel bounding box on page |
| edition_date | date | NO | | Date of the newspaper edition |
| collected_at | timestamptz | NO | now() | When PDF was first ingested |
| subheadline | text | YES | | Deck / standfirst line (migration 107) |
| byline | text | YES | | Author credit as printed |
| vision_text | text | YES | | Text extracted via vision model (fallback to OCR) |
| text_source | varchar(8) | YES | | Which extractor won: `ocr` / `vision` / `none` |
| detected_language | varchar(8) | YES | | Language detected by extractor |
| clip_source | varchar(8) | YES | | Body origin: `text` (embedded text layer) / `body` / `layout` / `none` |
| clipping_image_b64 | text | YES | | Base64 crop image (used during vision extraction; may be null after) |
| extraction_confidence | real | YES | | Pipeline confidence (0–1) in the extracted text |
| needs_review | boolean | NO | false | Flagged for human review |
| is_notice | boolean | NO | false | True if classified as a legal/public notice (excluded from cuttings surface) |
| is_duplicate | boolean | NO | false | Detected duplicate of another clipping |
| duplicate_of | int | YES | | ID of the authoritative duplicate (integer, not UUID) |
| source_pdf_path | text | YES | | Path/URL to source PDF |
| article_type | varchar(20) | YES | | Substrate type: `news` / `opinion` / `feature` / `interview` |
| primary_subject | text | YES | | One-sentence subject label |
| headline_translated | text | YES | | English translation of headline |
| body_text_translated | text | YES | | English translation of body |
| summary_preview | text | YES | | Short summary (1–2 sentences) |
| summary_snippet | text | YES | | Medium summary |
| summary_executive | text | YES | | Full executive summary |
| register_style | varchar | YES | | Writing style: `analytical` / `reportage` / `editorial` etc. |
| register_emotion | varchar | YES | | Dominant emotion: `alarm` / `neutral` / `positive` etc. NOTE: event-emotion, not hostility |
| register_is_breaking | boolean | NO | false | True if text signals a breaking story |
| topic_category | varchar | YES | | Coarse topic: `BUSINESS` / `TECHNOLOGY` / `LEGAL` etc. |
| topic_fine | varchar | YES | | Fine-grained topic label |
| entities_extracted | jsonb | YES | | Raw NER output array from spaCy |
| geo_primary | text | YES | | Primary location string, e.g. "Bengaluru" |
| geo_district | text | YES | | Matched district id, e.g. "hyderabad" |
| labse_embedding | vector(768) | YES | | LaBSE v4 embedding for semantic search |
| substrate_status | varchar | NO | 'pending' | Pipeline stage: `pending` / `ok` / `extract_failed` |
| extraction_version | int | NO | 0 | Tracks extractor version for re-processing |
| enriched_at | timestamptz | YES | | Timestamp of last substrate enrichment run |

**Joins:**
- `clipping_claims` / `clipping_events` / `clipping_locations` / `clipping_numbers` / `clipping_quotes` / `clipping_stances` — all FK on `clipping_id`
- `clipping_entity_mentions` matview — aggregated entity links
- `newspaper_sources` — source publication metadata

**Notes:**
- `text_source` distinguishes whether the final body came from embedded PDF text (`ocr`), a vision model (`vision`), or failed (`none`). `clip_source=text` indicates the localized text-layer anchor (highest quality).
- `is_notice` and `is_duplicate` rows are filtered out on the cuttings surface.
- `labse_embedding` uses the locked v4 recipe (migration 107 + d4c7ca8 fix).

---

## public.clipping_claims — [LIVE] (~19,014 rows)

**Purpose:** Structured factual claims extracted from each clipping. Mirrors `article_claims`.
**Populated by:** `clipping_enrich` task via Groq LLM.
**Read by:** RAG engine, analyst, cuttings detail page.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| clipping_id | uuid | NO | | FK → clippings(id) |
| claim_text | text | NO | | Full claim sentence |
| subject_entity_id | uuid | YES | | FK → entity_dictionary(id) — resolved subject entity |
| subject_text | text | YES | | Raw subject string |
| predicate | text | YES | | Predicate verb phrase |
| object_text | text | YES | | Object of the claim |
| confidence | real | NO | 0.5 | Extraction confidence (0–1) |
| created_at | timestamptz | NO | now() | |

**Joins:** `clippings` (clipping_id), `entity_dictionary` (subject_entity_id).

---

## public.clipping_events — [LIVE] (~17,816 rows)

**Purpose:** Structured events (dated occurrences) extracted from each clipping.
**Populated by:** `clipping_enrich` task.
**Read by:** Cuttings timeline panel.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| clipping_id | uuid | NO | | FK → clippings(id) |
| event_date | date | YES | | Date of the event |
| event_description | text | NO | | Narrative description |
| event_type | text | YES | | e.g. `protest` / `policy` / `appointment` |
| actors | text[] | NO | '{}' | Named actors involved |
| confidence | numeric | NO | 0.8 | |
| position | smallint | YES | | Ordinal position in clipping |
| is_future | boolean | NO | false | True if event is scheduled/future |
| created_at | timestamptz | NO | now() | |

**Joins:** `clippings` (clipping_id).

---

## public.clipping_locations — [LIVE] (~20,033 rows)

**Purpose:** Geolocated place mentions from each clipping.
**Populated by:** `clipping_enrich` task.
**Read by:** Geo panel, relevance scorer.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| clipping_id | uuid | NO | | FK → clippings(id) |
| location_text | text | NO | | Raw place name, e.g. "Hyderabad" |
| country | text | YES | | ISO country name |
| region | text | YES | | State/province |
| city | text | YES | | City |
| lat | numeric | YES | | Latitude |
| lng | numeric | YES | | Longitude |
| confidence | numeric | NO | 0.85 | |
| is_primary | boolean | NO | false | True for the dominant location |
| created_at | timestamptz | NO | now() | |

**Joins:** `clippings` (clipping_id).

---

## public.clipping_numbers — [LIVE] (~16,285 rows)

**Purpose:** Numeric/statistical values extracted from each clipping.
**Populated by:** `clipping_enrich` task.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| clipping_id | uuid | NO | | FK → clippings(id) |
| value | text | NO | | The number as a string, e.g. "₹4,200 crore" |
| unit | text | YES | | Unit label, e.g. "crore", "%" |
| context | text | YES | | Sentence providing context |
| position | smallint | YES | | Ordinal position in clipping |
| created_at | timestamptz | NO | now() | |

**Joins:** `clippings` (clipping_id).

---

## public.clipping_quotes — [LIVE] (~7,230 rows)

**Purpose:** Attributable quotations from each clipping.
**Populated by:** `clipping_enrich` task.
**Read by:** Cuttings quotes panel.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| clipping_id | uuid | NO | | FK → clippings(id) |
| speaker_name | text | NO | | Speaker name as printed |
| speaker_entity_id | uuid | YES | | FK → entity_dictionary(id) — resolved speaker |
| quote_text | text | NO | | The quotation |
| is_direct | boolean | NO | true | True if direct quote (in quotes), false if paraphrase |
| context | text | YES | | Attribution context sentence |
| created_at | timestamptz | NO | now() | |

**Joins:** `clippings` (clipping_id), `entity_dictionary` (speaker_entity_id).

---

## public.clipping_stances — [LIVE] (~9,616 rows)

**Purpose:** Actor stance/sentiment towards the topic of each clipping.
**Populated by:** `clipping_enrich` task.
**Read by:** Sentiment analysis, relevance scoring.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| clipping_id | uuid | NO | | FK → clippings(id) |
| actor | text | NO | | Actor name as extracted |
| stance | text | NO | 'neutral' | `positive` / `negative` / `neutral` / `critical` |
| intensity | numeric | NO | 0.5 | Stance strength (0–1) |
| actor_entity_id | uuid | YES | | FK → entity_dictionary(id) — resolved actor |
| created_at | timestamptz | NO | now() | |

**Joins:** `clippings` (clipping_id), `entity_dictionary` (actor_entity_id).

---

## public.clipping_entity_mentions — [LIVE, MATVIEW] (~27,051 rows)

**Purpose:** Materialized view resolving raw `entities_extracted` surface forms in `clippings` to canonical entity IDs via `entity_lookup`. Mirrors `article_entity_mentions` but scoped to clippings only (design isolation §6.1 — never merged into article matviews or CM metrics).
**Populated by:** `REFRESH MATERIALIZED VIEW CONCURRENTLY clipping_entity_mentions` — runs every 30 min via `/etc/cron.d/rig-matview-refresh` on Hetzner.
**Read by:** Entity-based filtering on cuttings surface; RAG engine; Analyst pillar.
**Freshness:** Refreshed on the 30-min cron alongside `article_entity_mentions`.

| column | type | nullable | meaning & example values |
|---|---|---|---|
| clipping_id | uuid | YES | FK → clippings(id) |
| entity_id | uuid | YES | FK → entity_dictionary(id) |
| canonical_name | text | YES | e.g. "Narendra Modi" |
| entity_type | text | YES | `person` / `location` / `organization` |
| country | char(2) | YES | e.g. `IN` |
| surface_forms | text[] | YES | All surface forms matched for this entity in the clipping |
| mention_rows | bigint | YES | Count of entity_lookup rows matched |

**Joins:** Implicitly joins `clippings`, `entity_lookup`, `entity_dictionary` — do not join those again when querying this view.

**Notes:** Created by migration 107 (`DROP MATERIALIZED VIEW IF EXISTS ... CREATE MATERIALIZED VIEW clipping_entity_mentions AS SELECT ...`). Requires `CONCURRENTLY` refresh — has a unique index on `(clipping_id, entity_id)`.

---

## public.newspaper_clippings — [FROZEN since 2026-05-26] (~5,170 rows, 387 MB)

**Purpose:** Legacy cuttings table from the original newspaper scraper (migration 005). Superseded by `clippings` (migration 105/107). Contains 5,170 rows from editions collected before the switch; no new rows since 2026-05-26.
**Populated by:** Legacy `newspaper_clippings` collector (now inactive).
**Read by:** RAG engine still calls `retrieve_relevant_newspaper_clippings` which may query both tables (inferred); primary product surface now uses `clippings`.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| newspaper_id | uuid | NO | | FK → newspaper_sources(id) |
| newspaper_name | text | NO | | Denormalized publication name |
| newspaper_language | text | YES | 'en' | ISO language code |
| edition_date | date | NO | | Edition date |
| page_number | int | YES | | Page number |
| headline | text | YES | | Article headline |
| headline_translated | text | YES | | English translation |
| article_text | text | YES | | Extracted body text |
| article_text_translated | text | YES | | English translation of body |
| bbox_left / bbox_bottom / bbox_right / bbox_top | float8 | YES | | Bounding box coordinates (4 columns) |
| clipping_image_b64 | text | YES | | Base64 crop image |
| topic_category | text | YES | | e.g. "POLITICS" |
| geo_primary | text | YES | | Primary geo label |
| entities_extracted | jsonb | YES | '[]' | Raw NER output |
| relevance_score | float8 | YES | | Relevance score |
| relevance_explanation | text | YES | | Explanation text |
| labse_embedding | vector(768) | YES | | LaBSE embedding |
| sentiment | text | YES | | Overall sentiment label |
| narrative_angle | text | YES | | Editorial framing label |
| collected_at | timestamptz | YES | now() | Ingest timestamp |

**Joins:** `newspaper_sources` (newspaper_id).

**Notes:** UNIQUE on `(newspaper_id, edition_date, headline)`. Has an HNSW index on `labse_embedding`. 387 MB predominantly from `clipping_image_b64` blobs. Not updated; treat as read-only historical corpus.

---

## public.newspaper_editions — [FROZEN since 2026-05-26] (~448 rows, 152 kB)

**Purpose:** Registry of fetched PDF editions (one row = one edition PDF). FK parent for `newspaper_clippings`.
**Populated by:** Legacy newspaper collector.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| newspaper_id | uuid | NO | | FK → newspaper_sources(id) ON DELETE CASCADE |
| edition_date | date | NO | | Edition date |
| pdf_url | text | NO | | URL to the PDF |
| fetched_at | timestamptz | NO | now() | When PDF was downloaded |

**PK:** `(newspaper_id, edition_date)`.
**Joins:** `newspaper_sources` (newspaper_id).
**Notes:** Last row 2026-05-26. The live system does not write new editions here; `clippings.edition_date` + `clippings.source_pdf_path` carry this information for active ingestion.

---

## public.newspaper_sources — [LIVE] (~50 rows, 96 kB)

**Purpose:** Registry of newspaper publications. Shared FK parent for both the legacy `newspaper_clippings` system and the live `clippings` table.
**Populated by:** Manual seeding + `006_expand_newspaper_sources.sql`.
**Read by:** Cuttings ingest pipeline; both `clippings` and `newspaper_clippings`.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| name | text | NO | | Publication name, e.g. "The Hindu" — UNIQUE |
| language | text | NO | 'en' | ISO language code |
| careerswave_url | text | YES | | CareersWave PDF portal URL |
| direct_pdf_url | text | YES | | Direct PDF download URL |
| is_active | boolean | YES | true | Whether this source is actively scraped |
| last_scraped_at | timestamptz | YES | | Last successful scrape timestamp |
| created_at | timestamptz | YES | now() | |

**Joins:** `clippings` (newspaper_source_id), `newspaper_clippings` (newspaper_id), `newspaper_editions` (newspaper_id).

---

## public.districts — [LIVE] (~59 rows, 96 kB)

**Purpose:** Gazetteer of districts. Primary aggregation grain for the CM Atlas heatmap. Seeded with Telangana (33 districts) and Andhra Pradesh districts; multi-tenant via `state_code`.
**Populated by:** Seed script `scripts/seeds/districts_telangana.sql` + AP seed; migration 041 added multi-tenant support.
**Read by:** `article_districts`, all CM atlas matviews, district modal endpoints (`/api/cm/atlas/`).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | text | NO | | PK — slug, e.g. `hyderabad`, `adilabad`, `ntr` |
| state_code | text | NO | | ISO-style state code, e.g. `TG`, `AP` |
| name | text | NO | | Display name, e.g. "HYDERABAD", "ADILABAD" |
| hq_city | text | NO | | District HQ city, e.g. "Hyderabad" |
| centroid_lat | float8 | NO | | Centroid latitude, e.g. 17.4199 |
| centroid_lon | float8 | NO | | Centroid longitude, e.g. 78.4815 |
| bbox | jsonb | YES | | Bounding box `{west,south,east,north}` |
| aliases | text[] | NO | | Alternative names matched during NER lookup |
| inserted_at | timestamptz | NO | now() | |

**Joins:** `article_districts`, `acled_events`, `air_quality_readings`, `mandi_prices`, `power_grid_status`, `weather_warnings`, `welfare_coverage`, `assembly_constituencies` (via `district` text match).

**Notes:** `id` is a text slug (not UUID). 59 rows live despite migration comment saying "33-row" — AP districts were added in a follow-up seed.

---

## public.article_districts — [LIVE] (~49,654 rows, 10 MB)

**Purpose:** Many-to-many between articles and districts. One article can tag multiple districts; `is_primary` flags the highest-confidence district for each article.
**Populated by:** `tasks.cm.tag_article_districts` (live, hooked into NLP processor); `tasks.cm.backfill_district_geo` (one-shot backfill).
**Read by:** CM Atlas news-volume layer; district modal.
**Freshness:** Last `inserted_at` = 2026-06-11 06:26:18 UTC.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| article_id | uuid | NO | | FK → articles(id) ON DELETE CASCADE |
| district_id | text | NO | | FK → districts(id) ON DELETE CASCADE |
| mention_count | int | NO | 1 | Number of times district was mentioned |
| confidence | real | NO | | NER resolution confidence (0–1), e.g. 0.775 |
| is_primary | boolean | NO | false | True for the dominant district per article |
| inserted_at | timestamptz | NO | now() | |

**PK:** `(article_id, district_id)` (inferred — composite).
**Joins:** `articles` (article_id), `districts` (district_id).

---

## public.assembly_constituencies — [LIVE] (~29 rows, 96 kB)

**Purpose:** ECI assembly constituency roster. Partial seed: 29 Hyderabad-area ACs (ECI numbers 49–66). Remaining Telangana and AP ACs not yet loaded.
**Populated by:** Manual seed from ECI delimitation roster; `state_code` column added in migration 041.
**Read by:** CM Page map (§VII), constituency modal.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| code | text | NO | | PK — ECI AC code string |
| state | text | NO | | State name, e.g. "Telangana" |
| number | int | NO | | ECI AC number, e.g. 49–66 for Hyderabad |
| name | text | NO | | AC name in English |
| name_te | text | YES | | AC name in Telugu |
| district | text | YES | | Parent district name (text, not FK) |
| parliamentary | text | YES | | Parent parliamentary constituency |
| reservation | text | YES | 'GEN' | Reservation category: `GEN` / `SC` / `ST` |
| centroid_lat | float8 | YES | | Centroid latitude |
| centroid_lon | float8 | YES | | Centroid longitude |
| source_url | text | YES | | ECI source URL |
| state_code | text | NO | | e.g. `TG` — added migration 041 |
| inserted_at | timestamptz | NO | now() | |

**Notes:** Intentionally partial — loading the remaining 101 TG + 175 AP ACs requires the verified ECI roster file; do not hand-enter.

---

## public.district_geo_backfill_cursor — [LIVE] (~1 row, 64 kB)

**Purpose:** Resumable cursor for the `backfill_district_geo` task. One row per surface (`articles`, `social_posts`) records progress so the task can resume after a crash without reprocessing.
**Populated by:** `tasks.cm.backfill_district_geo`.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| surface | text | NO | | PK — surface name, e.g. `articles` |
| last_processed | uuid | YES | | Last article/post UUID processed |
| rows_done | bigint | NO | 0 | Running count of rows processed |
| updated_at | timestamptz | NO | now() | |

**Notes:** Only 1 row currently (backfill likely complete for articles surface).

---

## public.source_run_health — [LIVE] (~6 rows, 136 kB)

**Purpose:** Per-scraper health tracking for CM atlas layer collectors. Read by `/api/cm/atlas/layer` endpoints to mark a layer as "data degraded" when `last_success_at` is stale.
**Populated by:** Each CM atlas collector task on run completion.
**Freshness:** `updated_at` = 2026-06-19 15:48 UTC (tgspdcl_power most recent).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| source_id | text | NO | | PK — collector name, e.g. `mandi_agmarknet`, `tgspdcl_power`, `cpcb_aqi`, `imd_weather`, `welfare_coverage`, `acled_sink` |
| last_success_at | timestamptz | YES | | Timestamp of last successful run |
| last_failure_at | timestamptz | YES | | Timestamp of last failure |
| last_failure | text | YES | | Error message from last failure |
| consecutive_failures | int | NO | 0 | Current failure streak; e.g. `mandi_agmarknet`=182, `tgspdcl_power`=1456, `cpcb_aqi`=2616 — all collectors are currently failing |
| rows_last_run | int | YES | | Rows written in last run |
| updated_at | timestamptz | NO | now() | |

**Notes:** `imd_weather` is the only source with a `last_success_at` (2026-06-19); all others show only failures. `consecutive_failures` in the hundreds indicates long-running collector failures (parsers broken or upstream APIs changed).

---

## public.mv_district_acled_7d — [EMPTY] (0 rows, 16 kB)

**Purpose:** CM v2 atlas — ACLED conflict-event layer. 7-day rolling count of conflict events and fatalities per district.
**Source:** Aggregates `acled_events`. Empty because `acled_events` has 0 rows (collector failing — 123 consecutive failures).
**Refreshed by:** 30-min matview cron.

| column | type | nullable | meaning & example values |
|---|---|---|---|
| district_id | text | YES | FK → districts(id) |
| value | bigint | YES | Event count in last 7 days |
| total_fatalities | bigint | YES | Fatalities in last 7 days |
| computed_at | timestamptz | YES | Refresh timestamp |

---

## public.mv_district_mandi_volatility_30d — [EMPTY] (0 rows, 16 kB)

**Purpose:** CM v2 atlas — commodity price volatility layer. 30-day price spread across AGMARKNET mandis per district.
**Source:** Aggregates `mandi_prices`. Empty because `mandi_prices` has 0 rows.

| column | type | nullable | meaning & example values |
|---|---|---|---|
| district_id | text | YES | FK → districts(id) |
| value | float8 | YES | Volatility score |
| commodity_count | bigint | YES | Distinct commodities tracked |
| computed_at | timestamptz | YES | Refresh timestamp |

---

## public.mv_district_news_volume_24h — [EMPTY] (0 rows, 64 kB)

**Purpose:** CM v2 atlas — news hotspot layer. 24-hour article volume per district, weighted by NER confidence.
**Source:** Aggregates `article_districts`. Empty despite `article_districts` having 49k rows — likely a WHERE clause filtering on `inserted_at > now()-24h` returning 0 (no new tagging since 2026-06-11).
**Refreshed by:** 30-min cron.

| column | type | nullable | meaning & example values |
|---|---|---|---|
| district_id | text | YES | FK → districts(id) |
| value | float8 | YES | Weighted volume score |
| article_count | bigint | YES | Articles mentioning district in last 24h |
| avg_confidence | float8 | YES | Mean NER confidence |
| computed_at | timestamptz | YES | Refresh timestamp |

---

## public.mv_district_power_stress — [EMPTY] (0 rows, 16 kB)

**Purpose:** CM v2 atlas — power stress layer. Average supply deficit (MW) per district.
**Source:** Aggregates `power_grid_status`. Empty because `power_grid_status` has 0 rows (1,456 consecutive collector failures).

| column | type | nullable | meaning & example values |
|---|---|---|---|
| district_id | text | YES | FK → districts(id) |
| value | float8 | YES | Stress score (0–100) |
| avg_deficit_mw | float8 | YES | Average MW deficit |
| computed_at | timestamptz | YES | Refresh timestamp |

---

## public.mv_district_stability_composite — [LIVE] (59 rows, 88 kB)

**Purpose:** CM v2 atlas — composite stability score per district. Weighted blend: AQI 30% + heat 25% + ACLED conflict 25% + news volume 20%. Currently all districts show value=100 (all sub-components = 1) because the three data sources (AQI, ACLED, power) have 0 data; only news component contributes.
**Refreshed by:** 30-min cron on Hetzner.
**Freshness:** `computed_at` = 2026-06-19 15:30:24 UTC.

| column | type | nullable | meaning & example values |
|---|---|---|---|
| district_id | text | YES | FK → districts(id) |
| value | float8 | YES | Composite score (0–100); currently 100 for all districts |
| aqi_component | float8 | YES | AQI sub-score |
| heat_component | numeric | YES | Heat sub-score |
| acled_component | float8 | YES | Conflict sub-score |
| news_component | float8 | YES | News volume sub-score |
| computed_at | timestamptz | YES | Refresh timestamp |

**Notes:** Value=100 for all 59 districts is a data artifact — no ACLED, AQI, or power data flowing. Do not interpret as "stable"; it means "no negative signal received."

---

## public.mv_district_welfare_coverage — [EMPTY] (0 rows, 16 kB)

**Purpose:** CM v2 atlas — welfare scheme coverage layer. Average scheme coverage percentage per district.
**Source:** Aggregates `welfare_coverage`. Empty because `welfare_coverage` has 0 rows (31 consecutive collector failures).

| column | type | nullable | meaning & example values |
|---|---|---|---|
| district_id | text | YES | FK → districts(id) |
| value | float8 | YES | Mean coverage pct (0–100) |
| schemes_tracked | bigint | YES | Number of schemes tracked |
| worst_scheme_pct | float8 | YES | Minimum coverage % across schemes |
| computed_at | timestamptz | YES | Refresh timestamp |

---

## public.acled_events — [EMPTY/PLANNED] (0 rows, 40 kB)

**Purpose:** Sink for ACLED conflict-event feed. Powers `mv_district_acled_7d` and district modal conflict panel.
**Intended collector:** `tasks.collectors.acled_sink` (every 6h) — registered in Celery, 123 consecutive failures.
**Schema only, no data yet.**

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| event_id | text | NO | | PK — ACLED event ID |
| event_date | date | NO | | Date of conflict event |
| event_type | text | NO | | e.g. `Protests` / `Violence against civilians` |
| sub_type | text | YES | | Sub-classification |
| actor1 | text | YES | | Primary actor |
| actor2 | text | YES | | Secondary actor |
| fatalities | int | NO | 0 | Fatality count |
| lat | float8 | YES | | Latitude |
| lon | float8 | YES | | Longitude |
| state_code | text | YES | | e.g. `TG` |
| district_id | text | YES | | FK → districts(id) |
| notes | text | YES | | Event narrative from ACLED |
| raw | jsonb | YES | | Full ACLED API response |
| inserted_at | timestamptz | NO | now() | |

---

## public.air_quality_readings — [EMPTY/PLANNED] (0 rows — inferred from source_run_health)

**Purpose:** AQI readings from CPCB stations per district. Powers `mv_district_stability_composite` AQI component.
**Intended collector:** `tasks.collectors.cpcb_aqi_task` — 2,616 consecutive failures (longest-running outage).
**Schema only, no data yet.**

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | bigint | NO | nextval(seq) | PK |
| station | text | NO | | Station name |
| station_code | text | YES | | CPCB station code |
| district_id | text | YES | | FK → districts(id) |
| state_code | text | NO | | e.g. `TG` |
| aqi | int | YES | | AQI index value |
| aqi_category | text | YES | | `Good` / `Moderate` / `Poor` / `Very Poor` / `Severe` |
| pm25 | real | YES | | PM2.5 µg/m³ |
| pm10 | real | YES | | PM10 µg/m³ |
| no2 | real | YES | | NO₂ µg/m³ |
| so2 | real | YES | | SO₂ µg/m³ |
| co | real | YES | | CO mg/m³ |
| o3 | real | YES | | O₃ µg/m³ |
| recorded_at | timestamptz | NO | | Station reading timestamp |
| inserted_at | timestamptz | NO | now() | |

---

## public.mandi_prices — [EMPTY/PLANNED] (0 rows, 40 kB)

**Purpose:** AGMARKNET commodity prices per district. Powers `mv_district_mandi_volatility_30d`. Prices in paise per quintal.
**Intended collector:** `tasks.collectors.mandi_agmarknet` (every 4h) — 182 consecutive failures.
**Schema only, no data yet.**

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | bigint | NO | nextval(seq) | PK |
| district_id | text | YES | | FK → districts(id) |
| state_code | text | NO | | e.g. `TG` |
| commodity | text | NO | | Commodity name, e.g. "Tomato" |
| variety | text | YES | | Variety label |
| market | text | YES | | Market/mandi name |
| min_price | int | YES | | Minimum price (paise/quintal) |
| max_price | int | YES | | Maximum price |
| modal_price | int | YES | | Modal (most common) price |
| arrival_qty | real | YES | | Arrival quantity (quintals) |
| recorded_at | date | NO | | Date of price record |
| inserted_at | timestamptz | NO | now() | |

---

## public.power_grid_status — [EMPTY/PLANNED] (0 rows, 32 kB)

**Purpose:** TGSPDCL power supply/demand readings per district. Powers `mv_district_power_stress`.
**Intended collector:** `tasks.collectors.tgspdcl_power` (every 30m) — 1,456 consecutive failures.
**Schema only, no data yet.**

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | bigint | NO | nextval(seq) | PK |
| district_id | text | YES | | FK → districts(id) |
| state_code | text | NO | | `TG` |
| demand_mw | int | YES | | Power demand in MW |
| supply_mw | int | YES | | Power supply in MW |
| deficit_mw | int | YES | (supply_mw - demand_mw) | Generated column: negative = deficit |
| feeder_status | text | YES | | Feeder status description |
| notes | text | YES | | Additional notes |
| recorded_at | timestamptz | NO | | Reading timestamp |
| inserted_at | timestamptz | NO | now() | |

**Notes:** `deficit_mw` is a generated column (computed from supply-demand).

---

## public.weather_warnings — [EMPTY/PLANNED] (0 rows, 40 kB)

**Purpose:** IMD weather warnings per district. Powers `mv_district_stability_composite` heat component.
**Intended collector:** `tasks.collectors.imd_weather_task` (every 1h) — `imd_weather` is the **only** collector with a recent `last_success_at` (2026-06-19), but 0 rows persisted; warnings may have expired before insertion or the write path is broken.
**Schema only, no data yet.**

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | bigint | NO | nextval(seq) | PK |
| district_id | text | YES | | FK → districts(id) |
| state_code | text | NO | | e.g. `TG` |
| kind | text | NO | | Warning type, e.g. `cyclone` / `heavy_rain` / `heatwave` |
| severity | text | NO | | `yellow` / `orange` / `red` |
| headline | text | YES | | Warning headline |
| detail | text | YES | | Extended warning detail |
| valid_from | timestamptz | NO | | Warning start time |
| valid_to | timestamptz | NO | | Warning expiry time |
| issued_at | timestamptz | NO | | IMD issuance timestamp |
| payload | jsonb | YES | | Raw IMD API response |
| inserted_at | timestamptz | NO | now() | |

---

## public.welfare_coverage — [EMPTY/PLANNED] (0 rows, ~16 kB)

**Purpose:** Government welfare scheme coverage statistics per district. Powers `mv_district_welfare_coverage`.
**Intended collector:** `tasks.collectors.welfare_coverage_task` — 31 consecutive failures.
**Schema only, no data yet.**

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | bigint | NO | nextval(seq) | PK |
| scheme | text | NO | | Scheme name, e.g. "PM-KISAN" |
| district_id | text | YES | | FK → districts(id) |
| state_code | text | NO | | e.g. `TG` |
| beneficiaries | int | YES | | Enrolled beneficiaries |
| target | int | YES | | Target beneficiary count |
| coverage_pct | real | YES | | beneficiaries/target × 100 |
| detail | text | YES | | Additional detail text |
| cycle_label | text | YES | | Reporting cycle, e.g. "2025-Q4" |
| recorded_at | date | NO | | Date of measurement |
| inserted_at | timestamptz | NO | now() | |

---

## public.coverage_gaps_daily — [LIVE] (~31 rows, 96 kB)

**Purpose:** Daily snapshot of entities that have high social volume but low article coverage. Powers the "Coverage Gaps" panel. Not a CM atlas collector — produced by an analytics task.
**Populated by:** Periodic analytics task (inferred from table comment).
**Read by:** Night-desk coverage gaps panel.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| detected_for_date | date | NO | | The date this gap was detected |
| entity_id | uuid | NO | | FK → entity_dictionary(id) — the under-covered entity |
| social_volume_7d | int | NO | 0 | Social post count in 7 days |
| article_volume_7d | int | NO | 0 | Article count in 7 days |
| ratio | real | NO | 0.0 | social_volume / article_volume — higher = bigger gap |
| summary | text | NO | '' | Natural-language summary of the gap |
| detected_at | timestamptz | NO | now() | |

**Joins:** `entity_dictionary` (entity_id).

---

*Generated 2026-06-19. Verified against live DB (Hetzner rig-postgres), migration files, and schema export files.*
