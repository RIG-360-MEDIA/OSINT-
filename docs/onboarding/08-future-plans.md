# 08 - Future Plans

> **TL;DR.** Six strategic threads on the roadmap. None are in
> flight; they're all "next when the v3 drain stabilises and the
> scraper recovery completes." Listed in approximate value order.
> For tactical day-to-day priorities see
> `09-todos-prioritized.md`.

## 1. Relevance v3 — 3-layer redesign

**Goal.** Stop the empty-feed problem for new users. Every user
should see *something* useful from day one, even with no
watchlist.

**Design.** Three layers combined into a single score:

- **Layer 1.** Current SQL entity match. Cap at ~40% of final
  score.
- **Layer 2.** Semantic embedding similarity. Add
  `articles.summary_embedding vector(768)` (LaBSE). Per-user
  "interest centroid" built from watchlist + recent reading
  history. Score = cosine(article, centroid).
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
-- user_profiles extension for last_centroid + last_centroid_at
```

See `03-relevance-system.md` for the full design.

## 2. Frontend redesign — intelligence publication

**Goal.** Rebuild the frontend from scratch as an
**intelligence-publication-style** app. Not a consumer product —
this is for government, PR, and MNC analysts in India. Inspired by
"Particle" (the AI news aggregator) but oriented around
multi-edition publishing rather than rolling feed.

**Model.** Five editions per day:

- 06:00 — Morning brief.
- 10:00 — Mid-morning update.
- 13:00 — Lunch read.
- 17:00 — Late-afternoon brief.
- 21:00 — Evening wrap.

Each edition is a curated set of stories with summary cards,
quote pull-outs, location maps, and analyst commentary. Users
subscribe to the editions they want.

**Design progress so far.**
- 8 HOME zones locked in a `demo-no-lines-v3.html` mockup
  (location TBD).
- Palette + typographic register + colour roles validated.
- Need to port to React components after extraction backlog
  stabilises.
- Component-by-component build estimated ~2-3 days.
- Mobile responsive pass after desktop.

This is the biggest single-project bet on the roadmap. Don't
start it until the substrate v3 drain is complete and the source
recovery is done.

## 3. Byline extractor — lift coverage 14% → 80%

**Goal.** Today's byline coverage is ~14%. Target is 80%.

**Plan.**
- Enumerate the meta-tag and JSON-LD forms used by the top 100
  sources.
- Add site-specific selectors as fallbacks.
- Extend the blacklist of generic strings ("Staff Reporter",
  "PTI", "ANI", "Web Desk", "News Desk", etc.) — these go to
  `byline_role`, not `byline_name`.
- Backfill existing articles with the improved extractor.

Lives in `backend/tasks/substrate/byline_periodic_task.py` and
`backfill_bylines.py`. Estimated 2-3 days.

## 4. Sources resurrection (~150 dead RSS paths)

**Goal.** Re-enable and URL-fix the ~232 remaining bulk-disabled
sources. Of those, ~150 are likely just URL-path drift (RSS feeds
moved, schemes changed).

**Plan.**
- Run `probe_all_disabled.py` with a more aggressive URL-mutation
  layer: try `/feed`, `/rss.xml`, `/rss/feed`, `https://` swap,
  www-vs-no-www, etc.
- For sources with no RSS, see if the HTML adapter still works.
- For each, commit a per-source migration (NOT manual SQL) so
  the state change is recoverable from git.

Estimated 1-2 days of mostly manual work, parallelisable.

## 5. Monitoring + alerting layer

**Goal.** Make every known-issues failure mode VISIBLE before a
user notices.

**Plan.**
- Lightweight metrics layer (Prometheus-style or just a
  /metrics endpoint scraped by a cron).
- Key metrics:
  - Queue depths per Celery queue.
  - Source-health rollup (count of active sources returning new
    articles in last 24h).
  - Drain process alive + v3 count delta in last hour.
  - FreshRSS auth healthy.
  - Cerebras / Groq quota remaining.
  - LLM call success rate per provider.
- Alert routing — email at minimum; SMS / phone notification
  preferred for P0 failures.
- Auto-restart for Celery workers if they crash (today the
  workers just die silently).
- Boot-time integrity checks: FreshRSS admin user, Tailscale
  to TRIJYA-7, watchdog running.

Estimated 3-5 days. Highest leverage piece on the roadmap from a
"stop fighting fires" perspective.

## 6. v4 prompt iteration (if needed)

**Goal.** Iterate beyond Prompt G if the v3 drain reveals new
quality issues.

**Current v3 stats (post-drain, 2026-05-16).**

| Metric                     | Value     | Target  |
|-----------------------------|-----------|---------|
| Quotes per article (median) | 1.4       | ~2.0    |
| Claims per article (median) | 3.2       | ~3.5    |
| Factual rate (claims)       | 80%       | 90%+    |
| Null-subject claims         | 0%        | 0% ✓    |
| Byline coverage             | 37%       | 80%     |

The 80% factual rate suggests room for a v4 with stronger
claim-anchoring rules. The 1.4 quotes/article is a sign Prompt G
might be too conservative on quote extraction (or that many
articles genuinely have few quotes — needs investigation).

Defer this until #1-#5 are landed.

## Secondary threads (mentioned in docs/future-todo.md)

These are smaller but worth knowing about:

- **Entity resolution.** ~11.6K canonical entities,
  ~14 aliases. Plan = bulk Groq job to generate 3-5 aliases per
  canonical (~$0.20 or 15% of one day's Groq quota), LaBSE
  embeddings on entity names, candidate auto-promotion. 2-3
  days total. Locks down voice-share / watchlist correctness.

- **Watchlist-priority re-pass scheduling.** Watchlist hits get
  priority queueing for substrate extraction. Currently
  first-come-first-served by article ID.

- **Source-tier auto-classification.** `source_tier` is
  currently hand-set. A classifier based on signal quality
  (substrate extraction success rate, byline presence, geo
  specificity, claim density) could auto-tier.

- **Dossier endpoint.** `DOSSIER_ENABLED=false` in compose —
  there's an experimental per-entity dossier endpoint behind a
  feature flag. Includes GDELT integration
  (`DOSSIER_GDELT_TIMEOUT_S=25`). Not currently surfaced in UI.

## Sequencing recommendation

If the operator could only pursue three threads, in order:

1. **Monitoring + alerting (#5).** Highest leverage — every
   other thread becomes safer to run unattended.
2. **Sources resurrection + byline (#3, #4).** Recovers existing
   capability that's been lost.
3. **Relevance v3 (#1).** Unblocks new-user UX. Required
   before the publication frontend (#2) is meaningful.

Frontend redesign (#2) is largest and should wait until all of
the above are stable.

## See also

- `09-todos-prioritized.md` — these threads broken into
  concrete priority order with effort estimates.
- `03-relevance-system.md` — v3 design in depth.
- `docs/future-todo.md` — the canonical roadmap doc.
