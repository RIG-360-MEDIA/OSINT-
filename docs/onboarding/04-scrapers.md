# 04 - Scrapers / Ingestion

> **TL;DR.** Ingestion is a 4-tier fetch cascade: FreshRSS → Direct
> RSS → HTML → Playwright. Trafilatura does the body extraction
> (~93% precision). 53 per-source Python adapters live in
> `backend/collectors/sources/`. Sources have a `source_tier` column
> (1/2/3) and a health-scoring system that auto-disables after 10
> consecutive failures. **~30-50% of currently-disabled sources are
> actually alive** — they were bulk-disabled by uncommitted manual
> SQL on 2026-04-25. 174 of 406 have been re-enabled after live
> probe; ~232 remain.

## The 4-tier fetch cascade

Implemented in `backend/collectors/tiered_fetcher.py`. Each tier is
tried in order; first success wins.

| Tier | Mechanism                                               | When used                                                                                |
|------|---------------------------------------------------------|------------------------------------------------------------------------------------------|
| 1    | **FreshRSS** (GReader API at `http://rig-freshrss:80`) | Default for any source with `source_type='rss'`. Cheap, batched, low-IP-burn.            |
| 2    | **Direct RSS** (httpx GET on the feed URL)              | Fallback when FreshRSS doesn't have the feed subscribed or returns empty.                |
| 3    | **HTML** (httpx + Trafilatura + per-source adapter)     | For `source_type='html'`, or as fallback when RSS is unavailable.                        |
| 4    | **Playwright** (full Chromium render)                   | Last resort. Used when the source has anti-bot detection that rejects httpx UAs (common for data-centre IPs hitting Indian govt portals). Slow + expensive. |

The cascade is *not* uniform across collectors. The four entry-point
files are:

- `rss_collector.py` — beat-driven FreshRSS sync (15-min cadence).
- `direct_rss_collector.py` — tier-2 fallback (30-min cadence).
- `html_collector.py` — tier-3 HTML scraping (6-hour cadence).
- `playwright_helper.py` — tier-4 helper, called from individual
  source adapters when their tier-3 path fails.

Plus specialised collectors:
- `govt_collector.py` — government PDF collection.
- `newspaper_collector.py` — newspaper-edition PDFs.
- `youtube_collector.py` — transcripts.
- `social_collector.py` — Reddit / Twitter / Telegram dispatch.
- `telegram_user_collector.py` — Telegram user-channel sweep.

## Trafilatura

The key body-extraction library. Used inside the HTML collector and
inside per-source adapters that need to clean tag soup down to body
text. Empirical precision on Indian news sources is ~93% — better
than `newspaper3k` or `readability-lxml` on the same sample. Don't
swap it out without an A/B.

## Source registry

The 53 source adapters live in `backend/collectors/sources/*.py`,
each decorated with `@register_source`. Adapter responsibilities:

- Define which URL patterns the adapter handles.
- Implement a tier-3 (HTML) fetcher.
- Optionally implement a tier-4 (Playwright) fetcher.
- Return canonicalised `Article` dicts ready for DB insertion.

Subdomains of `backend/collectors/sources/` cover (non-exhaustive):
- `central_regulators.py` — SEBI, RBI, NSE, BSE, etc.
- `commonwealth_*.py` — Commonwealth Games-era sources (seeded
  by migration 037).
- per-state govt portals.
- per-publication adapters for tricky news sites.

A full per-source verdict matrix lives in
`docs/qa/sources-per-source-verdict.md`. Reasons for breakage are
in `docs/qa/sources-why-broken.md`.

## Source tiers

`sources.source_tier` is an integer 1/2/3.

| Tier | Meaning                                                                              |
|------|--------------------------------------------------------------------------------------|
| 1    | High-trust, high-quality (e.g. PIB, Reuters India, top wire services).               |
| 2    | Standard. Most sources.                                                              |
| 3    | Aggregators, low-quality, or experimental.                                           |

Tier influences:
- Frequency of recheck.
- Relevance-score weighting.
- Whether briefs are allowed to lead with the source.
- Auto-disable thresholds (tier 1 is slower to disable than tier 3).

## Health scoring + auto-disable

Each source row has `failure_count` and `last_failure_at`. On
successful fetch, `failure_count = 0`. On failure, increment by 1.
At `failure_count >= 10`, the source is auto-disabled
(`is_active=false`).

This is intended as a soft circuit-breaker but combined with the
bulk-disable incident (below) it's a foot-gun: once a source is
disabled it never recovers without manual intervention.

## The big bulk-disable gotcha

On **2026-04-25**, a debug session ran manual SQL against the
production DB that bulk-flipped `is_active=false` on ~406 sources.
The query was **not committed** to a migration file and is not
recoverable from git. Of those 406:

- **174 have been re-enabled** by the May 2026 sweep (probed live
  with `probe_all_disabled.py` at repo root; the ones that returned
  HTTP 200 with parseable content got `is_active=true`).
- **~232 remain disabled** pending investigation. Some of those are
  genuinely dead (404, dead domain, deprecated RSS path), but a
  significant fraction are alive — they just need URL-path fixes
  (RSS feeds moved from `/rss` to `/feed`, or schemes changed from
  `http` to `https`).

**Implication.** If you're inferring "the codebase doesn't support
source X" because source X is disabled, **verify the source row
state first** — there's a real chance it's a victim of the bulk
disable, not an unsupported source.

## Byline extractor

In `backend/tasks/substrate/byline_periodic_task.py` and
`backfill_bylines.py`. Pulls `<meta name="author">`,
`<meta property="article:author">`, JSON-LD `author.name`, and a
few site-specific selectors. Has a blacklist of generic strings
("Staff Reporter", "PTI", "ANI", "Web Desk") that get demoted to
the `byline_role` column instead of `byline_name`.

Current coverage: **~14%**. P1 todo: lift to 80% by handling more
meta-tag forms and adding more site-specific selectors. Most of the
gap is site-specific HTML that Trafilatura's generic byline detector
misses.

## og:image / thumbnails

`tasks.fetch_og_images_batch` runs every 10 minutes on the
`collectors` queue. Uses Playwright (not httpx) because most Indian
news sites reject data-centre-IP httpx requests for `/og:image`
endpoints but accept a real browser. One Playwright instance per
batch, processes up to 30 articles, closes — see
`backend/tasks/thumbnail_task.py`.

## YouTube ingestion

Lives on its own `youtube` queue (concurrency=1, intentionally) and
uses `_youtube_throttle` to keep request cadence under YouTube's
IP-reputation threshold.

> **Foot-gun (logged in memory).** Never call yt-dlp or
> transcript-api raw from a debug shell on Hetzner. Always route
> through `_youtube_throttle`. CLI probes burnt the IP reputation on
> 2026-05-09 and recovery took ~24-72 hours.

## FreshRSS state

FreshRSS state lives in a single mounted directory inside the
`rig-freshrss` container:
`/config/www/freshrss/data/users/admin/`. The admin user
*directory* was wiped on **2026-05-15** by an unidentified cause.
With no admin user, the GReader API auth returns 403 on every
request, and the 574-feed subscription list is unreachable. Recovery
involved:

1. Recreate `admin` via the FreshRSS CLI inside the container.
2. `chown abc:users` on the user directory.
3. Restore `/config/www/freshrss/data/config.php` from the default
   template, with `api_enabled => true`.
4. **Resubscribe all 574 feeds** via the GReader
   `subscription/quickadd` API.

There's currently no boot-time integrity check. A missing admin
user looks identical to "no new RSS today." This is logged as a
known issue (see `07-known-issues.md` #1) and a P2 monitoring todo.

## Where to look in code

- `backend/collectors/tiered_fetcher.py` — the 4-tier driver.
- `backend/collectors/sources/__init__.py` — `@register_source`
  mechanism.
- `backend/collectors/sources/<source>.py` — per-adapter logic.
- `backend/collectors/rss_collector.py` (and `direct_rss_collector.py`,
  `html_collector.py`) — the periodic-task entry points.
- `backend/tasks/collector_tasks.py` — Celery task definitions.

## See also

- `06-operations-runbook.md` — "How to check FreshRSS health" and
  "How to test scraping end-to-end".
- `07-known-issues.md` — scrapers silently failing, FreshRSS auth.
- `09-todos-prioritized.md` — P1 "resurrect remaining ~100 disabled
  sources" and "byline extractor patch".
