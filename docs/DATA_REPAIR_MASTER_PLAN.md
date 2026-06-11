# Data Repair Master Plan — Every Fix Needed

Consolidates everything from quality audit, redundancy audit, temporal audit, field deep-dive, and architectural decisions. **Organized by fix type so you can batch by effort/cost.**

---

## CATEGORY A — Pure SQL fixes (no LLM, no code change)
Run-once SQL passes. Cheapest, safest, biggest immediate impact.

| # | Fix | What it does | Effort | Risk |
|---|---|---|---|---|
| A1 | **Entity-FK backfill from JSONB** | Read `articles.entities_extracted.label='DICT_MATCH'` → write `speaker_entity_id`, `subject_entity_id`, `actor_entity_id` on quotes/claims/stances. Lifts linking 2-8% → 50-60% | 1 hour | Low — nullable FKs, can reset |
| A2 | **NULL out hallucinated event_dates** | `UPDATE article_events SET event_date=NULL WHERE event_date<'1990-01-01' OR event_date>'2035-01-01'` — wipes year 48 AD and year 8113 garbage | 5 min | Zero |
| A3 | **Drop `inserted_at`** | 100% identical to `collected_at`. Pure synonym | 5 min | Low |
| A4 | **Drop `geo_secondary`** | 2.3% populated. Dead column | 5 min | Low |
| A5 | **Consolidate `author_name` → `byline`** | Move non-NULL author_name values into byline where byline is NULL, then drop author_name | 30 min | Low |
| A6 | **Generated column for `geo_primary`** | Replace stored column with `GENERATED ALWAYS AS (SELECT location_text FROM article_locations WHERE article_id=id AND is_primary=true LIMIT 1) STORED` | 1 hour | Medium — needs PG 12+ generated column or trigger |
| A7 | **Fix status flag inconsistencies** | One pass: `SET nlp_processed=TRUE WHERE id IN (SELECT article_id FROM article_claims)` etc. — reconcile flags with reality | 30 min | Low |
| A8 | **NULL out `canonical_url` when equals `url`** | `UPDATE articles SET canonical_url=NULL WHERE canonical_url=url` — removes 63K redundant copies | 5 min | Low |

---

## CATEGORY B — Code logic fixes (write/change code, then run once)
Real engineering. Each is a small file change + targeted backfill.

| # | Fix | What to change | Effort | Risk |
|---|---|---|---|---|
| B1 | **char_offset backfill** | Add `body.find(quote_text)` after quote extraction in `claims_quotes_task.py`. Regex-based, no LLM. Backfill existing 116K quotes with one pass | 2 hours | Low |
| B2 | **Quote translator skip English** | Add `if article.language_iso == 'en': return` early-return in translator. Stops wasting tokens on 6,500 English→English translations | 5 min | Zero |
| B3 | **Switch language detection to fasttext/langdetect** | Add `fasttext.detect(body)` as ground truth, write to `language_iso`, deprecate `language_detected` | 4 hours | Medium |
| B4 | **`canonical_url` normalizer fix** | Some sources canonicalize everything to homepage (bug). Fix the per-source canonicalization rules | 3 hours | Low |
| B5 | **Quote context extraction** | After extracting a quote, write the surrounding sentence (50 chars before + 50 after from `full_text_scraped`) into `context`. No LLM | 1 hour | Low |
| B6 | **English-quote translation cleanup** | One-time `UPDATE article_quotes SET quote_text_en=NULL, speaker_name_en=NULL WHERE article_id IN (SELECT id FROM articles WHERE language_iso='en')` — remove 6,500 wasted translations | 10 min | Low |
| B7 | **Event type canonicalization** | 574 distinct `event_type` values is too many. Build a 30-50 controlled vocab + LLM remap pass | 1 day | Medium |
| B8 | **Status flag consolidation refactor** | Replace 3 separate booleans (`nlp_processed`, `claims_extracted`, `quotes_extracted`) with one `pipeline_stage` enum (`fetched`, `nlp_done`, `claims_done`, `complete`). Migration job + code changes in 4-5 task files | 1 day | Medium — touches queue selectors |

---

## CATEGORY C — LaBSE embedding backfills (CPU/GPU pass, no LLM API)
Use the local LaBSE model. Cheap (no API cost), just compute time.

| # | Fix | What it does | Effort |
|---|---|---|---|
| C1 | **Backfill `article_claims.embedding`** | LaBSE encode `claim_text` for all 285K rows. Enables Mode A claim consensus clustering | ~24h compute |
| C2 | **Backfill old `articles.labse_embedding`** | Already 95.8% — just fill the missing 4% | ~4h |

---

## CATEGORY D — LLM re-run on existing rows (expensive)
Need Groq/Cerebras/Ollama tokens. Schedule for off-peak.

| # | Fix | Why | Tokens needed | Effort |
|---|---|---|---|---|
| D1 | **Re-extract substrate with FIXED predicate/object prompt** | 93% of claim triples missing predicate+object → re-run on all 80K articles with claims | ~80M tokens | 3-5 days at Groq daily cap |
| D2 | **Re-extract stances with negative-allowed prompt** | Zero negative stances today; can't detect opposition | ~40M tokens | 2-3 days |
| D3 | **Translate non-English quotes** | Telugu 15%, Hindi 8%, Kannada 3% have translations. Should be ~95% | ~20M tokens | 1 day |
| D4 | **Translate non-English article bodies** | Kannada at 50%, others at 91-94%. Fix Kannada gap | ~5M tokens | 4 hours |
| D5 | **`narrative_frame` classification** | 0% populated. PRD needs this for Stage 1 router. One short LLM call per article (just pick from 15 frames) | ~20M tokens | 1 day |
| D6 | **Geocode locations** | 19.9% have lat/lng. Use Nominatim (free, slow) or Google Maps API (paid, fast) for the other 80% | ~190K geocode calls | 2-3 days |
| D7 | **Re-extract events with date validation** | The 4.5% nonsense dates need re-extraction with sane bounds | ~10M tokens | half-day |

---

## CATEGORY E — New architecture / new tables
Bigger engineering, not just fixes.

| # | What to build | Why | Effort |
|---|---|---|---|
| E1 | **`entity_candidates` queue table** | 3-tier dictionary: track speaker names appearing in 5+ articles but not in entity_dictionary, LLM-fill metadata, human review, promote | 2-3 days |
| E2 | **Investigate v3 backfill lag** | Why has new-article v3 rate dropped from 100% → 54% since May 11? Likely a worker capacity issue or LLM quota issue | 1 day |
| E3 | **`narrative_frame` writer in extraction pipeline** | Once D5 backfills history, make sure new articles get it on first pass | 1 day |
| E4 | **Data quality dashboard** | One page showing daily population rates per field — so silent drift gets caught | 1-2 days |
| E5 | **Source-tier curation review** | 99% populated but is the tiering actually accurate? Sample audit + re-rank top 100 sources | 1 day |

---

## CATEGORY F — Drop redundant infrastructure
Cleanup only after dependencies are removed.

| # | What to drop | After we do | Risk |
|---|---|---|---|
| F1 | `articles.summary_preview` | UI code switched to truncate `summary_executive` | Low |
| F2 | `articles.summary_snippet` | Same | Low |
| F3 | `articles.entities_extracted` JSONB | Entity FK backfill (A1) finished; nothing reads JSONB anymore | Medium — verify no readers |
| F4 | `articles.language_detected` | B3 fasttext detector in production | Low |

---

## Suggested sprint order (by ROI)

### Day 1 — Quick wins (8 hours, massive impact)
- A1 — Entity-FK backfill from JSONB (linking 2-8% → 50-60%)
- A2 — NULL hallucinated event_dates
- A8 — NULL redundant canonical_url copies
- B2 — Quote translator skip English (saves tokens immediately)
- B6 — Cleanup wasted English→English quote translations

### Day 2 — Schema cleanup
- A3 — Drop inserted_at
- A4 — Drop geo_secondary
- A5 — Consolidate author_name → byline
- A6 — Generated column for geo_primary
- A7 — Status flag inconsistency cleanup

### Days 3-4 — Code logic
- B1 — char_offset backfill
- B5 — Quote context extraction
- B4 — canonical_url normalizer fix
- C1/C2 — LaBSE embedding backfills (run in background)

### Days 5-7 — Long-running LLM re-runs (kick off, monitor)
- D1 — Substrate re-extraction (fixed prompt) — biggest item
- D2 — Stance re-extraction (negative-allowed)
- D5 — narrative_frame classification

### Week 2 — Translations + geocoding
- D3 — Quote translation backfill
- D4 — Article body translation gaps
- D6 — Location geocoding

### Week 3 — Architecture
- E1 — entity_candidates queue
- E2 — v3 lag investigation
- E4 — Data quality dashboard

### Week 4 — Drop redundancies (after dependencies removed)
- B7 — Event type canonicalization
- B8 — Status flag refactor
- F1-F4 — Drop redundant columns

---

## Cost estimate

| Category | LLM token cost | Compute time | Human time |
|---|---|---|---|
| A (SQL only) | 0 | <1 hour | 4 hours |
| B (Code + targeted) | minimal | hours | 3 days |
| C (LaBSE backfills) | 0 | 1-2 days compute | 4 hours |
| D (LLM re-runs) | **~175M tokens** | spread across week | 1 day setup |
| E (New architecture) | varies | days | 5-7 days |
| F (Drops) | 0 | minutes | 4 hours |

**Total ~2-3 weeks of focused work** to get the data layer to where the narrative pipeline PRD assumes it already is.

---

## Field-by-field outcome table

| Field | Today | After repair |
|---|---|---|
| `articles.narrative_frame` | 0% | ~95% |
| `articles.geo_primary` | 24% junky | derived from `article_locations`, ~92% |
| `articles.geo_secondary` | 2.3% | DROPPED |
| `articles.full_text_translated` (non-English) | 50-94% | ~95% |
| `articles.byline` | 45% | ~45% (chronic upstream limit — kept as-is) |
| `articles.author_name` | 14% | DROPPED |
| `articles.canonical_url` | 80% (75% redundant) | NULL when matches url; kept when normalizing |
| `articles.language_detected` | 97% (low accuracy) | DROPPED |
| `articles.language_iso` | 95% | ~99% (fasttext) |
| `articles.inserted_at` | 100% (synonym) | DROPPED |
| `articles.summary_preview`/`snippet` | 95% but 3x cost | DROPPED (UI truncates exec) |
| `articles.nlp_processed`/`claims_extracted`/`quotes_extracted` | 24% inconsistent | merged into one `pipeline_stage` enum |
| `articles.entities_extracted` JSONB | 100% | DROPPED after A1 |
| `article_quotes.speaker_entity_id` | 6.1% | ~60% (A1) → ~75% (E1) |
| `article_quotes.quote_text_en` (non-English) | 3-15% | ~95% |
| `article_quotes.speaker_name_en` | 3-15% | ~95% |
| `article_quotes.char_offset_start/end` | 0% | ~100% (B1) |
| `article_quotes.context` | 10% | ~95% (B5) |
| `article_claims.predicate` | 7.2% | ~85% (D1) |
| `article_claims.object_text` | 7.2% | ~85% (D1) |
| `article_claims.subject_entity_id` | 2.0% | ~60% (A1) |
| `article_claims.embedding` | 0% | ~95% (C1) |
| `article_events.event_date` | 59% (4.5% junk) | ~70% clean (A2 + D7) |
| `article_events.event_cluster_id` | 4.2% | ~50% (after re-cluster) |
| `article_events.event_type` | 574 distinct | ~40 canonical (B7) |
| `article_stances.intensity` | always [0.1, 1.0] | full [-1, +1] (D2) |
| `article_stances.actor_entity_id` | 8.6% | ~60% (A1) |
| `article_locations.lat/lng` | 19.9% | ~85% (D6) |
| `article_locations.city` | 44% | ~70% (D6) |
| `article_numbers.context` | 46% | ~80% (better prompt) |

## What this gets you
- **Entity linking jumps from 2-8% → 60-75%** across all child tables
- **Storage ~25% smaller** after dropping 6 redundant columns
- **LLM cost ~30% lower** ongoing (no 3-summary generation, no English translation, fewer retries)
- **Mode A and Mode B** narrative pipeline both unblocked
- **Brief frontend** gets ~5x more quotes/claims with real entity context
- **Maps** become useful (atlas pages stop being half-empty)
- **Silent drift caught early** via the data quality dashboard
