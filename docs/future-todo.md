# Future TODO

Everything we've decided to build but DELIBERATELY deferred. Ordered by
when it should land relative to the v2 corpus stabilising.

Status key: 🟢 ready to start · 🟡 needs dependency · 🔴 blocked

---

## Recently shipped (2026-05-12)

Captured here so future-self knows what's already in production vs.
still on the todo list.

- **Migration 069** — v2 extraction schema (article_stances, article_numbers, summary columns, register, byline, full_text_translated, extraction_version, is_future on events). Applied.
- **Migration 070** — `article_locations.location_scope` enum (country/continent/ocean/sea/gulf/strait/region/global/unknown) + neutral-stance intensity reset to 0.0. Applied.
- **Migration 071** — `article_tweets` table + indexes (tweet content from free oEmbed). Applied.
- **Migration 072** — `articles.byline` column. Applied.
- **Parallel LLM pool** — Groq+Cerebras unified slot pool with JSON-validate retry path, `PARALLEL_LLM_POOL` kill-switch. Total pool now 51 keys (24 Groq + 27 Cerebras) after refresh on 2026-05-12.
- **Tweet content enrichment** — `backend/tasks/substrate/enrich_tweets.py` calls Twitter's public oEmbed endpoint (no API key, no rate limit). Wired inline into `_persist_structural` so every new v2 article auto-enriches its cited tweets. 95.8% recovery rate, 8+ languages including multi-script content.
- **HTML byline extractor** — `_extract_byline()` in `run_corpus_pass.py` parses JSON-LD → meta → CSS selectors with multilingual blacklist. ~42-45% coverage on v2 corpus, 824 unique journalists tracked. Zero LLM cost.
- **Periodic byline backfill** — Celery beat task `tasks.backfill_bylines_periodic` every 6h, picks up any v2 article missing byline (catches v1→v2 upgrades from semantic_repass). Routes to `collectors` queue.

---

## After v2 corpus stabilises (Day 5+)

### 1 · Personalized sentiment via LLM-as-judge   🟢

**Why:** Article-level sentiment is misleading. Same article can be positive
for User A and negative for User B depending on whose side they're on.
Pure entity-stance lookup is too weak. Graphs are too brittle to maintain.

**The design:**
```
Stage 1 (v2 extraction) — already running:
  Article → actor_stances, claims, summaries, register, translations

Stage 2 (personalized sentiment) — to build:
  (Article structured data + User profile text) → score for that user
  
  - User profile is FREE-FORM TEXT, editable per user.
  - LLM reads structured article data + user profile.
  - Returns: {score: -1.0 to 1.0, reasoning: "1-3 sentences"}
  - Cached in articles.user_sentiment or new per-user-sentiment table.
  - Triggered as background task on top N relevant articles per user/day.
```

**Schema additions when ready:**
```sql
ALTER TABLE users ADD COLUMN profile_text text;

CREATE TABLE article_user_sentiment (
  article_id uuid REFERENCES articles(id) ON DELETE CASCADE,
  user_id uuid REFERENCES users(id) ON DELETE CASCADE,
  score numeric,
  reasoning text,
  scored_at timestamptz DEFAULT now(),
  PRIMARY KEY (article_id, user_id)
);
```

**Effort:** ~2 days of code.
**Cost:** ~$0.0002 per (article × user) scoring at DeepSeek paid tier.
**For 50 top articles × 5 users/day = $0.05/day.**

**DO NOT use:**
- Relationship graphs (rot in 6 weeks, maintenance hell)
- DSPy (needs labeled training data we don't have — revisit at scale)

---

### 2 · Polish migration — location/data dedup + normalisation   🟡

**Why:** Known cosmetic bugs in v2 output that don't block usage but
should be cleaned in one consistent pass before users hit them.

**Migration 070_polish.sql:**
```sql
-- Strip literal "null"/"None" strings → real SQL NULL
UPDATE article_locations SET region = NULL WHERE region IN ('null','None','');
UPDATE article_locations SET city   = NULL WHERE city   IN ('null','None','');

-- Telugu-script → Roman normalisation
-- (lookup table for ~30 Telangana districts + neighbouring state capitals)
UPDATE article_locations SET city = 'Adilabad' WHERE city = 'ఆదిలాబాద్';
-- ... etc

-- Bengaluru/Bangalore, Mumbai/Bombay, Madras/Chennai, Calcutta/Kolkata
UPDATE article_locations SET city = 'Bengaluru' WHERE city ILIKE 'bangalore';
-- ... etc

-- Dedup duplicate (country, region, city) per article
DELETE FROM article_locations a USING article_locations b
WHERE a.article_id = b.article_id
  AND a.country = b.country
  AND COALESCE(a.region,'') = COALESCE(b.region,'')
  AND COALESCE(a.city,'') = COALESCE(b.city,'')
  AND a.id > b.id;

-- Reject non-country tokens (Mars, EU, Asia-Pacific, etc.)
-- Set country=NULL where it's not in ISO-3166
```

**Effort:** ~half day. Run once after corpus stable.

---

### 3 · Entity resolution — alias bootstrap + candidate pool   🟡

**Why:** Currently article_events.actors[] is free-text strings. Same person
("KTR" / "K. T. Rama Rao" / "Kalvakuntla Taraka Rama Rao") not linked.
Voice-share calculations are wrong because of fragmentation.

**Architecture (already discussed, plan locked):**

```
Phase A — Bulk alias bootstrap:
  One Groq batch job over all 11,604 canonical entities in entity_dictionary.
  Ask: "For each, list 3-5 common variants/aliases."
  Bulk INSERT into entity_aliases (currently has 14 rows; target ~30K-50K).
  Cost: ~$0.20 or 15% of one day's free Groq quota.

Phase B — LaBSE embeddings on entities:
  ALTER TABLE entity_dictionary ADD COLUMN labse_embedding vector(768);
  Batch-compute embeddings for canonical_name (model already loaded).
  Powers semantic similarity matching beyond exact alias.

Phase C — Bulk resolution pass over existing actors:
  Single Groq batch job:
    - Input: all unmatched actor strings + canonical entity list
    - Output per candidate: alias-of-canonical / merge-with-other-candidate / new-canonical
  Apply: INSERT into entity_aliases, INSERT into newsroom_entity_mentions
         (or new article_entity_mentions table).

Phase D — Candidate pool + auto-promotion:
  CREATE TABLE entity_candidates ...
  Nightly task: candidates with 5+ mentions across 2+ sources → promote to
                entity_dictionary as new canonical entries.
```

**Effort:** 2-3 days total. Sequenced after polish migration.

**Result:** every article's actors get canonical entity_id. Watchlist
queries unified. Voice-share rolls up correctly. New entities surface
automatically.

---

### 4 · Source-tier scoring   🟢

**Why:** "10 outlets carry story X" is misleading when 7 are wire-service
redistributions of one PTI feed. Tier-weighted voice-share fixes this.

**Work:**
```
1. Manually categorise ~200 sources into Tier 1/2/3:
     Tier 1: NDTV, Hindu, Eenadu, Sakshi, Mint, BS — original reporting
     Tier 2: Hindustan Times, TOI feeds, regional editions
     Tier 3: Sportskeeda, TV9 photo-gallery, click-bait aggregators

2. UPDATE sources SET source_tier = N;

3. Voice-share queries weight by tier (5x / 2x / 1x).
```

**Effort:** 1 hour of categorisation + 5-line query change. No Groq cost.

---

### 5 · Cross-modal integrations   🟡

**Why:** Articles cite YouTube clips + tweets. We extract the IDs already.
Connecting them unlocks verification + viral-clip detection.

**Three sub-tasks:**

```
5a · YouTube auto-enrichment from article citations:
   When article_media has a YouTube external_id NOT in youtube_clips,
   enqueue a fetch+transcript task.
   Estimated recovery: ~1,000 new clips from existing article citations.

5b · Quote-to-clip verification:
   For each article_quotes row, fuzzy-match speaker quote text
   against youtube_clips.transcript_segment of same speaker.
   If >85% match → set article_quotes.verified_clip_id = clip.id
   Powers the "quote verified against primary source" UI badge.

5c · Tweet ID enrichment:
   For each article_media of type='tweet', fetch tweet metadata
   (author, timestamp, engagement) and link to social pillar.
```

**Effort:** 5a is half a day, 5b is 1 day, 5c needs Twitter API access.

---

### 6 · Scraper recovery work   🟢

**Sources currently blocked at fetch time. Per docs/mistakes.md analysis:**

| Source | Articles lost | Fix approach | Effort |
|---|---|---|---|
| NDTV / Sky News / FT / Vanguard | ~3,800 | curl_cffi for TLS fingerprinting | 4-8 hrs |
| Prajavani (Karnataka) | 1,509 | section-narrowing OR Playwright | 3-4 hrs |
| Telugu/Odia junk-threshold tweak | ~400 | Per-script char threshold | 1 hr |
| Auto-update PIB feed | rolling | Already fixed via browser-headers in v2 | done |

---

### 7 · Observability   🟢

```
7a · Per-source success-rate dashboard
     Daily counter per source: ok/junk/fetch_failed/extract_failed.
     Surfaces regressions within hours.

7b · LLM-budget telemetry
     /admin/health/llm-budget endpoint
     Shows residual quota per provider.

7c · Substrate progress endpoint
     /admin/substrate/status returning {pending, ok, junk, fetch_failed, extract_failed}
     replaces SSH-to-SQL.
```

**Effort:** 1 day total. Quality-of-life improvement.

---

### 8 · Production-readiness gaps   🟢

```
8a · Off-server backup
     /root/backup-db.sh currently dumps to same VM disk.
     Add: push to Hetzner Storage Box (€3.45/mo, 1TB).
     Trigger: before onboarding any second user.

8b · Hetzner VM Backups
     Enable in Hetzner Cloud Console.

8c · Backup-cron failure alerting
     Check that latest backup is fresh (< 26h old).
     Email/Slack/log alert on miss.
```

---

### 9 · Frontend HOME v2 redesign   🟡

Status from earlier work this session — deferred while extraction backlog runs.

```
- 8 HOME zones locked in demo-no-lines-v3.html
- Palette + register + colour roles validated
- Need to port to React components after v2 corpus stabilises
- Component-by-component build, ~2-3 days
- Then mobile responsive pass
```

---

## Sequencing recommendation

```
Week 1 (corpus finishing — happening now):
  - Just watch the v2 refill complete
  - Run quality spot-checks
  - Don't add new work mid-flight

Week 2 (immediately after refill):
  - #14 data-quality cleanups (unknown locations, stance enum, quote context column)
  - #11 enable auto-trigger v2 processing (replaces manual runners)
  - #15 tweet-enrichment backfill task for v1→v2 upgraded articles
  - #2 polish migration (remaining cosmetic cleanups beyond 070/072)
  - #4 source-tier scoring (1 hour, immediate value)
  - #8a/b backup hardening (one afternoon)

Week 3 (scrapers come back online):
  - #10 + #12 + #13 — wire byline + published_at + tags + dek into scraper,
    keep the ownership boundary clean (scraper writes articles row,
    substrate owns child tables)
  - #3 entity resolution (the big architectural win)
  - #5a YouTube auto-enrichment
  - #17 brief generation switches to v2 fields (~70% token reduction)

Week 4:
  - #1 personalized sentiment layer (start with 1 user, expand)
  - #18 body embeddings via LaBSE on RTX 4090
  - #9 frontend port (#16 v2 field surfacing bundles here)

Later (when scale / users justify it):
  - #5b quote verification (cross-join article_quotes ↔ article_tweets)
  - #6 NDTV TLS workaround
  - Move to paid LLM tier (~$10-20/mo)
```

---

### 10 · Move byline extraction INTO the scraper   🟢

**Why:** Right now the byline pipeline is a separate Celery beat task
(`tasks.backfill_bylines_periodic`, every 6h) that re-fetches each
article's HTML to extract the byline. That works but is wasteful —
the scraper already has the HTML in hand at fetch time. If we wire
`_extract_byline()` into the collector pipeline, every new article gets
a byline on first ingest, no second HTTP request needed.

**Work:**
```
1. In backend/collectors/tiered_fetcher.py (or wherever the raw HTML
   ends up in the collector), import _extract_byline from
   backend/tasks/substrate/run_corpus_pass and run it before trafilatura
   strips the byline tags.
2. Write the result to articles.byline directly during INSERT.
3. Leave the periodic backfill task in place as a safety net for any
   article whose first-ingest byline came back null.
```

**Effort:** ~1 hour once we re-enable the scrapers. **Net effect:** the
6h backfill task starts processing 0 candidates because all new articles
already have bylines on arrival.

**Note for future-self:** the extractor is pure (no DB calls, no
external requests, just BS4 parse). Plug it in wherever the raw HTML
exists. The clean output passes the same blacklist tightened over the
v2 deploy on 2026-05-12 (rejects publication names, CMS handles,
"Audio By X" vendor strings, and multilingual "Desk" / "Web" patterns).

---

### 11 · Auto-trigger v2 processing for new articles   🟡

**Why:** Today, scraped articles sit in `substrate_status='pending'`
until someone manually runs `run_corpus_pass --all`. There's no Celery
hook between scrape and v2 enrichment, so new articles wait around
indefinitely if the manual runner isn't kicked off.

**The gap (current flow):**
```
collect_rss / collect_html  →  INSERT article (pending)  →  [WAITS]
                                                            ↓ (only when manually triggered)
                                                          run_corpus_pass --all
                                                            ↓
                                                          status='ok', extraction_version=2
```

**The fix:**
```
1. Refactor backend/tasks/substrate/run_corpus_pass.py:
   - Extract the inner batch loop into a callable `async def process_pending(limit: int)`.
   - Leave the CLI entry point intact for one-shot manual runs.

2. Create backend/tasks/substrate/substrate_periodic_task.py:
   @app.task(name="tasks.process_pending_substrate")
   def process_pending_substrate():
       asyncio.run(process_pending(limit=200))

3. Add to backend/celery_app.py:
   - include: "backend.tasks.substrate.substrate_periodic_task"
   - task_routes: "tasks.process_pending_substrate" → "nlp" queue
   - beat_schedule: "substrate-pending-every-5-min" → every 5 minutes
```

**Effort:** ~30 minutes.

**When to ship:** AFTER the current corpus refill completes. Don't
enable in parallel with manual `--all` runners or you'll double-process.

**Net effect:** new article scraped at 10:32 → v2-enriched by ~10:37.
No manual runner ever needed again. Pool depletion naturally
rate-limits the task — when keys are exhausted it just queues less
work next tick.

---

### 12 · Extract more free fields at scrape time   🟢 (bundles with #10)

**Why:** While we're already parsing HTML at fetch time for §10 byline,
we can grab three more useful fields with the same JSON-LD/meta scan.
All free metadata, no LLM, no extra HTTP calls.

**Work — three fields, ~30 lines total in `tiered_fetcher.py`:**

```
a · published_at (better source)
    Current: RSS pubDate, often missing or wrong (feed lag).
    Better:  JSON-LD `datePublished` → <meta property="article:published_time">.
    Schema:  articles.published_at_html (new column) — preserve RSS pubDate
             as articles.published_at so we can compare and pick best.

b · tags / article_section
    Source:  JSON-LD `keywords` array, `articleSection` field,
             <meta name="keywords">, <meta property="article:section">.
    Schema:  ALTER TABLE articles
               ADD COLUMN tags text[] DEFAULT '{}',
               ADD COLUMN article_section text;

c · dek / description
    Source:  <meta property="og:description"> or <meta name="description">.
    Schema:  ALTER TABLE articles ADD COLUMN dek text.
    Use:     "secondary headline" / preview text on /coverage cards.
```

**Effort:** 1 hour total, bundled with #10 byline rollout. No LLM cost.

**Notes for substrate compatibility:**
Substrate v2's `_update_article()` already uses COALESCE for every
column. As long as scraper writes to `articles` row fields (NOT to
child tables like `article_links` / `article_media`), substrate's
re-pass either confirms or refines the values — never destroys them.

---

### 13 · Scraper ↔ substrate ownership boundary   🟢 (design rule)

**Why:** Now that we're moving extraction work from substrate INTO the
scraper, we need a clear boundary so the two pipelines don't fight
each other or duplicate work.

**The rule:**
```
SCRAPER OWNS:                        SUBSTRATE OWNS:
  columns on `articles` row          everything in child tables
  (byline, published_at_html,        (article_links, article_media,
   tags, article_section, dek,       article_locations, article_events,
   thumbnail_url, language_iso)      article_quotes, article_claims,
                                      article_stances, article_numbers,
                                      article_tweets)
```

**Why this boundary:**
- `articles` row columns use COALESCE in `_update_article` → scraper's
  values survive substrate re-passes.
- Child tables use DELETE+INSERT in `_persist_structural` /
  `_persist_locations` / etc. → substrate WOULD wipe any scraper-
  written rows. So scraper must not touch them.

**If we ever want scraper to own child tables too:**
- Convert `_persist_*` helpers from DELETE+INSERT to UPSERT/ON CONFLICT
  (similar to how `_persist_tweets` already does it).
- OR: have substrate skip the structural parse when the scraper has
  already populated the child tables. Detect via `substrate_status` or
  a `structural_extracted_at` timestamp.

Defer that decision. Today, the safe answer is: scraper writes `articles`
fields, substrate owns child tables. Document this rule wherever a new
collector or extraction task gets added.

---

### 14 · Data-quality cleanups discovered during v2 audit   🟢

Small fixes that came out of the 2026-05-12 v2 quality audit. None
blocking, all cheap — bundle into one polish migration after corpus
refill.

**14a · Unknown-scope locations** (Migration 070 followup)
The 764 rows currently `location_scope='unknown'` split into three groups:
```sql
-- (a) real countries whose country column got dropped by the LLM:
--     Iran(4), India(3), Gaza(3), Telangana(5), Washington(5), London(3).
--     Backfill country from location_text via an alias lookup table.

-- (b) organizations mis-classified as places:
--     United Nations(7), Google(3), Microsoft(3), Amazon(3).
--     Move to entity_dictionary; delete from article_locations.

-- (c) non-locations entirely:
--     Mars(4), "online"(3), "January"(3). Delete.
```

**14b · Stance enum normalization**
The LLM occasionally returns stance values outside our enum:
```sql
UPDATE article_stances SET stance='supportive' WHERE stance IN ('positive','admiration');
ALTER TABLE article_stances
  ADD CONSTRAINT chk_stance_enum
  CHECK (stance IN ('supportive','neutral','critical'));
```
Plus tighten the prompt with explicit enum reminder.

**14c · Quote `context` column** ✓ SHIPPED in migration 073 (2026-05-12)
Column added, `_persist_quotes` writes it for new extractions. The
2,718 existing quotes have NULL context — will fill organically as
the re-pass completes.

**14d · Remaining 641 unknown-scope locations** (followup to migration 070+073)
Migration 073 cleaned 55 obvious cases (orgs, non-locations, common
countries) out of 764. The 641 leftover are smaller patterns we can
do in a single SQL sweep when convenient:
```
Indian neighborhoods missing country=India:
  attapur, rajendranagar, hyderabad (already-listed cities that should
  bind to India + parent city)
Strait/region variants we didn't catch in 070's lists:
  "hormuz strait" (had "strait of hormuz"), "gulf region", "gulf states",
  "eastern mediterranean"
Financial orgs:  BSE, NSE, JPMorgan Chase  → delete
Misc non-locations:  Moon  → delete
Specific places:  "white house"  → US + Washington
```
**Effort:** 20 min as migration 074. Non-blocking.

**14e · 281 v2 articles with NULL `full_text_translated`** (LOST work)
These are non-English articles where v2 extraction succeeded but the
`english_translation` field came back empty from Groq. They are
usable (we still have the original-language body and structured
fields) but the English translation column is null.

Fix: a small targeted task that re-runs ONLY the translation prompt
on `extraction_version=2 AND language_iso != 'en' AND full_text_translated IS NULL`.
~300 Groq calls (5-10 min). Non-blocking — articles work without it.

**Effort:** all of §14 combined ~1 hr when convenient.

---

### 15 · Tweet enrichment for v1→v2 upgrade path   🟡

**Why:** Inline tweet enrichment runs only inside `run_corpus_pass`'s
`_persist_structural`. Articles upgraded via `semantic_repass` (the
8K v1 articles getting bumped to extraction_version=2) do NOT get
tweet content automatically.

**Fix options (pick one):**
```
a · Add a backfill beat task — mirror tasks.backfill_bylines_periodic.
    Every 6h, sweep article_links for tweet URLs whose article has
    extraction_version=2 but no matching article_tweets row.
    Cheap, no LLM, idempotent.

b · Wire into semantic_repass directly.
    After persistence, look up article's links and call enrich_article_tweets.
    Adds ~1 sec per article. Cleaner, no second task.
```

**Recommendation:** option (a) — keeps semantic_repass simple, same
pattern as byline backfill. ~20 min of code.

---

### 16 · Frontend display of v2 fields   🟡 (BIG surface-area work)

**Why:** v2 extraction now populates a rich corpus that the UI doesn't
surface yet. Everything sits in DB unused:
```
- byline           — show "By [Name]" on article cards
- primary_subject  — one-line description per article
- summaries (3)    — preview/snippet/executive at different card sizes
- register         — colour-code articles by style/emotion/breaking
- locations        — map view, location-filtered timeline
- events           — events timeline per topic
- quotes           — featured-quote pull cards
- claims           — fact-check / dispute UI
- stances          — voice-share charts per entity
- numbers          — auto-extracted statistics
- article_tweets   — embedded tweets within article context
- english_translation — toggle for non-English articles
```

**Effort:** 2-3 weeks. Bundles with #9 (HOME v2 redesign).

**Sequencing:** Don't start until corpus refill finishes and entity
resolution (#3) ships. UI built before entities are resolved will need
re-wiring.

---

### 17 · Daily brief generation should use v2 fields   🟡

**Why:** Current `tasks.generate_all_briefs` writes briefs based on v1
relevance scoring + raw article text. With v2 we now have curated
`summary_executive`, structured `quotes`, `claims`, and `primary_subject`
— all higher signal than re-reading the article body.

**Work:**
```
1. Update brief LLM prompt to consume:
   - articles.summary_executive (instead of full_text_scraped)
   - article_quotes.quote_text (top 3 by speaker prominence)
   - article_claims.claim_text (claims with verifiable=true)
   - articles.byline (for source attribution)
2. Token budget drops ~70% per article (summary is 1K chars vs 8K body).
3. Quality improves — model sees pre-curated highlights, not raw noise.
```

**Effort:** ~half day. Wait until corpus has enough v2-enriched
articles (>50% coverage) to make the brief meaningfully better.

---

### 18 · Body embeddings (LaBSE on full text)   🟡

**Why:** We have title embeddings (`articles.title_embedding`) for
semantic search but no body embeddings. With multilingual LaBSE we
could:
- Find articles similar to a given article (better than tag-based)
- Cross-language clustering (Telugu/English/Hindi articles about same event)
- Power the Analyst RAG pillar's retrieval much better

**Work:**
```
ALTER TABLE articles ADD COLUMN body_embedding vector(768);
-- Backfill: ~75K articles × LaBSE inference. LaBSE is already loaded
-- (used in entity matching). Batch through GPU if available.
```

**Cost:** Compute-only — no LLM API. ~6-8 hours on RTX 4090 if user
sets that up (#1's RTX 4090 thread).

**Effort:** 1 day to wire up + however long the backfill takes.

---

## What's deliberately NOT here

- **Relationship graphs for sentiment.** Rejected — maintenance death-spiral. Use LLM-as-judge instead.
- **DSPy pipeline optimization.** Skip until 200+ labelled examples exist (need real users + weeks of usage first).
- **Self-hosted LLM on GPU.** Not cost-effective at current scale.
- **Multi-state corpus expansion (50 sources/state).** Park until v2 corpus + entity resolution shipped. Tools exist, just don't enable yet.
- **Twitter pillar reactivation.** Park indefinitely — Twitter API is paid + unreliable.
- **NDTV TLS fingerprint workaround.** Real but low priority — NDTV is recoverable via their RSS as fallback for now.
