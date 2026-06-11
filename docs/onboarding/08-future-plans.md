# 08 - Future Plans

> **TL;DR.** Eight strategic threads on the roadmap. Listed in
> approximate value order. For tactical day-to-day priorities see
> `09-todos-prioritized.md`. Updated 2026-05-28 with post-D1 reality.

---

## 1. Phase 1 source expansion (+100 global flagships)

**Goal.** Today's source pool is 81% India (659 of 793 sources).
Zero explicit US, RU, JP, FR, DE, BR, MX, IR, SA, AE national sources.
Phase 1 adds top 5 flagships × 20 priority countries — gives proper
global intelligence coverage.

**Plan.**
- Write `scripts/migrations/076_phase1_sources_insert.sql` with 100
  curated rows. Source list candidates: `docs/PHASE1_20_COUNTRIES.md`
- Schema is ready — migration 075 added `sources.country` (ISO 3166
  alpha-2) and `articles.source_country` propagates via trigger
- Test scrapability of each before enabling (HTML structure
  detection, RSS endpoint verification)
- Initial `health_score=0.3` (just above auto-disable threshold of
  0.1). Sources prove themselves over 7 days
- Monitor Day 1 article volume — expect +500-1000/day, well within
  Ollama capacity (~24K calls/day)

**Effort.** 1 day (curation + scrapability check + monitoring).

**Why this matters.** Without it our pool is fundamentally an Indian
intelligence platform. With it, it becomes a global one.

---

## 2. Relevance v3 — 3-layer redesign

**Goal.** Stop the empty-feed problem for new users. Every user
should see *something* useful from day one, even with no watchlist.

**Design.** Three layers combined into a single score:
- **Layer 1.** Current SQL entity match. Cap at ~40% of final score.
- **Layer 2.** Semantic embedding similarity. Add
  `articles.summary_embedding vector(768)` (LaBSE). Per-user
  "interest centroid" built from watchlist + recent reading history.
  Score = cosine(article, centroid).
- **Layer 3.** Behaviour learning. New `user_article_engagement`
  table logs every view/click/expand/dismiss/save/share. Small
  per-user reranker learns weights.

**Order.** Embedding job first (standalone A/B vs Layer 1). Then
engagement logging from the frontend. Then the reranker.

**Tables to add.**
```sql
ALTER TABLE articles ADD COLUMN summary_embedding vector(768);
CREATE TABLE user_article_engagement (
  id           bigserial PRIMARY KEY,
  user_id      uuid NOT NULL,
  article_id   uuid NOT NULL,
  event_type   text NOT NULL,
  occurred_at  timestamptz NOT NULL DEFAULT now()
);
```

See `03-relevance-system.md` for the full design.

---

## 3. Monitoring + alerting layer

**Goal.** Make every known-issues failure mode VISIBLE before a user
notices. Today every issue is "invisible until manually checked".

**Plan.**
- Lightweight metrics layer (Prometheus-style or `/metrics` endpoint
  scraped by cron)
- Key metrics:
  - Queue depths per Celery queue
  - Source-health rollup (count of active sources returning new
    articles in last 24h)
  - Drain process alive + v3 count delta in last hour
  - FreshRSS auth healthy
  - Cerebras / Groq quota remaining (rolling 24h TPD tracking)
  - LLM call success rate per provider
- Alert routing — email at minimum to `heretech.shodh1@gmail.com`;
  SMS/phone preferred for P0 failures
- Auto-restart for Celery workers if they crash (today they die
  silently)
- Boot-time integrity checks: FreshRSS admin user, Tailscale to
  Trijya, watchdog running, D1 cron script present

**Effort.** 3-5 days. **Highest leverage piece on the roadmap** from
a "stop fighting fires" perspective.

---

## 4. Narrative pipeline (Stage 0-6) wiring

**Goal.** Migration 070 created `narrative_clusters`,
`narrative_cluster_members`, `narrative_drafts` tables. Code at
`backend/tasks/narrative/` Stage 0-6 is scaffolded. Nothing runs.
Wire it up.

**Plan.**
1. Stage 0 (cluster assembly) — beat-scheduled nightly. Groups
   recent articles by LaBSE embedding similarity + temporal
   proximity into `narrative_clusters` rows.
2. Stage 2A (triangulation) — runs after Stage 0. Validates clusters
   have 3+ independent sources.
3. Stage 2B (interrogation) — pulls representative articles per
   cluster.
4. Stage 3-6 (lede / body / critic / revision) — LLM-driven draft
   generation; writes `narrative_drafts` rows.
5. Frontend brief page reads `narrative_drafts` for the daily digest.

**Effort.** 2 weeks for first end-to-end run.

**Blocks:** Requires LaBSE claim/summary embeddings to be working
(P1 todo to fix — currently 0.96% of claims have embeddings).

---

## 5. Frontend redesign — intelligence publication

**Goal.** Rebuild the frontend from scratch as an
**intelligence-publication-style** app. Not a consumer product —
this is for government, PR, and MNC analysts in India. Inspired by
"Particle" (the AI news aggregator) but oriented around
multi-edition publishing rather than rolling feed.

**Model.** Five editions per day:
- 06:00 — Morning brief
- 10:00 — Mid-morning update
- 13:00 — Lunch read
- 17:00 — Late-afternoon brief
- 21:00 — Evening wrap

Each edition is a curated set of stories with summary cards, quote
pull-outs, location maps, and analyst commentary. Users subscribe to
the editions they want.

**Design progress so far.**
- 8 HOME zones locked in a `demo-no-lines-v3.html` mockup
- Palette + typographic register + colour roles validated
- Need to port to React components
- Component-by-component build estimated ~2-3 days
- Mobile responsive pass after desktop

**This is the biggest single-project bet on the roadmap.** Don't
start it until the current D1 drain is complete and Phase 1 source
expansion has 7+ days of healthy data.

**Frontend dev DOES NOT require active scrapers.** ~30K substrate-
processed articles already in DB; brief page can render against
existing data while scrapers are paused. (See discussion in session
2026-05-28.)

---

## 6. TPD-aware drain back-pressure controller

**Goal.** Stop blowing Cerebras free-tier daily budget in 5 hours.

**Today.** Drain throughput controller knows per-minute rate limits
(RPM/TPM) but has no concept of the per-day token budget. Watchdog
flips to LOCAL_ONLY at <5% remaining, but by then 95% of cloud
capacity is wasted on the early-day burst.

**Plan.** Track rolling 24h token consumption per provider per key.
Throttle the drain so consumption tracks daily-budget pace (50%
through day → ~50% through budget, not 99%). Pre-emptive flip to
LOCAL_ONLY at 70% burn instead of 95%.

**Effort.** 1-2 days.

---

## 7. Sources resurrection (~150 dead RSS paths)

**Goal.** Re-enable and URL-fix the ~232 remaining bulk-disabled
sources from the 2026-04-25 cascade. Of those, ~150 are likely just
URL-path drift (RSS feeds moved, schemes changed).

**Plan.**
- Run `probe_all_disabled.py` with aggressive URL-mutation layer:
  try `/feed`, `/rss.xml`, `/rss/feed`, `https://` swap, www-vs-no-www
- For sources with no RSS, check if HTML adapter still works
- For each, commit a per-source migration (NOT manual SQL) so the
  state change is recoverable from git

**Effort.** 1-2 days mostly manual, parallelisable.

---

## 8. v4 prompt iteration (if needed)

**Current v3 stats (post-D1 fix, last 6h of 2026-05-28).**

| Metric | Value | Target |
|---|---|---|
| Summary preview / snippet / executive | **100%** | 100% ✓ |
| Primary subject | **100%** | 100% ✓ |
| Article type | **100%** | 100% ✓ |
| SPO triple completeness (claims) | **99%** | 99% ✓ |
| Author name | **100%** (was 14% pre-D28) | 95% ✓ |
| Locations populated | **99%** | 95% ✓ |
| Events populated | 96% | 95% ✓ |
| Numbers populated | 74% | 80% |
| Quotes populated | 59% | (article-dependent) |
| Article-type classified as "other" | 28% | <15% (refine prompt) |
| Failure rate | 0.28% | <1% ✓ |

**Open quality issues that v4 could address:**
- 28% "other" article-type is too high — classifier needs more
  sub-types or stricter "news" fallback
- Entity linking weak (~35% of child rows have linked entity_id)
- Claim embeddings missing (P1 to backfill)

Defer prompt iteration until current drain stabilises and these
targeted fixes (D8 publish_at anchor, entity-linking pass) ship.

---

## Secondary threads (mentioned in docs/future-todo.md)

These are smaller but worth knowing about:

- **Entity resolution Phase B.** 15,755 canonical entities currently
  with ~98% having aliases. Phase B = LaBSE embeddings on canonical
  names → semantic match. Phase C = bulk resolution pass over
  existing actor strings. Phase D = candidate auto-promotion table.

- **Watchlist-priority re-pass scheduling.** Watchlist hits get
  priority queueing for substrate extraction. Currently
  first-come-first-served by article ID.

- **Source-tier auto-classification.** `source_tier` is hand-set. A
  classifier based on signal quality (substrate success rate, byline
  presence, geo specificity, claim density) could auto-tier.

- **Dossier endpoint.** `DOSSIER_ENABLED=false` in compose —
  experimental per-entity dossier endpoint behind a feature flag.
  Includes GDELT integration (`DOSSIER_GDELT_TIMEOUT_S=25`). Not
  surfaced in UI.

- **Whisper audio transcription.** `whisper` queue exists, no
  consumer. Reserved for podcast / video transcription.

- **vLLM via WSL2 on Trijya.** Only practical Windows option for
  vLLM. Complex setup. Probably never worth it unless we need
  genuine 100+ calls/min sustained, which a single 4090 can't deliver
  for qwen3:14b anyway.

---

## Sequencing recommendation

If the operator could only pursue four threads, in order:

1. **Phase 1 source expansion (#1).** Unblocks global coverage. 1
   day. Schema already ready.
2. **Monitoring + alerting (#3).** Highest leverage — every other
   thread becomes safer to run unattended. 3-5 days.
3. **Relevance v3 (#2).** Unblocks new-user UX. Required before the
   publication frontend (#5) is meaningful.
4. **Narrative pipeline (#4).** Unblocks the brief-page editorial
   loop. Required for the frontend redesign to have content to
   render.

Frontend redesign (#5) is largest and should wait until 1-4 are
stable.

---

## See also

- `09-todos-prioritized.md` — these threads broken into concrete
  priority order with effort estimates
- `03-relevance-system.md` — v3 design in depth
- `02-substrate-pipeline.md` — D1 SPO fix + child tables
- `11-session-2026-05-28-learnings.md` — full session log with all
  context behind why these threads exist
- `docs/PHASE1_20_COUNTRIES.md` — Phase 1 source list candidates
- `docs/BEST_SOURCES_GLOBAL.md` — full Excel dataset analysis
