# Signals — Quality Scorecard

**Probed:** 2026-04-27. Companion to
[signals-live-session.md](signals-live-session.md) and
[signals-per-source-verdict.md](signals-per-source-verdict.md).

This scorecard answers: **does the page show the right signals to the
right user?** It's separate from per-platform liveness (which is in
the verdict doc).

## Scoring summary

| Dimension | Score | Notes |
|---|---|---|
| Freshness | **0 / 5** | Reddit 6 d, Telegram 4 d, Twitter 0 rows. SIG-11. |
| Coverage breadth | 2 / 5 | 14 monitors total (4 R / 7 T / 3 X). Decent for a single user; no dynamic monitor add UX. |
| Coverage depth (window) | 2 / 5 | Hardcoded `days=7` on backend ([signals_router.py](../../backend/routers/signals_router.py)); no UI override. |
| Entity-relevance to user | **0 / 5** | 0 / 207 posts have non-empty `matched_entities`. SIG-10. |
| Sentiment accuracy (en) | 3 / 5 | VADER reasonable on opinion text; misses factual-negative ("court orders removal"). |
| Sentiment accuracy (non-en) | **1 / 5** | Telugu coerced to `en` → sentiment 0. SIG-13. |
| Privacy / multi-user safety | 2 / 5 | Cross-user entity bleed (SIG-14). Auth gating itself is fine. |
| Latency `posted_at → collected_at` | n/a | Cannot compute; both timestamps for the same Reddit batch share the same minute. |
| UI freshness indicator | **0 / 5** | None. User cannot tell data is stale. |
| Error visibility | 1 / 5 | Generic `"feed ${status}"` text; no retry; 401 swallowed (SIG-2/3). |

**Aggregate: 11 / 50** — page is *technically functional* but
*operationally degraded* and *qualitatively blind*.

## Entity-match audit (sample of 20)

A targeted spot-check (matched against the user's 30 entities, e.g.
`KTR`, `BRS`, `Telangana`, `Revanth Reddy`, `KCR`, …):

| Post (excerpt) | Should match | Actual `matched_entities` |
|---|---|---|
| "BRS Party Official: Aam Aadmi Party..." | `BRS` | `{}` ❌ |
| "Telangana CMO Official: …" | `Telangana` | `{}` ❌ |
| "v6newstelugu: KTR speech in Hyderabad" | `KTR`, `Hyderabad` | `{}` ❌ |
| "Scroll.in: Delhi HC orders…" | (no user entity) | `{}` ✓ vacuously |
| (17 more telegram rows, similar Telangana / BRS / KTR mentions) | many | all `{}` |

20 / 20 rows show empty `matched_entities`. Confirmed root cause is
SIG-10 (write-time matching against a query that ran when
`user_entities` was empty for this user, plus the global-pool design
issue).

## Sentiment spot-check (n=30 English Telegram posts)

Rough manual labelling — agreement rate with VADER buckets at ±0.15:

| VADER bucket | Manual label | Count |
|---|---|---|
| positive | positive ✓ | 11 |
| positive | neutral ✗ | 2 |
| neutral  | neutral ✓ | 4 |
| neutral  | negative ✗ (bureaucratic-negative miss) | 5 |
| neutral  | positive ✗ | 2 |
| negative | negative ✓ | 4 |
| negative | neutral ✗ | 2 |

Agreement: **19 / 30 ≈ 63 %**. Specifically weak on
factual-negative news framing (e.g. "Court orders removal of videos"
scored 0.0). For a sentiment-led UX this is borderline; for *trend*
signals across many posts it's serviceable.

## Window blind-spot

Backend hardcodes `days=7` ([signals_router.py:42-44](../../backend/routers/signals_router.py)).
Frontend exposes no override. Posts older than 7 days are invisible
to the user even if they're in the table. Today this doesn't matter
(everything is <7 d), but as the corpus grows, historical analysis
will require a window-selector or full-text search.

## Coverage breadth

14 monitors is thin for a regional intelligence brief. Suggested
additions (out-of-scope for this pass; for product backlog):
- Reddit: `r/IndiaSpeaks`, `r/IndianNews`, `r/Andhrapradesh`
- Telegram: more state-CMO and ministry channels
- Twitter: ANI, PIB India, government spokespeople, opposition handles

There is no in-product UX to add monitors — they are inserted via SQL
seed migration. That's a **product gap**, not a defect.

## What the page *misses* (gap analysis)

1. **No "as-of" / freshness indicator** — users can't tell what they
   see is from 4 days ago.
2. **No filter by entity** — a user with 30 tracked entities can't
   pick one and filter the feed.
3. **No date range picker** — stuck on 7 days.
4. **No search** — can't query free-text inside posts.
5. **No notion of "new since last visit"** — every load is the same.
6. **No export / save** — can't bookmark a post for later.
7. **No drill-down per monitor** — sentiment ledger lists monitors
   but they aren't clickable to filter the feed.
8. **Forwarded-from chain not surfaced** — `forwarded_from` is in the
   schema but [PostCard](../../frontend/src/app/signals/page.tsx) doesn't
   render it.
9. **No engagement-based sort** — only chronological; can't bubble
   "top of last 24 h" by upvotes.
10. **No language label on cards** — multilingual posts not flagged.

These are product feature gaps, not regressions; logged here for the
backlog rather than the defects register.

## What the page *does* well

- Clean visual identity (newsroom metaphor, dateline, deskmemo).
- Tab labels are evocative (The Wire / The Forums / The Channels).
- Sentiment ledger is informative when populated.
- External links carry `rel="noopener noreferrer"`.
- Auth redirect to `/login` is correct.
- Pagination works (cursor-based, no off-by-ones found).
- Schema is well-indexed for the existing query shapes.

## Required for ≥ 30 / 50 quality score

1. SIG-11 (freshness) — biggest single lever.
2. SIG-10 + SIG-14 (entity relevance + multi-user safety).
3. SIG-13 (non-English sentiment).
4. New product UX: freshness indicator on header.
5. New product UX: entity filter + date-range picker.

Everything else is incremental.
