# Narrative Pipeline — Data Readiness Audit

Captured 2026-05-25 from production. Answers the 14 verification questions from the PRD.

## Verdict per mode

**Mode A (multi-source triangulation): ❌ BLOCKED — need 2 fixes**
**Mode B (single-source interrogation): ❌ BLOCKED — need 1 critical fix**
**Both modes: ⚠️ need 2 schema/backfill items**

## Detailed answers

### Both-mode foundational (1-7)

| # | Field | Coverage | Verdict |
|---|---|---|---|
| 1 | `thread_id` populated | **95.7%** (5,251 threads, 86,847 articles) | ✅ ready |
| 2 | `entities_extracted` JSONB | **100%** populated | ✅ ready (schema check pending) |
| 3 | `article_quotes.is_direct` | **100% populated, 88.8% direct** | ✅ |
| 3 | `article_quotes.char_offset_start/end` | **0% populated** | ❌ **needs backfill** |
| 4 | `article_numbers.context` (≥30 chars) | **46.4%** | ⚠️ half-populated |
| 4 | `article_numbers.unit` | **89.9%** | ✅ |
| 5 | `narrative_frame` populated | **0%** | ❌ **complete backfill needed** |
| 6 | `register_emotion`/`register_style` | n/a (query timeout) | ⚠️ recheck |
| 7 | `source_tier` | n/a (query timeout) | ⚠️ recheck |

### Mode A critical (8-10) — multi-source triangulation

| # | Field | Result | Verdict |
|---|---|---|---|
| 8 | `article_claims.embedding` | **0% populated** of 285,255 claims | ❌ **MODE A BLOCKER** — no embeddings means no consensus clustering |
| 9 | `article_stances.intensity` variance | All values in **[0.1, 1.0]** range. ZERO negative stances. 73K low-pos + 117K high-pos. | ❌ **MODE A BLOCKER** — without negative stances, you can't detect disagreement |
| 10 | Cluster size distribution | median=1, avg=15.83. **3,644 single-article threads, 1,607 multi-article (Mode A candidates = 31% of threads)** | ✅ — enough multi-source clusters to make Mode A worth building |

### Mode B critical (11-14) — single-source interrogation

| # | Field | Result | Verdict |
|---|---|---|---|
| 11 | `speaker_entity_id` linked | **6.1%** of 116,538 quotes | ❌ **MODE B BLOCKER** |
| 11 | `subject_entity_id` linked | **2.0%** of 285,255 claims | ❌ **MODE B BLOCKER** |
| 11 | `actor_entity_id` linked | **8.6%** of 190,881 stances | ❌ **MODE B BLOCKER** |
| 12 | `labse_embedding` populated | **95.8%** of articles | ✅ |
| 13 | Claims-per-article distribution | median=3, avg=3.53, **72% have 3+ claims** | ✅ enough material for internal tension scan |
| 14 | Archive depth (`labse_embedding`) | Oldest **2026-04-16** = **~5-6 weeks** | ⚠️ historical rhyme limited to recent past |

## Critical issues — what blocks the build

### Blocker 1: claim embeddings missing (Mode A only)
- `article_claims.embedding` is 0% populated despite 285K claim rows
- Without it, Stage 2A's claim consensus clustering can't run
- **Fix**: backfill embeddings on existing claims via LaBSE (24-48h batch job, no LLM cost)

### Blocker 2: stance intensity has no negative values (Mode A only)
- All 190,881 rows are positive [0.1, 1.0]
- Without negative stances, you can't tell agreement from disagreement
- **Fix**: re-extract stances with a corrected prompt that allows -1.0 to +1.0 range. Re-run on backlog

### Blocker 3: entity linking near-zero (Mode B critical, 70% of volume)
- `speaker_entity_id` 6.1%, `subject_entity_id` 2.0%, `actor_entity_id` 8.6%
- Without entity IDs, "entity history lookup" returns nothing for 90%+ of speakers/subjects
- **Fix already partially deployed**: today's `_resolve_entity_id` alias patch jumped this from ~2% to ~70% match rate on test names. Need to **backfill** all existing rows with the new resolver.

### Required schema additions (PRD §"Schema additions probably needed")
- `narrative_frame` needs backfill (currently 0%) — single LLM pass over the corpus
- `char_offset_*` on quotes needs backfill (currently 0%) — regex pass against `full_text_scraped`
- `claim_cluster_id` column on `article_claims` (parallel to `event_cluster_id`)
- `lede_candidates` materialized view
- `generated_articles` output table
- `historical_neighbors` precomputed K-NN table (depends on archive depth fix)

### Archive depth warning
- Only 5-6 weeks of LaBSE-indexed articles
- "Historical rhyme" lookups will mostly find the same week
- **Fix**: backfill embeddings on older `articles` rows (if their bodies are still in DB)

## Go/no-go recommendation

**Don't start the pipeline build yet.** Three backfills must run first:

1. **claim embeddings** (LaBSE, ~24h) — unlocks Mode A
2. **stance re-extraction with negative range** (LLM, ~3 days at Groq capacity) — unlocks Mode A
3. **entity_id backfill** with the patched resolver (SQL UPDATE pass, ~1h) — unlocks Mode B for 70% of volume

After backfills, Mode B is ready to prototype. Mode A is ready after the cluster work + claim_cluster_id schema.

**Total prep time before pipeline coding: ~1 week.**
