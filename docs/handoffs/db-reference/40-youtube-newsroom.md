# 40 — YouTube Clips + Newsroom DB Reference

Transcripts are fetched exclusively via a residential-relay (laptop, `YT_RELAY_URL`) using yt-dlp + authed cookies — never called directly from Hetzner. Discovery is decoupled from fetch: `pending_youtube_videos` is the queue. **`youtube_clips_v2` is the current live clips table** (substrate-style, 5 k rows, written since mid-2026); `youtube_clips` is the legacy table (13.7 k rows, last write 2026-06-07, frozen). The NEWSROOM schema (`newsroom_*`) is a separate `/clips` redesign for live TV intelligence (Telugu-focused, 25 channels registered, very low segment/broadcast counts — seeded but largely stalled at ~37 segments from 2026-05-10).

---

## public.youtube_clips_v2 — [LIVE] (~5,058 rows, 50 MB)

**Purpose:** Current entity-keyed clips table. One row per clip extracted from a video transcript. Substrate-aligned (claims/quotes/stances/locations in child tables). Included in the `content_items` union view via `clip_uuid`.  
**Populated by:** `backend/collectors/youtube_v2/` extractor task (Hetzner), after relay delivers transcript to `pending_youtube_videos`.  
**Read by:** Night-desk Home feed, `content_items` view, relevance scorer (`user_clip_relevance`), `youtube_clip_entity_mentions` matview.  
**Freshness:** Last row 2026-06-19 15:36 UTC (actively updated).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | bigint | NOT NULL | GENERATED ALWAYS AS IDENTITY | Surrogate PK (integer sequence). Used in FK references from child tables. |
| video_id | text | NOT NULL | — | YouTube video ID, e.g. `dQw4w9WgXcQ`. |
| video_title | text | NOT NULL | — | Full title of the source video. |
| channel_id | text | NOT NULL | — | YouTube channel ID string. |
| channel_name | text | NOT NULL | — | Human-readable channel name. |
| video_published_at | timestamptz | NULL | — | Video publish timestamp from YouTube metadata. NULL if unavailable. |
| video_url | text | NOT NULL | — | Full watch URL, e.g. `https://youtube.com/watch?v=…`. |
| clip_start_seconds | integer | NOT NULL | — | Start offset within the video (seconds). |
| clip_end_seconds | integer | NOT NULL | — | End offset within the video (seconds). |
| embed_url | text | NOT NULL | — | Iframe-embeddable URL with start time param. |
| matched_entity | text | NOT NULL | — | Canonical entity name that triggered this clip, e.g. `"KCR"`. Validated at insert. |
| summary | text | NOT NULL | — | English summary of clip content. Non-filler, validated at insert. |
| transcript_segment | text | NOT NULL | — | Raw transcript text for the clip window. CHECK: btrim length > 0. |
| transcript_language | text | NOT NULL | — | ISO language code, e.g. `"te"`, `"hi"`, `"en"`. |
| transcript_source | text | NOT NULL | — | `'manual_captions'` or `'auto_captions'`. |
| confidence | real | NOT NULL | — | Clip extraction confidence, 0.0–1.0. |
| importance | varchar(20) | NOT NULL | `'medium'` | `'high'` / `'medium'` / `'low'` — entity prominence within clip. |
| labse_embedding | vector(768) | NULL | — | LaBSE embedding (v4 recipe). 5,060/5,058 rows populated (effectively all). Used for semantic clustering. |
| relevance_score | real | NULL | — | Per-user relevance score (0 rows populated — scored in `user_clip_relevance`). |
| processed | boolean | NOT NULL | `false` | Whether substrate NLP (substrate enrichment pass) has completed. |
| created_at | timestamptz | NOT NULL | `now()` | Row insertion time. |
| clip_uuid | uuid | NOT NULL | `gen_random_uuid()` | UUID surrogate for `content_items` UNION view (id is BIGINT; view needs UUID across arms). |
| segment_type | varchar(30) | NULL | — | `debate` / `interview` / `speech` / `press_conference` / `news_report` / `panel`. Set by substrate enrichment. |
| speaker | text | NULL | — | Identified speaker name. NULL is correct for auto-captions (no speaker labels). |
| primary_subject | text | NULL | — | Primary topic subject string. Set by enrichment pass. |
| topic_category | varchar(20) | NULL | — | Coarse topic bucket, e.g. `POLITICS`, `CRIME`. Mirrors article substrate. |
| topic_fine | varchar(20) | NULL | — | Fine-grained topic within category. |
| entities_extracted | jsonb | NULL | — | spaCy-extracted entities JSON blob. 3,424/5,058 rows populated. |
| substrate_status | varchar(16) | NOT NULL | `'pending'` | `pending` → `processing` → `ok` / `extract_failed` / `junk`. Mirrors articles.substrate_status. |
| extraction_version | integer | NOT NULL | `0` | Incremented each extraction pass. |
| enriched_at | timestamptz | NULL | — | Timestamp of last substrate enrichment completion. |
| is_watchlisted | boolean | NOT NULL | `true` | `true` = matched_entity is a monitored user entity; `false` = newsworthy clip kept in keep-all mode (migration 111). 3,796 true / 1,264 false. |

**Joins:**
- `youtube_clip_claims.clip_id → id`
- `youtube_clip_locations.clip_id → id`
- `youtube_clip_quotes.clip_id → id`
- `youtube_clip_stances.clip_id → id`
- `youtube_clip_entity_mentions.clip_id → id` (matview)
- `user_clip_relevance.clip_id → id`
- Referenced in `content_items` view via `clip_uuid`

**Notes:** `video_published_at` is the original YouTube publish timestamp, not the processing time. Claims backfill for old clips (confidence flat 0.85, is_direct always false) was a known bug fixed in commit 04485bc — old clips may have stale claim values.

---

## public.youtube_clips — [FROZEN since 2026-06-07] (~13,735 rows, 118 MB)

**Purpose:** Legacy clips table from the original pipeline. Larger row count but no substrate child tables and no FK references. No new writes since 2026-06-07.  
**Populated by:** Old youtube pipeline (pre-v2). No longer written.  
**Read by:** Legacy queries only; not in `content_items` view.  
**Freshness:** `MAX(collected_at) = 2026-06-07 02:27 UTC`. FROZEN.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NOT NULL | `gen_random_uuid()` | UUID PK (contrast: v2 uses BIGINT). |
| video_id | text | NOT NULL | — | YouTube video ID. |
| video_title | text | NOT NULL | — | Source video title. |
| channel_id | text | NOT NULL | — | YouTube channel ID. |
| channel_name | text | NOT NULL | — | Channel display name. |
| video_published_at | timestamptz | NULL | — | Video publish timestamp. |
| video_url | text | NOT NULL | — | Watch URL. |
| clip_start_seconds | integer | NOT NULL | — | Start offset (seconds). |
| clip_end_seconds | integer | NOT NULL | — | End offset (seconds). |
| embed_url | text | NOT NULL | — | Iframe embed URL. |
| transcript_segment | text | NOT NULL | — | Raw transcript window text. |
| transcript_language | text | NULL | `'en'` | ISO language code, default English. |
| transcript_translated | text | NULL | — | English translation if source non-English. |
| matched_entity | text | NOT NULL | — | Canonical entity name that triggered clip. |
| matched_entity_type | text | NULL | — | Entity type string (PERSON, ORG, etc.). |
| labse_embedding | vector(768) | NULL | — | LaBSE embedding (legacy recipe — may be wrong-recipe; v4 campaign does NOT target this table). |
| relevance_score | float8 | NULL | — | Relevance score (old scorer). |
| collected_at | timestamptz | NULL | `now()` | Row insertion time (note: column name differs from v2's `created_at`). |
| processed | boolean | NULL | `false` | NLP processing flag. |
| transcript_source | text | NULL | `'captions'` | Source of transcript (`'captions'` in legacy; v2 uses `'manual_captions'`/`'auto_captions'`). |
| confidence | numeric(4,3) | NULL | `0.600` | Clip confidence, legacy default 0.600 (v2 has no DB default). |

**Joins:** None — no FK references from child tables.

**Notes:** 118 MB vs 50 MB for v2 despite 2.7× more rows, mainly due to TOAST-stored embeddings. Do not join with v2 child tables. The `collected_at` column (not `created_at`) is the insertion timestamp. This table should be treated as an archive.

---

## public.youtube_clip_claims — [LIVE] (~14,144 rows, 3.7 MB)

**Purpose:** Structured SPO (subject-predicate-object) claims extracted from clip transcripts by the Groq LLM substrate pass.  
**Populated by:** Substrate NLP task targeting `youtube_clips_v2`.  
**Read by:** Clip detail pages; analyst RAG.  
**Freshness:** Active (follows youtube_clips_v2 substrate processing).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NOT NULL | `gen_random_uuid()` | PK. |
| clip_id | bigint | NOT NULL | — | FK → `youtube_clips_v2.id`. |
| claim_text | text | NOT NULL | — | Full natural-language claim, e.g. `"KCR announced 2 crore jobs"`. |
| subject_text | text | NULL | — | SPO subject, e.g. `"KCR"`. NULL if extraction failed. |
| predicate | text | NULL | — | SPO predicate, e.g. `"announced"`. |
| object_text | text | NULL | — | SPO object, e.g. `"2 crore jobs"`. |
| confidence | real | NOT NULL | `0.5` | Claim confidence 0.0–1.0. Default 0.5 (old clips may have flat 0.85 — known bug). |
| created_at | timestamptz | NOT NULL | `now()` | Row creation time. |

**Joins:** `clip_id → youtube_clips_v2.id`

**Notes:** Known bug (pre-04485bc): `claims=0` on old clips (SPO extraction had no text-key), `confidence` flat at 0.85, `is_direct` always false on `youtube_clip_quotes`. Claims backfill for old clips still pending.

---

## public.youtube_clip_locations — [LIVE] (~4,400 rows, 792 kB)

**Purpose:** Geographic locations mentioned in each clip, with structured geo decomposition.  
**Populated by:** Substrate NLP task.  
**Read by:** Geo-filter on clip feed; relevance geo multiplier.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NOT NULL | `gen_random_uuid()` | PK. |
| clip_id | bigint | NOT NULL | — | FK → `youtube_clips_v2.id`. |
| location_text | text | NOT NULL | — | Raw location string, e.g. `"Hyderabad"`. |
| country | text | NULL | — | ISO country code or name, e.g. `"IN"`. |
| region | text | NULL | — | State/region, e.g. `"Telangana"`. |
| city | text | NULL | — | City, e.g. `"Hyderabad"`. |
| is_primary | boolean | NOT NULL | `false` | True for the primary/most-prominent location in the clip. |
| created_at | timestamptz | NOT NULL | `now()` | Row creation time. |

**Joins:** `clip_id → youtube_clips_v2.id`

---

## public.youtube_clip_quotes — [LIVE] (~4,079 rows, 1.4 MB)

**Purpose:** Speaker-attributed quotes extracted from clip transcripts.  
**Populated by:** Substrate NLP task.  
**Read by:** Clip detail pages; speaker analysis.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NOT NULL | `gen_random_uuid()` | PK. |
| clip_id | bigint | NOT NULL | — | FK → `youtube_clips_v2.id`. |
| speaker_name | text | NOT NULL | — | Attributed speaker, e.g. `"KCR"`. |
| quote_text | text | NOT NULL | — | The quote text. |
| is_direct | boolean | NOT NULL | `true` | True = direct quote; false = paraphrase. Old clips may have this wrong (always false bug, fixed in 04485bc). |
| created_at | timestamptz | NOT NULL | `now()` | Row creation time. |

**Joins:** `clip_id → youtube_clips_v2.id`

---

## public.youtube_clip_stances — [LIVE] (~5,267 rows, 1.1 MB)

**Purpose:** Actor→target stance records (directed sentiment) for each clip.  
**Populated by:** Substrate NLP task (Groq LLM).  
**Read by:** Entity stance analysis; relevance scorer (sentiment_for_user).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NOT NULL | `gen_random_uuid()` | PK. |
| clip_id | bigint | NOT NULL | — | FK → `youtube_clips_v2.id`. |
| actor | text | NOT NULL | — | The entity expressing the stance, e.g. `"BJP"`. |
| target | text | NULL | — | The entity targeted by the stance, e.g. `"KCR"`. NULL = self-stance. |
| stance | text | NOT NULL | `'neutral'` | `'positive'` / `'negative'` / `'neutral'`. |
| intensity | numeric | NOT NULL | `0.5` | Stance intensity 0.0–1.0. |
| created_at | timestamptz | NOT NULL | `now()` | Row creation time. |

**Joins:** `clip_id → youtube_clips_v2.id`

**Notes:** `actor` column = SOURCE of stance; `target` column = entity being assessed. Do not confuse with article_stances (same schema, different parent table).

---

## public.youtube_clip_entity_mentions — [LIVE MATVIEW] (~660 rows, 200 kB)

**Purpose:** Canonical entity mapping for YouTube clips — resolves `matched_entity` text to `entity_dictionary` UUIDs. Intentionally separate from article/clipping matviews to keep CM metrics article-only.  
**Populated by:** `REFRESH MATERIALIZED VIEW youtube_clip_entity_mentions` (scheduled).  
**Read by:** Entity pages; clip → entity joins.  
**Freshness:** Last refresh unknown; 660 rows as of 2026-06-19.

| column | type | nullable | meaning & example values |
|---|---|---|---|
| clip_id | bigint | NULL | FK-equivalent → `youtube_clips_v2.id`. |
| entity_id | uuid | NULL | FK-equivalent → `entity_dictionary.id`. |
| canonical_name | text | NULL | Canonical entity name, e.g. `"K. Chandrashekar Rao"`. |
| entity_type | text | NULL | Entity type from dictionary, e.g. `PERSON`, `ORG`. |
| country | char(2) | NULL | 2-char ISO country from entity_dictionary. |
| surface_form | text | NULL | The surface form as it appeared in the clip's matched_entity field. |
| mention_rows | integer | NULL | Count of clips matching this entity. |

**Joins:** Joins to `youtube_clips_v2` on `clip_id`; joins to `entity_dictionary` on `entity_id`.

**Notes:** relkind = `m` (materialized view). All columns nullable because it is a matview projection. Not in `information_schema.tables` — query via `pg_matviews` or `pg_class WHERE relkind='m'`.

---

## public.youtube_channels — [LIVE] (~72 rows, 1.2 MB)

**Purpose:** Channel registry for the youtube_v2 pipeline. Controls which channels are polled for new videos and their priority/quality metadata.  
**Populated by:** Manual admin inserts / channel management.  
**Read by:** Discovery task (RSS poller), prioritisation logic.  
**Freshness:** `MAX(last_checked_at) = 2026-06-19 15:22 UTC` (actively polled).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NOT NULL | `gen_random_uuid()` | PK. |
| channel_id | text | NOT NULL | — | YouTube channel ID string, UNIQUE. |
| channel_name | text | NOT NULL | — | Display name. |
| channel_url | text | NOT NULL | — | Full channel URL. |
| description | text | NULL | — | Channel description (optional). |
| subscriber_count | integer | NULL | — | Subscriber count (not actively refreshed). |
| is_active | boolean | NULL | `true` | Whether channel is actively polled. 67 active / 5 inactive. |
| last_checked_at | timestamptz | NULL | — | Last discovery poll timestamp. |
| created_at | timestamptz | NULL | `now()` | Channel registration time. |
| tier | text | NULL | `'tier_2'` | `'tier_1'` (11) / `'tier_2'` (34) / `'tier_3'` (27). Priority tier for polling. |
| poll_priority | integer | NULL | `50` | Numeric poll priority (higher = checked more often). |
| quality_score | numeric(4,3) | NULL | `0.500` | Channel quality score 0.000–1.000. |
| language | text | NULL | `'mixed'` | Primary language, e.g. `'te'`, `'hi'`, `'en'`, `'mixed'`. All 72 rows = `'mixed'` (not yet populated per-channel). |
| category | text | NULL | — | Channel category (politics, business, etc.). |
| last_yielded_at | timestamptz | NULL | — | Last time a video from this channel was successfully yielded. |
| consecutive_dry_polls | integer | NULL | `0` | Number of consecutive polls finding no new videos. |
| last_video_published_at | timestamptz | NULL | — | Published timestamp of the most recent known video. |
| deactivated_reason | text | NULL | — | Human note explaining why is_active was set false. |

**Joins:** `channel_id` (text) cross-references `youtube_clips_v2.channel_id` and `pending_youtube_videos.channel_id` (both text, no FK constraint).

**Notes:** `language` column shows `'mixed'` for all 72 rows — not yet per-channel populated despite the column existing. Tier distribution: tier_1=11, tier_2=34, tier_3=27. This table is separate from `newsroom_channels` (different pipeline, different ID scheme).

---

## public.pending_youtube_videos — [LIVE] (~19,837 rows, 38 MB)

**Purpose:** Discovery-to-transcript queue. Hetzner RSS discovery inserts rows here; the residential relay drains them by fetching transcripts; a Hetzner task then extracts clips from transcribed rows.  
**Populated by:** RSS discovery collector (Hetzner).  
**Read by:** Relay fetch worker (residential), clip extractor task (Hetzner).  
**Freshness:** `MAX(updated_at) = 2026-06-19 15:46 UTC` (actively drained).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | bigint | NOT NULL | GENERATED ALWAYS AS IDENTITY | PK (integer sequence). |
| video_id | text | NOT NULL | — | YouTube video ID (UNIQUE). |
| video_title | text | NOT NULL | — | Video title at discovery time. |
| channel_id | text | NOT NULL | — | YouTube channel ID. |
| channel_name | text | NOT NULL | — | Channel display name. |
| video_published_at | timestamptz | NULL | — | Video publish timestamp from RSS. |
| status | text | NOT NULL | `'pending'` | Status lifecycle — see below. CHECK constraint enforces valid values. |
| transcript_json | jsonb | NULL | — | Full transcript from relay: `{video_id, language, source, segments: [{start, duration, text}]}`. Set on transition to `transcribed`. |
| transcript_language | text | NULL | — | Language code from relay (e.g. `"te"`). |
| transcript_source | text | NULL | — | `'manual_captions'` or `'auto_captions'`. |
| attempts | integer | NOT NULL | `0` | Fetch attempt count. Incremented on each relay attempt. |
| last_error | text | NULL | — | Last error message from relay or extractor. |
| discovered_at | timestamptz | NOT NULL | `now()` | Discovery timestamp. |
| transcribed_at | timestamptz | NULL | — | Timestamp when relay delivered transcript. |
| extracted_at | timestamptz | NULL | — | Timestamp when clip extraction completed. |
| updated_at | timestamptz | NOT NULL | `now()` | Last status update timestamp. |
| extract_attempts | integer | NOT NULL | `0` | Extraction attempt count (added migration 110, retry counter after 429 bug). |
| is_political | boolean | NOT NULL | `false` | Title mentions a watched entity or political term. Prioritised to front of fetch queue (migration 112). NEVER aged out. 11,289 true / 8,548 false. |

**Status lifecycle (live counts 2026-06-19):**

| status | count | meaning |
|---|---|---|
| `skipped` | 14,337 | Hourly cull — oldest pending rows aged out to bound queue size (newest-first policy). |
| `extracted` | 2,780 | Transcript fetched + clips extracted into `youtube_clips_v2`. Terminal success. |
| `pending` | 1,830 | Awaiting relay fetch. |
| `failed` | 626 | Relay or extractor exhausted retries. |
| `no_transcript` | 258 | Video has no captions available (live chat, music, etc.). |
| `fetching` | 6 | Currently being fetched by relay (stale if relay crashed; these 6 rows are from 2026-06-17). |

**Joins:** `channel_id` cross-references `youtube_channels.channel_id` (text, no FK). `video_id` is UNIQUE.

**Notes:** `fetching` status added in migration 109 to detect relay crashes. `extract_attempts` added in migration 110 after a bug set status=`extracted` unconditionally even on 429 errors. Priority index: `(status, is_political DESC, video_published_at DESC)` — political videos always fetched first within `pending`. Discovery rate ~2,400/day vs fetch ceiling ~480/day — explains the large `skipped` count (queue bounding).

---

## public.newsroom_channels — [LIVE registry, LOW activity] (~25 rows, 640 kB)

**Purpose:** Channel registry for THE NEWSROOM pipeline — a separate `/clips` redesign targeting Telugu/Hindi/English live TV. Distinct from `youtube_channels` (different pipeline). Cross-reference to YouTube via `yt_handle`.  
**Populated by:** Manual seeding.  
**Read by:** Newsroom liveness checker task (`tasks.newsroom.check_liveness`).  
**Freshness:** `MAX(last_live_check_at) = 2026-05-25 07:28 UTC` — liveness checks stalled ~25 days ago.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NOT NULL | `gen_random_uuid()` | PK. |
| name | text | NOT NULL | — | Human name, e.g. `"TV9 Telugu"`. |
| yt_handle | text | NOT NULL | — | YouTube @handle, UNIQUE. e.g. `"@tv9telugulive"`. |
| language | text | NOT NULL | — | `'te'` / `'hi'` / `'en'`. All 25 rows = `'te'` (Telugu). |
| beat | text | NOT NULL | — | Editorial beat, e.g. `'telangana_politics'`. All 25 rows = `'telangana_politics'`. |
| is_live_24x7 | boolean | NOT NULL | `false` | Whether channel is always-live. 21 true / 4 false. |
| active | boolean | NOT NULL | `true` | Whether channel is actively monitored. 22 active / 3 inactive. |
| created_at | timestamptz | NOT NULL | `now()` | Registration time. |
| current_live_video_id | text | NULL | — | YouTube video ID of currently-live broadcast. NULL if not live. Refreshed every 5 min by liveness task (currently stalled). |
| current_live_title | text | NULL | — | Title of current live broadcast. |
| last_live_check_at | timestamptz | NULL | — | Last liveness check timestamp. `MAX = 2026-05-25`. |
| last_live_at | timestamptz | NULL | — | Most recent observed-live timestamp. Persists across non-live windows. |

**Joins:** `newsroom_broadcasts.channel_id → id`.

**Notes:** All 25 seeded channels are Telugu (`language='te'`), all on `beat='telangana_politics'`. The liveness checker has not run since 2026-05-25. No FK to `youtube_channels`.

---

## public.newsroom_broadcasts — [LIVE schema, LOW activity] (~2 rows, 112 kB)

**Purpose:** One row per broadcast (live stream window or VOD ingest). A 24×7 channel creates a new row each time the stream goes up; VOD ingest creates one row per video.  
**Populated by:** Newsroom ingest task.  
**Read by:** Newsroom segment queries.  
**Freshness:** `MAX(started_at) = 2026-05-10 06:52 UTC`. Only 2 rows — pipeline is stalled.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NOT NULL | `gen_random_uuid()` | PK. |
| channel_id | uuid | NOT NULL | — | FK → `newsroom_channels.id`. |
| yt_video_id | text | NOT NULL | — | YouTube video ID. UNIQUE per (channel_id, yt_video_id). |
| title | text | NULL | — | Broadcast title in source language. |
| title_en | text | NULL | — | English translation of title. |
| started_at | timestamptz | NOT NULL | — | Broadcast start timestamp. |
| ended_at | timestamptz | NULL | — | Broadcast end (NULL if still live). |
| is_live | boolean | NOT NULL | `false` | Whether broadcast was/is a live stream. Both rows = `false` (VOD). |
| duration_sec | integer | NULL | — | Duration in seconds. |
| created_at | timestamptz | NOT NULL | `now()` | Row creation time. |

**Joins:** `channel_id → newsroom_channels.id` (CASCADE DELETE). `newsroom_segments.broadcast_id → id`.

---

## public.newsroom_segments — [LIVE schema, LOW activity] (~37 rows, 168 kB)

**Purpose:** Speaker-attributed transcript segments from broadcasts. Holds canonical reconciled text plus all 3 raw lens outputs (yt-dlp auto-captions, Groq Whisper, local ASR) for audit. One segment = one speech turn or time window.  
**Populated by:** Newsroom transcript/speaker diarization task.  
**Read by:** ECHO mode, DOSSIER mode, newsroom entity analysis.  
**Freshness:** `MAX(created_at) = 2026-05-10 06:52 UTC`. 37 rows — pipeline stalled.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NOT NULL | `gen_random_uuid()` | PK. |
| broadcast_id | uuid | NOT NULL | — | FK → `newsroom_broadcasts.id`. |
| start_sec | numeric(10,2) | NOT NULL | — | Segment start offset in seconds. |
| end_sec | numeric(10,2) | NOT NULL | — | Segment end offset. |
| speaker_label | text | NULL | — | Raw diarization label, e.g. `'SPEAKER_01'` from pyannote. |
| speaker_entity_id | uuid | NULL | — | FK → `entity_dictionary.id` (resolved speaker). SET NULL on delete. |
| text_native | text | NOT NULL | — | Canonical text in source language. |
| text_en | text | NULL | — | English translation. |
| confidence | numeric(3,2) | NULL | — | ASR/transcription confidence 0.00–1.00. |
| l1_text | text | NULL | — | Lens 1: yt-dlp auto-captions (raw). |
| l2_text | text | NULL | — | Lens 2: Groq Whisper output (raw). |
| l3_text | text | NULL | — | Lens 3: local ASR (Faster-Whisper / IndicConformer) (raw). |
| is_quote | boolean | NOT NULL | `false` | True if segment is a direct quote (Phase 3 extract_quotes). 5 of 37 rows. |
| is_editorial | boolean | NOT NULL | `false` | True if anchor opinion vs reported speech. 2 of 37 rows. |
| sentiment | numeric(3,2) | NULL | — | Sentiment score -1.00 to +1.00. |
| framing | text | NULL | — | Framing label (e.g. `'alarmist'`, `'neutral'`). |
| is_live | boolean | NOT NULL | `false` | True if segment was from a live broadcast (as opposed to VOD). 0 of 37 rows live. |
| created_at | timestamptz | NOT NULL | `now()` | Row creation time. |

**Joins:** `broadcast_id → newsroom_broadcasts.id`; `speaker_entity_id → entity_dictionary.id`; `newsroom_entity_mentions.segment_id → id`; `newsroom_breaking_segments.segment_id → id`.

**Notes:** The 3-lens audit fields (`l1_text`, `l2_text`, `l3_text`) are kept verbatim to allow post-hoc regression debugging of the 3-Lens Consensus pipeline. `text_native` is the canonical reconciled output.

---

## public.newsroom_entity_mentions — [LIVE schema, LOW activity] (~86 rows, 112 kB)

**Purpose:** Segment ↔ entity_dictionary join table. Drives ECHO (entity co-occurrence) and DOSSIER (entity timeline) modes. One row per entity mention within a segment.  
**Populated by:** Newsroom entity extraction task.  
**Read by:** ECHO mode, DOSSIER mode.  
**Freshness:** 86 rows, all from 2026-05-10 window. Stalled.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NOT NULL | `gen_random_uuid()` | PK. |
| segment_id | uuid | NOT NULL | — | FK → `newsroom_segments.id`. |
| entity_id | uuid | NOT NULL | — | FK → `entity_dictionary.id`. |
| span_start | integer | NULL | — | Character offset start within `text_native`. |
| span_end | integer | NULL | — | Character offset end within `text_native`. |
| was_phonetic | boolean | NOT NULL | `false` | True if entity was matched phonetically (Telugu ASR name variants). |
| created_at | timestamptz | NOT NULL | `now()` | Row creation time. |

**Joins:** `segment_id → newsroom_segments.id`; `entity_id → entity_dictionary.id`.

---

## public.newsroom_breaking_segments — [EMPTY] (~0 rows, 16 kB)

**Purpose:** Many-to-many join between breaking-news clusters and segments. Enables the WALL banner to show "carried by N channels — see segments [...]". A segment can belong to multiple clusters (edge case).  
**Populated by:** Newsroom breaking-news clustering task.  
**Read by:** WALL banner / breaking news UI.  
**Freshness:** 0 rows. Table created, never populated.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| cluster_id | uuid | NOT NULL | — | FK → `newsroom_breaking_clusters.id` (CASCADE DELETE). Part of composite PK. |
| segment_id | uuid | NOT NULL | — | FK → `newsroom_segments.id` (CASCADE DELETE). Part of composite PK. |

**Joins:** `cluster_id → newsroom_breaking_clusters.id`; `segment_id → newsroom_segments.id`.

**Notes:** `newsroom_breaking_clusters` is not in the assigned table list but is the parent referenced by this join table. The table has a secondary index on `segment_id` for reverse lookups.

---

## Table Summary

| table | kind | rows | size | status |
|---|---|---|---|---|
| youtube_clips_v2 | table | 5,058 | 50 MB | LIVE (last write 2026-06-19) |
| youtube_clips | table | 13,735 | 118 MB | FROZEN (last write 2026-06-07) |
| youtube_clip_claims | table | 14,144 | 3.7 MB | LIVE |
| youtube_clip_locations | table | 4,400 | 792 kB | LIVE |
| youtube_clip_quotes | table | 4,079 | 1.4 MB | LIVE |
| youtube_clip_stances | table | 5,267 | 1.1 MB | LIVE |
| youtube_clip_entity_mentions | matview | 660 | 200 kB | LIVE |
| youtube_channels | table | 72 | 1.2 MB | LIVE |
| pending_youtube_videos | table | 19,837 | 38 MB | LIVE |
| newsroom_channels | table | 25 | 640 kB | LIVE registry; liveness stalled 2026-05-25 |
| newsroom_broadcasts | table | 2 | 112 kB | STALLED (last 2026-05-10) |
| newsroom_segments | table | 37 | 168 kB | STALLED (last 2026-05-10) |
| newsroom_entity_mentions | table | 86 | 112 kB | STALLED (last 2026-05-10) |
| newsroom_breaking_segments | table | 0 | 16 kB | EMPTY |
