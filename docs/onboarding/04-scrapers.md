# 04 - Scrapers / Ingestion

> **TL;DR.** Ingestion is a 4-tier fetch cascade: FreshRSS → Direct
> RSS → HTML → (Playwright **DISABLED** since 2026-05-27). Trafilatura
> does body extraction (~93% precision). 53 per-source Python adapters
> live in `backend/collectors/sources/`. Sources have `source_tier`
> (1/2/3) and a health-scoring system that auto-disables after **25**
> consecutive failures (was 10 pre-D33). **793 sources total, 550
> active, country-coded via migration 075** — 81% India, 7% global
> wires, 12% rest of world. Phase 1 expansion (+100 priority-country
> flagships) queued in P1 backlog.

---

## The 4-tier fetch cascade (current state)

Implemented in `backend/collectors/tiered_fetcher.py`. Each tier is
tried in order; first success wins.

| Tier | Mechanism | When used | Status today |
|---|---|---|---|
| 1 | **FreshRSS** (GReader API at `http://rig-freshrss:80`) | Default for `source_type='rss'`. Cheap, batched. | ✅ Active |
| 2 | **Direct RSS** (httpx GET on feed URL) with **rotating browser UAs** | Fallback when FreshRSS doesn't have feed subscribed or returns empty. | ✅ Active, D34 rotation added |
| 3 | **HTML** (httpx + Trafilatura + per-source adapter) with **rotating UAs** | For `source_type='html'`, or as fallback. | ✅ Active |
| 4 | **Playwright** (full Chromium render) | Last resort for anti-bot sites. | ❌ **DISABLED via `PLAYWRIGHT_ENABLED=false`** (D39, 2026-05-27) — memory leak: Crawl4AI Chromium accumulated 5+ GB over 8h. Three guard checks in `playwright_helper.py` block re-enablement until fixed. |

Beat cadences (collectors queue):
- `rss_collector.py` — beat-driven FreshRSS sync, **15-min cadence**.
- `direct_rss_collector.py` — tier-2 fallback, **30-min cadence**.
- `html_collector.py` — tier-3 HTML scraping, **6-hour cadence**.
- `playwright_helper.py` — disabled module, returns immediately on
  call.

Specialised collectors (route to different queues):
- `govt_collector.py` — government PDF collection (`documents` queue,
  concurrency=2, prefetch=1)
- `newspaper_collector.py` — newspaper-edition PDFs (`documents`
  queue — moved off `collectors` because 30-60min PDF processing was
  blocking RSS)
- `youtube_collector.py` — transcripts (`youtube` queue, concurrency=1)
- `social_collector.py` — Reddit / Twitter / Telegram (`social`
  queue, concurrency=2)
- `telegram_user_collector.py` — Telegram user-channel sweep

---

## Browser UA rotation (D34, 2026-05-27)

`_browser_headers()` in both `rss_collector.py` and
`direct_rss_collector.py` returns a random UA from a 6-tuple
(`_BROWSER_UAS`). Rotates per-request to avoid IP fingerprinting that
pegs us as a data-centre crawler.

Spans Chrome 119/120/121 on Windows + macOS + Android plus Firefox
desktop. Mirror the same rotation logic anywhere new outbound HTTP
goes.

---

## Trafilatura

Body-extraction library used inside the HTML collector and inside
per-source adapters. Empirical precision on Indian news sources is
~93% — better than `newspaper3k` or `readability-lxml` on the same
sample. Don't swap without an A/B.

---

## Source registry (793 sources, 550 active)

### Country distribution (per migration 075, 2026-05-28)

| Country | Sources | Active | % of pool |
|---|---|---|---|
| 🇮🇳 IN India | 659 | 432 | 83% |
| ⚪ XX global wires | 83 | 72 | 10% |
| 🇬🇧 GB UK | 19 | 18 | 2% |
| 🇨🇳 CN China | 9 | 7 | 1% (all defense feeds — Xinhua Military, PLA Daily, etc.) |
| 🇬🇭 GH, 🇳🇬 NG | 4 each | 4 | regional production high |
| 🇦🇺 AU, 🇲🇾 MY | 3 each | 3 | |
| 🇱🇰 LK, 🇵🇰 PK, 🇿🇦 ZA, 🇰🇪 KE, 🇧🇩 BD | 1-2 each | varies | |

**Gap:** Zero explicit national sources for USA, RU, JP, FR, DE, BR,
MX, IR, SA, AE. Phase 1 expansion (P1 backlog) adds 100 priority-
country flagships.

### Source adapter files

The 53 source adapters live in `backend/collectors/sources/*.py`,
each decorated with `@register_source`. Adapter responsibilities:
- Define URL patterns the adapter handles
- Implement tier-3 (HTML) fetcher
- Optionally implement tier-4 (Playwright) fetcher
- Return canonicalised `Article` dicts ready for DB insertion

Subdomains of `backend/collectors/sources/`:
- `central_regulators.py` — SEBI, RBI, NSE, BSE, etc.
- Per-state govt portals
- Per-publication adapters for tricky news sites

Per-source verdict matrix: `docs/qa/sources-per-source-verdict.md`.
Reasons for breakage: `docs/qa/sources-why-broken.md`.

### sources schema (post-migration 075)

```
id          uuid
name        text
domain      text
rss_url     text
source_type text       -- 'rss' | 'scrape' | 'api'
source_tier int        -- 1=high-trust, 2=standard, 3=experimental
language    text       -- ISO 639-1 (en, hi, te, kn, or, ta, ...)
geo_states  text[]     -- regions/states/cities (legacy, mixed)
country     char(2)    -- ISO 3166-1 alpha-2 (NEW, migration 075)
topics      text[]
health_score      real      -- 0.0-1.0 (floor 0.1 since D33)
consecutive_failures int    -- triggers auto-disable at 25 (was 10)
is_active   boolean
last_collected_at timestamptz
created_at  timestamptz
```

---

## Health scoring + auto-disable (D33, 2026-05-27)

Each source row tracks:
- `health_score` (0.0–1.0) — declines on failure, climbs on success
- `consecutive_failures` (int) — strict counter

Changes shipped today:

| Setting | Was | Now (D33) | Why |
|---|---|---|---|
| Health-score floor | `0.0` | **`0.1`** | A score-zero source never recovered automatically; floor at 0.1 lets weekly reset task lift it. |
| Auto-disable threshold | 10 failures | **25** | 10 was triggering on transient outages. 25 better matches genuine "this source is dead". |
| Weekly Monday reset | None | **`tasks.reset_source_health_weekly`** at 00:00 UTC Mondays | Reset all `health_score=0` rows to 0.1 so they get a fresh shot every week. |

### Beat schedules (current, post-D29/D34)

| Task | Cadence | Purpose |
|---|---|---|
| `tasks.collect_rss` | every 15 min | tier-1 FreshRSS sync |
| `tasks.collect_rss_direct` | every 30 min | tier-2 direct RSS |
| `tasks.collect_html` | every 6 hours | tier-3 HTML |
| `tasks.refresh_rss_urls` | every 6h:20min | rotate browser UAs, refresh URL redirects |
| `tasks.reset_source_health_weekly` | Monday 00:00 UTC | weekly source-circuit-breaker reset |
| `tasks.enrich_journalist_batch` | every 5 min | extract `author_name` from `byline` for last 100 articles |
| `tasks.fetch_og_images_batch` | every 10 min | thumbnail backfill |

### `tasks.enrich_journalist_batch` (D28-D29, 2026-05-27)

NEW periodic task. Parses `articles.byline` → `articles.author_name`
using:
- Generic blocklist (PTI, ANI, Staff Reporter, News Desk, Web Desk
  — go to `byline_role`, not `byline_name`)
- ALL-CAPS reject rule DROPPED (was over-filtering legit BBC-style
  bylines)
- "Read More" suffix stripper

Returns `{processed: N, extracted: M, message: "..."}`. Returns
`message: "no pending articles"` when nothing to do, which is the
common state.

---

## The big bulk-disable gotcha (historical, 2026-04-25)

On **2026-04-25**, a debug session ran manual SQL against the prod DB
that bulk-flipped `is_active=false` on ~406 sources. Query was NOT
committed to a migration file.

- **174 have been re-enabled** by the May 2026 sweep (live-probed
  with `probe_all_disabled.py`; ones returning HTTP 200 with parseable
  content got `is_active=true`)
- **~232 remain disabled** pending investigation. Some genuinely
  dead, significant fraction need URL-path fixes (RSS feeds moved
  from `/rss` to `/feed`, scheme changes `http`→`https`)

**Implication.** If you're inferring "the codebase doesn't support
source X" because source X is disabled, **verify the source row state
first** — there's a real chance it's a victim of the bulk disable.

---

## Byline extractor (post-D28 refinement)

In `backend/tasks/substrate/byline_periodic_task.py` and
`backfill_bylines.py` + `tasks.enrich_journalist` (above). Pulls:
- `<meta name="author">`
- `<meta property="article:author">`
- JSON-LD `author.name`
- Site-specific selectors

Generic-string blocklist (D28 expanded): `Staff Reporter`, `PTI`,
`ANI`, `IANS`, `Web Desk`, `News Desk`, `Reuters`, `AP`, etc. → these
go to `byline_role`, not `byline_name`.

ALL-CAPS reject rule REMOVED in D28 (was wrongly demoting legit
all-caps bylines from international wires).

Current coverage: ~86% of recent articles have `author_name`
populated (vs ~14% pre-D28). P1 todo: 86% → 95%+ via site-specific
selectors.

---

## og:image / thumbnails

`tasks.fetch_og_images_batch` runs every 10 minutes on the
`collectors` queue. Originally used Playwright but now uses **httpx +
rotating UAs** (since Playwright is disabled). Some sites that
required full Chromium render now fail thumbnail fetch silently —
acceptable degradation while Playwright is sidelined.

`backend/tasks/thumbnail_task.py`. Processes up to 30 articles per
invocation.

---

## YouTube ingestion

Lives on its own `youtube` queue (concurrency=1, intentionally) and
uses `_youtube_throttle` to keep request cadence under YouTube's
IP-reputation threshold.

> **Foot-gun (logged in memory).** Never call yt-dlp or
> transcript-api raw from a debug shell on Hetzner. Always route
> through `_youtube_throttle`. CLI probes burnt the IP reputation on
> 2026-05-09; recovery took 24-72 hours.

---

## FreshRSS state

State lives in a single mounted directory inside the `rig-freshrss`
container: `/config/www/freshrss/data/users/admin/`.

**Wipe incident, 2026-05-15:** the admin user *directory* was wiped
by an unidentified cause. With no admin user, the GReader API auth
returns 403 on every request, and the 574-feed subscription list is
unreachable. Recovery involved:

1. Recreate `admin` via the FreshRSS CLI inside the container
2. `chown abc:users` on the user directory
3. Restore `/config/www/freshrss/data/config.php` from default
   template, with `api_enabled => true`
4. Resubscribe all 574 feeds via GReader `subscription/quickadd` API

There's currently no boot-time integrity check. A missing admin user
looks identical to "no new RSS today." Logged as known issue (E1) and
P2 monitoring todo.

---

## Collectors queue concurrency (D44)

`worker-collectors` was `concurrency=1`; bumped to **3** in D44 so a
single slow 30-60min scrape doesn't block all RSS work. Trade-off
risk: overlapping I/O could cause timeout cascades. Monitor first
24-48h; if stable, keep; if not, fall back to 1 + move slow scrapers
to dedicated queue.

---

## Common foot-guns

1. **Don't call yt-dlp/transcript-api raw from shell.** Always
   `_youtube_throttle`. (See E2 in known-issues.)
2. **Don't manually `UPDATE sources SET is_active=...` in prod.**
   Always via migration file. Bulk-disable cascade (2026-04-25)
   happened this way.
3. **Don't re-enable Playwright without fixing memory leak.** Three
   guard checks in `playwright_helper.py` will reject any call. If
   absolutely needed, set `PLAYWRIGHT_ENABLED=true` AND have the OOM
   fix ready.
4. **Don't bypass `enrich_journalist`** with custom byline parsing;
   it has the blocklist that filters wire-service auto-bylines.

---

## Where to look in code

- `backend/collectors/tiered_fetcher.py` — the 4-tier driver
- `backend/collectors/sources/__init__.py` — `@register_source`
- `backend/collectors/sources/<source>.py` — per-adapter logic
- `backend/collectors/rss_collector.py` + `direct_rss_collector.py` +
  `html_collector.py` — periodic-task entry points
- `backend/tasks/collector_tasks.py` — Celery task definitions
- `backend/tasks/source_health_reset_task.py` — weekly reset (D33)
- `backend/tasks/rss_url_refresh_task.py` — 6h URL refresh (D34)
- `backend/tasks/enrich_journalist.py` — periodic byline → author
- `backend/collectors/playwright_helper.py` — Playwright (DISABLED)

---

## See also

- `06-operations-runbook.md` — "How to check FreshRSS health",
  "How to test scraping end-to-end"
- `07-known-issues.md` — scrapers silently failing, FreshRSS auth,
  Playwright disabled
- `09-todos-prioritized.md` — P1 Phase-1 source expansion (+100
  flagships), P3.9 resurrect remaining disabled sources
- `docs/PAUSE_INGEST_RUNBOOK.md` — SIGSTOP / SIGCONT collectors
- `11-session-2026-05-28-learnings.md` — RSS health changes, UA
  rotation, Playwright disable rationale
