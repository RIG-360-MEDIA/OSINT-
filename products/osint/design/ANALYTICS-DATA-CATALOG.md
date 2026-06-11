# ANALYTICS — Pure-Data Catalog (verified against Hetzner `rig` DB, 2026-06-02)

> Scope: **pure data only** — counts, distributions, timelines, lists, breakdowns of
> raw collected/extracted facts. **No intelligence** (no scores, LLM prose, directional
> verdicts). Everything is *personalized*: filtered to the user's primary subject +
> watchlist + regions/topics/languages/sources. Derived/model outputs are listed
> separately in the **Excluded** appendix so we know what we're deliberately not using.
>
> Every number below is a live `count()` / `count(distinct)` from the production DB,
> not an estimate (pg_stat row estimates were stale for several tables).

---

## 0. The corpus, in one breath
- **149,455 articles.** Range 2010-06-29 → 2026-06-01, but **96% are Apr–Jun 2026**
  (Apr 19,568 · **May 112,407** · Jun 11,488). The meaningful analytics window is the
  ~47-day replay window (16 Apr – 01 Jun 2026); May is the dense month.
- **993 sources** (Tier-1 434 / T2 479 / T3 80; rss 686 / scrape 264 / api 43).
- **17,165 entities** in the dictionary (person 55% / org 22% / location 14% /
  constituency 7% / role 3%), each with `state`, `party`, `aliases`.

## 1. The personalization spine (how every card filters)
- **`analytics.user_brief_prefs`** (1 row per user) is the filter spec:
  `primary_subject_id`, `watchlist` (jsonb), `regions`, `topics`, `languages`,
  `sources`, `stance`, `events`. The user sets these in onboarding.
- **`public.user_entities`** (64 rows for the seeded user): `canonical_name`,
  `entity_type`, `why_watching`, `priority` — the curated watchlist (types: topic 36 /
  person 12 / scheme 6 / org 6 / project 2 / place 2). *`user_watchlist` is empty (0).*
- **The join:** watchlist `entity_id` → `article_entity_mentions(entity_id)` → `articles`
  → then slice by any facet below. "Your coverage" = articles mentioning your entities.
- ⚠️ **Rely on the curated watchlist, not raw top-mentions** — the highest-frequency
  `canonical_name`s are NER noise ("Government NDA Seats: 202", "Pen", "Amarish Der").

---

## PURE-DATA MODULES (the menu)

### A. Volume & time (the pulse) — `articles`
Source: `published_at` 96.7% · `collected_at` · `register_is_breaking` 100%.
- Total articles about your entities (filtered count) + Δ vs prior period.
- Daily / weekly **volume time-series** (the May spike is real).
- New in last 24h / 7d / 30d.
- **Coverage calendar heatmap** (articles per day).
- Collection lag (`collected_at − published_at`) — how fast each outlet surfaces you.
- Breaking-flagged volume over time (`register_is_breaking`).

### B. Language mix — `articles.language_iso` (84% non-null)
en 65.7% · te 11.3% · (null) 15.8% · kn 3.0% · hi 2.5% · ml/mr/ta/zh/vi.
- Language split of *your* coverage (donut).
- English vs Telugu over time (the cross-language gap — pure counts).
- Same entity, en vs te volume side by side.

### C. Outlets & sources — `articles.source_id` → `sources` (993)
`source_tier` (article-level 99%: T1 35% / T2 62% / T3 2.5%), `sources.name/domain/
source_type/language/geo_states[]/topics[]/health_score`.
- Top outlets covering you (ranked count).
- Tier mix of your coverage (T1/T2/T3 donut).
- Outlet-language and outlet-type (rss/scrape/api) breakdown.
- Per-outlet volume over time (who's ramping coverage of you).
- Outlet geography (sources carry `geo_states[]`).

### D. Topics & format — `articles`
`topic_category` 98.8% · `article_type` 85% · `topic_fine` 16.8% · `topic_categories` (25, hierarchical `rolls_up_to`).
- Topic breakdown of your coverage: POLITICS 21.4K · SECURITY 10.3K · LEGAL 7.5K ·
  FINANCE 5.9K · BUSINESS · HEALTH · INFRASTRUCTURE · GOVERNANCE · ENVIRONMENT ·
  **AGRICULTURE** · INTERNATIONAL · TECH (OTHER is 38% — a big bucket, flag it).
- News vs Opinion vs Analysis vs Explainer split (`article_type`).
- Topic volume over time (which issues are *rising in count* — pure volume, no sentiment).

### E. Entities & co-mention — `article_entity_mentions` (348,575 rows / 96,429 arts / 64.5%)
Cols: `entity_id, canonical_name, entity_type, country, surface_forms[], mention_rows`.
Join out to `entity_dictionary` (type, state, party, aliases).
- Mention volume per watchlist entity (ranked bars).
- **Co-mention graph** — which other entities appear in the same articles as yours
  (pure co-occurrence counts; the raw network, no "alliance" interpretation).
- Entity profile card: type · state · party · aliases · surface-forms seen.
- New entities first appearing in your coverage this period.

### F. Events — `article_events` (~258K / 103,750 arts / 69.4%) + `event_clusters` (6,859)
Cols: `event_date, event_type, event_description, actors[], is_future, effective_event_date`.
Types: announcement 53K · statement 33K · release 31K · meeting 25K · accident 25K ·
legal 14K · **election 8.8K** · market_event 8.5K · **protest 4.3K**.
- Event feed involving your entities (dated, typed).
- Event-type mix (donut).
- **Upcoming events** (`is_future = true`) → a forward calendar.
- Deduped events via `event_clusters` (with `article_count`, `source_count`).

### G. Geography — `article_locations` (302,887 / 106,370 arts / 71.2%) + `article_districts`
`lat/lng` only **19.8%** geocoded · `city` 43% · `region` 36%. Districts: 33,634 rows /
20,264 arts (13.6%), `district_id` + `is_primary` — Telangana-level.
- **Pin map** of where your coverage is datelined (use the 60K geocoded rows; label others by region text).
- **Telangana district heat** (`article_districts` → district choropleth).
- State/region breakdown (`geo_primary` 73% / `geo_secondary[]`).

### H. Quotes — `article_quotes` (85,742 / 37,440 arts / 25.1%)
`speaker_name` 100% · `speaker_entity_id` 49% · `is_direct` 84% · `quote_text` ·
**`quote_text_en` 0.24%** (translation essentially absent).
- Quote feed by/about your entities (speaker + verbatim, **original language**).
- Most-quoted speakers in your coverage.
- ⚠️ Showing non-English quotes *in English* = LLM translation = out of scope (pure-data
  shows them in te/hi/en as collected).

### I. Claims (raw triples) — `article_claims` (193,977 / 57,840 arts / 38.7%)
`claim_text` · `subject_entity_id` 37% · `predicate` 95% · `object_text` 95% · `confidence`.
- Subject–predicate–object statements mentioning your entity (a factual claim ledger,
  shown verbatim — *no* true/false judgement).
- Claim volume over time.

### J. Numbers / figures — `article_numbers` (170,381 / 49,286 arts / 33.0%)
`value` · `unit` 86% · `context` 100%.
- "**Figures mentioned**" feed in your coverage — e.g. ₹2,300 cr, 16 lakh, 202 seats —
  each with its sentence context. Pure extracted statistics.

### K. Media — `article_media` (1,852,860 / 125,305 arts / 83.8%)
`url` 100% · `is_hero` (124,101 hero images) · `media_type` · captions ~0.1%.
- Visual wall / thumbnails of your coverage (`thumbnail_url` 89.6% on articles + hero media).
- Media-type mix.

### L. Social posts — `article_tweets` (6,155 / 4,021 arts / 2.7%) + `social_clusters` (28)
`author_handle, tweet_text, hashtags[], mentions[], posted_at, image_urls[]`.
- Embedded tweets in your coverage (small but real). Note: a thin layer.

### M. Readability — `articles`
`word_count` 85% · `reading_minutes` 85% · `body_quality`.
- Length distribution of your coverage; total reading-time; long-form vs brief share.

### N. Authorship — `articles`
`author_name` 71% · `byline` 67%.
- Top bylines writing about you; named vs wire/unbylined share.

---

## Excluded — derived / "intelligence" (available, but NOT pure data)
Listed so we know what exists and are choosing to leave it off this page:
- `summary_executive / summary_preview / summary_snippet` (LLM summaries) — 73%.
- `register_emotion` (neutral/alarm/approval/curiosity/urgency/lament/…) — 73% — classifier tag.
- `register_style` (factual/analytical/polemical/…) — 73% — classifier tag.
- `article_stances` (actor + supportive/neutral/critical + intensity) — 34.7% — the directional engine's input.
- `user_article_relevance` (`score_final`, `relevance_tier`, `sentiment_for_user`,
  `matched_entity_names`) — per-user scoring.
- `narrative_frame` (empty) · `narrative_clusters` (0 rows) · `article_contradictions`
  (1 row) · `entity_dossier` (9) — effectively dead / not populated.

## Data-quality flags (Aryan's read)
1. **Entity NER is noisy at the head** → personalize off the curated `user_entities`
   watchlist (entity_id), never off raw mention frequency.
2. **Translation is absent** (quotes en 0.24%, full_text_translated 14%) → multilingual
   display means showing original language; English rendering needs LLM (excluded here).
3. **Geocoding is partial** (lat/lng 20%) → district choropleth (Telangana) is the
   reliable map; global pins are sparse.
4. **`topic_category` OTHER = 38%** and `content_type` is single-valued ("article") →
   not every facet is evenly useful; weight the populated ones.
5. **Row counts:** trust `count()` (above), not pg_stat estimates (claims were 58K est →
   194K actual).

---

# II. THE COMBINATORIAL SPACE — why it's ~90, not 15

The 15 above are **1-D slices**. The corpus is a **star schema**; the value is in *crossing*
the dimensions, and every cross is plain SQL (`JOIN` / `GROUP BY` / `FILTER` / window
function). **No LLM anywhere.** Proven live on 2026-06-02:
- `topic × language`: **AGRICULTURE is 30% Telugu** vs FINANCE 5% — the farm story lives in te.
- `topic × emotion-tag`: **SECURITY skews `alarm` ~6:1** over `approval`.
- window fn: **31 May = 7,616 articles vs 7-day avg 3,758** (2× surge), from `avg() OVER`.
- ratio: FINANCE 11.0% opinion vs SECURITY 4.3%.

### Dimensions (~13)
time · entity (watchlist) · topic · source · tier · language · district/geo · article_type ·
emotion-tag · style-tag · event_type · stance · author/speaker.

### Metrics (~10)
count(articles) · count(mentions) · count(quotes) · count(claims) · count(events) ·
distinct(sources) · distinct(entities) · sum(word_count) · avg(reading_minutes) · count(numbers).

### Pattern catalog (with counts)
- **1-D distributions [~12]** — the "15" lived here.
- **Time-series [~12]** — each dimension/day over the window (volume, topic mix, en-vs-te,
  news-vs-opinion, emotion, events, quotes, mentions/entity, tier, district, source-breadth, author).
- **2-D cross-tabs [~30]** — entity×topic, entity×source, entity×language, entity×emotion,
  entity×stance, entity×event_type, entity×district, entity×time, topic×time, topic×source,
  topic×language, topic×tier, topic×emotion, topic×district, source×tier, source×language,
  source×stance, source×topic, language×time, type×topic, type×source, emotion×time,
  event_type×time, district×topic, district×time, author×entity, author×topic, speaker×entity,
  tier×time, predicate×entity.
- **Ratios & shares [~10]** — share-of-voice (entity vs watchlist/rivals), opinion:news,
  T1-share, en:te, supportive:critical (stance), coverage concentration (HHI / top-3 share),
  quote:article, solo:co-mention, originator-vs-follower (first source per `event_cluster`),
  geocoded-share.
- **Leaderboards [~12]** — top sources, entities, co-mention partners, authors, quoted
  speakers, districts, event types, claim predicates/objects, numbers/figures, busiest days,
  fastest-rising entities, top topics.
- **Surge / sequence (window fns) [~10]** — volume vs trailing-7d, WoW % change, first-seen
  /last-seen entity, longest streak, peak-day, acceleration, day-of-week & hour pattern,
  collection-lag trend, event lead-time (`is_future`), recurrence.
- **Network / co-occurrence [~6]** — entity×entity adjacency matrix, entity–source bipartite,
  entity–topic bipartite, bloc by co-mention threshold, bridge entities, source overlap.
- **Geo crosses [~6]** — district choropleth, district×topic, district×time, district×entity,
  state(`geo_primary`) map, geocoded pin map.
- **Quality / ops [~5]** — field completeness, entity-resolution rate, geocode rate,
  collection-lag distribution, source health/activity.

### Total
≈ 12 + 12 + 30 + 10 + 12 + 10 + 6 + 6 + 5 = **~93 valid pure-SQL analytics.**
High-value subset to build first: **~30** (the cross-tabs + surge + share-of-voice + leaderboards).

The first pass looked thin because I enumerated **columns, not the dimensional cross-product.**
Every item here is a `GROUP BY` — nothing computes through an LLM.

---

# III. LIVE SIGNAL RANKING (run 2026-06-02)

Method: built the real personalized universe = **9,699 articles** mentioning the Revanth
Reddy watchlist (direct `article_entity_mentions`; the stored relevance feed is scored for a
different user, so not used). Ran all 30 against it. Rated by **variance/concentration ×
coverage × survives-personalization × noise**.

> Headline: personalization shrinks N hard (Revanth alone = 431 articles; KCR 266, KTR 223).
> The analytics that survive are **aggregates over the whole watchlist** and **cross-tabs/
> time-series** — not single-entity fine slices, and not raw entity leaderboards (NER noise).

## TIER A — HIGH signal, build first (12)
| # | Analytic | Evidence from the live run |
|---|---|---|
| 10 | **Topic × emotion** | POLITICS alarm 484 vs approval 170; GOVERNANCE is the *only* topic where approval(18) > alarm(13); AGRI alarm 60:9. Real story. |
| 28 | **Topic over time (weekly)** | POLITICS peaked 05-04 (868) → faded (99); SECURITY rose late (242→328); LEGAL spiked 05-18 (310). Issue rotation is visible. |
| 11 | **Topic × language** | AGRICULTURE is **Telugu-majority** (te 87 / en 75); FINANCE English-heavy (113/41). Strategic. |
| 21 | **Volume + surge (window fn)** | 20 May = 502 vs 7-day avg 133 = **3.8× spike** detected by SQL alone. |
| 22 | **Share of voice** | Revanth 431 · KCR 266 · KTR 223 · BJP 180 · Harish 94 — clean, stable ranking. |
| 05 | **Language mix** | en 5,616 (58%) / te 3,826 (39%) — clean bilingual split. |
| 03 | **Outlet leaderboard** | Telangana Today 2,096 · Namasthe Telangana 1,982 · Siasat 1,391 — top-2 = 42%. |
| 07 | **Emotion distribution** | neutral 46% / **alarm 21%** / approval 10% — real structure, alarm notably high. |
| 09 | **Stance split** | neutral 3,531 / supportive 3,478 / **critical 2,990 (31%)** — balanced, informative. |
| 15 | **Upcoming events** | **2,929 future-dated events** (of 19,994) — a real forward calendar. |
| 27 | **Claims density** | 47% of these articles carry claims (14,660 claims, 47% subject-resolved) — denser than global. |
| 17 | **Top speakers** | Modi 152 · Revanth 126 · Harish 77 · KTR 68 — real voices (needs name dedup). |

## TIER B — MEDIUM, useful with handling (9)
14 Event-type mix (announcement/statement/legal/protest — accident is noise) · 16 District
geography (Hyderabad 7,915 dominates; nalgonda/karimnagar/warangal real) · 02 Topic dist
(clear, but OTHER 39% + SPORTS 557 dilute) · 23 Stance-by-entity (directional but name-
fragmented: Revanth/A Revanth/CM Revanth split) · 26 Quotes (28% of base, 65% resolved) ·
19 Numbers (good *filtered* to currency/crore/seats/percent; count/date are filler) ·
25 Collection lag (**median 0.4h** = seen in 24 min; avg skewed by backfill) · 06 News:opinion
(8.9% opinion) · 30 Media wall (94% have a hero image — enabler).

## TIER C — LOW / fix-before-use (9)
12 Entity leaderboard — **dominated by NER noise** ("Revolutionary Marxist Party" 1,620,
"Amarish Der" 1,547) · 13 Co-mention pairs — noise + dedup artifacts (BJP = "Bharatiya
Janata Party" counted separately) · 20 Author/byline — **76% blank** in the Telugu-heavy
universe · 04 Tier mix — 85% T2 (monotonous) · 08 Style — 80% factual · 18 Claim predicates
— generic (is/has/said dominate) · 24 Opinion/T1 ratios — single numbers · 29 New entrants —
noisy (Royal Australian Navy, Tokyo Electron leak in).

## Cross-cutting verdicts (Aryan)
1. **Cross-tabs & time-series win** (Tier A is mostly 2-D and temporal) — exactly where SQL
   joins pay off. Single-field lists are Tier B/C.
2. **Never rank entities by raw frequency** — the leaderboard is noise; curated-watchlist
   share-of-voice (#22) is clean. Entity dedup (`entity_id`, not `actor`/`canonical_name`
   text) is a prerequisite for #12/#13/#17/#23/#29.
3. **Byline dies under personalization** (76% blank) — drop it for this persona.
4. **Volume has collection-artifact drops** (to 2 on some days) — smooth with the 7-day MA
   (#21), don't plot raw.
5. **Claims/stance are denser in the political slice** (47% / balanced) than global — lean in.

