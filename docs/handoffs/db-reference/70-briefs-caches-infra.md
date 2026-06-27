# DB Reference — Briefs, Caches, Topics, Views & Infra

Domain: daily brief generation, coverage caches, canonical topic vocabulary, unified content read surface,
pipeline-freshness monitoring views, analytics caches, translation cache, clustering eval artifacts,
and Celery/Kombu queue plumbing tables.  
All sizes and row counts sampled 2026-06-19.

---

## public.briefs — [LIVE] (~41 rows, 856 kB) TABLE

**Purpose:** One row per (user_id, brief_date) — the LLM-generated daily intelligence digest.
Content is raw Markdown stored in `content`. No status column; presence of the row implies successful generation.

**Populated by:** `tasks.generate_brief` (Celery, `brief` queue). Default model `llama-3.3-70b-versatile`.
**Read by:** `/api/brief` endpoint, Brief page in night-desk.
**Freshness:** One row per user per calendar day; generated_at tracks generation time.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | Primary key |
| user_id | uuid | NO | — | FK → users(id); identifies which user's brief |
| content | text | NO | — | Full Markdown text of the brief (sections separated by headers) |
| brief_date | date | NO | — | Calendar date the brief covers, e.g. `2026-06-19` |
| generated_at | timestamptz | YES | now() | When the LLM finished generation |
| articles_used | integer | YES | 0 | Count of article rows passed to the LLM as context |
| model_used | text | YES | `llama-3.3-70b-versatile` | Groq model ID used for generation |
| source_counts | jsonb | YES | — | Per-pillar counts: `{articles, govt_docs, social_posts, newspaper_clippings, video_clips}` |
| evidence | jsonb | YES | — | Structured evidence per pillar: `{govt_docs[], social_posts[], newspaper_clippings[], video_clips[]}` — article IDs / clip IDs cited |

**Joins:** `briefs.user_id → users.id`; `briefs.brief_date + user_id → brief_quality_scores (user_id, brief_date)`.
**Notes:** No UNIQUE constraint visible but (user_id, brief_date) is de-facto unique by task logic. Migration: `020_briefs_evidence.sql`, `057_newsroom_briefs.sql`.

---

## public.brief_quality_scores — [LIVE] (~24 rows, 80 kB) TABLE

**Purpose:** Daily rubric scorecard per brief — populated by `tasks.score_brief_quality`. One row per (user_id, brief_date), append-only (upsert on PK). Scores are 0.0–1.0; overall_score is weighted aggregate.

**Populated by:** `backend/tasks/brief_quality_task.py` on `brief` queue.
**Read by:** QA dashboards, brief remediation monitoring.
**Freshness:** Runs after brief generation each day.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | Primary key |
| user_id | uuid | NO | — | FK → users(id) |
| brief_date | date | NO | — | Date of the scored brief |
| scored_at | timestamptz | NO | now() | When scoring ran |
| has_situation_status | boolean | NO | false | Section "Situation Status" present? |
| has_key_developments | boolean | NO | false | Section "Key Developments" present? |
| has_entities_today | boolean | NO | false | Section "Entities Today" present? |
| has_signals_to_watch | boolean | NO | false | Section "Signals to Watch" present? |
| has_financial_pulse | boolean | NO | false | Section "Financial Pulse" present? |
| has_source_coverage | boolean | NO | false | Section "Source Coverage" present? |
| bracket_cites | integer | NO | 0 | Count of `[N]` citation brackets in content |
| pillar_cites | integer | NO | 0 | Count of pillar-level citations found |
| failure_marker_count | integer | NO | 0 | Occurrences of `[Generation failed` marker in content |
| invalid_indexes | jsonb | NO | `[]` | List of `[section_name, [bad_indexes]]` where cited index doesn't resolve |
| article_recency_avg_days | numeric | YES | — | Mean age of articles used (smaller = fresher) |
| article_recency_max_days | numeric | YES | — | Max age of any article used |
| articles_within_36h | integer | YES | — | How many source articles were <36h old |
| section_word_counts | jsonb | NO | `{}` | `{section_name: word_count}` for each section |
| overall_score | numeric | YES | — | Weighted aggregate 0.0–1.0 |

**Joins:** `brief_quality_scores.(user_id, brief_date) → briefs.(user_id, brief_date)`.
**Notes:** Migration `036_brief_quality_scores.sql`. Table comment: "Daily rubric scorecard for the Brief pillar. fix/brief-prod-readiness P2.10."

---

## public.top_stories_daily — [LIVE] (~114 rows, 712 kB) TABLE

**Purpose:** Cached Top-5 story list for the /coverage/articles page. Refreshed every 6 hours.
`user_id IS NULL` = global fallback list shown to users who have no personalisation.

**Populated by:** `tasks.generate_top_stories` (beat, every 6h).
**Read by:** `/api/coverage/top-stories` endpoint.
**Freshness:** Max age 6h; 114 rows across multiple users + global.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | Primary key |
| date | date | NO | — | Calendar date the list is for |
| user_id | uuid | YES | — | FK → users(id); NULL = global list |
| stories | jsonb | NO | — | Ordered array of story objects (title, article_id, summary, relevance_score, sources[]) |
| generated_at | timestamptz | NO | now() | Generation timestamp |
| generated_by_model | text | NO | `llama-3.3-70b-versatile` | LLM model used to produce summaries |

**Joins:** `top_stories_daily.user_id → users(id)` (nullable).
**Notes:** Contains denormalised story data — not FK-linked to articles individually. Global row (user_id IS NULL) is the safe fallback when personalisation is unavailable.

---

## public.coverage_panel_summaries — [LIVE] (~5 rows, 32 kB) TABLE

**Purpose:** LLM-generated 2–3 line summary for each /coverage hub panel (articles, newspaper, tv, social, govt).
One row per slug — PK is slug. Idempotent upsert; refreshed daily at 04:15 UTC.

**Populated by:** `tasks.refresh_coverage_summaries` (beat).
**Read by:** `/api/coverage/panels` at request time; falls back to seeded static text on first boot.
**Freshness:** Updated daily; ~5 rows always present.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| slug | text | NO (PK) | — | Panel identifier; CHECK IN `('articles','newspaper','tv','social','govt')` |
| summary | text | NO | — | 2–3 line LLM-generated description of current activity |
| generated_at | timestamptz | NO | now() | When last generated |
| generated_by_model | text | NO | `llama-3.1-8b-instant` | Model used; note cheaper model vs brief generation |
| source_sample_size | integer | NO | 0 | Number of source items fed to the LLM |

**Joins:** None — standalone cache.
**Notes:** Migration `040_coverage_panel_summaries.sql`. Table comment confirms 04:15 UTC cron. Seed rows inserted at migration time so no cold-start empty page.

---

## public.topic_categories — [LIVE] (~25 rows, 32 kB) TABLE

**Purpose:** Canonical topic vocabulary used by the NLP pipeline for article/clipping/clip classification.
`is_new=FALSE` = original 15 topic_category values. `is_new=TRUE` = 10 finer-grain topic_fine buckets added later.
`rolls_up_to` maps every fine bucket back to one of the original 15 for consumers that want coarser grouping.

**Populated by:** Migration seed only (static vocabulary).
**Read by:** NLP classifier, frontend topic filters, topic_fill Celery task.
**Freshness:** Static — no live writes.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| name | text | NO (PK) | — | Category identifier used in articles.topic_category / topic_fine, e.g. `POLITICS` |
| is_new | boolean | NO | false | false = original 15 (topic_category); true = added 10 (topic_fine) |
| rolls_up_to | text | NO | — | Parent category name; for original-15 rows, equals self |
| description | text | YES | — | Human-readable description of the category |
| introduced_at | date | NO | `2026-05-30` | Date the row was seeded |

**Full value list (all 25 rows):**

| name | is_new | rolls_up_to | description |
|---|---|---|---|
| AGRICULTURE | false | AGRICULTURE | Farming, crops, farmers, MSP, irrigation |
| BUSINESS | false | BUSINESS | Companies, corporate deals, industry, trade |
| ENVIRONMENT | false | ENVIRONMENT | Climate, pollution, wildlife, forests, conservation |
| FINANCE | false | FINANCE | Stocks, banking, earnings, RBI, mutual funds, economy |
| GOVERNANCE | false | GOVERNANCE | Policy, administration, bureaucracy, govt programs |
| HEALTH | false | HEALTH | Disease, hospitals, medicine, public health |
| INFRASTRUCTURE | false | INFRASTRUCTURE | Roads, rail, metro, power, water, construction |
| INTERNATIONAL | false | INTERNATIONAL | Foreign affairs, diplomacy, world events |
| LEGAL | false | LEGAL | Court judgments, litigation, judiciary, law |
| OTHER | false | OTHER | Genuinely none of the above |
| POLITICS | false | POLITICS | Party politics, elections, legislators, govt formation |
| SECURITY | false | SECURITY | Military ops, terrorism, border, internal security |
| SOCIAL | false | SOCIAL | Society, caste, gender, communities, human interest |
| SPORTS | false | SPORTS | Cricket, football, IPL, tournaments, athletes |
| TECHNOLOGY | false | TECHNOLOGY | IT, software, AI, gadgets, internet, startups |
| CRIME | true | SECURITY | Murder, theft, fraud, arrests, police cases |
| DEFENCE | true | SECURITY | Armed forces, weapons, defence deals, military exercises |
| DISASTER | true | ENVIRONMENT | Floods, earthquakes, accidents, fires, cyclones, rescue |
| EDUCATION | true | SOCIAL | Schools, universities, exams, results, admissions |
| ENTERTAINMENT | true | SOCIAL | Films, music, celebrities, OTT, TV, cinema |
| LIFESTYLE | true | SOCIAL | Food, travel, fashion, wellness, culture |
| OBITUARY | true | SOCIAL | Deaths, tributes, passing of notable people |
| RELIGION | true | SOCIAL | Temples, festivals, religious events, faith, pilgrimages |
| SCIENCE | true | TECHNOLOGY | Research, space, ISRO, discoveries, scientific studies |
| WELFARE | true | GOVERNANCE | Ration, pensions, subsidies, scholarships, welfare schemes |

**Joins:** Referenced by `articles.topic_category`, `articles.topic_fine`, `clippings.topic_category/topic_fine`, `youtube_clips_v2.topic_category/topic_fine`.
**Notes:** No surrogate ID — `name` is the PK. All 10 `is_new=TRUE` rows collapse into one of 6 parent categories: SECURITY (2), ENVIRONMENT (1), SOCIAL (5), TECHNOLOGY (1), GOVERNANCE (1).

---

## public.content_items — VIEW

**Purpose:** Unified read surface merging articles, clippings, and YouTube clips into one queryable relation.
The `src` discriminator column (`article` | `clipping` | `clip`) identifies the source pillar.
Clippings exclude notices and duplicates; clips exclude `junk` and `extract_failed` substrate statuses.

**Definition summary:**
```sql
SELECT a.id, 'article' AS src, a.title AS headline, a.full_text_scraped AS body_text,
       a.topic_category, a.topic_fine, a.language_iso AS language,
       a.primary_subject, a.published_at::date AS item_date,
       a.entities_extracted, a.labse_embedding, NULL::double precision AS relevance_score
FROM articles a

UNION ALL

SELECT c.id, 'clipping' AS src, c.headline, c.body_text,
       c.topic_category, c.topic_fine,
       COALESCE(c.detected_language, c.language) AS language,
       c.primary_subject, c.edition_date AS item_date,
       c.entities_extracted, c.labse_embedding, c.relevance_score
FROM clippings c
WHERE c.is_notice = false AND c.is_duplicate = false

UNION ALL

SELECT yc.clip_uuid AS id, 'clip' AS src, yc.video_title AS headline,
       yc.transcript_segment AS body_text,
       yc.topic_category, yc.topic_fine, yc.transcript_language AS language,
       COALESCE(yc.primary_subject, yc.matched_entity) AS primary_subject,
       yc.video_published_at::date AS item_date,
       yc.entities_extracted, yc.labse_embedding,
       yc.relevance_score::double precision AS relevance_score
FROM youtube_clips_v2 yc
WHERE yc.substrate_status NOT IN ('junk', 'extract_failed');
```

| column | type | meaning |
|---|---|---|
| id | uuid | Source-table primary key (article.id / clipping.id / clip_uuid) |
| src | text | Discriminator: `article` \| `clipping` \| `clip` |
| headline | text | title (article), headline (clipping), video_title (clip) |
| body_text | text | full_text_scraped (article), body_text (clipping), transcript_segment (clip) |
| topic_category | text | Coarse topic bucket (original 15) |
| topic_fine | text | Fine topic bucket (any of 25) |
| language | text | ISO language code; clippings prefer detected_language over stored language |
| primary_subject | text | Main entity/subject; clips fall back to matched_entity |
| item_date | date | Published date cast to date |
| entities_extracted | boolean | Whether entity extraction has run |
| labse_embedding | vector | LaBSE embedding (shared v4 recipe) |
| relevance_score | float8 | Relevance to user; NULL for articles (scoring is per-user elsewhere) |

**Joins:** Backed by `articles`, `clippings`, `youtube_clips_v2`. No direct FK from view.
**Notes:** clippings.relevance_score is populated; articles carry NULL here because article relevance is stored in `article_user_relevance`. See playbook §4.

---

## public.v_freshness_now — VIEW

**Purpose:** Single-row snapshot of the article ingestion pipeline's current health — newest article age, ingestion velocity, embedding coverage, NLP backlog.

**Definition summary:** Correlated scalar subqueries returning:

| column | meaning |
|---|---|
| newest_article | Max collected_at across all articles |
| newest_age_min | Minutes since newest article was collected |
| ingested_1h | Articles collected in last 1 hour |
| ingested_24h | Articles collected in last 24 hours |
| pct_embedded_24h | % of last-24h articles that have a labse_embedding |
| nlp_pending | Articles where nlp_processed = false (backlog size) |
| vectors_total | Total articles with any embedding |
| vectors_with_provenance | Articles where embedding_revision IS NOT NULL (v4 recipe) |

**Notes:** Operations monitoring view — use for at-a-glance pipeline health.

---

## public.v_freshness_coverage_by_age — VIEW

**Purpose:** Article corpus broken into age buckets with embedding and NLP completion rates per bucket.

| column | meaning |
|---|---|
| bucket | Age bracket: `0-2d`, `2-7d`, `7-14d`, `14d+` |
| total | Total articles in bucket |
| embedded | Articles with labse_embedding |
| pct_embedded | % embedded |
| nlp_done | Articles with nlp_processed = true |
| substrate_ok | Articles with substrate_status = 'ok' |

**Notes:** Ordered by oldest collected_at DESC within bucket.

---

## public.v_freshness_fresh_window — VIEW

**Purpose:** Rolling-window freshness metric for 3 time horizons: last 2h, 6h, 24h.

| column | meaning |
|---|---|
| window | Label: `1_last_2h`, `2_last_6h`, `3_last_24h` |
| collected | Articles collected in window |
| embedded | Embedded within window |
| embedded_pct | % embedded |
| nlp_done | NLP complete |
| substrate_ok | Substrate extracted |
| substrate_pct | % substrate ok |

---

## public.v_freshness_pipeline_lag — VIEW

**Purpose:** P50/P95 latency (in minutes) for two pipeline stages over the last 24 hours: embedding and substrate extraction.

| column | meaning |
|---|---|
| stage | `embed` or `substrate` |
| n_24h | Articles processed in last 24h for this stage |
| p50_min | Median lag from collected_at → stage completion (minutes) |
| p95_min | 95th-percentile lag (minutes) |

**Definition summary:**
- `embed` leg: `embedded_at - collected_at` for articles embedded in last 24h.
- `substrate` leg: `substrate_processed_at - collected_at` for articles with substrate_status='ok' processed in last 24h.

**Notes:** All four v_freshness_* views are articles-only (no clippings, no clips).

---

## public.celery_taskmeta — [LIVE] (~348k rows, 148 MB) TABLE

**Purpose:** Celery framework result backend — stores task execution results, status, traceback.
~90.6% SUCCESS, ~9.4% FAILURE, 0.02% RETRY as of 2026-06-19.

| column | type | meaning |
|---|---|---|
| id | integer | Auto-increment PK |
| task_id | varchar | Celery task UUID |
| status | varchar | `SUCCESS`, `FAILURE`, `RETRY`, `PENDING`, `STARTED` |
| result | bytea | Pickled return value or exception |
| date_done | timestamp | Completion time (no timezone) |
| traceback | text | Stack trace on failure |
| name | varchar | Task dotted name, e.g. `tasks.nlp_processor.run_nlp` |
| args | bytea | Pickled positional args |
| kwargs | bytea | Pickled keyword args |
| worker | varchar | Worker hostname that executed the task |
| retries | integer | Retry count |
| queue | varchar | Queue the task was routed to |

**Notes:** Large table (148 MB). Celery does not auto-prune; old results accumulate. `result` and `args`/`kwargs` are pickle-encoded — not directly queryable as JSON.

---

## public.celery_tasksetmeta — [EMPTY] (0 rows, 24 kB) TABLE

**Purpose:** Celery chord/group result tracking. Not in active use — 0 rows.

| column | type | meaning |
|---|---|---|
| id | integer | PK |
| taskset_id | varchar | Group/chord ID |
| result | bytea | Pickled group result |
| date_done | timestamp | Completion time |

---

## public.kombu_message — [LIVE] (~143k rows, 320 MB) TABLE

**Purpose:** Kombu (AMQP-over-Postgres) message store — pending and in-flight Celery task messages.
320 MB is the largest non-embedding table; messages accumulate if workers lag.

| column | type | meaning |
|---|---|---|
| id | integer | Auto PK |
| visible | boolean | true = available for pickup; false = locked by worker |
| timestamp | timestamp | Enqueue time (no timezone) |
| payload | text | JSON-encoded task message body |
| version | smallint | Kombu message format version |
| queue_id | integer | FK → kombu_queue(id) |

**Joins:** `kombu_message.queue_id → kombu_queue.id`.

---

## public.kombu_queue — [LIVE] (~77 rows, 40 kB) TABLE

**Purpose:** Kombu queue registry — one row per named queue (includes reply queues for pidbox control).

| column | type | meaning |
|---|---|---|
| id | integer | PK |
| name | varchar | Queue name, e.g. `nlp`, `relevance`, `collectors`, `youtube`, `documents`, `social`, `brief`; also `<worker-uuid>.reply.celery.pidbox` entries |

**Notes:** The 77 rows include many ephemeral reply queues. Active application queues: collectors, social, youtube, documents, nlp, relevance, brief.

---

## public.mc_host_metrics — [LIVE] (~17,481 rows, 2488 kB) TABLE

**Purpose:** Mission Control host telemetry — CPU, memory, disk, and other OS metrics captured from the Hetzner server on a schedule. Consumed by the MC dashboard.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| captured_at | timestamptz | NO | now() | When the metric was recorded |
| metric | text | NO | — | Metric name, e.g. `cpu_percent`, `mem_used_gb`, `disk_used_pct` |
| value | numeric | YES | — | Numeric reading |
| unit | text | YES | — | Unit string, e.g. `%`, `GB`, `MB/s` |
| detail | jsonb | YES | — | Additional structured context (e.g. per-core breakdowns) |

**Notes:** No surrogate ID column (PK is implicit or captured_at+metric compound). Accumulates over time; ~17k rows suggests several days of per-minute polling.

---

## public.velocity_baselines — [EMPTY/PLANNED] (0 rows, 24 kB) TABLE

**Purpose:** Statistical baselines for entity mention velocity — daily mean, std-dev, and spike/silence thresholds per entity. Powers "entity spike" alerting. Schema exists but no rows computed yet.

| column | type | nullable | default | meaning |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| entity_name | text | NO | — | Entity (canonical name from entity_dictionary) |
| baseline_type | text | NO | — | Type of signal being baselined (inferred: `articles`, `clips`, `social`) |
| daily_mean | float8 | NO | 0.0 | Rolling daily mean mention count |
| daily_stddev | float8 | NO | 0.0 | Rolling daily std-dev |
| spike_threshold | float8 | NO | 0.0 | Mean + N×stddev above which a spike is flagged |
| silence_threshold | float8 | NO | 0.0 | Below which silence is flagged |
| computed_at | timestamptz | YES | now() | When baseline was last computed |

---

## public.journalist_profiles — [EMPTY/PLANNED] (0 rows, 24 kB) TABLE

**Purpose:** Per-author × per-entity stance profile — aggregates how many times an author covered an entity favourably, adversely, or neutrally. Schema seeded but no rows populated.

| column | type | nullable | default | meaning |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| author_name | text | NO | — | Journalist byline as appears in articles |
| entity_name | text | NO | — | Entity being covered |
| for_count | integer | YES | 0 | Articles with favourable stance toward entity |
| against_count | integer | YES | 0 | Articles with adversarial stance |
| neutral_count | integer | YES | 0 | Neutral coverage |
| bias_indicator | text | YES | — | Computed label, e.g. `pro`, `anti`, `neutral` (inferred) |
| updated_at | timestamptz | YES | now() | Last update |

---

## public.event_dissent — [EMPTY] (0 rows, 40 kB) TABLE

**Purpose:** Cross-source sentiment-divergence flags — marks events where different sources take meaningfully divergent stances. Powers "Dissent" detector chips on event cards in night-desk.

| column | type | nullable | default | meaning |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| thread_id | uuid | YES | — | FK → story_clusters_archive or story thread (inferred) |
| breaking_cluster_id | uuid | YES | — | FK → event/breaking cluster |
| sources | jsonb | NO | — | Array of source IDs with divergent stance |
| sentiment_variance | real | NO | 0.0 | Variance in sentiment scores across sources |
| framing_summary | text | NO | — | LLM-generated text describing the divergence |
| detected_at | timestamptz | NO | now() | Detection timestamp |
| detected_by_model | text | NO | `llama-3.3-70b-versatile` | Model that generated framing_summary |

**Notes:** Schema and description match planned Dissent detector feature. 0 rows — not yet populated in production.

---

## analytics.home_cache — [LIVE] (~5 rows, 264 kB) TABLE

**Purpose:** Per-user cached home-page payload. One row per user (upsert). Large JSONB blob — precomputed at schedule to keep the home page load instant.

| column | type | nullable | default | meaning |
|---|---|---|---|---|
| user_id | uuid | NO (PK) | — | FK → users(id) |
| payload | jsonb | NO | — | Full serialised home-page data (top stories, clips, cuttings, entity signals) |
| computed_at | timestamptz | NO | now() | When payload was last computed |

**Notes:** 5 rows = 5 active users with caches. The large size (264 kB / 5 rows ≈ 53 kB per user) confirms the payload is a rich pre-aggregation.

---

## analytics.page_cache — [LIVE] (~20 rows, 512 kB) TABLE

**Purpose:** Per-user, per-page cached payloads for slower analytics pages. Multiple pages per user.

| column | type | nullable | default | meaning |
|---|---|---|---|---|
| user_id | uuid | NO | — | FK → users(id) |
| page | text | NO | — | Page identifier, e.g. `clips`, `cuttings`, `signals` |
| payload | jsonb | NO | — | Pre-computed page data |
| computed_at | timestamptz | NO | now() | Cache timestamp |

**Joins:** PK is `(user_id, page)` (inferred from upsert semantics).

---

## analytics.report_cache — [LIVE] (~6 rows, 280 kB) TABLE

**Purpose:** Per-user per-edition-date cached report (newspaper/clippings edition report). Built by the clipping report task.

| column | type | nullable | default | meaning |
|---|---|---|---|---|
| user_id | uuid | NO | — | FK → users(id) |
| edition_date | date | NO | — | Edition date the report covers |
| report | jsonb | NO | — | Full report structure (sections, clippings cited, summary) |
| built_at | timestamptz | NO | now() | When the report was built |

**Joins:** PK is `(user_id, edition_date)` (inferred).

---

## analytics.text_en — [LIVE] (~12,908 rows, 3168 kB) TABLE

**Purpose:** Translation cache — stores English translations of non-English strings so each unique string is translated once via Google Translate (free endpoint), keyed by MD5 hash of the source text. 12,908 rows represents the unique non-English strings translated to date.

**Populated by:** `backend/nlp/i18n.py` — called from night-desk relevance/display paths when non-English text is detected.
**Read by:** Night-desk frontend data layer when rendering non-English article summaries.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| src_hash | text | NO (PK) | — | MD5 hex of the original source string (UTF-8 encoded) |
| text_en | text | NO | — | English translation produced by Google Translate (gtx endpoint, capped at 4800 chars) |
| created_at | timestamptz | NO | now() | First translation timestamp |

**Notes:** No source_lang column — language detection is implicit in the translate API call. Failures are silent (no row inserted). Hash collision risk is negligible at this scale. Source: `backend/nlp/i18n.py` with `_md5()` keying and `_translate_one()` via httpx.

---

## analytics.article_signals_mv — [LIVE] (~48,668 rows, 141 MB) MATVIEW

**Purpose:** Pre-filtered, pre-joined view of articles that have passed substrate extraction (v3, post-2026-05-27), carrying their top-5 canonical locations. Used by analytics and relevance scoring as a fast signals surface — avoids scanning the full articles table with its 50+ columns.

**Populated by:** `REFRESH MATERIALIZED VIEW analytics.article_signals_mv` (run by cron every 30 min per `project_matview_refresh_cron.md`).
**Read by:** Relevance scorer v3, analytics dashboards, CM political intelligence tasks.
**Freshness:** Refreshed every 30 minutes. Max published_at as of sampling: `2026-05-27 17:58:11+00` (oldest eligible — matview starts at substrate cutover date).

**Definition:** Selects from `articles` where `substrate_status='ok'` AND `extraction_version=3` AND `substrate_processed_at > '2026-05-27 16:00:00+00'` AND `primary_subject IS NOT NULL` AND `primary_subject NOT LIKE '%no substantive content%'` AND `article_type IN ('news','analysis','opinion','explainer','interview')`. Joins article_locations to build a top-5 canonical_locations array (primary first, then city/state/country by mention count).

| column | type | nullable | meaning |
|---|---|---|---|
| article_id | uuid | YES | PK of source articles row |
| primary_subject | text | YES | Main entity/subject |
| language_iso | text | YES | ISO language code, e.g. `en`, `te`, `hi` |
| source_id | uuid | YES | FK → sources(id) |
| source_country | char(2) | YES | ISO country code of the source outlet |
| collected_at | timestamptz | YES | When article was ingested |
| published_at | timestamptz | YES | Article publication timestamp |
| article_type | text | YES | `news`, `analysis`, `opinion`, `explainer`, or `interview` |
| title | text | YES | Article headline |
| summary_executive | text | YES | Executive summary from substrate extraction |
| lede | text | YES | First 1500 chars of full_text_scraped |
| canonical_locations | text[] | YES | Top-5 location strings (city/state/country), primary first |
| extraction_version | smallint | YES | Always 3 in this matview |
| substrate_processed_at | timestamptz | YES | When substrate ran |

**Joins:** `article_signals_mv.article_id → articles.id`; `source_id → sources.id`.
**Notes:** 48,668 rows covers the substrate-v3 corpus from 2026-05-27 onward. The cutoff date is hardcoded in the matview definition — articles before that date never appear here even if re-processed.

---

## analytics.hard_neg_fps — [LIVE] (~13 rows, 24 kB) TABLE

**Purpose:** False-positive hard negatives for the clustering/deduplication eval harness. Each row is a manually-labelled article pair that the model incorrectly predicted as "same event" (FP = false positive). Used to calibrate the clustering scorer and template-detection logic.

| column | type | nullable | meaning & example values |
|---|---|---|---|
| a_id | uuid | YES | Article ID of first pair member |
| b_id | uuid | YES | Article ID of second pair member |
| a_language | text | YES | Language of article A, e.g. `en`, `hi`, `te` |
| b_language | text | YES | Language of article B |
| same_source | boolean | YES | Whether both articles are from the same outlet |
| trgm_subject | numeric | YES | Trigram similarity of primary_subject fields (0–1) |
| trgm_title | numeric | YES | Trigram similarity of titles (0–1) |
| shared_actors | integer | YES | Count of shared named actors |
| shared_locations | integer | YES | Count of shared named locations |
| a_subject | text | YES | primary_subject of article A |
| b_subject | text | YES | primary_subject of article B |
| a_title | text | YES | Title of article A |
| b_title | text | YES | Title of article B |
| a_source_name | text | YES | Outlet name for A |
| b_source_name | text | YES | Outlet name for B |
| label | text | YES | `FP` — confirmed false positive |
| label_reason | text | YES | Human annotation explaining why they are NOT the same event (e.g. "TEMPLATE: IPL Impact Players for different match pairs") |

**Notes:** 13 rows — a small labelled eval set. Live examples include IPL template articles, same-topic horoscopes from same outlet, and genuinely different stock-market events (US vs India). No FK constraints — IDs are article UUIDs.

---

## analytics.night_repair_scorecard — [LIVE] (~4 rows, 48 kB) TABLE

**Purpose:** Audit log for the nightly clustering repair pipeline (night-detector / janitor). One row per nightly run; stores the eval gate result, action counts, sample split decisions, and plan summary. Used to detect runaway repairs and verify rollback counts.

**Populated by:** `scripts/maintenance/run_v8.sh` / night-detector cron (03:30 nightly).
**Read by:** Operations monitoring, clustering pipeline health checks.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | bigint | NO | sequence | Monotonic run ID |
| batch_id | text | YES | — | Clustering batch/run identifier, e.g. `1781767919` |
| run_at | timestamptz | YES | now() | When the repair run executed |
| gate_result | text | YES | — | Eval gate outcome: `PASS`, `FAIL`, `UNKNOWN` |
| n_rollback | integer | YES | — | Number of splits rolled back (0 = no rollbacks needed) |
| n_actions | integer | YES | — | Total split actions applied this run |
| sample_splits | jsonb | YES | — | Array of sampled split decisions with verdict, story_id, n_children, reasons |
| plan_summary | jsonb | YES | — | Run metadata: `{run_id, batch_id, min_child, n_actions, partition_res}` |

**Notes:** 4 rows = 4 nightly runs recorded. `gate_result=UNKNOWN` on 2 of 4 runs suggests the eval gate logic was not fully activated. `sample_splits` contains LLM SPLIT/KEEP verdicts with reasoning strings.

---

## Summary: Empty / Planned Tables

| table | status | reason |
|---|---|---|
| public.velocity_baselines | EMPTY/PLANNED | Schema seeded; backfill task not yet run |
| public.journalist_profiles | EMPTY/PLANNED | Schema seeded; NLP stance-aggregation task not yet built |
| public.event_dissent | EMPTY | Dissent detector feature not yet live |
| public.celery_tasksetmeta | EMPTY | Celery chords not used in current task graph |
