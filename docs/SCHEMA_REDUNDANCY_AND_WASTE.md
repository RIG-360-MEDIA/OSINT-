# Schema Redundancy & Waste Audit — 2026-05-26

Stupid things in the schema/data found while investigating geo_primary vs article_locations.

## The geo question — no good reason

`articles.geo_primary` (text, 24% populated, half-junk) + `articles.geo_secondary` (array, **2.3% populated**) exist alongside `article_locations` (rich child table, 92.7% coverage with text+country+city+lat/lng+scope+is_primary).

There is NO need for `geo_primary` / `geo_secondary`. They're legacy from an earlier schema design that wanted a quick lookup on the article row. The proper approach: `SELECT location_text FROM article_locations WHERE article_id=? AND is_primary=true`. Should be dropped or made into a generated column.

## English "translation" wasted tokens

For English **articles**: `full_text_translated` is correctly **0%** populated for English. ✅

For English **quotes** though: we DID translate 6,592 English quotes into English:
- **4,214 are identical** to the original (pure waste — translated "I love you" → "I love you")
- **2,383 are DIFFERENT** (bizarre — LLM re-wrote English to slightly different English; hallucinated rewrites)

The translator should NEVER fire on English quotes. **Wasted ~6,500 LLM calls.** This is happening because the translator doesn't check the article's source language before firing.

## 9 more stupid things found

### 1. `author_name` AND `byline` — same field, twice
| Field | Populated |
|---|---|
| `author_name` | 14% |
| `byline` | 35% |
| Both populated and IDENTICAL | 9,116 rows |
| Both populated and DIFFERENT | 1,872 rows |

Two columns for the same data. The "different" rows are usually one being a clean name and the other being a job title slip. **Pick one, drop the other.**

### 2. `url` AND `canonical_url` — 75% redundant
| Metric | Value |
|---|---|
| `canonical_url` populated | 80.6% |
| `canonical_url = url` (exact copy) | **63,210 rows (75% of populated)** |
| `canonical_url ≠ url` (legitimately normalized) | 27,644 |

For 3 in 4 cases, canonical_url just re-stores the same URL. Should be NULL when identical, or computed on demand.

### 3. `language_detected` AND `language_iso` — two language fields
| Field | Rows populated |
|---|---|
| `language_detected` | 109,613 |
| `language_iso` | 90,869 |
| Both match | 81,442 |
| Both differ | 6,834 |

Two parallel columns tracking language. Should be one source of truth.

### 4. Four timestamps, two are synonyms
- `collected_at` = `inserted_at` for **100%** of 112,669 rows (literally same value)
- `inserted_at` ≈ `updated_at` for 96% of rows (rarely updated)
- Plus `published_at` (from source, different — keep)

**`collected_at` and `inserted_at` are duplicates.** Drop one.

### 5. Four "done" flags that don't agree
`nlp_processed`, `claims_extracted`, `quotes_extracted`, `substrate_status='ok'` — should all mean "processing is finished". But:
- **27,694 of 112,669 rows (24.6%) have mismatched values across these 4 flags.**

So 1 in 4 articles has at least one flag saying "done" and another saying "not done". Pipeline is inconsistent about what "done" means.

### 6. Three category fields competing
| Field | Distinct values | Notes |
|---|---|---|
| `topic_category` | 15 | coarse |
| `article_type` | 13 | news/opinion/etc |
| `primary_subject` | **81,667** | free-text LLM output — every article gets unique |

Three different ways to ask "what is this article about". `primary_subject` having 82K distinct values is essentially a free-text field that can't be used for grouping. **Pick the two that matter, drop the third.**

### 7. `entities_extracted` JSONB duplicates the child tables
This JSONB blob lives on every article. Sample:
```json
[{"name":"Telangana","type":"location","prominence":1.0},
 {"name":"200","type":"person","prominence":1.0},   // ← "200" classified as PERSON
 {"name":"Tamil Nadu","type":"location","prominence":0.6},
 ...]
```
Same entities also live (in better form) in `article_quotes.speaker_name`, `article_claims.subject_text`, `article_stances.actor`, `article_locations.location_text`. **Triple-storage of the same data with different formats and DIFFERENT quality (note "200" → person).**

### 8. `geo_secondary` — 2.3% populated, dead
Only 2,500 of 112K articles have any geo_secondary values. Either pipe it from `article_locations WHERE is_primary=false` or drop the column.

### 9. Three summary lengths instead of one + truncation
`summary_preview` (≤500 chars), `summary_snippet` (≤1000 chars), `summary_executive` (≤4000 chars). All three are stored. Could be ONE field (`summary_executive`) with UI truncation. Costs 3x storage and 3x LLM output tokens (since the prompt asks for three).

## What this means

The schema has **~15 redundant or wasted columns** that double-store data, generate wasted LLM calls, or sit at 0-3% populated. Estimated drop:
- Storage: ~20% smaller per article row
- LLM cost: ~20% lower (don't re-translate English, don't generate 3 summary versions, don't double-populate categorization)
- Maintenance: fewer "which field is the real one?" bugs

## Clean schema would look like

For each duplicate pair, pick one:

| Drop | Keep |
|---|---|
| `geo_primary`, `geo_secondary` | `article_locations` (with `is_primary` flag) |
| `author_name` | `byline` |
| `canonical_url` (when equals `url`) | `url` |
| `language_detected` | `language_iso` |
| `inserted_at` | `collected_at` |
| `claims_extracted`, `quotes_extracted` (booleans) | `substrate_status` + `extraction_version` |
| `primary_subject` (free text) | `article_type` (controlled vocab) |
| `entities_extracted` (JSONB) | the 4 normalized child tables |
| `summary_preview`, `summary_snippet` | `summary_executive` + UI truncation |
| `narrative_frame` (0%) | (drop or actually populate) |

## Wasted LLM cost estimate (per day at current ingest)
~5,000 articles/day × 3 summaries × 2,000 tokens each = **30M tokens/day of redundant summary generation**.
+ ~150 English quotes/day getting redundantly "translated" = **wasted Groq capacity**.

That's roughly **3x the Groq daily quota** burned on storing the same data 3 different ways.
