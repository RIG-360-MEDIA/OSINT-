# RIG Database — Field-Level Audit & Quality Report

> Goal: judge **every field's real quality**, find **redundant/overlapping fields**
> (so we build on the rich one, not the primitive one), and ground the 70-feature
> feasibility map in what the data *actually* supports.
>
> Access: read-only `analytics_user`, `default_transaction_read_only = on`,
> SELECT-only, via the `rig-postgres` container. All numbers are **live** queries
> (date of audit: 2026-06-14). No fabricated stats.

---

## A. Census — the single most important finding

**The schema is ~200 tables; only ~40 hold meaningful product data.** A
promising table name means nothing — many are empty scaffolding. Build only on
what is populated.

### A.1 Populated assets (real data to build on)

**Articles core + substrate**
| Table | Rows | Note |
|---|---|---|
| `articles` | 292,023 | the spine |
| `article_links` | 12,414,972 | inter-article link graph |
| `article_media` | 3,800,610 | images/media refs |
| `article_entity_mentions` | 1,136,329 | **canonical** article↔entity join (use this, not inline jsonb) |
| `article_locations` | 564,816 | geo per article |
| `article_events` | 511,883 | event tags |
| `article_numbers` | 461,676 | figures/stats |
| `article_claims` | 405,647 | subject/predicate/object claims |
| `article_stances` | 378,109 | actor + stance (use for hostility, NOT register_emotion) |
| `article_quotes` | 244,372 | speaker + quote (+ _en translation cols) |
| `entity_mention_daily` | 256,927 | daily entity rollup (trend-ready) |
| `article_districts` | 49,654 | district tagging |
| `article_tweets` | 12,698 | linked tweets |

**Clippings pillar (newspaper) — FULL substrate, richer than expected**
`clippings` 4,794 · `clipping_entity_mentions` 10,118 · `clipping_locations` 8,197 · `clipping_events` 7,382 · `clipping_claims` 7,231 · `clipping_numbers` 6,176 · `clipping_stances` 3,982 · `clipping_quotes` 3,088

**YouTube pillar — FULL substrate too**
`youtube_clips_v2` 1,233 · `youtube_clip_claims` 5,336 · `youtube_clip_stances` 2,212 · `youtube_clip_locations` 1,804 · `youtube_clip_quotes` 1,270 · `youtube_clip_entity_mentions` 660 · (`youtube_clips` v1 legacy 971; `pending_youtube_videos` 7,619 queue; `youtube_channels` 120)

**Entities**
`entity_dictionary` 19,356 (NOT 44K) · `entity_lookup` **9** (suspiciously tiny — investigate) · `analytics.entity_image` 134

**Clustering (analytics) — multiple generations, must pick the live one**
`story_clusters_v8` 178,258 / `_members_v8` 274,426 (newest, in-progress?) · `story_clusters` 34,599 / `_members` 136,581 (documented LIVE keeper) · `story_clusters_old` 37,982 (rollback) · `event_clusters` 6,859 (**product surface**) · enrichment: `story_quotes` 27,721, `story_sources` 11,953, `story_facts` 9,552, `story_timeline` 716, `story_geo` 702, `story_stance` 645 (enrichment only covers ~716 stories)

**Per-user / relevance**
`user_article_relevance` 264,138 · `user_cutting_relevance` 2,076 · `user_clip_relevance` 620 · `analytics.users` **2** · `analytics.user_brief_prefs` 5 · `briefs` 7 · `sources` 1,220 · `topic_categories` 25

### A.2 Empty scaffolding — features needing these are BLOCKED (no data)
All **0 rows**: every `cm_*` (political intelligence: promises, handles, stance_scores, spokesperson_quotes, dissent, counter_narratives, coalitions, issues…), every `social_*` (Signals/threads pillar), every `govt_*` (Documents pillar), every `newsroom_*`, district reference (`districts`, `assembly_constituencies`, `mandi_prices`, `weather_warnings`, `power_grid_status`, `air_quality_readings`, `acled_events`, `welfare_coverage`), `dossier_*`/`entity_dossier`, `narrative_*`, per-user engagement (`alerts`, `notification_rules`, `notification_events`, `user_watchlist`, `user_watched_entities`, `user_entities`, `user_cards`, `user_breaking_now`), `analyst_sessions`/`analyst_turns`, `collections`, `top_stories_daily`, `coverage_gaps_daily`, `article_contradictions`, `event_dissent`, and the empty user system (`public.users`, `public.user_profiles`, `public.user_page_access`). Old newspaper tables (`newspaper_clippings/editions/sources`) superseded by `clippings`.

> **Implication for the 70 features:** anything I earlier mapped to political
> intelligence, social signals, govt documents, district dashboards, dossiers, or
> the built-in alerts/watchlist tables is **data-blocked** today — the moat lives
> in articles + clippings + youtube + their substrate + entities + clustering +
> relevance. We either build on those, or we must *generate* the missing data.

---

## B. `articles` — field coverage & quality (n = 292,911; live through 2026-06-14)

Grade key: **A** trust it · **B** usable, partial · **C** weak signal · **F** dead/junk.

| Field | Coverage | Grade | Verdict |
|---|---|---|---|
| `title` | 99.2% | A | spine |
| `full_text_scraped` | 99.4% | A | native-language full body |
| `lead_text_translated` | 97.2% | A | **the reliable English text** |
| `lead_text_original` | 96.1% | A | native-language lead |
| `labse_embedding_v4` | 93.9% | A | **canonical embedding** (recipe `v4-tr-title-1024`) |
| `topic_category` | 99.9% | A* | universal, *but 21% = `OTHER` (unclassified)* |
| `nlp_processed` | 99.8% | A | processing flag |
| `summary_preview/snippet/executive` | 71.0% | B | 3 tiers, filled together, same cohort |
| `primary_subject` | 71.0% | B | one-line subject, enriched cohort |
| `topic_fine` | 65.6% | B | finer topic |
| `geo_primary` | 69.8% | B | **granularity-mixed** (India/Telangana/Hyderabad all appear) |
| `entities_extracted` (jsonb) | 82.9% | B | raw; prefer `article_entity_mentions` |
| `word_count`/`reading_minutes` | 85% | B | |
| `labse_embedding` (legacy) | 97.7% | C | **recipe-mixed — do NOT use for similarity** |
| `register_emotion` | 70.8% | C | 42% `neutral`, 29% null; event-emotion, **not** hostility → use `article_stances` |
| `full_text_translated` | **17.5%** | C | **sparse** — don't rely on for English full body |
| `topic_category_orig` | 41.4% | C | legacy pre-rollup |
| `geo_secondary` | 100% non-null | **F** | **defaulted junk** (never null = no signal) |
| `narrative_frame` | **0%** | **F** | **dead column** |
| `content_type` | 100% = `'article'` | **F** | **constant — no information** |
| `labse_embedding_v0_backup` | 47.6% | F | backup, ignore |

**Processing cohorts:** `substrate_status` = `ok` 80.4% · `fetch_failed` 11.4% · `junk` 7.4%. **17.0% are duplicates** (`is_duplicate`). → Clean working set = `substrate_status='ok' AND NOT is_duplicate` ≈ **~200K articles**.

**Language mix (`language_detected`):** en 66.5% · **te (Telugu) 9.4%** · **hi (Hindi) 4.6%** · ml/kn/ta/bn/mr + null 9.5%. A genuinely multilingual Indian corpus — **Telugu is #2, Hindi #3.** (`language_iso` is a noisier duplicate — more nulls; use `language_detected`.)

---

## C. Redundant / overlapping fields — "use this, NOT that"

| Need | ✅ USE (rich) | ❌ NOT (primitive/legacy/dead) | Why |
|---|---|---|---|
| Semantic vector | `labse_embedding_v4` (94%) | `labse_embedding` (97% but recipe-mixed); `_v0_backup` | only v4 is one clean recipe; legacy mixes recipes → bad cosine |
| English text | `lead_text_translated` (97%) + `title` | `full_text_translated` (17%) | full-text EN is sparse |
| Native full body | `full_text_scraped` (99%) | — | for on-the-fly translation |
| Topic | `topic_category` (99.9%) + `topic_fine` (66%) | `topic_category_orig` (41%) | orig is legacy |
| Geo | `article_locations` (564K, structured country/region/city) or `geo_primary` | `geo_secondary` (defaulted junk) | secondary = 100% non-null = no signal |
| Entities | `article_entity_mentions` (canonical, 82% of articles, `surface_forms`) | `entities_extracted` jsonb (raw); `entity_lookup` (**9-row test stub**) | matview is resolved + cross-script |
| Sentiment / hostility | `article_stances` (directed: supportive/neutral/critical) | `register_emotion` (event-emotion, 42% neutral) | stance is the real signal |
| **Dead — never use** | — | `narrative_frame` (0), `content_type` (constant), `geo_secondary` (defaulted) | no information |

---

## D. Structured substrate quality (the moat material)

**Article coverage (of 292,911):** locations 68.0% · claims 53.0% · stances 49.2% · numbers 45.5% · quotes 36.3%. → Substrate exists for **roughly half** the corpus (the enriched `ok` cohort).

- **`article_stances`** (378K rows) — **A−**. Clean directed signal: supportive 149K / neutral 139K / critical 82K + minor classes. **45% entity-resolved** (`actor_entity_id`). Best field for framing/sentiment; partial entity linkage is the caveat.
- **`article_claims`** (541K) — **B**. avg confidence 0.734, **66% ≥0.7**. But **134K distinct predicates = free-text, not normalized** → great for evidence retrieval, weak for `GROUP BY predicate` rollups. 30% subject-entity-resolved.
- **`article_quotes`** (244K) — **B− / C**. 80% direct quotes; 39% speaker-resolved; **`quote_text_en` is EMPTY (202 rows / 0.08%)** → English quote display needs **on-the-fly translation**.
- **`article_numbers`** (461K) — **C+**. Units mix real figures (`percent`, `currency`, `INR`, `USD`, `count`) with temporal junk (`date`, `year`, `time`) and even `runs` (cricket). **Filter to numeric units** before any "figure" feature.

---

## E. Entities

- **`article_entity_mentions`** (matview) — **A, the canonical path.** 1.13M rows, **241,342 distinct articles (82%)**, 10,331 distinct entities. Columns: `article_id, entity_id, canonical_name, entity_type, country, surface_forms, mention_rows`. `surface_forms` carries the cross-script variants → powers cross-language entity feeds.
- **`entity_dictionary`** (19,356) — **B+.** person 57% / org 22% / location 12% / constituency 6% / role 2%. Fill: country 57%, state 38%, **party 18%** (politicians only). `aliases` = text[] on every row; 369 `redirected_to` (dedup). Only **10,331 / 19,356 entities actually appear** in articles.
- **`entity_lookup`** — **F (dead).** 9 rows, all Australian politicians (Albanese, Wong, Chalmers…). A test stub. **Do not use** — the earlier plan citing it as the resolver was wrong.

---

## F. Story clustering — generations & coverage

- **Live `analytics.story_clusters`** = 34,599 clusters over **136,581 articles (47% of corpus)**. avg size 3.9, max **5,593**, but only **945 clusters have ≥3 articles** → a long tail of singletons/pairs + a few big events. The ~945 multi-article clusters are the real "events."
- **Generations (redundant — pick carefully):** `story_clusters_v8` = **178,258** (newest candidate, 274K members) · `story_clusters` = 34,599 (documented LIVE) · `story_clusters_old` = 37,982 (rollback). **Verify which is wired to product before building** (docs say `story_clusters` is live; v8 is the in-progress next gen).
- **Cross-language = CONFIRMED in data.** Per-cluster `languages` jsonb on big events: e.g. `{en:2805, te:2264, hi:135, bn:68, kn:24, …}`; another `{en:3140, te:803, hi:96, …}`. Single events genuinely span **EN/TE/HI** → the framing-contrast moat has real material **today** (for the ~945 multi-article clusters).
- **Enrichment is thin:** `story_timeline` 716 stories · `story_sources` 716 · `story_facts` 567. Rich story pages (timeline/facts) exist for **only ~716 stories**; the rest need generation.
- **`public.event_clusters`** (6,859) — a separate cleaner **product** event table (`canonical_description/actors/event_type/date, importance_score`). Two clustering systems coexist; `story_clusters` is richer (has `languages`, `stance_distribution`, `representative_title`).

---

## G. Per-user layer

- **`analytics.users`** (2 rows) — real auth model: `id, org_id, email, full_name, designation, is_super_admin, …`. **Org-scoped (multi-tenant ready).** The empty `public.users`/`public.user_profiles` are a dead parallel system.
- **`user_article_relevance`** (264K rows) — **rich & sophisticated** but **only 1 user populated**: `score_stage1, score_final, relevance_tier, relevance_explanation, sentiment_for_user, geo_multiplier_applied, matched_entity_names`. The two-stage scorer with per-user explanation already covers ~264K articles for that 1 user.
- **`analytics.user_brief_prefs`** (5 rows) — preference schema already designed: `watchlist, regions, topics, languages, sources, stance, events, delivery, personality`. Strong foundation for personalization.

---

## H. Cross-pillar pillars (clippings + youtube)

- **`clippings`** (4,929) — **A−, high quality.** translated headline 97%, translated body 75%, embedding 97%, entities 97%, substrate `ok` 97%. **Language: hi 1,420 / te 1,198 / en 1,161 / mr/gu/ml/bn/kn** — *mostly regional-language* newspaper cuttings with English translation already filled → ideal multilingual material. Full substrate present (claims/stances/quotes/numbers/locations/entity_mentions).
- **`youtube_clips_v2`** (1,233) — **A, fully enriched** (embedding/summary/transcript/entities all ~100%), 41 channels. Small but clean. Full substrate present.
- **⚠ Cross-pillar embedding space:** articles = LaBSE `v4-tr-title-1024`; clippings/youtube = plain `labse_embedding` (no recorded recipe). Same model family, but **comparability is unverified** → a P0 empirical check (article → cosine → clippings; eyeball coherence) is **required before** any cross-pillar "find similar."

---

## I. Headline conclusions for the build

1. **Clean working corpus ≈ 200K** articles (`substrate_status='ok'`, de-duped), embedded with v4, 66% English / 34% Indian-language.
2. **The moat has data today:** multilingual clustering already stitches EN/TE/HI per event; stances give directed framing; clippings/youtube add two more languaged modalities with full substrate.
3. **Don't trust:** `labse_embedding` (legacy), `register_emotion` (as sentiment), `quote_text_en` (empty), `geo_secondary`/`narrative_frame`/`content_type` (dead), `entity_lookup` (stub).
4. **Data-blocked (empty tables):** political-intel, social/signals, govt-docs, districts, dossiers, narratives, built-in alerts/watchlist — any feature needing these must generate data first.
5. **Per-user & enrichment are infra-ready but barely populated** (1 user, 716 enriched stories) — fine for V1, needs a backfill plan to scale.
6. **Verify before trusting:** cross-pillar embedding comparability; which clustering generation is live.
