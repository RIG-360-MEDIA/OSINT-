# Field-by-Field Deep Audit + Quality Drilldown — 2026-05-26

Answers to specific questions + quality check on every field including 100%-populated ones.

## 1. `full_text_translated` — by language

| Language | Articles | Translated | % | Verdict |
|---|---|---|---|---|
| en | 66,182 | 0 | 0% | ✅ correct — English doesn't need translation |
| te (Telugu) | 14,350 | 13,027 | **91%** | ✅ works |
| hi (Hindi) | 1,664 | 1,569 | **94%** | ✅ works |
| kn (Kannada) | 725 | 359 | 50% | ⚠️ half-broken |
| mr (Marathi) | 20 | 20 | 100% | ✅ (tiny sample) |

**Plot twist:** translation actually WORKS for the major Indian languages. The overall "17%" looked bad because **60% of corpus is English** (which legitimately has 0% translated). For non-English, translation runs at 50-94%.

## 2. `byline` — author field — 45% populated

Likely chronic since day 1. Many feeds simply don't include author metadata. Not a regression, just an upstream limit. Indian regional newspapers often omit byline.

## 3. `narrative_frame` — what is it for?

Designed (per the new narrative-pipeline PRD) to be one of ~15 frames: `scene_first`, `contradiction_first`, `character_first`, `number_first`, `historical_rhyme`, `quiet_pattern`, `timeline_unfolding`, `stance_split`, `single_source_scoop`, `aftermath`, `human_cost`, `power_move`, etc. Stage 1 of the new pipeline uses it to pick how to write the article.

**Today: 0% populated.** Column exists but no code writes to it. Pure decoration.

## 4. `geo_primary` — only 24%, since when?

**Worse than just low — the data inside is JUNK.** Sample values: `"108"`, `"114"`, `"480"`, `"491"` (numeric IDs!) mixed with `"Adilabad"`, `"Agra"`, `"Ahmedabad"` (city names). **Schema-inconsistent.**

**What the observe page actually uses is `article_locations`, not `geo_primary`.** `article_locations` has **80,523 articles covered (92.7%)** — that's the table that powers the map. `geo_primary` is a legacy single-text field that was never reliably populated.

So: observe page = ✅ working off `article_locations`. The 24% `geo_primary` is decorative legacy.

## 5. `extraction_version` — what is it

A SMALLINT (1, 2, or 3) tracking which version of the extraction prompt processed the article:
- v1 = legacy (Cloudflare-1010 incident era) — 22,882 rows
- v2 = interim prompt — 15,709 rows
- v3 = current full schema — **74,078 rows** ✅
- NULL = unprocessed

Today ~66% of corpus is at v3. The semantic_repass backfill is what upgrades v1/v2 → v3.

## 6. `speaker_name_en` — what languages are missing it most

| Source lang | Quotes | Translated | % |
|---|---|---|---|
| English | 94,583 | 6,592 | 7% (mostly redundant — English speakers don't need translation) |
| Telugu | 13,707 | 2,029 | **15%** — most missed |
| Hindi | 1,550 | 124 | 8% |
| Kannada | 654 | 21 | 3% |
| Marathi | 29 | 0 | 0% |

For non-English quotes (where it matters), translation runs **3-15%**. Severely broken.

## 7. `quote_text_en` — why some, not others; English-only?

Same pattern as #6. The translator IS supposed to fire for non-English quotes only (English doesn't need it). But the translator misses 85-97% of the non-English quotes it should be processing. Cause: Groq `json_validate_failed` errors when translation prompt output isn't strict JSON — translator gives up silently.

## 8. `char_offset_start/end` — what they're for

Position of the quote in the article body — char index where the quote starts/ends in `full_text_scraped`. Used to highlight the quote in context, or pull surrounding text. Today 0% populated. The extractor never returns offsets. Easy fix: regex `body.find(quote_text)` after extraction.

## 9. `context` — surrounding sentence

The sentence(s) around the quote to disambiguate it. Only 10.4% populated. Sample query failed earlier — can't show examples. Use case: when two speakers say similar quotes, the context tells you which event each was about.

## 10. `article_claims` — quality

Sampled 8 random claims:
- 1 of 8 has FULL triple: `"proposed pipelines | would attract | ₹12,500 crore in investment"` ✅
- 7 of 8 have predicate=NULL, object=NULL
- Several have subject="article" (placeholder) or "CUST" (garbage code)

**Verdict:** the **7% with full triples are HIGH QUALITY.** The **93% with NULLs are essentially worthless** — they're just sentence fragments with a phantom subject. The extraction prompt fails to return triples for most claims.

Working "as fallback" but not as intended.

## 11. `article_events` — quality

Sampled events:
- "RS Praveen Kumar media conference on POCSO case" ✅
- "Referral of nominations to Senate committees" ✅
- "NDA legislators meet in Guwahati" ✅
- "Family protests at police station" ✅

**Events look real and meaningful.** Event_type vocab too wide (574 distinct values — needs canonicalization).

But `event_date` has serious data quality issues:
- **min date: 0048-01-01** (year 48 AD)
- **max date: 8113-05-28** (year 8113)
- 7,598 events dated in the future (some legitimate, many hallucinated)
- 1,966 events dated before year 2000 (likely LLM hallucination)
- 44,286 events dated in last year (likely accurate)

**~4.5% of dated events have nonsense dates from LLM hallucination.**

## 12. `article_locations` vs `geo_primary` — the difference

| Field | Where | What it stores | Coverage |
|---|---|---|---|
| `articles.geo_primary` | row on `articles` | single text "Mumbai" or junk ID | **24%** ⚠️ |
| `article_locations` | child table (multi-row per article) | rich: text + country + city + lat/lng + scope | **92.7%** of articles have ≥1 location row ✅ |
| `article_locations.lat/lng` geocoded | inside that child table | actual coordinates | **19.9%** (so 1 in 5 of mentions is mapped) |

**The observe page** = uses `article_locations` (works for 92.7%)
**The article-level "primary location"** field = unused / broken (24%, junky values)

The observe page's atlas isn't lying — it's powered by the working table. The `geo_primary` text field on `articles` is just decorative.

## Quality check on "100% populated" fields — are they real?

### `title` (99.9% populated)
- 780 titles under 20 chars (junky)
- 31,100 in 20-60 char range (normal)
- 80,789 in 60+ chars (long, good)
- 9 generic ("Home", "News", "Live") — almost zero noise
**Verdict: solid**

### `summary_executive` (94.8% populated)
- Avg length 751 chars (3-paragraph summaries)
- Range 42-2400 chars
- 4,480 articles (3%) have <20 char summaries — too short
- Sample shows informative content
**Verdict: solid for 97%, 3% has stubs**

### `quote_text` (100%)
- 307 quotes under 10 chars (0.3% junk)
- 4,565 in 10-30 chars (probably real but short)
- 111,786 in 30+ chars (real quotes)
- 2,187 ALL-CAPS (likely headlines mis-extracted)
**Verdict: 96% real, ~2% junk, ~2% misclassified headlines**

### `article_numbers` (sample)
- "12 count | Reform UK seats won" ✅
- "15 metric tons | April gold imports" ✅
- "300 km range" ✅
- "1 failure" ✅
- "2027 | Planned release year" ✅ (year, not money)
- "not disclosed" ⚠️ junk
- "600,000 USD" ✅
- "30th May 2026 date" ⚠️ date stored as number
**Verdict: ~80% real numbers, ~20% has type-confusion (dates, "not disclosed") in the value field**

### `article_type` (100%)
- 10 types, top: news (61K), analysis (4.3K), sports_result (1.8K), explainer (1.4K)
- Healthy distribution, no junk category dominates
**Verdict: solid**

### `confidence` on claims (100%)
- All 285K rows populated
- But no audit of whether the value is meaningful vs always 1.0
- Recommend sampling distribution

## Summary of quality issues per table

| Table | Volume | What's real | What's junk |
|---|---|---|---|
| `articles` | 112K | titles, bodies, summaries, types ~95-100% | `narrative_frame` 0%, `geo_primary` 24% with junk IDs |
| `article_quotes` | 116K | quote_text 96% real | translations 3-15%, context 10%, char_offsets 0% |
| `article_claims` | 285K | 7% are real triples | 93% NULL predicate/object — basically unusable |
| `article_events` | 187K | descriptions good | 4.5% have nonsense dates (year 48 AD or year 8113) |
| `article_stances` | 190K | actors populated | intensity never negative — can't detect opposition |
| `article_locations` | 233K | text + country good | only 20% geocoded |
| `article_numbers` | 225K | 80% real numbers | 20% confused (dates as numbers, "not disclosed") |
| `entity_dictionary` | 11.6K | aliases 97%, 6.6K persons | ✅ healthy |

## Bottom line per field type

**Content fields (titles, bodies, summaries):** 95-100% real ✅
**Categorical fields (article_type, register):** 95-100% real ✅
**Relation fields (claim triples, entity IDs, embeddings, narrative_frame):** 0-10% — barely populated ❌
**Geocoding fields (lat/lng, geo_primary):** 20% — broken ❌
**Translation fields:** 50-90% for non-English (works), but speaker/quote translations only 3-15% ❌
**Temporal fields (event_date):** populated but 4.5% are hallucinated junk ⚠️

The pattern is unambiguous: **anything the LLM does in a single pass is solid. Anything requiring a second pass, a join, a geocoder, a translator, or an embedder is mostly broken.**
