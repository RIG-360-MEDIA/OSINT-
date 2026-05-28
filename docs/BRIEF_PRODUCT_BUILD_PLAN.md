# OSINT Brief Product — Build Plan (2026-05-28)

Step 2 of the kickoff. **No code beyond Step 1 cleanup yet.** This doc
reconciles the new kickoff with three existing planning docs from a
parallel session, surfaces an architecture decision the user needs to
make, and lists the open questions blocking Step 3.

---

## TL;DR

The brief-app frontend already exists and is **already wired to live
backend endpoints** that the parallel session built earlier today. The
new kickoff prompt asks for a fresh `products/osint/backend/` FastAPI
service using a read-only DB role — which would re-implement endpoints
that *already work* in `backend/routers/brief_router.py`.

**Two valid paths.** Pick one before I write code:

| | **Path A — Strict kickoff** | **Path B — Pragmatic reuse** |
|---|---|---|
| Backend lives in | `products/osint/backend/` (new FastAPI) | `backend/routers/brief_router.py` (already shipped, parallel-session work) |
| DB role | `analytics_user` (read-only on public, RW on analytics schema) | Existing rig-backend role (RW everywhere; trust-based) |
| Brief-app `RIG_API_BASE` points to | new `osint-backend:8002` | existing `robin-osi.rig360media.com` |
| Docker services | NEW `osint-backend` + `osint-frontend` | reuse `rig-backend` + new `osint-frontend` only |
| Safety net | Postgres enforces read-only | Code-discipline enforced |
| Throwaway risk | Re-implements ~558 lines of working SQL from `backend/observability/brief_*.py` | None |
| Coupling | Brief product can be redeployed without touching rig-backend | Brief releases bundled with rig-backend redeploys |
| Effort delta | +1.5 days (rewriting queries against analytics_user) | 0 days |

**My recommendation: Path B**, with one safety addition — wire `osint-frontend` through a *narrow* read-through proxy in `products/osint/backend/` that just forwards `/api/brief/*` to rig-backend, so the deploy boundary stays clean even while the SQL lives in rig-backend for now. Migration to Path A becomes a copy-paste later.

---

## What already exists (audited 2026-05-28)

### Frontend — `products/osint/frontend/brief-app/`

| File | Size | What it is |
|---|---|---|
| `index.html` | 1.4 KB | Entry point. Loads React 18 + Babel from unpkg CDN. Spectral font from Google Fonts. No bundler. |
| `app.jsx` | 99 KB / 1682 lines | Single-file React app. ~70 top-level components. Sections: TopBar, BriefMasthead, KPI tiles, MoodSection, WatchedEntities, DefiningStories, CoverageMatrix, NarrativeGap, Blindspot, Horizon, EmergingSignals, ForecastPulse, etc. |
| `primitives.jsx` | 17.5 KB | Shared building blocks exposed on `window.RIG`: Icon, Sparkline, MetricNumber, StanceDot, LanguagePill, LiveDot, Countdown, Reveal, SectionHead, ImageSlot, MethodPopover. |
| `data.js` | 17 KB | IIFE exposing `window.RIG_DATA = { SPARK, STORIES, ENTITIES, HORIZON, CLIMBING, BLINDSPOT, RECOMMENDED, nextRefreshAt }`. Mock data, Telangana-political-domain. |
| `styles.css` | 282 KB | Single file. Spectral typography. |
| `image-slot.js` | 31 KB | Image-handling primitives. |
| `images/` | 9 PNGs | Entity portraits (Naidu, Rahul, Akhilesh, Owaisi) + story thumbnails (Telangana cabinet, India UN report, electoral bonds) + blindspot illustrations. |
| `Morning Brief.html` / `index.html` | Identical | Render target. |
| `start.bat` | 0.5 KB | Launches `py -3 -m http.server 5173`. |

### Frontend — live-data plumbing already present

`app.jsx` lines 10–72 contain four `useLive*` hooks already polling Hetzner:

```js
const RIG_API_BASE = "https://robin-osi.rig360media.com";
useLiveKpi()      → GET /api/brief/kpi      (60s poll)
useLiveEntities() → GET /api/brief/entities (60s poll)
useLiveEmerging() → GET /api/brief/emerging (60s poll)
useLiveStories()  → GET /api/brief/stories  (60s poll)
```

Each hook holds a static fallback (from `window.RIG_DATA`) and overlays
live data when the fetch returns. Polling cadence: 60s setInterval.

### Backend — `backend/routers/brief_router.py` (parallel session, modified today)

Live endpoints matching the four hooks above:

```
GET /api/brief/entities      → 4 watched-entity cards (Naidu, Rahul, Akhilesh, Owaisi)
GET /api/brief/emerging?limit=5
GET /api/brief/stories?limit=5
GET /api/brief/kpi
```

Backed by `backend/observability/brief_entities.py` (237 lines),
`brief_emerging.py` (123 lines), `brief_stories.py` (198 lines) — total
**558 lines of working SQL** against the live `public.*` schema.

### DB substrate (per onboarding + auto-memory; not re-verified yet)

- ~119K articles in DB, ~30K with full v3 substrate today
- `entity_mention_daily` (T6) for sparkline + surge ratios
- `event_clusters` with `importance_score` (T5) for defining stories
- `article_stances` / `article_quotes` / `article_locations` / `article_events`
- `articles.source_country` (migration 075), `effective_event_date` (072), `location_scope` (074)
- **Migration 076** created the `analytics_user` role + `analytics` schema per the kickoff (untested by me)

### Parallel-session planning docs (read in full)

- `docs/BRIEF_APP_BUILD_PLAN.md` (147 lines) — Day 0–N feature sequence.
- `docs/BRIEF_APP_PRODUCTION_PLAN.md` (188 lines) — 3 deploy options; Option A (Vite + Caddy at `brief.rig360media.com`) recommended.
- `docs/BOSS_BRIEF_GAP_ANALYSIS.md` (180 lines) — feature-by-feature inventory of all 47 components: **18 READY, 20 need new SQL aggregation, 9 need new LLM synthesis, 0 impossible.** ~2 weeks to ship.

The parallel session has not yet started the "20 new aggregations" or "9 LLM syntheses" work. The 4 endpoints already shipped cover the foundational tier (KPI / entities / emerging / stories).

---

## What the new kickoff changes

| Topic | Parallel-session plan | New kickoff |
|---|---|---|
| Frontend home | `brief-app/` at repo root | `products/osint/frontend/brief-app/` ✅ moved in Step 1 |
| Backend home | Extend `backend/routers/brief_router.py` | New FastAPI in `products/osint/backend/` |
| DB access role | rig-backend role (RW) | `analytics_user` (read-only) + `analytics` schema |
| Deploy as | Static via Caddy at `brief.rig360media.com` | NEW Docker services `osint-backend:8002` + `osint-frontend:3001` |
| Build pipeline | Vite + GitHub Actions rsync | Docker compose, deployed alongside rig-backend |
| Polling pattern | 60s setInterval (already in code) | TanStack Query + cursor pagination + country filters + multi-edition routing |

The kickoff also introduces requirements the parallel-session plan didn't address:

- **Cursor pagination** (`?cursor={collected_at}__{id}&limit=N`) — currently the 4 endpoints return fixed-size payloads, no cursor support
- **Country-filter chips** using `articles.source_country` — no endpoint accepts a country filter
- **Freshness-filter chips** (6h / 24h / 7d / all-time) — the current endpoints are hard-coded to 24h
- **Multi-edition routing** (`?edition=morning|midmorning|lunch|afternoon|evening`) — no edition concept exists in the backend
- **`narrative_drafts`** as the source for an edition (per `08-future-plans.md` §5) — table exists from migration 070 but no writer task

These additions DO require backend work regardless of which path we choose.

---

## Recommended build sequence (assumes Path B)

### Phase 0 — Verify the live system (Step 3 in kickoff; ~1 hr)
1. Open SSH tunnel: `ssh -i ~/.ssh/rig_hetzner -L 5433:rig-postgres:5432 root@178.105.63.154 -N`
2. Verify `analytics_user` access — read works on `public.articles`, write blocked, RW works on `analytics` schema
3. Curl Hetzner `/api/brief/{kpi,entities,emerging,stories}` directly to confirm endpoints respond + capture real response shapes
4. Render `products/osint/frontend/brief-app/index.html` locally (just `start.bat`) — confirm it renders and the 4 live hooks fire

### Phase 1 — Vite-ify the frontend (~3 hr)
1. Add `package.json` + `vite.config.js` to `brief-app/`
2. Convert 3 unpkg `<script>` tags in `index.html` to ES `import` statements
3. Replace `window.RIG_DATA` + `window.RIG` globals with module exports
4. Keep `app.jsx` largely untouched (one diff: change globals to imports at top)
5. `npm run dev` → confirm visual parity with current `start.bat` flow
6. Add `Dockerfile` for production build

### Phase 2 — Switch polling to TanStack Query (~2 hr)
1. Replace the 4 hand-rolled `useLive*` hooks with `useQuery` calls (`staleTime: 60_000`, `refetchInterval: 120_000`)
2. Add a `<QueryClientProvider>` at the root
3. Add the "Last updated X min ago" badge using `dataUpdatedAt` from React Query
4. **Decision needed:** keep the static fallbacks from `window.RIG_DATA` (current design) or show skeleton loaders? (recommend: skeletons; keep mock data only for Storybook / Playwright)

### Phase 3 — Wire the 20 new aggregations (~5 days, biggest phase)
Per the gap analysis. Extend `backend/routers/brief_router.py` and `backend/observability/brief_*.py`. Each new endpoint = new feature signed off one-by-one. Order from the gap analysis:
- Per-story sparkline + coverage breakdown + lens cards + cite blocks + thumbnail
- Voices Overnight aggregation
- Horizon 7-day calendar
- Coverage matrix
- Recommended Reading (filter by `article_type IN ('analysis','opinion')`)
- Mini India map (state-level grouping)
- Outlet bias snapshot
- (15 more — see `docs/BOSS_BRIEF_GAP_ANALYSIS.md` for the full list)

### Phase 4 — New kickoff-driven features (~3 days)
- Country filter using `articles.source_country` — add `?country=` to relevant endpoints
- Freshness filter — add `?since=6h|24h|7d|all` 
- Cursor pagination on list endpoints — `?cursor=collected_at_iso__id&limit=N`
- Multi-edition routing — define edition cutoffs + read `narrative_drafts` for curated picks (requires the editions writer task — separate Celery job)

### Phase 5 — LLM-synthesis pieces (~1 week)
The 9 features the gap analysis identifies as needing new prompts (CM/Driving narrative, Blindspot Insights, Forecast Pulse, Tactical Recs, etc.). Each = new prompt + daily Celery task. **Defer until Phase 0–4 are stable** — these block on real LLM spend.

### Phase 6 — Production deploy (~1 day)
Per parallel session's BRIEF_APP_PRODUCTION_PLAN.md Option A: Vite build → rsync to Hetzner `/var/www/brief-app/` → Caddy block for `brief.rig360media.com`. New kickoff says Docker services `osint-frontend:3001`; I'll write *both* a Dockerfile and a static-deploy path and you pick.

---

## Backend API contract (target — Path B extended)

```
GET /api/brief/kpi?since=24h
  → { articlesParsed, outlets, languages, sentiment, lang_breakdown[] }

GET /api/brief/entities
  → { entities: [{ rank, name, init, party, region, classification,
                   mentions_today, change_pct, sentiment, velocity,
                   velocityBars: number[15], latest_quote, ... }] }

GET /api/brief/stories?limit=5&country=IN&since=24h
  → { stories: [{ rank, headline, summary, spark[24], metrics, coverage,
                  lens[], principalQuote, thumbnail, importance_score }] }

GET /api/brief/emerging?limit=5
  → { signals: [{ entity_name, surge_pct, mentions_24h, ... }] }

GET /api/brief/articles?edition=morning&cursor=…&limit=20&country=IN&since=24h   ← NEW
  → { articles: [...], next_cursor: "..." | null }

GET /api/brief/editions/list                                                       ← NEW
  → { editions: [{ slug, scheduled_for_utc, articles_count, status }] }

GET /api/brief/horizon?days=7                                                      ← NEW
  → { dates: [{ date, events: [{ type, source, confidence, ... }] }] }
```

Everything above sits on existing `rig-backend` under `/api/brief/*`.

---

## SQL views needed in `analytics.*` schema (Path A only)

If we go Path A, these views give the new `osint-backend` clean read-only
slices without touching `public.*` directly:

- `analytics.v_brief_entity_card_24h` — per-watched-entity rollup (mentions, change_pct, sentiment, velocity bars, latest quote)
- `analytics.v_brief_emerging_signals_24h` — surging entities
- `analytics.v_brief_defining_stories_24h` — top N by importance_score with article/outlet counts
- `analytics.v_brief_kpi_24h` — articles parsed, outlets, languages, sentiment
- `analytics.v_brief_articles_cursor` — cursor-paginated article cards (for /api/brief/articles)
- `analytics.v_brief_horizon_7d` — forward-looking events
- `analytics.v_brief_country_breakdown_24h` — source_country counts

Even on Path B, these views are useful as a future portability layer.

---

## Open questions (block Step 3+)

1. **Path A vs Path B?** (see TL;DR table). My recommendation: B with thin proxy.
2. **TanStack Query vs SWR?** Kickoff says "preferred TanStack". Confirm.
3. **Auth.** The brief endpoints currently have no auth. The parallel-session plan assumes a "super_admin gate or new persona gate" (from production plan §2). Kickoff is silent. Should brief endpoints require Supabase JWT, or be open within the VPN?
4. **Static fallback vs skeletons.** Brief-app currently shows mock data when fetch is in-flight. Should we keep that pattern or show proper skeletons?
5. **"Multi-edition" semantics.** Future-plans §5 says 5 editions/day. Kickoff repeats this. But the brief-app design only has ONE "Morning Brief" rendered — no edition selector visible. Do we want me to add an edition switcher to the existing design, or leave UI alone and just have the data swap server-side at edition boundaries?
6. **Drain interaction.** The drain is running on Hetzner against rig-backend's nlp/relevance queues. None of the brief endpoints write or touch nlp, so we're safe to add new read-only endpoints. Confirm I shouldn't add any Celery work in this product (kickoff says yes — read-only product). Confirm.
7. **`narrative_drafts` writer.** Migration 070 created the table. Who writes to it? If we need editions, that requires a new Celery job — out of scope for "products/osint/" per kickoff. Defer or include?

---

## What I have NOT done yet

- Run Step 3 (DB tunnel + access verification) — waiting on path decision
- Read `app.jsx` end-to-end (only sampled top + component map; 1682 lines is too long for in-context reading — will read as-needed)
- Inspect `styles.css` (282 KB — will use grep for specific classes when needed)
- Render the brief-app locally (Docker is local-down; can launch via `start.bat` without Docker; haven't done yet)
- Curl the live Hetzner endpoints to capture real response shapes (waiting on tunnel)
- Read the rendered `Top Bar Exploration.html` design study
- Touched `backend/` at all

---

## Awaiting decisions

Once you pick:
- Path A vs B,
- Auth pattern,
- Edition selector,

I'll move to Step 3 (verify Hetzner tunnel + endpoint shapes) and from
there into Phase 0 → 1 → 2.
