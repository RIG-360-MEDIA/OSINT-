# Corpus Core + NLP Substrate

## Domain overview

This domain contains the primary article corpus and every structured fact extracted from it by the v3 substrate pipeline. `articles` is the spine: every other table in this domain is a child of it. `sources` is the registry of RSS/HTML origins that feeds `articles`. The eight substrate tables (`article_claims`, `article_stances`, `article_quotes`, `article_numbers`, `article_events`, `article_locations`, `article_media`, `article_links`) are populated per-article by Groq-backed Celery tasks on the `nlp` queue. `article_tweets` captures embedded tweets scraped from article HTML. `article_contradictions` cross-links pairs of claims flagged as divergent by an NLI pass.

**Pipeline note:** RSS/HTML scrape → `articles` (raw collect) → substrate extraction (`substrate_status`: pending → ok/junk/failed) → child rows inserted into the eight substrate tables → embeddings written by `embed_fill` (locked V4 recipe: translated lead + title, `embedding_revision='v4-tr-title-1024'`, writes both `labse_embedding` and `labse_embedding_v4`). Embeddings and NLP extraction are independent Celery tasks; both gate on `substrate_status='ok'`.

---

## public.sources — [LIVE] (~1,229 rows, 3.9 MB)

**Purpose:** Registry of every ingest origin (RSS feeds, scraped sites, YouTube channels, etc.).
**Populated by:** manual seed + collector registration at source onboarding.
**Read by:** article ingest tasks, relevance scorer, night-desk API for source metadata.
**Freshness:** static registry; `last_collected_at` updated on each collection run.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NOT NULL | gen_random_uuid() | PK |
| name | text | NOT NULL | — | Display name, e.g. `The Hindu` |
| domain | text | NOT NULL | — | Root domain, UNIQUE suffix convention, e.g. `thehindu.com` |
| rss_url | text | NULL | — | Feed URL; NULL for scrape-only sources |
| source_type | text | NOT NULL | — | e.g. `rss`, `scrape`, `youtube`, `newspaper` |
| source_tier | integer | NOT NULL | 2 | 1=national flagship, 2=regional, 3=hyperlocal |
| language | text | NULL | `'en'` | BCP-47 language tag of primary publication language |
| geo_states | text[] | NULL | `'{}'` | State tags for filtering, e.g. `{Telangana,Andhra Pradesh}` |
| topics | text[] | NULL | `'{}'` | Editorial topic tags assigned at registration |
| health_score | double precision | NULL | 1.0 | Decay score based on consecutive fetch failures (0.0–1.0) |
| consecutive_failures | integer | NULL | 0 | Incremented per failed collect; reset on success |
| is_active | boolean | NULL | true | False = paused from collection |
| last_collected_at | timestamptz | NULL | — | Last successful collection timestamp |
| created_at | timestamptz | NULL | now() | Registration timestamp |
| country | char(2) | NOT NULL | `'XX'` | ISO 3166-1 alpha-2 country code (`IN`, `US`, `XX`=unknown). Prefer over `geo_states` for country-level grouping. |
| political_lean | text | NULL | — | Editorial lean label (sparse; values seen: NULL-dominant) |

**Joins:** `articles.source_id → sources.id`.
**Notes:** `geo_states` is a text array for multi-state sources; for country grouping use `country` column, not `unnest(geo_states)`. `source_tier` denormalised into `articles.source_tier` at insert time.

---

## public.articles — [LIVE] (~354,839 rows, 9.6 GB)

**Purpose:** Spine of the corpus — one row per collected article/page. All substrate tables FK back here.
**Populated by:** `backend/tasks/nlp_processor.py` (NLP pass) + RSS/HTML collectors; substrate columns filled by `embed_fill` and Groq extraction tasks.
**Read by:** Night-desk API (`products/osint/backend`), relevance scorer, clustering pipeline, brief generator, RAG retrieval.
**Freshness:** `max(collected_at)` = 2026-06-19 (active); `max(substrate_processed_at)` also current.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NOT NULL | gen_random_uuid() | PK |
| source_id | uuid | NOT NULL | — | FK → sources.id |
| url | text | NOT NULL | — | Original article URL |
| url_hash | text | NOT NULL | — | UNIQUE; SHA/MD5 of normalised URL — primary dedup key at ingest |
| title | text | NOT NULL | — | Article headline (original language) |
| lead_text_original | text | NULL | — | First paragraph or meta description in original language |
| lead_text_translated | text | NULL | — | English translation of lead_text_original (by Groq) |
| full_text_scraped | text | NULL | — | Full body text extracted from HTML |
| full_text_translated | text | NULL | — | Full body translated to English |
| language_detected | varchar(10) | NULL | — | Language code detected at scrape time (legacy field) |
| language_iso | text | NULL | — | ISO 639-1 code, e.g. `te`, `hi`, `en` (preferred over language_detected) |
| published_at | timestamptz | NULL | — | Publication timestamp from RSS/meta; NULL if not parseable |
| collected_at | timestamptz | NOT NULL | now() | When the row was inserted by the collector |
| updated_at | timestamptz | NULL | now() | Last update timestamp |
| content_type | text | NOT NULL | `'article'` | Always `article` for this table; other values reserved |
| source_tier | integer | NULL | — | Denormalised from `sources.source_tier` at insert |
| source_country | char(2) | NULL | — | Denormalised from `sources.country` via INSERT trigger (ISO 3166-1 alpha-2) |
| thumbnail_url | text | NULL | — | Hero image URL |
| byline | text | NULL | — | Raw byline string |
| author_name | text | NULL | — | Extracted/normalised author name |
| canonical_url | text | NULL | — | Canonical URL if different from `url` (used for cross-source dedup comparison) |
| word_count | integer | NULL | — | Body word count |
| reading_minutes | smallint | NULL | — | Estimated reading time |
| body_quality | text | NULL | `'unknown'` | `high` / `medium` / `low` / `unknown` — Unicode-aware junk score |
| **NLP / processing flags** | | | | |
| nlp_processed | boolean | NULL | false | True after first NLP pass (entities, topic, geo). Legacy gate; prefer `substrate_status`. |
| nlp_claimed_at | timestamptz | NULL | — | Timestamp when the NLP worker claimed the row (advisory lock pattern) |
| nlp_confidence | text | NULL | `'normal'` | Confidence tier of NLP output: `normal` / `low` |
| claims_extracted | boolean | NOT NULL | false | True after article_claims rows written |
| quotes_extracted | boolean | NOT NULL | false | True after article_quotes rows written |
| substrate_status | text | NULL | `'pending'` | Pipeline state: `pending` → `ok` / `fetch_failed` / `extract_failed` / `junk` / `skipped` |
| substrate_processed_at | timestamptz | NULL | — | Timestamp of last substrate extraction attempt |
| extraction_version | smallint | NULL | 1 | Substrate schema version (increment to trigger re-extraction) |
| **Classification** | | | | |
| article_type | text | NULL | — | `news` / `opinion` / `analysis` / `listicle` / `horoscope` / `recipe` / `live_blog` / `photo_essay` / `interview` / `press_release` / `other`. Set by Groq classifier. |
| article_type_orig | text | NULL | — | Pre-correction value of article_type (saved before classifier override) |
| topic_category | text | NULL | — | Coarse topic bucket, e.g. `Politics`, `Crime`, `Economy`. Set by NLP classifier. |
| topic_category_orig | text | NULL | — | Pre-correction value of topic_category |
| topic_fine | text | NULL | — | Richer 25-bucket topic (see topic_categories table). Populated after 2026-05-30; NULL for older rows → fall back to topic_category. Not FK-constrained. |
| geo_primary | text | NULL | — | Primary geographic focus (state/city/country string), e.g. `Telangana` |
| geo_secondary | text[] | NULL | `'{}'` | Hotfix remnant (migration 088); nothing reads it; scheduled for DROP |
| primary_subject | text | NULL | — | Short free-text primary subject label from substrate pass |
| **Summarisation** | | | | |
| summary_preview | text | NULL | — | 1–2 sentence teaser summary |
| summary_snippet | text | NULL | — | Medium summary (~3–5 sentences) |
| summary_executive | text | NULL | — | Full executive summary for analyst/brief use |
| **Register / tone** | | | | |
| narrative_frame | text | NULL | — | Groq-tagged framing label (e.g. `accountability`, `victim`). Powers Source Comparator framing diffs. |
| register_style | text | NULL | — | Writing style label from substrate |
| register_emotion | text | NULL | — | Event-emotion label (e.g. `alarm`, `celebration`). NOTE: this is NOT hostility/negativity — it is the emotion of the event being reported, not editorial stance. Use `article_stances` for negativity/bias measures. |
| register_is_breaking | boolean | NULL | false | True if article was flagged as breaking news |
| **Entities** | | | | |
| entities_extracted | jsonb | NULL | `'[]'` | Inline entity array (spaCy local extraction). Format: `[{"text": "KCR", "label": "PERSON"}, ...]`. Populated by NLP worker; may be stale if entity_collapse occurred. |
| thread_id | uuid | NULL | — | Stub for thread grouping (freeze noted 2026-05-25; currently stale) |
| **Deduplication** | | | | |
| is_duplicate | boolean | NULL | false | True if this row is a duplicate of another article |
| duplicate_of | uuid | NULL | — | FK → articles.id of the canonical version |
| **Embeddings** | | | | |
| labse_embedding | vector(768) | NULL | — | Active search embedding. V4 recipe: LaBSE over `[translated_lead + title]`, written by `embed_fill`. WARNING: pre-V4 rows (stamped with wrong recipe) also exist here — filter by `embedding_revision = 'v4-tr-title-1024'` for homogeneous retrieval. |
| labse_embedding_v4 | vector(768) | NULL | — | Shadow column written simultaneously with `labse_embedding` by embed_fill (V4 recipe). Exists for safe swap during re-embed campaign. |
| labse_embedding_v0_backup | vector(768) | NULL | — | Backup of original (lead-only) embedding before V4 campaign overwrote `labse_embedding`. |
| embedded_at | timestamptz | NULL | — | When `labse_embedding` was last written. NULL for pre-2026-05-30 vectors. |
| embedding_model | text | NULL | — | Model id, e.g. `sentence-transformers/LaBSE`. NULL = unknown (pre-provenance). |
| embedding_revision | text | NULL | — | Pinned HF commit hash / recipe tag, e.g. `v4-tr-title-1024`. NULL = unknown. Mixed non-null values → incomparable vector space. |
| **Full-text search** | | | | |
| fts | tsvector | NULL | (generated) | Generated tsvector: title=weight A, lead_text=weight B. Used in BM25 leg of RRF hybrid retrieval. |

**Joins:**
- `articles.source_id → sources.id`
- `articles.duplicate_of → articles.id` (self-referential)
- All substrate tables → `articles.id`
- `user_article_relevance.article_id → articles.id`
- `article_districts.article_id → articles.id`

**Notes:**
- Primary dedup key is `url_hash` (UNIQUE index). `canonical_url` used for softer cross-source dedup comparison.
- Embedding recipe: `embed_fill` is the SOLE owner of `labse_embedding`. `nlp_processor` was previously writing a lead-only embedding into this column, causing recipe-mix drift; that behaviour was removed. Always filter `embedding_revision = 'v4-tr-title-1024'` before doing cosine search to exclude mixed-recipe rows.
- `register_emotion` reflects event-emotion (e.g. `alarm` on a flood story is about the flood, not editorial hostility). Never use it as a negativity/bias proxy — use `article_stances` instead.
- `geo_secondary` is a dead column pending DROP; ignore it.
- Live substrate_status distribution (sampled 2026-06-19): `ok` = majority, `pending` ≈ recent uncollected, `junk`/`fetch_failed`/`extract_failed` = smaller tails.
- Live article_type distribution: `news` dominant, then `opinion`, `analysis`, `press_release`.
- Live topic_category distribution: `Politics`, `Crime`, `Economy`, `International` are top buckets.
- V4 re-embed campaign was in progress as of 2026-06-19: `labse_embedding_v4` was being populated; some rows had only `labse_embedding_v0_backup` (old recipe).

---

## public.article_claims — [LIVE] (~687,106 rows, 2.6 GB)

**Purpose:** Factual claims extracted per article in Subject-Predicate-Object form. Powers Contradictions inbox, Compare mode, claim-search.
**Populated by:** `nlp` queue Groq tasks (`llama-3.1-8b-instant` by default), gated by `claims_extracted=false`.
**Read by:** `article_contradictions` detection, Compare mode, Analyst RAG.
**Freshness:** `max(extracted_at)` current (2026-06-19).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NOT NULL | gen_random_uuid() | PK |
| article_id | uuid | NOT NULL | — | FK → articles.id |
| claim_text | text | NOT NULL | — | Full claim sentence, e.g. `KCR announced ₹6,000 crore investment in Hyderabad` |
| subject_text | text | NULL | — | Subject entity string extracted from claim |
| subject_entity_id | uuid | NULL | — | FK → entity_dictionary.id (resolved entity for subject) |
| predicate | text | NULL | — | Verb/predicate, e.g. `announced`, `allocated` |
| object_text | text | NULL | — | Object of the claim |
| confidence | real | NOT NULL | 0.5 | LLM confidence score (0.0–1.0) |
| embedding | vector(768) | NULL | — | Claim-level LaBSE embedding for semantic claim search |
| extracted_at | timestamptz | NOT NULL | now() | Extraction timestamp |
| extracted_by_model | text | NOT NULL | `'llama-3.1-8b-instant'` | Model that extracted this claim |

**Joins:**
- `article_claims.article_id → articles.id`
- `article_claims.subject_entity_id → entity_dictionary.id`
- `article_contradictions.claim_a_id → article_claims.id`
- `article_contradictions.claim_b_id → article_claims.id`

**Notes:** 687k rows for 354k articles ≈ ~2 claims/article average. Older articles may have 0 claims if they were processed before the claims extraction task was active. The `claims_extracted` flag on `articles` is the authoritative gate — check it, not existence of child rows.

---

## public.article_contradictions — [LIVE] (~1 row, 80 kB)

**Purpose:** Pairs of claims flagged as divergent by a Groq NLI pass (llama-3.3-70b-versatile). Powers Contradictions inbox.
**Populated by:** `nlp` queue contradiction detection task.
**Read by:** Night-desk Contradictions UI.
**Freshness:** Effectively empty at time of snapshot (1 row). The detection task depends on sufficient claim coverage first.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NOT NULL | gen_random_uuid() | PK |
| claim_a_id | uuid | NOT NULL | — | FK → article_claims.id (first claim) |
| claim_b_id | uuid | NOT NULL | — | FK → article_claims.id (second claim) |
| entity_id | uuid | NULL | — | FK → entity_dictionary.id (entity the claims disagree about) |
| divergence_summary | text | NOT NULL | — | NLI-generated summary of the contradiction |
| confidence | real | NOT NULL | 0.5 | NLI confidence score |
| detected_at | timestamptz | NOT NULL | now() | Detection timestamp |
| detected_by_model | text | NOT NULL | `'llama-3.3-70b-versatile'` | Model that detected the contradiction |
| is_resolved | boolean | NOT NULL | false | True if an editor dismissed/resolved the contradiction |

**Joins:** `claim_a_id`, `claim_b_id` → `article_claims.id`; `entity_id` → `entity_dictionary.id`.
**Notes:** Table is essentially empty (~1 row). The NLI pipeline depends on `article_claims` having sufficient density; at scale expect ~0.1–0.5% of claim pairs to produce contradictions.

---

## public.article_stances — [LIVE] (~483,322 rows, 100 MB)

**Purpose:** Directed-sentiment stances extracted per article — one row per (article, target-entity) pair.
**Populated by:** `nlp` queue Groq extraction tasks.
**Read by:** Brief trending, watchlist matchers, `article_entity_mentions` matview, Source Comparator bias analysis.
**Freshness:** `max(created_at)` current (2026-06-19).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NOT NULL | gen_random_uuid() | PK |
| article_id | uuid | NOT NULL | — | FK → articles.id |
| actor | text | NOT NULL | — | **TARGET entity name** (see critical note below) |
| actor_entity_id | uuid | NULL | — | FK → entity_dictionary.id for the target entity |
| stance | text | NULL | — | Stance label toward the target, e.g. `positive`, `negative`, `neutral`, `critical`, `supportive` |
| intensity | numeric | NULL | — | Stance intensity score (0.0–1.0) |
| created_at | timestamptz | NULL | now() | Extraction timestamp |

**Joins:** `article_stances.article_id → articles.id`; `article_stances.actor_entity_id → entity_dictionary.id`.

**CRITICAL NOTE — Directed Sentiment:** The column named `actor` is **the TARGET of the stance, not its actor/subject**. The article's author/source is the implicit agent. When querying for "what is the sentiment toward KCR?", filter on `actor = 'KCR'` or `actor_entity_id = <KCR uuid>`. This naming is a legacy bug; the semantic is `target`. Also: `article_stances` is the correct table for negativity/bias analysis — `articles.register_emotion` is event-emotion and skews everything negative (a flood article registers `alarm` regardless of editorial bias).

---

## public.article_quotes — [LIVE] (~309,369 rows, 177 MB)

**Purpose:** Attributed quotations extracted per article, with speaker resolution and English translation.
**Populated by:** `nlp` queue Groq tasks (`llama-3.1-8b-instant`), gated by `quotes_extracted=false` on articles.
**Read by:** Quote sidebar, speaker-scoped retrieval, analyst RAG.
**Freshness:** `max(extracted_at)` current (2026-06-19).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NOT NULL | gen_random_uuid() | PK |
| article_id | uuid | NOT NULL | — | FK → articles.id |
| speaker_name | text | NOT NULL | — | Raw speaker name string from article |
| speaker_entity_id | uuid | NULL | — | FK → entity_dictionary.id (resolved speaker) |
| quote_text | text | NOT NULL | — | Quote verbatim in original language |
| quote_text_en | text | NULL | — | English translation of quote_text |
| speaker_name_en | text | NULL | — | English transliteration/translation of speaker name |
| translated_at | timestamptz | NULL | — | When quote_text_en was generated |
| context | text | NULL | — | Surrounding sentence(s) providing quote context |
| char_offset_start | integer | NULL | — | Character offset in full_text_scraped where quote begins |
| char_offset_end | integer | NULL | — | Character offset where quote ends |
| is_direct | boolean | NOT NULL | true | True = verbatim direct quote; false = paraphrase/reported speech |
| extracted_at | timestamptz | NOT NULL | now() | Extraction timestamp |
| extracted_by_model | text | NOT NULL | `'llama-3.1-8b-instant'` | Model used |

**Joins:** `article_quotes.article_id → articles.id`; `article_quotes.speaker_entity_id → entity_dictionary.id`.
**Notes:** `is_direct` defaults to true; paraphrases are rarer. `char_offset_*` allows quote highlighting in UI but may be NULL for older extractions. Translation columns populated in a secondary pass.

---

## public.article_numbers — [LIVE] (~587,028 rows, 101 MB)

**Purpose:** Numerical facts extracted per article (monetary values, counts, percentages, dates).
**Populated by:** `nlp` queue substrate extraction tasks.
**Read by:** Brief quantitative summary, analyst RAG.
**Freshness:** `max(created_at)` current (2026-06-19).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NOT NULL | gen_random_uuid() | PK |
| article_id | uuid | NOT NULL | — | FK → articles.id |
| value | text | NOT NULL | — | The numeric value as text, e.g. `6000`, `12.5`, `₹500 crore` |
| unit | text | NULL | — | Unit label, e.g. `crore`, `%`, `km`, `MW` |
| context | text | NULL | — | Surrounding sentence providing context for the number |
| position | smallint | NULL | — | Ordinal position of this number in the article (1-based) |
| created_at | timestamptz | NULL | now() | Extraction timestamp |

**Joins:** `article_numbers.article_id → articles.id`.
**Notes:** `value` is stored as text to preserve original formatting. Join with `context` to interpret units and scale.

---

## public.article_events — [LIVE] (~619,010 rows, 176 MB)

**Purpose:** Discrete events extracted per article with date, type, actors, and clustering FK.
**Populated by:** `nlp` queue substrate extraction tasks.
**Read by:** Clustering pipeline, brief timeline, event-cluster surfacing.
**Freshness:** `max(created_at)` current (2026-06-19).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NOT NULL | gen_random_uuid() | PK |
| article_id | uuid | NOT NULL | — | FK → articles.id |
| event_date | date | NULL | — | Raw extracted event date (may be year-incorrect for old events) |
| effective_event_date | date | NULL | — | **Year-corrected event date** using Option-4 clamp (migration 053); use this for clustering and brief queries |
| event_description | text | NOT NULL | — | Free-text description of the event |
| event_type | text | NULL | — | Event category, e.g. `election`, `arrest`, `flood`, `policy_announcement` |
| actors | text[] | NULL | — | Array of actor names involved in event |
| confidence | numeric(3,2) | NULL | — | Extraction confidence (0.00–1.00) |
| position | smallint | NULL | — | Ordinal position of event in article |
| is_future | boolean | NULL | false | True if the event is scheduled/anticipated rather than past |
| event_cluster_id | uuid | NULL | — | FK → event_clusters_archive.id; NULL = unclustered |
| created_at | timestamptz | NOT NULL | now() | Extraction timestamp |

**Joins:** `article_events.article_id → articles.id`; `article_events.event_cluster_id → event_clusters_archive.id`.
**Notes:** Always use `effective_event_date` rather than `event_date` in queries — `event_date` may contain year errors (e.g. an article published 2026 mentioning a "2019 election" might be extracted as event_date=2019-01-01, which `effective_event_date` corrects via clamping logic in migration 053).

---

## public.article_locations — [LIVE] (~679,686 rows, 171 MB)

**Purpose:** Geo-entities extracted from each article: country, region, city, and optional lat/lng.
**Populated by:** `nlp` queue substrate extraction tasks.
**Read by:** Geo heatmap, relevance geo-scorer, regional filtering.
**Freshness:** `max(created_at)` current (2026-06-19).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NOT NULL | gen_random_uuid() | PK |
| article_id | uuid | NOT NULL | — | FK → articles.id |
| location_text | text | NOT NULL | — | Raw location string as it appeared in text, e.g. `Hyderabad` |
| country | text | NULL | — | Normalised country name |
| region | text | NULL | — | State/province, e.g. `Telangana` |
| city | text | NULL | — | City name |
| lat | numeric(8,5) | NULL | — | Latitude (geocoded) |
| lng | numeric(8,5) | NULL | — | Longitude (geocoded) |
| confidence | numeric(3,2) | NULL | — | Geocoding/extraction confidence |
| position | smallint | NULL | — | Ordinal position in article |
| created_at | timestamptz | NOT NULL | now() | Extraction timestamp |

**Joins:** `article_locations.article_id → articles.id`.
**Notes:** Multiple rows per article. `lat`/`lng` may be NULL for unresolved or ambiguous place names. Use `region` for state-level filtering.

---

## public.article_media — [LIVE] (~4,608,800 rows, 1.3 GB)

**Purpose:** Images, videos, and other embedded media extracted from article HTML.
**Populated by:** HTML scraper at collect time (not substrate extraction).
**Read by:** Article card thumbnail display, media gallery.
**Freshness:** `max(created_at)` current (2026-06-19).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NOT NULL | gen_random_uuid() | PK |
| article_id | uuid | NOT NULL | — | FK → articles.id |
| media_type | text | NOT NULL | — | `image` / `video` / `embed` (live DB: `image` is dominant) |
| url | text | NULL | — | Media asset URL |
| external_id | text | NULL | — | Platform-specific ID (e.g. YouTube video ID for embedded videos) |
| caption | text | NULL | — | Image/video caption |
| alt_text | text | NULL | — | HTML alt text |
| width | smallint | NULL | — | Pixel width (if known) |
| height | smallint | NULL | — | Pixel height (if known) |
| position | smallint | NULL | — | Ordinal position of media in article |
| is_hero | boolean | NOT NULL | false | True if this is the article's primary/hero image |
| created_at | timestamptz | NOT NULL | now() | Extraction timestamp |

**Joins:** `article_media.article_id → articles.id`.
**Notes:** 4.6M rows for 354k articles ≈ ~13 media items/article average (articles embed many images). Table is large (1.3 GB); avoid full scans. Filter `is_hero=true` for thumbnail queries.

---

## public.article_links — [LIVE] (~14,741,716 rows, 4.6 GB)

**Purpose:** Outbound hyperlinks extracted from article HTML — enables link-graph analysis and cross-source dedup via canonical_url matching.
**Populated by:** HTML scraper at collect time.
**Read by:** Link-graph analytics (migration 064 note), cross-source dedup pipeline.
**Freshness:** `max(created_at)` current (2026-06-19).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NOT NULL | gen_random_uuid() | PK |
| article_id | uuid | NOT NULL | — | FK → articles.id |
| outbound_url | text | NOT NULL | — | Raw outbound URL from `<a href>` |
| outbound_url_normalized | text | NULL | — | Normalised form (query params stripped, lowercased) |
| outbound_domain | text | NULL | — | Extracted domain of the outbound URL |
| anchor_text | text | NULL | — | Anchor text of the link |
| link_type | text | NULL | — | Classification of link (live values: e.g. `internal`, `external`, `social`) |
| position | smallint | NULL | — | Ordinal position of link in article body |
| created_at | timestamptz | NOT NULL | now() | Extraction timestamp |

**Joins:** `article_links.article_id → articles.id`.
**Notes:** Largest table in the domain at 14.7M rows (4.6 GB). NEVER full-scan; always filter by `article_id` or `outbound_domain`. Useful for citation network and for finding reposts via matching `outbound_url_normalized` against `articles.canonical_url`.

---

## public.article_tweets — [LIVE] (~15,447 rows, 23 MB)

**Purpose:** Embedded tweets scraped from article HTML — captures Twitter embeds referenced in news articles.
**Populated by:** HTML scraper; `fetch_status` tracks async tweet-detail fetch.
**Read by:** Social signal enrichment, article detail sidebar.
**Freshness:** `max(fetched_at)` current (2026-06-19). Sparse relative to corpus size (15k rows vs 354k articles).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NOT NULL | gen_random_uuid() | PK |
| article_id | uuid | NOT NULL | — | FK → articles.id |
| tweet_id | text | NOT NULL | — | Twitter/X tweet ID |
| tweet_url | text | NOT NULL | — | Full tweet URL |
| author_handle | text | NULL | — | Twitter handle, e.g. `@TelanganaCMO` |
| author_name | text | NULL | — | Display name |
| author_profile_url | text | NULL | — | Profile URL |
| tweet_text | text | NULL | — | Tweet body text |
| tweet_html | text | NULL | — | Raw oEmbed HTML |
| language | text | NULL | — | Detected language of tweet |
| posted_at | date | NULL | — | Date tweet was posted |
| has_image | boolean | NULL | false | True if tweet contains image media |
| image_urls | text[] | NULL | `'{}'` | Array of image URLs in tweet |
| hashtags | text[] | NULL | `'{}'` | Hashtags extracted from tweet text |
| mentions | text[] | NULL | `'{}'` | @mentions extracted from tweet text |
| links_in_tweet | text[] | NULL | `'{}'` | URLs embedded in tweet text |
| fetched_at | timestamptz | NULL | now() | When row was created/tweet fetched |
| fetch_status | text | NULL | `'pending'` | `pending` / `ok` / `failed` — status of tweet-detail API fetch |
| fetch_error | text | NULL | — | Error message if fetch_status='failed' |

**Joins:** `article_tweets.article_id → articles.id`.
**Notes:** Coverage is sparse (~4% of articles). Twitter API changes have made this feed intermittent. `posted_at` is date-only (no time). The `fetch_status` lifecycle allows async retry for tweets not yet resolved.
