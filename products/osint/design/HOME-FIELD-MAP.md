# HOME PAGE — complete field & table map (every component)

Legend: ✅ verified usable (coverage) · ⚠️ thin/use-with-care · ❌ empty — DO NOT USE ·
⚙️ derived (we compute it) · 🤖 LLM (faithfulness-gated) · 👤 from user prefs.
All coverage figures are live-DB verified (corpus ≈ 139,681 articles).

## MASTER INVENTORY — what's actually usable

### Persona / config — `analytics.user_brief_prefs` 👤
- `primary_subject_id` (= YOU), `primary_subject_meta` (name/role/party)
- `watchlist.entity_meta[]` (rivals/allies, with relation), `topics`, `regions`, `languages`

### `articles` (≈139,681)
- `title` ✅100 · `summary_executive` ✅75 · `summary_preview/snippet` ✅
- `collected_at` ✅ (date; 2026-04-16 → 06-01) · `language_iso` ✅ (en 66% / te 11% / kn / hi; null 16%)
- `topic_category` ✅98.8 (COARSE: OTHER 37.7%, AGRICULTURE 1,210, FINANCE 5,540) · `topic_fine` ⚠️11
- `register_emotion` ✅75 (neutral/alarm/curiosity/approval/urgency/lament/admiration/mockery/concern/criticism/anger…) → **article emotional tone + rough polarity**
- `register_style` ✅75 (factual/analytical/polemical/promotional/sensational) → **attack-piece vs straight news**
- `article_type` ✅85 (news/opinion/analysis/explainer) → **op-ed detector (opinion+analysis)**
- `register_is_breaking` ✅ → breaking flag · `primary_subject` ✅75 · `geo_primary` ✅73.6
- `thumbnail_url` ✅ (exists) · `source_id` · `source_tier` ✅99.3 · `labse_embedding` ✅98.5 (the workhorse)
- `byline` ~66 · `author_name` ~38
- ❌ `narrative_frame` (0%) · ❌ `content_type` (all "article", no TV)

### `article_entity_mentions` (348k) — who's in each article
- `entity_id` ✅76.5 resolved · `article_id` · `surface_forms` · (87.2% of articles have entities)
### `entity_dictionary` (17,165) — `canonical_name`, `aliases` (resolve id→name) ✅
### `article_stances` (118,835; 34% of articles) — explicit directional stance
- `actor_entity_id` (WHO) · `stance` (effectively supportive/critical/neutral) · `intensity` ✅ (0.1–1.0)
- ⚠️ NO `target` column → "toward you" = salience proxy
### `article_quotes` (77,989; 24.5% of articles)
- `speaker_entity_id` ✅50.9 · `speaker_name` ✅100 · `quote_text` ✅ · `quote_text_en` ❌0.3 (translate via 🤖)
### `sources` (993) — `name`, `source_tier` ✅99.3 (1/2/3), `geo_states`, `language`
- (`source_type` = rss/scrape/api = ingest method, NOT media type)
### `article_locations` (289k; region/city 73.6%) — `country/region/city` ✅, `lat/lng` ⚠️27, `is_primary`
### `article_districts` (32k; ⚠️14%) — district tagging (thin)
### `article_media` (1.7M; 83% of articles) — `media_url` → thumbnails
### `entity_mention_daily` (28k; ~10 days only 2026-05-22→06-01)
- keyed by `entity_text` (NAME not id) · `date` · `n_claims/n_quotes/n_stances/n_sources/n_mentions_total` → **daily trajectory/velocity** (⚠️ no hourly, ~10-day window)

### ❌ EMPTY — never reference
story clusters (`event_cluster_id` 398/246k, 96% singletons) · `narrative_frame` (0) · `narrative_cluster_members` (0) · `entity_mention_hourly` (doesn't exist) · `quote_text_en` (~0.3%) · `content_type` (single value) · `topic_fine` (11%)

### ⚙️ DERIVED — we compute (no field exists)
- **STORY GROUP** = cluster articles by `labse_embedding` similarity in a time window + shared entities + title/FTS overlap (replaces empty clusters)
- **COORDINATION** = one story-group spanning N outlets within a short window
- **TRANSLATION** = 🤖 on `quote_text` · **"TV"** = heuristic on `sources.name` (no field)
- **RELEVANCE/personalization** = existing `relevance.score_relevant(prefs, window)`

---

## PER-COMPONENT FIELD MAP

### SHELL
- **Masthead** → prefs (`primary_subject_meta`), replay clock (as-of)
- **Breaking ticker** → `articles.register_is_breaking` + `collected_at` + relevance → `title`

### ① THE BRIEFING
**Bottom Line · Where You Stand** → `article_entity_mentions`(you) + `register_emotion` + `article_stances.intensity` + `language_iso` + `entity_mention_daily`(week-over-week) → score → 🤖
**Bottom Line · Know This** → ⚙️story-group + `entity_mention_daily`(daily growth) + `register_emotion` + `register_is_breaking` → 🤖
**Bottom Line · The Attack** → `article_stances`(neg)+`register_emotion` + `actor_entity_id`+`entity_dictionary`(who) + `source_tier` + `article_quotes`(the line) + ⚙️story spread → line
**Bottom Line · Your Move** → positive coverage (`register_emotion` approval/admiration + supportive `article_stances`) + attack facts → 🤖
**What Happened** → ⚙️story-group dedupe + `title`+`collected_at`+`sources.name`+`summary_executive` + relevance → 🤖 explanatory, fact-checked, source-linked
**What It Means** → fact-sheet: What-Happened + dominant `register_emotion`/`article_stances` + `actor_entity_id` + ⚙️coordination + cross-language(`language_iso`) + share-of-voice(`article_entity_mentions`) → 🤖
**Why It Matters** → strength by `topic_category` (emotion/stance per topic) + attacked topic + trend(`entity_mention_daily.n_stances`) → 🤖 ⚠️coarse topics
**What's Next** → rising story daily growth(`entity_mention_daily`) + spread: `language_iso`, `source_tier`, `article_type`, TV=⚙️heuristic → 🤖 + confidence ⚠️daily/~10-day, a guess
**How to Play It** → gaps: cross-language(`language_iso`) + silence(`topic_category` opp-vs-you counts) + real-vs-noise(⚙️spread) + op-eds(`article_type`=opinion/analysis) → 🤖 orders
**The Other Side** → negativity grouped by `source_id`(concentration) + `source_tier` + sample size + downplayed positives(`register_emotion`) + flip trigger → 🤖

### ② TOP STORIES FOR YOU
relevance(prefs topics/subject/regions) + ⚙️story-group dedupe → top ~6; per card: `title`, `sources.name`, `collected_at`(age), `article_media.media_url`/`thumbnail_url`(image), `topic_category`, `register_emotion`/`article_stances`(stance dot), `summary_executive` + relevance-reason → "For you" 🤖

### ③ PEOPLE TO WATCH
top entities: `watchlist`(prefs) + `article_entity_mentions`(top-mentioned) + `entity_dictionary`(name); per entity:
- sentiment toward you → `article_stances`(actor=entity, you salient) + `register_emotion`
- trajectory → `entity_mention_daily`(name-match) ⚠️~10-day
- quote → `article_quotes`(speaker_entity_id=entity)
- relation → `watchlist` meta or inferred from stance polarity
- summary/why/watch → 🤖 from the above

### THE SIX
**The Hard Truth** → silence(`topic_category` opp-vs-you, esp FINANCE) + cross-language(`language_iso`) + `register_emotion`/`article_stances` → 🤖
**Real or Noise?** → ⚙️story spread(`source` count + `source_tier` + `language_iso`) + `entity_mention_daily`(daily velocity) + `article_type` → verdict
**Are You Being Heard?** → `article_quotes.speaker_entity_id`(you vs opp) per `source_id` → ratio
**The Coverage Split** → `language_iso`(te vs en) + `geo_primary`/`article_locations.region` sentiment + `register_emotion`/`article_stances` → 🤖 ⚠️region not pins (lat/lng 27%, districts 14%)
**Who To Call** → per-`source` favourability (`article_stances`/`register_emotion` over time) + `source_tier` + trajectory + `byline`(journalist where present) → decision
**Ready For You** → 🤖 counter (from positive facts) + ⚙️translation(`quote_text`) + attack facts → drafts
