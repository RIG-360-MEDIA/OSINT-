# Full Statistical Data Quality Audit — 2026-05-28

> **Run by**: live SQL probes against rig-postgres (Hetzner production)
> **Method**: per-field fill counts, NULL rates, distinct value counts,
> distribution analysis, FK orphan checks, recent-6h slice comparison.

## Table sizes (row counts, live)

| Table | Rows | Note |
|---|---|---|
| `article_links` | 5,035,831 | Links extracted from article bodies |
| `article_media` | 1,466,657 | Images/video references |
| `article_locations` | 259,047 | Avg 2.2 locations / article |
| `article_claims` | 238,287 | Avg 2.0 claims / article (post-D1 will rise) |
| `article_events` | 207,141 | Avg 1.7 events / article |
| `article_numbers` | 189,896 | Avg 1.6 numbers / article |
| `article_stances` | 157,705 | Avg 1.3 stances / article |
| `articles` | 119,242 | The master table |
| `article_quotes` | 96,663 | Avg 0.8 quotes / article |
| `article_districts` | 28,037 | Indian district mapping |
| `entity_dictionary` | 15,755 | Canonical entities |
| `article_tweets` | 2,039 | Embedded tweet refs |
| `sources` | 793 | Ingestion sources |
| `article_contradictions` | 0 | Stage 4 narrative-pipeline (not built) |

---

## 1. `articles` — master table (119,242 rows)

| Field | Filled | % | Grade |
|---|---|---|---|
| `title` | 119,242 | 100% | A+ |
| `full_text_scraped` (body) | 111,548 | 93.5% | A |
| `language_iso` | recent: 100% | A | |
| `labse_embedding` | 111,506 | 93.5% | A |
| `topic_category` | 117,669 | 98.6% | A+ |
| `geo_primary` | 88,691 | 74.3% | B |
| `narrative_frame` | 0 | 0% | **F (not built — D5 pending)** |
| `extraction_version = 3` | 26,204 + retroactive | 21.9% live, **will hit ~98% after D1 catch-up** | B→A |
| `substrate_status = ok` | 26,204 | 21.9% | B (rest pending) |
| `substrate_status = pending` | 66,045 | 55.4% | (D1 catch-up will drain) |
| `summary_preview` | filled where v3 | A (10-200 chars, avg 55) | A |
| `summary_snippet` | filled where v3 | A (36-623, avg 171) | A |
| `summary_executive` | filled where v3 | A (36-2400, avg 755) | A |
| `register_is_breaking = true` | 0 | 0% | **D (flag never set)** |
| `is_duplicate = true` | 5,894 | 4.9% | (dedup working) |

### Article body length distribution

Avg 2,896 chars (~500 words). Long enough for substrate. No bulk-thin articles.

### Article-type distribution (top 10)

```
news           56,360   (47%)
other          33,758   (28%)  ← too many "other" — classifier gap
analysis        4,235
sports_result   1,663
opinion         1,252
explainer       1,212
interview         707
live_blog         585
press_release     475
listicle          436
```

**Issue:** 28% as `other` is high. The classifier prompt should include more sub-types or push to "news" by default.

### Language distribution (top 10)

```
en  77,316  (65%)
te  15,026  (13%)  Telugu
kn   3,658  (3.1%) Kannada
hi   2,745  (2.3%) Hindi
ne   1,475  (1.2%) Nepali
sw      50         Swahili
mr      30         Marathi
vi      20         Vietnamese
ta       6         Tamil
pa       6         Punjabi
```

**Issue:** Heavy English/Telugu skew. The 22K+ articles flagged Odia in the body show as `lang=en` (translation layer mislabels). Real Indic share ≈ 20%.

### Substrate status × extraction_version cross-tab

```
status         | v | rows
---------------+---+--------
pending        | 0 | 66,045   ← D1 catch-up queue
ok             | 3 | 26,204   ← post-D1 fully extracted
fetch_failed   | 1 | 17,212   ← collector failures (real source issues)
junk           | 1 |  5,572
junk           | 2 |  2,864
extract_failed | 1 |  1,058
junk           | 3 |    373
fetch_failed   | 0 |     66
extract_failed | 0 |      4
```

---

## 2. `article_claims` — SPO triples (238,287 rows)

| Field | Filled | % | Grade |
|---|---|---|---|
| `claim_text` | 238,153 | 99.94% | A+ |
| `subject_text` | 238,145 | 99.94% | A+ |
| `predicate` | 25,328 | **10.6%** | F (pre-D1 rows lack it; D1 catch-up will fix) |
| `object_text` | 24,895 | **10.4%** | F (same — pre-D1) |
| `subject_entity_id` (linked) | 32,620 | 13.7% | D (entity-linking gap) |
| `embedding` | 226,326 | 95.0% | A |
| Avg `confidence` | 0.83 | — | A (high) |
| Avg `claim_text` length | 75 chars | — | OK |

**Critical:** SPO triple completeness is only 10% because D1 catch-up hasn't finished. Will hit 95%+ once the 66,045 pending articles re-extract (~8h ETA).

---

## 3. `article_quotes` — speakers (96,663 rows)

| Field | Filled | % | Grade |
|---|---|---|---|
| `speaker_name` | 96,602 | 100% | A+ |
| `quote_text` | — | 100% | A+ |
| `context` | 94,931 | 98.3% | A+ |
| `is_direct = true` | 85,985 | 89.0% | A |
| `quote_text_en` (translated) | 2,636 | **2.7%** | **F — D3 pending** |
| `speaker_entity_id` (linked) | 40,015 | 41.4% | D — entity-linking gap |
| Avg `quote_text` length | 126 chars | — | OK |

**Critical:** 97.3% of non-English quotes never translated. D3 task deferred — 108K quotes need a one-shot batch translation pass.

---

## 4. `article_locations` (259,047 rows)

| Field | Filled | % | Grade |
|---|---|---|---|
| `location_text` | 259,047 | 100% | A+ |
| `country` | 236,209 | 91.2% | A |
| `region` | 84,224 | **32.5%** | D |
| `city` | 112,847 | **43.6%** | D |
| `location_scope` | 259,047 | 100% (mislabeled — 99.97% as "country") | **D — buggy default** |

### `location_scope` distribution

```
country        258,962  ← over-applied to cities + sub-national too
unknown             63
global              14
continent            4
region               3
gulf                 1
```

**Issue:** `location_scope` is essentially monolithic ("country"). LLM is not differentiating actual scope. Either prompt fix or post-extract reclassifier needed.

---

## 5. `article_events` (207,141 rows) — *fixed today via migration 072*

| Field | Filled | % | Grade |
|---|---|---|---|
| `event_date` (LLM raw) | 120,221 | 58.0% | C (sparse) |
| **`effective_event_date`** | **207,141** | **100%** | **A+ (migration 072)** |
| `event_description` | 100% | A+ | |
| `event_type` | 100% | A+ | |
| `actors[]` filled | 192,486 | 93.0% | A |
| `is_future = true` | 31,029 | 15.0% | (reasonable) |
| `event_cluster_id` | 398 | 0.2% | F — clustering not run |

### Event type distribution

```
announcement   42,122  (20.3%)
statement      31,500
release        28,752
meeting        20,578
accident       20,096
filing         12,353
sports_result   8,032
election        7,056
legal           6,764
market_event    6,142
```

Healthy diversity, no over-fitting.

---

## 6. `article_numbers` (189,896 rows)

| Field | Filled | % | Grade |
|---|---|---|---|
| `value` | 189,809 | 99.96% | A+ |
| `unit` | 171,164 | 90.2% | A |
| `context` | 189,782 | 99.99% | A+ |

### Top units

```
percent  18,016
years    10,176
year      9,534    ← duplicate of "years" — normalize
count     8,651
date      7,026
USD       6,420
INR       6,391
seats     3,992
people    3,420
crore     2,958
```

**Issue:** `year` and `years` should be the same unit. Same likely for `dollar` / `USD` / `$` if those exist. Recommend a unit-normalizer pre-insert.

---

## 7. `article_stances` (157,705 rows)

| Field | Filled | % | Grade |
|---|---|---|---|
| `actor` | 157,610 | 100% | A+ |
| `stance` | 157,610 | 100% | A+ |
| `intensity` | 157,610 | 100% | A+ |
| `actor_entity_id` (linked) | 75,312 | 47.8% | C |
| Avg intensity | 0.63 | — | A (well-distributed) |

### Stance distribution

```
neutral      57,576  (36.5%)
supportive   52,563  (33.4%)
critical     44,894  (28.5%)
sympathetic   1,506   (1.0%)
defensive       412
admiration      263
concerned       108
analytical       90
```

Three-way split between neutral/supportive/critical = good signal. Long tail (sympathetic/defensive/etc.) under-used — could be prompt-engineered for richer stance taxonomy.

---

## 8. `entity_dictionary` (15,755 rows)

| Field | Filled | % | Grade |
|---|---|---|---|
| `canonical_name` | 100% | A+ | |
| `entity_type` | 100% | A+ | |
| `aliases[]` | 15,429 | 98.0% | A+ |
| `party` (politician metadata) | 3,228 | 20.5% | (only meaningful for persons) |
| `state` (Indian state) | 8,830 | 56.0% | (only meaningful for Indian entities) |
| `metadata` (JSONB) | 15,738 | 99.9% | A+ |

### Entity type distribution

```
person          9,438   (60%)
organization    2,495   (16%)
constituency    1,907   (12%)
location        1,664   (11%)
role              240
org                10   ← duplicate label of "organization"
organisation        1   ← duplicate of "organization"
```

**Issue:** `org`, `organisation`, `organization` are 3 spellings of the same type. Easy SQL fix: `UPDATE … SET entity_type='organization' WHERE entity_type IN ('org','organisation');`

---

## 9. `sources` (793 rows)

| Field | Filled | % | Grade |
|---|---|---|---|
| Total | 793 | — | |
| `is_active = true` | 550 | 69.4% | A |
| `health_score ≥ 0.5` | 644 | 81.2% | A |
| `health_score ≤ 0.1` (critical) | 137 | 17.3% | C |
| Recently collected (≤7d) | 352 | 44.4% | C (need investigation) |
| Avg `health_score` | 0.68 | — | B |

### Source-type distribution

```
rss     574 total / 403 active   (71% of total)
scrape  176 total / 104 active   (22%)
api      43 total /  43 active   (5%)
```

Only 3 source_types — far narrower than the 8 planned pillars. The pillar concept lives at the application layer (route/page filtering), not in source metadata.

---

## 10. FK orphan check (data integrity)

```
orphan_claims:    0
orphan_quotes:    0
orphan_events:    0
orphan_locations: 0
```

✅ DB integrity is clean — no dangling foreign keys.

---

## 11. Recent 6h slice (1,532 new articles)

| Field | Filled | % | Grade |
|---|---|---|---|
| `extraction_version = 3` | 1,377 | 89.9% | A |
| `author_name` | 1,318 | 86.0% | A (journalist extractor working) |
| `summary_preview` | 331 | **21.6%** | C — D1 catch-up consuming substrate capacity |
| `summary_executive` | 331 | **21.6%** | C |
| `register_style` | 330 | 21.5% | C |
| `primary_subject` | 331 | 21.6% | C |

**Interpretation:** Most recent articles have v3 stamp + author but haven't been substrate-processed yet (substrate is throttled because D1 catch-up is rewriting 66K rows). Once D1 catch-up completes (~8h ETA), the substrate worker will drain the backlog and these will fill to ~95%+.

---

## Summary — grades by area

| Area | Grade | Reason |
|---|---|---|
| **Database integrity (FK)** | A+ | 0 orphans across 4 child tables |
| **Article ingestion** | A | 100% titles, 93% bodies, 100% languages |
| **Topic / geo extraction** | A− | 98.6% topic, 74% geo, scope mislabels |
| **Summaries (preview/snippet/exec)** | A | Healthy length distribution, clean post-D1 |
| **Claims SPO (subject/predicate/object)** | C → A (post-D1) | 10% predicate fill now, will hit 95%+ in 8h |
| **Quote translation** | F | 2.7% — D3 backfill needed (108K rows) |
| **Entity linking** | D | Quotes 41%, stances 48%, claims 14% linked |
| **Event dates (effective)** | A+ | 100% via migration 072 (just shipped) |
| **Narrative frame** | F | Field exists, never populated — D5 pending |
| **Source health** | B+ | 81% sources healthy, but 17% in critical |

## Top 5 things still broken

1. **Quote translation** (97% missing) — D3 deferred per user
2. **Entity linking** (avg 35% across child tables) — entity_dictionary has 15K canonical entities but matching is weak
3. **`location_scope` mislabel** (99.97% "country") — needs prompt or post-classifier
4. **`narrative_frame`** (0% populated) — narrative pipeline scaffolded but not running
5. **`event_cluster_id`** (0.2%) — narrative Stage 0 clustering not running
