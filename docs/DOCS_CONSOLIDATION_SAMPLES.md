# What's redundant — sampled content from each cluster

Generated 2026-05-28

## Data Quality Audits (32)

### `docs/DATA_QUALITY_AUDIT_2026-05-26.md` (6.6KB, 2026-05-25)
**Title:** Comprehensive Data Quality Audit — 2026-05-26
**Intro:** Every table, every field, every silent break.
**Sections:** TL;DR — 7 critical findings (worst first) · ARTICLES table — column population rates (sorted w · ARTICLE_QUOTES (116,538 rows) · ARTICLE_CLAIMS (285,255 rows) — the big revelation · ARTICLE_EVENTS (187,341 rows) · ARTICLE_LOCATIONS (233,573 rows) · ENTITY_DICTIONARY (11,605 entities) — actually sol · TEMPORAL ANOMALY (the most worrying finding)

### `docs/DATA_QUALITY_AUDIT_2026-05-28.md` (11.4KB, 2026-05-27)
**Title:** Full Statistical Data Quality Audit — 2026-05-28
**Intro:** | Table | Rows | Note |
**Sections:** Table sizes (row counts, live) · 1. `articles` — master table (119,242 rows) · 2. `article_claims` — SPO triples (238,287 rows) · 3. `article_quotes` — speakers (96,663 rows) · 4. `article_locations` (259,047 rows) · 5. `article_events` (207,141 rows) — *fixed today  · 6. `article_numbers` (189,896 rows) · 7. `article_stances` (157,705 rows)

### `docs/DATA_QUALITY_TEMPORAL_ANALYSIS.md` (4.1KB, 2026-05-25)
**Title:** Temporal Quality Analysis — Is breakage chronic or recent?
**Intro:** Scraping span: 2026-04-16 → 2026-05-25 (40 days, 112,555 articles total)
**Sections:** Article-level enrichment by week · Claims quality by week · Quote quality by week · Locations geocoding by week · Two categories of breakage · Verdict — answering your question · What this means for the repair sprint

### `docs/DB_AUDIT_2026-05-26_v2.md` (147.6KB, 2026-05-26)
**Title:** RIG-Surveillance Database Quality Audit
**Intro:** Generated: 2026-05-26T21:43:29.580558+00:00
**Sections:** Table inventory (118 tables in `public` schema) · `article_links` · `article_media` · `article_claims` · `article_locations` · `article_numbers` · `article_stances` · `article_events`

### `docs/DB_COLUMN_PROFILE_2026-05-26.md` (44.5KB, 2026-05-26)
**Title:** RIG-Surveillance Per-Column Quality Profile (fast pass)
**Intro:** Generated: 2026-05-26T21:46:30.769367+00:00
**Sections:** `article_links` — 4,774,569 rows · 9 columns · `article_media` — 1,396,074 rows · 12 columns · `article_claims` — 306,278 rows · 11 columns · `article_locations` — 251,167 rows · 13 columns · `article_numbers` — 240,114 rows · 7 columns · `article_events` — 200,582 rows · 12 columns · `article_stances` — 204,207 rows · 7 columns · `article_quotes` — 124,823 rows · 14 columns

### `docs/FIELD_BY_FIELD_DEEP_AUDIT.md` (9KB, 2026-05-25)
**Title:** Field-by-Field Deep Audit + Quality Drilldown — 2026-05-26
**Intro:** Answers to specific questions + quality check on every field including 100%-populated ones.
**Sections:** 1. `full_text_translated` — by language · 2. `byline` — author field — 45% populated · 3. `narrative_frame` — what is it for? · 4. `geo_primary` — only 24%, since when? · 5. `extraction_version` — what is it · 6. `speaker_name_en` — what languages are missing  · 7. `quote_text_en` — why some, not others; English · 8. `char_offset_start/end` — what they're for

### `docs/ARTICLE_EXTRACTION_FIELDS.md` (4.5KB, 2026-05-25)
**Title:** Article Extraction — Complete Field Reference
**Intro:** Captured 2026-05-25 from production schema.
**Sections:** 1. `articles` table (the root row — 47 columns) · 2. Linked child tables (per article) · Summary

### `docs/PIPELINE_DATA_READINESS.md` (4.8KB, 2026-05-25)
**Title:** Narrative Pipeline — Data Readiness Audit
**Intro:** Captured 2026-05-25 from production. Answers the 14 verification questions from the PRD.
**Sections:** Verdict per mode · Detailed answers · Critical issues — what blocks the build · Go/no-go recommendation

### `docs/SCHEMA_REDUNDANCY_AND_WASTE.md` (6KB, 2026-05-25)
**Title:** Schema Redundancy & Waste Audit — 2026-05-26
**Intro:** Stupid things in the schema/data found while investigating geo_primary vs article_locations.
**Sections:** The geo question — no good reason · English "translation" wasted tokens · 9 more stupid things found · What this means · Clean schema would look like · Wasted LLM cost estimate (per day at current inges

### `docs/DATA_REPAIR_MASTER_PLAN.md` (11.1KB, 2026-05-25)
**Title:** Data Repair Master Plan — Every Fix Needed
**Intro:** Consolidates everything from quality audit, redundancy audit, temporal audit, field deep-dive, and architectural decisio
**Sections:** CATEGORY A — Pure SQL fixes (no LLM, no code chang · CATEGORY B — Code logic fixes (write/change code,  · CATEGORY C — LaBSE embedding backfills (CPU/GPU pa · CATEGORY D — LLM re-run on existing rows (expensiv · CATEGORY E — New architecture / new tables · CATEGORY F — Drop redundant infrastructure · Suggested sprint order (by ROI) · Cost estimate

## Onboarding / Memory (18)

### `docs/onboarding/00-README.md` (6.5KB, 2026-05-17)
**Title:** 00 - Onboarding README
**Intro:** RIG Surveillance is a multi-pillar intelligence aggregator targeted at
**Sections:** What RIG Surveillance is · Read in this order · Cross-cutting source-of-truth files · TL;DR for a new session · Don't break

### `docs/onboarding/01-architecture.md` (9.7KB, 2026-05-17)
**Title:** 01 - System Architecture
**Intro:** Each pillar is its own page in the frontend and its own ingestion
**Sections:** The 8 product pillars · Container topology · Celery queues and their consumers · TRIJYA-7 (the GPU box) · Tailscale routing · Data flow at a glance · Hetzner production access · Frontend conventions

### `docs/onboarding/02-substrate-pipeline.md` (10KB, 2026-05-17)
**Title:** 02 - Substrate Pipeline (v3 Extraction)
**Intro:** articles.extraction_version is a single-character column. The drain
**Sections:** What `extraction_version` means · The v3 prompt — Prompt G · The 6 v3 child tables · The drain script · Unified LLM pool (overview) · Known bugs / gotchas in the substrate pipeline · v3 quality stats (post-drain, 2026-05-16)

### `docs/onboarding/03-relevance-system.md` (6.9KB, 2026-05-17)
**Title:** 03 - Relevance System
**Intro:** - user_watched_entities (migration 068) — per-user watchlist:
**Sections:** How it works today · Relevance v3 — the design (not built yet) · Brief generation · Analyst pillar — synchronous RAG · See also

### `docs/onboarding/04-scrapers.md` (8.6KB, 2026-05-17)
**Title:** 04 - Scrapers / Ingestion
**Intro:** Implemented in backend/collectors/tiered_fetcher.py. Each tier is
**Sections:** The 4-tier fetch cascade · Trafilatura · Source registry · Source tiers · Health scoring + auto-disable · The big bulk-disable gotcha · Byline extractor · og:image / thumbnails

### `docs/onboarding/05-llm-infrastructure.md` (10KB, 2026-05-17)
**Title:** 05 - LLM Infrastructure
**Intro:** | Provider     | Keys | Model                             | Quota                                    | Speed       | Cos
**Sections:** The three providers · Quota dynamics · The unified pool — `backend/nlp/groq_client.py` · Ollama on TRIJYA-7 · The drain watchdog · Cooldown logic in detail · Three failover paths in practice · Groq Cerebras failover — when do they switch?

### `docs/onboarding/06-operations-runbook.md` (8.6KB, 2026-05-17)
**Title:** 06 - Operations Runbook
**Intro:** The drain rewrites every article from v1/v2 to v3. To see how far
**Sections:** How to check drain progress · How to restart the drain — MIXED mode · How to restart the drain — Ollama-only mode · How to check FreshRSS health · How to test scraping end-to-end · How to check Cerebras quota · How to check Groq quota · How to read the watchdog log

### `docs/onboarding/07-known-issues.md` (9KB, 2026-05-17)
**Title:** 07 - Known Issues
**Intro:** Symptom. The DB has 574 active RSS sources, but new-article
**Sections:** 1. Scrapers silently fail (FreshRSS auth, bulk-dis · 2. Drain stalls when Ollama daemon dies on TRIJYA- · 3. No monitoring / alerting · 4. Cerebras TPD burn during long drains · 5. Groq organisation restrictions (uncommon but ha · 6. `semantic_repass.py` ignores `LOCAL_LLM_PRIMARY · 7. Worker-collectors backed-up queue accumulates s · 8. (Operational, not on the canonical list) — YouT

### `docs/onboarding/08-future-plans.md` (7.3KB, 2026-05-17)
**Title:** 08 - Future Plans
**Intro:** Goal. Stop the empty-feed problem for new users. Every user
**Sections:** 1. Relevance v3 — 3-layer redesign · 2. Frontend redesign — intelligence publication · 3. Byline extractor — lift coverage 14% → 80% · 4. Sources resurrection (~150 dead RSS paths) · 5. Monitoring + alerting layer · 6. v4 prompt iteration (if needed) · Secondary threads (mentioned in docs/future-todo.m · Sequencing recommendation

### `docs/onboarding/09-todos-prioritized.md` (7.3KB, 2026-05-17)
**Title:** 09 - Prioritised Backlog
**Intro:** Status. In progress. ~23K v1 articles remaining as of
**Sections:** P0 — Active now · P1 — This week · P2 — This month · P3 — Someday · See also

### `docs/onboarding/10-context-from-may-2026-session.md` (9.2KB, 2026-05-17)
**Title:** 10 - Context From the May 2026 Session
**Intro:** Discovery date. 2026-05-13.
**Sections:** 1. Old Ollama install was 553MB and silently CPU-o · 2. FreshRSS admin user wiped on 2026-05-15 · 3. FreshRSS subscription persistence is fragile · 4. The 7-variant prompt eval — Prompt G is the win · 5. The 32-line drain watchdog auto-recovers MIXED  · 6. Re-enabled 174 of 406 bulk-disabled sources · Auxiliary findings from the same session · See also

### `docs/onboarding/REQUIREMENTS.md` (12.8KB, 2026-05-17)
**Title:** Onboarding Requirements — living document
**Intro:** ---
**Sections:** How to use this doc · Profile schema — today vs target · Cross-cutting fields (used by many features) · Per-feature requirements · Backlog — fields with no current owner · How the wizard will be derived

### `CLAUDE.md` (7KB, 2026-05-17)
**Title:** CLAUDE.md
**Intro:** Project context for any Claude session working in this repo. Read this
**Sections:** New session? Read docs/onboarding/00-README.md fir · What this project is · Deployment topology — IMPORTANT · Source-of-truth files · Govt-documents pillar — current state · Common foot-guns · Conventions · When in doubt

## Sprint plans / PRDs (9)

### `docs/RECONCILIATION_PLAN_2026-05-26.md` (5.5KB, 2026-05-26)
**Title:** Branch Reconciliation Plan — 2026-05-26
**Intro:** - Local fix/brief-prod-readiness is 131 commits ahead, 74 commits behind origin/fix/brief-prod-readiness.
**Sections:** Situation · What origin has (74 commits) — by category · What local has that origin doesn't (131 commits) · Conflicts predicted (per file) · Recommended strategy: **rebase-the-deltas** · Alternative: "merge with abandonment" · Risk assessment · Do tonight

### `docs/UNIFICATION_PLAN_2026-05-26.md` (6.7KB, 2026-05-26)
**Title:** Branch Unification + Code Cleanup Plan
**Intro:** Goal: ONE unified branch, all security patches applied, code professionally formatted, no vulnerabilities, no dead code,
**Sections:** Phase 1 — Safety net (10 min, ZERO risk) · Phase 2 — Per-file decision matrix (30 min) · Phase 3 — Reset + cherry-pick (1-2 hours) · Phase 4 — Code quality pass (1-2 hours) · Phase 5 — Security audit (30 min) · Phase 6 — Test pass (30-60 min) · Phase 7 — Production verification (30 min) · Phase 8 — Push (5 min)

### `docs/PHASE1_20_COUNTRIES.md` (46.2KB, 2026-05-27)
**Title:** Phase 1 — 20-country flagships
**Intro:** awk: cmd. line:20: warning: regexp escape sequence \d' is not a known regexp operator
**Sections:** 🇺🇸 US  (sheet183.xml) · 🇬🇧 UK  (sheet62.xml) · 🇮🇳 India  (sheet81.xml) · 🇧🇩 Bangladesh  (sheet15.xml) · 🇦🇺 Australia  (sheet11.xml) · 🇯🇵 Japan  (sheet88.xml) · 🇨🇳 China  (sheet38.xml) · 🇰🇷 Korea  (sheet94.xml)

### `docs/BEST_SOURCES_GLOBAL.md` (2KB, 2026-05-27)
**Title:** Global news dataset — best sources by tier
**Intro:** Generated: 2026-05-27
**Sections:** Tier-1 flagships per priority country (LIVE, natio · 📊 By region (LIVE national_flagship counts) · ⭐ Top recommendation

