# Comprehensive Data Quality Audit — 2026-05-26

Every table, every field, every silent break.

## TL;DR — 7 critical findings (worst first)

1. **`article_claims.predicate` only 7.2% populated** — 285K claim rows but no relation verb on 93% of them. Most "claims" are just "X is mentioned"
2. **`article_claims.object_text` only 7.2%** — same root cause as #1; subject-predicate-object triples are mostly broken
3. **`article_quotes` translations 7.9%** — non-English quotes mostly never get English versions
4. **`article_locations.lat/lng` only 19.9%** — 80% of mentioned places aren't geocoded
5. **`article_events.event_date` only 59%** — 40% of events have no date; timeline broken
6. **`article_events.event_cluster_id` only 4.2%** — cluster linking nearly empty; Mode A spine missing
7. **Recent ingest QUALITY IS LOWER than older** — last_7d v3=54% vs older v3=100%. The new pipeline regressed somewhere.

## ARTICLES table — column population rates (sorted worst→best)

| Column | Populated | Verdict |
|---|---|---|
| `narrative_frame` | **0.0%** | ❌ never written — column dead |
| `full_text_translated` | **17.2%** | ❌ 80%+ of non-English articles untranslated |
| `geo_primary` | **24.3%** | ⚠️ low |
| `is_duplicate=true` | 25.7% | ✅ healthy dedup rate |
| `byline` | 45.0% | ⚠️ author missing on half |
| `register_emotion` / `register_style` | 94.6% | ✅ |
| `primary_subject` / `summary_executive` | 94.8% | ✅ |
| `language_iso` / `thread_id` / `labse_embedding` | 95-96% | ✅ |
| `published_at` / `lead_text` / `source_tier` | 98-99% | ✅ |
| `article_type` / `word_count` / `fts` / `claims_extracted` / `quotes_extracted` | 100% | ✅ |

**article_type vocab (10 types):** news (61K), analysis (4.3K), sports_result (1.8K), explainer (1.4K), opinion (1.3K), other (1.2K), interview (758), live_blog (595), listicle (484), press_release (483). **Healthy diversity.**

**source_tier:** tier 1 = 38,558 articles, tier 2 = 72,137, tier 3 = 940, NULL = 920. ✅ mostly populated.

## ARTICLE_QUOTES (116,538 rows)

| Field | Rate | Status |
|---|---|---|
| `quote_text` avg length 125 chars (range 1–1361) | min=1 is junky | ⚠️ |
| `quote_text_en` translation | **7.9%** | ❌ |
| `speaker_name_en` | **7.9%** | ❌ |
| `context` (surrounding) | **10.4%** | ❌ |
| `char_offset_start/end` | **0.0%** | ❌ never populated |
| `speaker_entity_id` link | 6.1% (from yesterday) | ❌ |

## ARTICLE_CLAIMS (285,255 rows) — the big revelation

| Field | Rate | Status |
|---|---|---|
| `subject_text` | 99.9% | ✅ |
| **`predicate`** | **7.2%** | ❌ **most claims are missing the verb** |
| **`object_text`** | **7.2%** | ❌ **most claims are missing the object** |
| `subject_entity_id` link | 2.0% | ❌ |
| `confidence` score | 100% | ✅ |
| `embedding` | 0.0% | ❌ |

**What this means:** the substrate prompt is extracting "who" (subject) but failing on the "does what to what" (predicate + object). So we have 285K rows that look like claims but are really name-mentions.

## ARTICLE_EVENTS (187,341 rows)

| Field | Rate | Status |
|---|---|---|
| `event_date` | 59.4% | ⚠️ |
| `event_type` | 100% | ✅ (574 distinct types — possibly too many) |
| `actors` array | 92.9% | ✅ |
| `event_cluster_id` link | **4.2%** | ❌ T5 clustering ran on small subset |
| `is_future=true` | 26,809 | ✅ feature works |

## ARTICLE_LOCATIONS (233,573 rows)

| Field | Rate | Status |
|---|---|---|
| `lat`/`lng` (geocoded) | **19.9%** | ❌ |
| `country` | 91.3% | ✅ |
| `city` | 44.0% | ⚠️ |
| `is_primary=true` | 83,227 (36%) | ✅ |
| `location_scope` | 100% | ✅ |

## ENTITY_DICTIONARY (11,605 entities) — actually solid

| Metric | Value |
|---|---|
| Total entities | 11,605 |
| Persons | 6,625 |
| With aliases | 97.2% |
| Avg aliases per entity | 3.5 |
| With state | 71.6% |
| With party | 23.3% |

**Conclusion:** the entity dictionary itself is fine. The breakage is in the **linker**, not the dictionary.

## TEMPORAL ANOMALY (the most worrying finding)

| Bucket | Articles | summary≥80 | translation | extraction_v3 |
|---|---|---|---|---|
| last_7d | 24,249 | **84.7%** | 17.1% | **54.0%** |
| last_30d | 53,709 | 98.6% | 19.3% | 97.0% |
| older | 8,889 | 100% | 4.9% | 100% |

**Recent ingest quality is LOWER than older.** Multiple causes possible:
- Some articles still being processed (substrate_processed_at lags)
- v3 upgrade pass behind schedule
- Recent failures piling up
- Worth its own investigation

## ORPHAN / INTEGRITY CHECK ✅

| Check | Result |
|---|---|
| Quotes pointing at deleted articles | **0** |
| Claims pointing at deleted articles | **0** |
| Events pointing at deleted articles | **0** |
| Articles flagged duplicate with valid pointer | 36,145 / 36,145 (100%) |

Schema-level referential integrity is **perfect**. All breakage is at the field/extraction level, not the FK level.

## Severity grading

| Priority | Issue | Impact |
|---|---|---|
| **P0** | claims predicate/object 7.2% | Most claims aren't usable as claims |
| **P0** | Recent data v3 only 54% | New articles aren't getting full enrichment |
| **P0** | Quote translations 7.9% | English UI shows fragments |
| **P1** | Entity linking 2-8% | Cross-article tracking broken |
| **P1** | Location geocoding 19.9% | Maps mostly empty |
| **P1** | Event cluster linking 4.2% | Story aggregation broken |
| **P1** | Event dates 59% | Timeline broken |
| **P2** | claims embedding 0% | Blocks Mode A narrative pipeline |
| **P2** | narrative_frame 0% | Blocks Stage 1 router |
| **P2** | char_offsets 0% | Blocks quote-context lookup |
| **P3** | byline 45% | Cosmetic — author attribution incomplete |

## Repair sprint plan (priority order, 1-2 weeks)

### Week 1 — Make existing data actually usable
1. **Fix substrate prompt** so predicate + object are extracted reliably. Re-extract 285K claims (~5 days at Groq capacity). [P0]
2. **Investigate why v3 upgrade lags 7-day window** — should always be ≤30 min after substrate. [P0]
3. **Re-link entity IDs** with patched `_resolve_entity_id` (already deployed today). Single SQL UPDATE pass. [P1]
4. **Fix translation prompt** — Groq json_validate_failed issue from yesterday. Re-translate 285K untranslated quotes. [P0]

### Week 2 — Enable narrative pipeline
5. **Backfill `claims.embedding`** (LaBSE, ~24h, no LLM cost). [P2]
6. **Backfill `narrative_frame`** (single-pass LLM classification). [P2]
7. **Re-cluster events** to populate `event_cluster_id` on more than 4%. [P1]
8. **Geocode locations** (Nominatim / Google Maps API). [P1]
9. **Re-extract stances** with corrected prompt allowing negative values. [P1]

After this sprint, **then** start the narrative pipeline (Mode A/B).
