# Article Extraction — Complete Field Reference

Captured 2026-05-25 from production schema.

## 1. `articles` table (the root row — 47 columns)

### Identity & source
- `id` UUID — primary key
- `source_id` UUID → `sources.id`
- `url`, `url_hash`, `canonical_url`
- `collected_at`, `inserted_at`, `updated_at`
- `published_at` — from feed metadata
- `source_tier` — quality bucket of the source
- `byline` — author from page metadata

### Raw content
- `title`
- `lead_text_original`, `lead_text_translated`
- `full_text_scraped` — body in original language
- `full_text_translated` — body in English
- `language_detected`, `language_iso`
- `thumbnail_url`
- `author_name` — older field, superseded by `byline`
- `content_type`
- `word_count`, `reading_minutes`
- `body_quality` — heuristic grade

### NLP / extraction (LLM-driven, v3 substrate)
- `article_type` — news, opinion, analysis, sports_result, horoscope, etc.
- `primary_subject` — top topic phrase
- `summary_preview` (≤500 chars)
- `summary_snippet` (≤1000 chars)
- `summary_executive` (≤4000 chars)
- `register_style` — formal / opinion / breaking-news / explainer / etc.
- `register_emotion` — anger / concern / celebration / neutral
- `register_is_breaking` — bool
- `narrative_frame` — older field
- `topic_category` — coarse category

### Entities & geography
- `entities_extracted` JSONB — entity blob (name, type, role)
- `geo_primary`, `geo_secondary` ARRAY

### Substrate / pipeline status
- `extraction_version` SMALLINT — 1 (legacy), 2 (interim), 3 (current)
- `substrate_status` — ok / fetch_failed / junk / extract_failed / pending
- `substrate_processed_at`
- `claims_extracted`, `quotes_extracted` BOOL — done flags
- `nlp_processed`, `nlp_confidence`

### Dedup / clustering
- `is_duplicate`, `duplicate_of`
- `thread_id` — links to threads table
- `labse_embedding` (768-dim vector) — for semantic similarity
- `fts` — Postgres tsvector for full-text search

## 2. Linked child tables (per article)

### `article_quotes` — every quote extracted
- `speaker_name`, `speaker_name_en` (translated)
- `speaker_entity_id` → `entity_dictionary.id` (NULL if no canonical match)
- `quote_text`, `quote_text_en` (translated)
- `is_direct` — direct quote vs paraphrased
- `char_offset_start`, `char_offset_end` — position in article
- `context` — surrounding sentence
- `extracted_at`, `extracted_by_model`, `translated_at`

### `article_claims` — factual assertions
- `claim_text` — full sentence
- `subject_text` + `subject_entity_id` — who/what
- `predicate` — relation verb
- `object_text` — what they claim about
- `confidence` REAL
- `embedding` (768-dim) for similarity
- `extracted_at`, `extracted_by_model`

### `article_events` — incidents mentioned
- `event_date`, `effective_event_date`
- `event_description`, `event_type`
- `actors` ARRAY — who's involved
- `is_future` — predicted vs already-happened
- `event_cluster_id` → `event_clusters.id` (T5 cluster)
- `confidence`, `position`

### `article_stances` — actor sentiment alignment
- `actor` + `actor_entity_id`
- `stance` — supports / opposes / neutral
- `intensity` NUMERIC [-1, +1]

### `article_locations` — places mentioned
- `location_text`, `city`, `region`, `country`
- `lat`, `lng` (geocoded)
- `confidence`
- `mention_count` — how many times in body
- `is_primary` — main story location vs ancillary
- `location_scope` — local / national / international

### `article_numbers` — figures cited
- `value` TEXT
- `unit` — Crore, percent, USD, etc.
- `context` — surrounding phrase
- `position`

### `article_districts`, `article_links`, `article_media`, `article_tweets`
- Minor: districts mentioned, outbound links, embedded media URLs, tweet refs

### `user_article_relevance`, `user_breaking_now`
- Per-user scoring layer (RAG / personalized brief)

### `audit_decisions`, `notification_events`, `collection_articles`
- Workflow / audit / batching metadata

## Summary

Per article, the system writes/reads ~**14 tables** total. From ONE article body, the LLM extracts:
- 1 summary (3 lengths)
- 1 article_type + 1 primary_subject + register (style, emotion, breaking)
- 0–10 claims
- 0–8 quotes (each with speaker, attribution, optional translation)
- 0–6 events (each with date, actors, cluster link)
- 0–5 stances (actor + position + intensity)
- 0–5 locations (each geocoded)
- 0–8 numbers (with units + context)
- 1 LaBSE embedding (768-dim) for similarity search
- 1 English translation of full body (if non-English)
