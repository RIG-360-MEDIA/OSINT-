# Client API — Data Quality, VERIFIED against the live database (2026-07-05)

Method: queried production `rig-postgres` directly (not docs). 875,650 articles total; the
docs were wrong on several points (column names, district "missing", translation "missing"),
so everything below is a live measurement.

## A. SOLID enough to ship
| Capability | Measured | Verdict |
|---|---|---|
| Freshness / volume | 20,946 articles/24h, 189k/7d, latest **today** | ✅ genuinely live |
| Full-text present | **94.3%** of last-7d (≈6% null) | ✅ good |
| NLP + substrate enrichment | **100%** of last-7d | ✅ keeps up |
| Mention trend | `entity_mention_daily` **fresh to today**, 659k rows | ✅ |
| Entities | 19,385 dictionary entries; 1.04M sentiment rows | ✅ |
| Sources | 2,039 (tier1 502 / tier2 1,375 / tier3 162) | ✅ |
| Story freshness | clusters carry a real `updated_at` that moves; 77,570 updated in 7d | ✅ (stories *do* stay live) |
| Story richness | cluster has `article_count`, `source_count`, `independent_source_count`, `stance_distribution`, `sentiment`, `representative_title`, `representative_quote`, `importance_score` | ✅ richer than docs claimed |

## B. NOT perfect — number → root cause → fix
1. **Article `updated_at` is frozen — moves on only 0.95% of rows.** → The pipeline writes enrichment to *related* tables and never bumps `articles.updated_at`. → **Fix:** add `api_ready_at` + bump-on-change trigger; partner cursor sorts on it. *(This is the sync must-fix.)*
2. **Sentiment covers only ~28% of new articles (≈50% on regionally-tagged).** 24h: sentiment **28.4%**, quote **20.9%**, claim **31.0%**; district-tagged subset **49.8%**. → Directed sentiment/quotes/claims run **selectively** — a stance needs a recognised *target entity*; entity-less articles get none (LLM cost-gating too). → **Fix:** expose sentiment where present; add a **general (non-directed) sentiment fallback** for entity-less articles, or set the expectation that sentiment = the entity-relevant subset (which, for a client tracking specific entities, is the subset they care about anyway).
3. **`language_iso` populated on only 67.6% of recent articles** — a third have no language tag. → `language_iso` is under-filled vs `language_detected` (two columns). → **Fix:** backfill `language_iso` from `language_detected`; make the pipeline always set it.
4. **Full-body translation only 33%** (92% have a lead/gist translation). → Substrate translates a length-capped gist, not the whole body. → **Fix:** run full-body MT where the client needs verbatim, or sell it honestly as "faithful gist + original".
5. **District tagging = 28,571 articles (3.3% of all), 59 districts, AP+TG only.** → Gazetteer scoped to the Telugu states. → **Fix:** it works — per client, seed that state's gazetteer + ingest local (tier-3) sources; nationally it's a data exercise, not code.
6. **Clustering is mostly singletons.** 348,407 clusters, **median = 1 article**; only **7,723 are ≥3-independent-source ("surfaceable")**; a **14,893-article mega** exists. → Most events are single-article; over-merge megas still occur. → **Fix:** expose **only the surfaceable tier (≥3 independent sources)** as "stories"; keep the anti-mega/`SIZE_NET` guard + nightly repair.
7. **Credibility / misinformation flag — absent** (no table in DB). → Never built. → **Fix:** net-new model, or explicit fast-follow (don't promise it).

## C. Corrections to the earlier (docs-based) audit
- District: docs said "not linked / missing" → **real** (`article_districts`, 28.5k articles, AP+TG).
- Story columns: docs said `member_count` → **real is `article_count`**; median cluster is 1 article.
- Translation: audit said "missing" → **92% gist / 33% full-body**.
- Source-breakdown / trending / breaking → **exist** (`observe_panels`).
- Full-text null: guessed ~10% → **measured 6%**.
- New gap not previously flagged: **`language_iso` 32% missing**.

## D. Bottom line for the pitch
- **Volume, freshness, entities, trend, sources, story metadata** = genuinely strong, ship as-is.
- **Sentiment** is the honest soft spot: ~28% global / ~50% regional coverage because it's entity-gated — frame it as "sentiment on tracked entities/relevant content", not "every article".
- **Districts** = real but regional; **translation** = gist-strong, full-body partial; **stories** = expose the ≥3-source tier only.
- **Two true builds:** the `updated_at`/ready-stamp sync fix, and (if wanted) a credibility flag. Everything else is coverage-tuning + wiring, not missing intelligence.
