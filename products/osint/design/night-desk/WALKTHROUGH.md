# ROBIN-OSINT — Web App Walkthrough

> A team guide to the deployed political-intelligence SPA. Read this to
> understand what every page does, how to navigate it, and what data sits
> behind each screen.
>
> **Live URL:** https://desk.rig360media.com
> **What it is:** A per-persona ROBIN-OSINT workspace — a single-page React app
> that turns ~119K Indian news articles + social signals + YouTube transcripts
> + govt PDFs into a personalized daily intelligence picture for one principal
> (e.g. a state government / a political figure) and their watchlist.

---

## 1. The 30-second mental model

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser (Vite/React SPA)  ──►  osint-backend (FastAPI)  ──►  Postgres │
│  desk.rig360media.com           /api/brief/*  /api/me        (analytics_user,│
│  Supabase JWT in header         read-only, persona-scoped     READ-ONLY)     │
└─────────────────────────────────────────────────────────────────┘
```

- The **frontend** is static React served by Caddy. It holds no secrets and
  no business data — it only renders what the API returns.
- Every request carries a **Supabase JWT** (`Authorization: Bearer …`).
- The **backend** (`osint-backend`) connects to Postgres as `analytics_user`
  (read-only on `public.*`). It **personalizes every response** to the signed-in
  user's saved preferences (`analytics.user_brief_prefs`).
- Heavy pages (Home / War Room / Analytics / Map) are served from a **30-minute
  precomputed cache**; Dossier and the Report are computed live.
- All time windows use **`analytics.now_sim()`** — a replay-safe clock — so the
  app can run against a paused/replayed dataset without "everything looks old".

**Why two teammates see different data:** the app is *persona-scoped*. Your
principal, watchlist, region and topics (set during onboarding) decide which
articles form your "universe". There is no global feed — every number is
relative to your persona.

---

## 2. Signing in & access

| Step | What happens |
|---|---|
| **Login** (`/`, when signed out) | Email + password → `supabase.auth.signInWithPassword()`. JWT is stored in `localStorage` (`sb-osint-auth-token`). |
| **Principal resolve** | `useMe()` calls **`GET /api/me`** → returns `{ id, email, name, onboarded, is_super_admin }`. |
| **Onboarding gate** | If `onboarded` is false, the user is sent through the 12-step wizard which writes `analytics.user_brief_prefs` (principal, watchlist, regions, topics, stance, personality, delivery). |
| **App shell** | Once a principal resolves, the six-page shell renders. |

- Accounts are **invite-only** (`/api/onboarding/invite/{token}` → `accept`).
- Super admin (`is_super_admin`) unlocks admin surfaces. The seeded super admin
  is `pranavsinghpuri09@gmail.com`.

---

## 3. The app shell (persistent chrome on every page)

| Element | File | Behaviour |
|---|---|---|
| **Sidebar** (left rail) | `components/Sidebar.jsx` | 6 nav items: Home · War Room · Analytics · Dossier · Map · Dispatch. **Collapsed by default**; your choice is remembered (`localStorage: nd-rail`). Toggle with the **☰** button. |
| **CommandBar** (top) | `components/CommandBar.jsx` | Dark/light **theme toggle** (`localStorage: nd-theme`). |
| **Ticker** (under top bar) | `components/Ticker.jsx` | Scrolling headline tape. |
| **Routing** | `App.jsx` | Real URLs per page via the History API — `/`, `/war-room`, `/analytics`, `/dossier`, `/map`, `/dispatch`. Back/forward work; base-path aware (works at `/` and on a subpath). |
| **Page transition** | `App.jsx` | Framer-motion fade/slide on page switch; scroll resets to top. |

---

## 4. Page-by-page walkthrough

> URLs below are the deployed paths. "Feeds from" lists the **verified** API
> calls each page makes.

### 4.1 Home — "The Briefing" · `/`
**Purpose:** the daily executive brief — what happened, what it means, what's next.

**What you see (top → bottom):**
1. **Masthead** — principal name, state, as-of time, confidence.
2. **THE BRIEFING** — narrative analysis: *What Happened · What It Means · Why It
   Matters · The Other Side · What's Next (with a confidence tag) · How To Play It.*
3. **TOP STORIES FOR YOU** — importance-ranked cards (thumbnail, headline, tone
   badge, source, age, "why matched"). Ranked by relevance/coverage, not random.
4. **PEOPLE TO WATCH** — principals + highest-coverage individuals with a latest
   headline and presence/pressure mini-charts.
5. **THE SIX** — six storyline tiles (major clusters / "hard truths").

**Feeds from:** `GET /api/brief/home` (the brief + sections) and
`GET /api/brief/top-articles?limit=6` (the ranked story cards).
**Backend builder:** `home_sections.py` (+ `analytics.home_cache`, 30-min refresh).

---

### 4.2 War Room — "The Crisis Desk" · `/war-room`
**Purpose:** threat surface — who is being attacked, how hard, by whom.

**What you see:**
1. **THREAT STACK** — adverse storylines as "cables": severity badge, risk score,
   the claim (with English gloss for regional-language items), who/when/origin,
   and a facet breakdown (what it is / who it hurts / who's acting / what it hits).
2. **THE FIELD** — three readable panels:
   - **MOMENTUM** — story volume per entity, with the adverse share in red.
   - **ATTACK MAP** — rival × topic grid of adverse co-occurrence (raw counts).
   - **ALLIANCE / BLOC** — friend-vs-foe outlet structure.

> Note: the old **COUNTER-ATTACK** panel was intentionally removed.

**Feeds from:** `GET /api/brief/warroom`.
**Backend builder:** `war_room.py` — 21-day window; uses the POL stance map and
the `_BODY_PRESENT` hallucination filter so a name must actually appear in the
article body to count.

---

### 4.3 Analytics — "The Instrument Panel" · `/analytics`
**Purpose:** the quantitative view — pure data, no LLM narrative.

**What you see (three bands):**
- **The Big Picture** — daily coverage-volume area chart (with spike alerts),
  top topics, and a tone donut (supportive / neutral / hostile).
- **Who & Where** — per-entity sparklines + trend, entity share-of-voice, geo spread.
- **The Detail** — event calendar, attributed **quotes**, **claims** (predicate +
  text + source), key **figures**, and the **Picture Wall** (real article images).

**Feeds from:** `GET /api/brief/analytics`.
**Backend builder:** `analytics_page.py` — materializes your persona's article
universe once, then each card aggregates from it. Directional metrics use
`article_stances` (POL).

---

### 4.4 Dossier — "Entity Files" · `/dossier`
**Purpose:** a deep file on any watched person/org.

**What you see:**
- **Left:** searchable roster (search by name, filter person/org, alignment dot).
- **Right (on select):** the entity file — **Pulse** (mentions/day), **Standing**
  (support vs critical), **Share of Voice**, **Issue Footprint**, **In Their
  Words** (quotes), **The Ledger** (claims), **Network** (co-mentions), **Reach**
  (EN vs Telugu), **Timeline** (dated milestones), plus an auto-summary.
- **Load more** paginates the entity's whole-corpus article feed.

**Feeds from:**
`GET /api/brief/dossier/roster` → `GET /api/brief/dossier/entity/{id}` →
`GET /api/brief/dossier/entity/{id}/articles?limit=20&cursor=…`.
**RBAC:** you can only open an entity that is your principal or on your watchlist
(otherwise `403`). Computed live (no cache).

---

### 4.5 Map — "The Theatre" · `/map`
**Purpose:** the geospatial picture — coverage + stance on a real map, plus live
external layers.

**What you see:**
- A **deck.gl / Maplibre** map, **flat 2D by default** (3D available).
- **Scope toggle:**
  - **MINE** — your state's **district choropleth** (colour = net stance, drill a
    district for its article feed). The view holds on the world ~2s then **flies
    to your region**.
  - **GLOBAL** — a **world country choropleth** built from the corpus (colour =
    coverage); click a country to drill its file + articles. Pulls back to world.
- **Global layers** — NASA **EONET** natural-event hotspots (e.g. wildfires) and
  **ACLED** conflict points as scatter bubbles.
- **LIVE CHANNELS** — up to 6 auto-playing YouTube news streams, scoped to the view.
- **Legend** + situation cards below the map.

**Feeds from:** `GET /api/brief/map?scope={mine|global}` · `/api/brief/global-layers`
· `/api/brief/district/{id}` (+`/articles`) · `/api/brief/country/{iso}`
(+`/articles`) · `/api/brief/channels?scope=…`.
**Backend builders:** `map_page.py`, `country.py`, `global_layers.py`,
`live_channels.py`.

---

### 4.6 Dispatch — "The Daily Report" · `/dispatch`
**Purpose:** preview, download, and email the daily PDF Intelligence Report.

**What you see:** a single `ReportDispatch` panel (the old mock cards were removed):
- A **preview** of today's report.
- **Download PDF** — pulls `GET /api/brief/report.pdf` (a fully-formatted,
  Telugu-capable PDF with sections A–I, KPIs, and top stories with thumbnails).
- **Email me** — `POST /api/brief/report/send` mails the PDF to your signed-in
  address.

**Feeds from:** `GET /api/brief/report` (preview JSON) · `GET /api/brief/report.pdf`
· `POST /api/brief/report/send`.
**Backend:** `report_builder.py` (content) → `report_render.py` (WeasyPrint PDF)
→ `report_email.py` (Gmail SMTP 587/STARTTLS).

---

## 5. The daily report email (automated)

Independently of the Dispatch button, a cron job (`send_daily_reports.py`)
generates and emails each signed-in user their **state daily brief** every
morning (IST). It joins `analytics.users` for addresses, builds a persona-scoped
report, renders the PDF, and sends it. Failures are isolated per-recipient.
Subject: `RIG OSINT · {state} Daily Brief · {date}`.

---

## 6. Backend API reference (what the frontend actually calls)

| Page | Method · Path | Returns |
|---|---|---|
| Auth | `GET /api/me` | Signed-in principal (id, email, onboarded, is_super_admin) |
| Home | `GET /api/brief/home` | Masthead + The Briefing + People to Watch + The Six |
| Home | `GET /api/brief/top-articles?limit=` | Relevance-ranked story cards |
| War Room | `GET /api/brief/warroom` | Threat stack + The Field (momentum/attack-map/bloc) |
| Analytics | `GET /api/brief/analytics` | ~20 data cards (volume, topics, tone, quotes, claims, picture wall…) |
| Dossier | `GET /api/brief/dossier/roster` | Watchlist registry |
| Dossier | `GET /api/brief/dossier/entity/{id}` | Full entity file |
| Dossier | `GET /api/brief/dossier/entity/{id}/articles?limit=&cursor=` | Paginated entity feed |
| Map | `GET /api/brief/map?scope={mine\|global}` | District/country bubbles + feed |
| Map | `GET /api/brief/global-layers` | NASA EONET + ACLED layers |
| Map | `GET /api/brief/country/{iso}` (+`/articles`) | Country file + paginated feed |
| Map | `GET /api/brief/district/{id}` (+`/articles`) | District file + paginated feed (RBAC) |
| Map | `GET /api/brief/channels?scope=` | Up to 6 live YouTube channels |
| Dispatch | `GET /api/brief/report` | Report preview JSON |
| Dispatch | `GET /api/brief/report.pdf` | Report PDF download |
| Dispatch | `POST /api/brief/report/send` | Email the report to the user |
| Health | `GET /health` · `GET /ready` | Liveness / readiness probes |

> Additional server-side endpoints exist for onboarding (`/api/onboarding/*`)
> and may exist but are not called by the current six-page shell.

---

## 7. Data & personalization (how a "universe" is built)

- **Prefs** live in `analytics.user_brief_prefs`: `primary_subject_id` (your
  principal), `watchlist.entity_ids`, `regions.states`, `topics`, `languages`,
  `stance`, `personality`, `delivery`.
- `principal_of(prefs)` picks the focal entity; `_primary_state()` picks your
  region for the Map/Report.
- Page builders assemble the article **universe** via `article_entity_mentions`
  where `entity_id ∈ (principal, watchlist)`, resolving entity merges through
  `entity_dictionary.redirected_to`.
- **Stance** everywhere uses **POL** (maps `article_stances.intensity` →
  supportive/neutral/hostile) gated by **`_BODY_PRESENT`** (the entity must
  appear in the article body — anti-hallucination).

**Key tables/views:** `articles`, `article_stances`, `article_entity_mentions`,
`article_districts`, `sources`, `entity_dictionary`, `districts`,
`analytics.users`, `analytics.user_brief_prefs`, `analytics.home_cache`,
`analytics.entity_image`, `youtube_clips`, and the `story_*` story-layer matviews.

---

## 8. Glossary

| Term | Meaning |
|---|---|
| **Principal** | The focal entity the persona is built around (e.g. the state govt / CM). |
| **Watchlist** | The set of entities a user tracks; defines their article universe. |
| **POL** | The SQL stance map turning sentiment intensity into supportive/neutral/hostile. |
| **`_BODY_PRESENT`** | Filter requiring an entity's name to appear in the article body before it counts. |
| **`now_sim()`** | Replay-safe "current time" so the app works on paused/replayed data. |
| **Substrate** | The v3 extraction layer (translation, register, entities) over raw articles. |
| **Tier (1/2/3)** | Source/entity importance tiers used for ranking and source weighting. |

---

## 9. Ops quick reference

- **Frontend build:** `products/osint/design/night-desk/` (Vite). Env:
  `VITE_BRIEF_API`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`.
- **Backend:** `products/osint/backend/` (FastAPI). Deploy = scp to
  `/root/rig/products/osint/backend/` then `docker compose build osint-backend
  && up -d` (image is baked, not bind-mounted).
- **Serving:** dockerized Caddy (`rig-caddy`) terminates TLS for
  `desk.rig360media.com`.
- **Caches:** Home/War Room/Analytics/Map = 30-min precompute; Dossier + Report
  = live. Map uses a per-scope cache key.
- **Source of truth for the wider stack:** repo root `CLAUDE.md` and
  `docs/onboarding/`.

---

## 10. Known limitations (be honest with the team)

- **Analysis window is wide.** Pages summarize over multi-day/-week windows, so
  the top-line picture can look stable hour-to-hour even though ingestion is live.
- **YouTube clips:** caption-based transcripts ingest fine; caption-less videos
  need audio transcription which is currently blocked from the data-center IP
  (needs a residential proxy) — so clip volume can lag.
- **Twitter/X** signals are ingested but hidden from the UI for now.

---

*Maintained alongside the ROBIN-OSINT app. If a page or endpoint changes, update
sections 4 and 6 first — they're what the team relies on to navigate.*
