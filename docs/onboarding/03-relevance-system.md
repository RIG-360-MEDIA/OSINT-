# 03 - Relevance System

> **TL;DR.** Today, each user gets a per-article score in
> `user_article_relevance`, computed by a simple entity-match algorithm
> (does the article mention an entity on this user's watchlist?). It
> works but is brittle for new users with empty watchlists. A v3
> redesign is on the books: a 3-layer scorer combining SQL match,
> semantic embedding similarity, and behaviour learning. The v3 is
> **designed but not implemented**. Layer 2 is BLOCKED by a missing
> piece: claim/summary embeddings have fallen out of the pipeline
> (0.96% of recent claims have embedding != NULL — P1 to fix).

---

## How it works today

### Tables involved

- `user_watched_entities` (migration 068) — per-user watchlist:
  user_id → entity_id (FK to `entity_dictionary`).
- `user_article_relevance` — the score table. One row per
  (user_id, article_id). Includes `score`, `matched_entities[]`,
  `scored_at`.
- `articles` (the source row) — now with `source_country` available
  for country-aware weighting (migration 075, 2026-05-28).
- `entity_dictionary` + `entity_aliases` — canonical entity
  vocabulary. **15,755 canonical entities** as of 2026-05-28. 98%
  have at least one alias (migration 073 normalized entity_type
  spellings).

### The flow

1. Beat fires `tasks.score_unscored_articles` periodically (every
   ~5 min). The task pulls articles without a relevance row for a
   given user batch.
2. For each (article, user) pair, the scorer:
   - Pulls the article's actors, locations, entities from substrate
     output.
   - Joins against the user's watchlist.
   - Computes a simple weighted match score (count + entity
     importance + recency boost).
   - Inserts a row in `user_article_relevance`.
3. Beat fires `tasks.generate_brief_for_user` daily at 00:30. The
   brief task pulls the top-N relevance rows for that user and
   formats them.

### Pre-built worker tasks

All routed to the `relevance` queue (concurrency=4):

| Task | When fires | What it does |
|---|---|---|
| `tasks.score_relevance_batch` | On demand | Score a specific batch of articles for all users. |
| `tasks.score_unscored_articles` | Beat every 5 min | Find articles without a relevance row and score them. |
| `tasks.backfill_user_relevance` | On new user signup | Backfill last N days of articles for a user that just joined. |
| `tasks.score_govt_doc_relevance` | On new doc insert | Same idea but for `govt_documents`. |
| `tasks.score_govt_doc_for_all_users` | Beat daily | Backfill loop. |
| `tasks.generate_all_briefs` | Beat 00:30 | Driver that fan-outs to `generate_brief_for_user` per user. |
| `tasks.generate_brief_for_user` | On demand / from above | Daily brief generation. |
| `tasks.score_brief_quality` | After brief generated | Heuristic quality scorer (migration 036). |

### The new-user empty-feed problem

The current SQL-match-only scorer requires entries in
`user_watched_entities` to produce any score above zero. A user who
signs up with an empty watchlist sees an empty `/coverage` feed and
an empty brief. This is the headline UX problem driving the v3
redesign.

Workaround today: the super-admin bootstrap seeds the super_admin
user(s) (currently `pranavsinghpuri09@gmail.com`) with a default
watchlist that covers the most-monitored entities in the org.
Regular users have to build their watchlist before they see anything
useful.

---

## Relevance v3 — the design (not built yet)

The plan is a **3-layer scorer** that always returns *something*
even for a new user:

### Layer 1 — SQL entity match (today)

Keep the current weighted entity match. Cheap, deterministic,
well-understood. Cap its contribution at ~40% of the final score.

### Layer 2 — Semantic embedding similarity

- **`articles.labse_embedding`** already exists (vector 768) — **93%
  populated** for processed articles. Used historically by claim
  similarity but not yet by relevance.
- New: `articles.summary_embedding vector(768)` for summary-text
  similarity (separate from labse_embedding which is full-body).
- Compute embeddings nightly for new articles.
- Build a per-user "interest centroid" from their explicit watchlist
  + their recent reading history. Centroid = LaBSE average over
  watched entity names + recently-engaged article summaries.
- Score = cosine(article_embedding, user_centroid).
- This gives every user *some* score for every article, regardless
  of watchlist depth.

**🚨 BLOCKER:** As of 2026-05-28, **only 0.96% of recent claims have
`embedding != NULL`** (225 of 23,391 sampled). The LaBSE pipeline
step has fallen out. Before Layer 2 can ship, this needs to be
restored AND backfilled. See `07-known-issues.md` O5 and
`09-todos-prioritized.md` P1.4.

### Layer 3 — Behaviour learning

- New table `user_article_engagement` — logs every (user_id,
  article_id, event_type, timestamp) where event_type ∈ {view,
  click, expand, dismiss, save, share}.
- A small reranker model learns per-user weights from this signal:
  which topics, which sources, which times of day get engaged with.
- Blends with layers 1+2 to produce the final score.

### Tables to add

```sql
ALTER TABLE articles ADD COLUMN summary_embedding vector(768);

CREATE TABLE user_article_engagement (
  id           bigserial PRIMARY KEY,
  user_id      uuid NOT NULL,
  article_id   uuid NOT NULL,
  event_type   text NOT NULL,
  occurred_at  timestamptz NOT NULL DEFAULT now()
);

-- Extend user_profiles with interest centroid + last_centroid_at.
```

### Order of implementation

1. **Fix the LaBSE embedding backfill first** (P1.4 blocker). Until
   claim/summary embeddings are populated, neither narrative
   clustering nor relevance v3 Layer 2 can work.
2. Migration + nightly embedding job → Layer 2 standalone, A/B vs
   Layer 1.
3. Engagement logging from frontend → start collecting data.
4. Per-user reranker → once there's enough engagement data.

A standalone design doc at `docs/relevance-v3-plan.md` may exist or
will be created when v3 starts.

---

## Possible future weighting: source-country awareness

With migration 075 (2026-05-28) every article now has
`source_country` (ISO 3166 alpha-2). A future scorer enhancement
could weight by user-stated geographic interests:

- User watching India + UK content → boost articles with
  `source_country IN ('IN', 'GB', 'XX')`
- User watching China-specific intelligence → boost
  `source_country = 'CN'` (currently only 9 sources, all defense)

Not yet implemented. Trivial SQL addition once user_profiles has a
`country_focus[]` column.

---

## Brief generation

Daily brief generation lives in `backend/tasks/brief_task.py` and
runs on the `brief` queue (shared process with `relevance`). Quality
scoring lives in `brief_quality_task.py` (migration 036).

The brief structure has been redesigned multiple times during the QA
pass (see `docs/qa/brief-redesign-mockup.md`,
`docs/qa/brief-monitoring-mode-mockup.md`,
`docs/qa/brief-remediation-plan.md`). The current production brief
is on the `fix/brief-prod-readiness` branch — that's the canonical
branch state.

**Frontend dev for the brief page does NOT require active scrapers.**
~119K articles already in DB with full substrate v3 output (post-D1
fix delivers 99% SPO completeness, 100% summaries). Can build/test UI
against existing data while scrapers are paused for the current
drain.

---

## Analyst pillar — synchronous RAG

The `/analyst` page is *not* relevance-scored in the same way. It's
a synchronous FastAPI endpoint that does RAG over the corpus per
query. Lives in `backend/routers/analyst_router.py` (or similar —
check `backend/routers/`). QA trail in `docs/qa/analyst-*.md`.

---

## See also

- `02-substrate-pipeline.md` — the substrate output that the
  relevance scorer joins against. Note D1 SPO fix means
  `article_claims` now has reliable subject/predicate/object — could
  be used by future scorers.
- `08-future-plans.md` — the relevance v3 redesign in the strategic
  roadmap context.
- `09-todos-prioritized.md` — v3 is listed at P2, but P1.4 (LaBSE
  backfill) blocks it.
- `07-known-issues.md` O5 — the claim-embeddings-missing root cause.
- `11-session-2026-05-28-learnings.md` — context for why we know
  embeddings are missing (DB audit done today).
