# 05 — Data Model & Pipelines

## Key tables / views (in `public.*` unless noted)
| Object | Role |
|---|---|
| `articles` | Core corpus. Fields used a lot: `title`, `collected_at`, `source_id`, `topic_category`, `geo_primary` (free-text place, e.g. "Andhra Pradesh", "Amaravati", "Bengaluru"), `language_iso`, `thumbnail_url`, `entities_extracted` (jsonb array), and the TEXT fields below. |
| `article_stances` | Sentiment polarity (`intensity`, ±1). Basis of POL / tone. |
| `article_entity_mentions` | Article ↔ entity (defines the persona universe). |
| `article_districts` | Article ↔ district (state-level scoping / map RBAC). |
| `sources` | Outlets (`name`, `source_tier`, country). |
| `entity_dictionary` | Entities (`canonical_name`, `aliases`, `entity_type`, `redirected_to` for merges). |
| `districts` | Indian districts (`name`, `state_code`, centroid lat/lon). |
| `analytics.user_brief_prefs` | Per-user persona config (see 03). |
| `analytics.home_cache` | 30-min precompute for Home/WarRoom/Analytics/Map. |
| `analytics.text_en` | **Translation cache** (`src_hash` → `text_en`) used by i18n. |
| `analytics.now_sim()` | The live/replay clock for all time gates. |

## Article TEXT fields (important for summaries)
- `summary_executive` — LLM exec summary. **Only ~60–72% coverage** (varies by
  language/source). This is the *preferred* card summary.
- `summary_preview`, `summary_snippet` — effectively **empty** (0% in samples).
- `lead_text_translated` / `lead_text_original` — article lead. **`lead_text_translated`
  is often still the original language (Telugu) for ~84% of te articles** — it is
  NOT reliably English. ~98% of articles missing an exec summary DO have a lead.
- `full_text_translated`, `full_text_scraped` — full body.
- `thread_id` — intended event/story cluster id, **currently 0% populated** (event
  clustering isn't running) → cannot be used for same-event de-dup yet.
- `is_duplicate` / `duplicate_of` — near-dup flags (~9% flagged).

## The relevance core (`relevance.py`)
- `score_relevant(db, prefs, window_hours, limit, half_life_h)` returns scored
  articles. Signals: entity tier (subject ×6 / core ×3 / extended ×1.5-on-turf),
  title-salience +2, keyword +1.5, geo ±, topic ±, noise −4; multiplied by an
  exponential freshness decay (`half_life_h`).
- The candidate SQL (`_SQL`) is **plan-stable on purpose** — a clever
  salience-first WHERE once flipped Postgres into a 15-minute plan. **Do the clever
  re-ranking in Python**, not in that SQL. Treat SQL changes there as high-risk.
- `summary` returned = `COALESCE(summary_executive, lead_text_translated, lead_text_original)`
  (HTML-stripped, capped ~400 chars) — this is the 2026-06-05 summary fallback.

## i18n (`i18n.py`)
- `attach_en(db, items, key)` translates a non-English field to English via the
  free Google endpoint and caches in `analytics.text_en` (translate-once).
- `is_english(s)` = script-ratio check. Headlines AND summaries are translated
  this way (summary translation added 2026-06-05).

## Ingestion (the wider RIG platform feeds public.articles)
- Articles/clips/docs are ingested by the main **rig-backend** Celery workers
  (separate container). osint-backend only READS. Freshness is healthy
  (~14k articles/24h; AP-relevant ~60/day; newest minutes old).
- **YouTube clips** ingestion runs on rig-backend's `youtube` queue (re-enabled
  2026-06-05 — see 06/07).
