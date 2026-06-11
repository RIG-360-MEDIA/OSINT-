# Temporal Quality Analysis — Is breakage chronic or recent?

Scraping span: **2026-04-16 → 2026-05-25 (40 days, 112,555 articles total)**

## Article-level enrichment by week

| Week | Articles | v3 % | summary % | translation % | narrative_frame % |
|---|---|---|---|---|---|
| 2026-04-13 | 4,225 | 100% | 100% | 6% | 0% |
| 2026-04-20 | 4,955 | 100% | 100% | 4% | 0% |
| 2026-04-27 | 13,883 | 100% | 100% | 11% | 0% |
| 2026-05-04 | 27,939 | 100% | 100% | 22% | 0% |
| 2026-05-11 | 11,596 | **86%** | 93% | 24% | 0% |
| 2026-05-18 | 20,542 | **54%** | 83% | 16% | 0% |
| 2026-05-25 | 3,707 | **55%** | 92% | 21% | 0% |

## Claims quality by week

| Week | N claims | predicate % | object % | entity_id % | embedding % |
|---|---|---|---|---|---|
| 2026-04-13 | 14,845 | 8% | 8% | 2% | 0% |
| 2026-04-20 | 17,758 | 7% | 7% | 3% | 0% |
| 2026-04-27 | 50,370 | 7% | 7% | 2% | 0% |
| 2026-05-04 | 95,040 | 7% | 7% | 3% | 0% |
| 2026-05-11 | 31,347 | 7% | 7% | 2% | 0% |
| 2026-05-18 | 60,569 | **3%** | **3%** | **1%** | 0% |
| 2026-05-25 | 11,524 | **0%** | **0%** | **0%** | 0% |

## Quote quality by week

| Week | N quotes | translation % | entity_id % | char_offsets % |
|---|---|---|---|---|
| 2026-04-13 | 5,703 | 2% | 8% | 0% |
| 2026-04-20 | 6,907 | 0% | 8% | 0% |
| 2026-04-27 | 20,906 | 0% | 6% | 0% |
| 2026-05-04 | 38,692 | 9% | 8% | 0% |
| 2026-05-11 | 14,388 | **21%** | 7% | 0% |
| 2026-05-18 | 25,154 | 9% | **3%** | 0% |
| 2026-05-25 | 4,752 | 4% | **0%** | 0% |

## Locations geocoding by week

| Week | N | geocoded % |
|---|---|---|
| 2026-04-13 | 11,966 | 17% |
| 2026-04-20 | 14,601 | 18% |
| 2026-04-27 | 41,321 | 18% |
| 2026-05-04 | 79,821 | 21% |
| 2026-05-11 | 25,669 | 21% |
| 2026-05-18 | 50,430 | 19% |
| 2026-05-25 | 9,765 | 22% |

## Two categories of breakage

### Category 1 — CHRONIC (broken since day 1, every week)
These never worked, no week is better than another:

- `predicate` / `object_text` extraction: **always 7-8%** (recently dropped to 0)
- entity_id linking everywhere: **always 2-8%**
- quote translations: **always 0-25%** (bouncing, never stable)
- `narrative_frame`: **always 0%**
- `char_offset_start/end`: **always 0%**
- `claims.embedding`: **always 0%**
- location geocoding: **always 17-22%**

**Conclusion:** these are wiring bugs, not regressions. Schema fields exist but the code paths that populate them were never built or never worked from day one.

### Category 2 — RECENT REGRESSIONS (worked, then broke)

**Two clear breakages around May 11-18:**

1. **`extraction_version=3` dropped 100% → 54%**
   - Weeks Apr 13 to May 04: 100% upgraded
   - May 11: 86%
   - May 18 onward: 54-55%
   - **Cause:** v3 upgrade pipeline started failing on ~half of new articles around May 11

2. **claims/quotes entity_id link rate collapsed to 0%**
   - Stable 2-8% for 5 weeks
   - May 18: dropped to 1-3%
   - May 25: **0%**
   - **Cause:** likely a code change broke `_resolve_entity_id` around May 18. Today's patch (alias support) should restore it, but only for NEW data going forward — the existing 100K+ rows need re-linking.

## Verdict — answering your question

**Most of the breakage is CHRONIC, not recent.** Your data has been ~7-8% complete on predicate/object/entity-linking since you started scraping 40 days ago. The brief frontend has been working only because it reads the fields that DO get populated (summary, type, register).

**Two genuine recent regressions:**
- v3 upgrade backlog (started ~May 11)
- entity linking total collapse (~May 18 → 0%)

Both regressions stack on top of the chronic problems, making last 7-14 days the worst window in the entire history.

## What this means for the repair sprint

**A re-extract / re-link pass MUST cover ALL 112K articles, not just recent.** The structured-data pipeline was always missing relations — there's no "good baseline" to revert to. You're rebuilding the connective tissue from scratch across the full archive.

The good news: text content (titles, bodies, summaries, articles_types) is solid throughout. You aren't losing the content layer — you're building the relations layer on top of it for the first time.
