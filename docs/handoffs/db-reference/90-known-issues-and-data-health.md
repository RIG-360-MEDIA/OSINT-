# Known issues & data health — READ BEFORE TRUSTING A TABLE

Every item below was verified against **live production data on 2026-06-19**. This is the "what's stale,
broken, or a trap" layer — consult it before relying on any table for analysis or answering.

## 🔴 Broken features (queries fail or return garbage)
- **Chronicle is broken at runtime.** `products/osint/backend/routers/chronicle_router.py` queries
  UNSUFFIXED `analytics.story_clusters` / `story_facts` / `story_quotes` / `story_stance` / `story_timeline`
  — **none of those relations exist**. The keeper was renamed to `story_clusters_archive` when `_v8` was
  promoted and the router was never repointed. Only 1 `chronicle_cache` row + 2 `user_story_assignments`
  exist, and both FK to `story_clusters_archive`. Fix = repoint the router to `_v8` + migrate those rows.
- **CM-v2 district atlas is cosmetically healthy but meaningless.** `mv_district_stability_composite`
  shows `value = 100` for all 59 districts because 3 of its 4 input collectors are dead (AQI ~2,616 fails,
  ACLED ~123, power ~1,456 fails). Only the news component has real input. Do not treat the composite as real.
- **`weather_warnings` write path is broken.** The `imd_weather` collector reports `last_success_at`
  2026-06-19, yet the table is **0 rows** (fetches but never persists, or warnings expire first).

## 🟠 Frozen / stalled pipelines (rows exist but are STALE)
- **`youtube_clips` (legacy)** — FROZEN since 2026-06-07. Use **`youtube_clips_v2`** (LIVE, last write
  2026-06-19). Legacy is bigger (13,735 rows) but has no child tables.
- **Newsroom** (`newsroom_broadcasts`/`_segments`/`_entity_mentions`) — effectively stalled since
  **2026-05-10** (2 broadcasts, 37 segments, 86 mentions). Liveness checker last ran 2026-05-25.
  `newsroom_breaking_segments` is empty.
- **`newspaper_clippings` (legacy)** — FROZEN since 2026-05-26; superseded by **`clippings`** (LIVE).
  Still 387 MB on disk (base64 image blobs per row).
- **`article_districts` tagging stalled** — last insert 2026-06-11 → `mv_district_news_volume_24h` is
  EMPTY (24h window, nothing recent). The `tag_article_districts` task has stopped.
- **`pending_youtube_videos`** has 6 stale `fetching` rows from 2026-06-17 (a relay crash); the dominant
  status is `skipped` (~14,337 — the hourly newest-first cull bounding the queue).

## 🟡 Query traps (right table, wrong assumption)
- **Directed sentiment:** `article_stances.actor` / `actor_entity_id` is the **TARGET** of the sentiment,
  not the speaker. "Sentiment toward KCR" → `WHERE actor_entity_id = <KCR>`. Same for `clipping_stances`.
- **Emotion ≠ bias:** `register_emotion` (e.g. `alarm`) is event-emotion (alarm about a flood), not
  editorial hostility. Use `article_stances` for any negativity/bias measure.
- **Event dates:** use `article_events.effective_event_date` (year-clamped, migration 053), not `event_date`.
- **Embeddings:** `articles.labse_embedding` is **recipe-mixed** (two incompatible recipes). The locked
  recipe is `v4-tr-title-1024`; filter on the revision/recipe column before cosine search. Three embedding
  columns exist (`labse_embedding`, the v4 shadow, a v0 backup). Clip/clipping embeddings are not v4 →
  cross-pillar cosine is unreliable.
- **Relevance score columns:** `user_*_relevance` use `score_stage1` and `score_final`, **not `score`**.
  `user_govt_doc_relevance` differs from the others: adds `urgency` + `geo_match_strength`, uses
  `computed_at` not `scored_at`.
- **RBAC:** `analytics.users` has **no `role` column** — authz is the `is_super_admin` boolean. A text
  `role` (`user|super_admin`) exists only on `public.users`. The two user systems share no IDs/FKs.
- **`user_page_access`** column is `page_slug` (values: coverage, clips, cuttings, threads, signals,
  documents, brief, analyst, worldmonitor), not `page_key`.
- **`briefs`** stores body in a column literally named `content` (text); there is no `status`/`content_md`
  — row presence = success. `brief_quality_scores` joins on `(user_id, brief_date)`, no FK to `briefs.id`.
- **`topic_categories`** PK is `name` (text), no id. 25 rows = 15 originals (`is_new=false`,
  self-`rolls_up_to`) + 10 fine buckets (`is_new=true`) that collapse into only 6 of the 15 parents.
- **`story_sources_v8.source_tier` is 100% NULL** — join to `sources` for tier. **`story_enrichment_status_v8`
  has no `coverage_tag` column** (older code referencing it errors). **`story_generated_v8.member_hash` is
  NULL on older rows** → those always regenerate. **`story_clusters_v8.redirected_to` FKs to
  `story_clusters_archive`** (old keeper), not self.
- **`article_signals_mv`** has a hardcoded cutoff `2026-05-27 16:00 UTC` — pre-cutoff articles never appear
  even after re-processing.
- **`v_freshness_pipeline_lag`** measures only `embed` + `substrate`, articles only (no clip/clipping lag).
- **`youtube_channels.language` = `'mixed'` for all 72 rows** (never populated). **`is_watchlisted`**: ~25%
  of clips (1,264/5,058) are kept via keep-all mode → `WHERE is_watchlisted` silently drops them.
- **`entity_mention_daily`** joins by `entity_text` (not a UUID FK) → entity renames/merges do NOT cascade;
  must be backfilled after dictionary changes.

## 👻 Data artifacts / ghosts
- **`event_clusters_archive.canonical_date` max = `2060-01-01`** — a test artifact; `ORDER BY canonical_date`
  surfaces ghost rows at the top.
- **`districts` has 59 rows, not 33** — AP districts were seeded after the "33-row Telangana" comment.
- **`entity_dict_meta.entry_count` (17,066) lags the live `entity_dictionary` (19,356)** — ~2,290 entities
  added after the last meta refresh.
- **`entity_aliases`** is only 14 rows — a curated editorial override (KCR/KTR + Telugu-script
  disambiguation), not a bulk alias store.
- **`analytics.entity_image`** covers only ~0.7% of entities (134/19,356; 16 `ok=false`; last 2026-06-09).
- **`article_contradictions`** is effectively empty (1 row) despite the detection pipeline existing
  (needs claim density to trip the threshold).
- **`articles.geo_secondary`** is a dead hotfix column (migration 088) nothing reads — pending DROP.

## ⚪ Empty / planned (schema only, 0 rows)
`event_dissent`, `velocity_baselines`, `journalist_profiles`, `celery_tasksetmeta`, and the CM-v2 collector
sinks `acled_events`, `air_quality_readings`, `mandi_prices`, `power_grid_status`, `weather_warnings`,
`welfare_coverage`. Atlas matviews `mv_district_acled_7d` / `_mandi_volatility_30d` / `_news_volume_24h` /
`_power_stress` / `_welfare_coverage` are empty (their sources are empty/stalled).

## 🗑️ Leftover scratch (do NOT use; safe to drop later)
`analytics._v9_cand` / `_v9_members` / `_v9_members_pure` (kept only for an in-flight fix-test),
`story_cluster_members_v8shadow` / `_v8shadow4`, `story_edges_v8copy` / `_v8shadow` / `_v8shadow4`,
`analytics.hard_neg_fps`. These are validation scratch from the clustering rebuild.

## 💾 Largest objects (ops context)
`articles` 9.6 GB · `article_links` 4.6 GB · `article_claims` 2.6 GB · `clippings` 1.7 GB ·
`article_media` 1.3 GB · `newspaper_clippings` 387 MB (legacy blobs) · `kombu_message` 320 MB
(143k undrained broker messages — largest non-content table) · `story_clusters_v8` 285 MB.
