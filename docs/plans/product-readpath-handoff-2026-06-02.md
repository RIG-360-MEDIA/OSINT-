# RIG OSINT — Product Read-Path & Handoff (2026-06-02)

Orientation for whoever picks up the **Night Desk** product next. Read top to
bottom once; after that use it as an index. Every number here was verified
against the live DB this session — but **re-verify before trusting** (sources and
data drift; see §5).

> **Map goal — CLOSED / PARKED 2026-06-03.** The `/goal "make it fully"` map objective is
> closed at the state in §3 below: 6 surfaces + 6-week replay + arcs + 2 live overlays
> (Fires/Quakes) shipped and verified on real DB data, World-Monitor-independent. The
> "fully" remainder — click-drill-in, AI situation read, animated stance-over-time,
> genericity, and the unbuilt API layers (§3 ❌ / §9) — is **deferred, not done**. This
> is a deliberate park, not a completion claim. Reopen from §9 when re-prioritized.

---

## 0. TL;DR
- **Night Desk** = the OSINT design prototype at `products/osint/design/night-desk/`
  (React 18 + Vite + deck.gl), persona = **Government of Telangana / CM Revanth Reddy**.
- Runs at **http://localhost:5180/** — **no auth** (unauthenticated prototype; persona
  hardcoded in `src/data/persona.js`, mirroring DB user `03f93124-eec3-46ac-a41e-829cb663b615`).
- The **Map** ("The Theatre") is the most-built page: a deck.gl + MapLibre 3D Telangana
  map with 6 data surfaces, a 6-week replay, arcs, and live Fires/Quakes overlays.
- It is **World-Monitor-independent** (own proxy, own keys, own basemap — see §4).
- Still **Telangana/Revanth-hardcoded** — the generic/multi-persona abstraction is NOT done (§7).

## 1. Read path (start here)
1. This file.
2. `products/osint/design/MAP-LAYERS-MASTER.md` — the layer catalog + built status + live-source drift.
3. `products/osint/design/MAP-FEATURES-CATALOG.md` — what the DB can power for the map.
4. `src/pages/MapPage.jsx` + `src/data/telangana-map.js` — the actual map + its data.
5. `src/data/persona.js` — the one persona seam (swap this to go multi-tenant).
6. `products/osint/design/ANALYTICS-DATA-CATALOG.md` — the broader pure-data analytics sweep.

## 2. What's built (prototype)
6 pages, all hardcoded data (0% backend-wired): Home (broadsheet brief), War Room
("Cable Desk"), Analytics ("Instrument Panel", 20 modules), Dossier ("Subject File",
66 watchlist entities + 54/66 real Wikipedia portraits + evidence-first Verify drawer),
**Map** (below), Dispatch. Design language is bespoke per page ("AXIOM" dark system).

## 3. The Map — feature inventory
### ✅ Wired & working (verified this session)
- **6 surfaces** (colour + height of the 33 districts, real DB data): Stance · Volume ·
  Revanth (persona footprint) · Outlets · Surge (wk-over-wk) · Issue (+8-topic sub-filter).
- **6-week time-replay** scrubber (animates heights to each week's real coverage).
- **Narrative arcs** (district co-mention) · **3D/Flat** (Flat = true top-down) · **⌖ reset** ·
  pan/zoom/rotate · dark world basemap (env-swappable) · self-updating legend · hover cards.
- **Live overlays via our proxy + reused keys:** 🔥 Fires (NASA FIRMS, ~365 live pts) · ◎ Quakes (USGS).
- Foundation: 33 real district polygons (udit-001 geojson), all real numbers.

### ❌ NOT wired (should have)
- **Click-through drill-in** (district → its top stories/quotes/claims) — only a hover tooltip today. *Highest value.*
- **AI situation read** — `GROQ_API_KEY` works but unused; click district → LLM writes what's happening.
- **Animated stance-over-time** (replay animates volume only, not the friendly↔hostile colour).
- District labels · search/jump-to-district · replay **play** button · daily granularity · verify/explain drawer.
- **API layers not built:** News/events (GDELT geo 404 — needs a working source), Ships (AISStream key present, WS layer unbuilt), Flights (OpenSky — needs key), Air (OpenAQ key), shutdowns (OONI/IODA), population (WorldPop/Kontur H3), night-lights (VIIRS), World Bank context, weather.
- **Product:** genericity (§7), bounds-lock to India, export/share, responsive.
- **Deliberately skipped:** `article_events` "events" layer — verified NOT map-ready (geo = article's district not event's, ~70% noise, no dedup).

## 4. Infra — World-Monitor independence, proxy, keys
- **World Monitor** (`koala73/worldmonitor`, Elie Habib) is a deployed third-party app
  (`rig-worldmonitor`, `rig-wm-*` containers). **License: AGPL-3.0 + commercial licence required
  for SaaS.** We treat it as *reference only* — copied ideas + the source list, **not** code.
- Night Desk is decoupled: **own proxy** `server/proxy.mjs` (zero-dep, :8788, routes per source),
  **own gitignored `.env`** (`.env.example` committed), **own basemap** (`VITE_BASEMAP_URL`, Carto default).
  Verified 0 WM references in code; survives `docker stop rig-worldmonitor`.
- **Keys** (copied from the `rig-worldmonitor` container env into `night-desk/.env`, values never logged):
  - ✅ live: `NASA_FIRMS_API_KEY`, `GROQ_API_KEY`, `FRED_API_KEY`, `EIA_API_KEY`, `FINNHUB_API_KEY`.
  - stored: `AISSTREAM_API_KEY` (WS, layer not built). ⚠ `AVIATIONSTACK_API` (429 throttled).
  - **empty on the box** (add your own): Cloudflare, ACLED, OpenAQ, OpenSky, UCDP, OpenRouter.
- Health check anytime: `node server/check-keys.mjs` (never prints values).

## 5. Data-quality findings — READ BEFORE TRUSTING ANY LAYER
- **emotion ≠ stance** — use `article_stances` for any bias/hostility measure; `register_emotion`'s
  "alarm" is event-emotion (floods/crime) and skews everything negative.
- **Entity "home-turf" from raw NER is garbage** (Bengali MPs, cricketers, orgs-as-persons).
  Only trust entity↔district scoped to the **66 verified watchlist** entities.
- **Live "keyless" sources have rotted:** GDELT geo **404**, UCDP **401** (needs token), ReliefWeb v1
  **410 Gone**, GDELT DOC **429**. Only FIRMS (keyed) + USGS (keyless) are reliable now.
- **Outlet bias is persona-specific:** Telangana Today is generally +, but **critical of Revanth**
  (9 sup / 32 crit). Namasthe Telangana drives the hostility (6/59).
- **Replay week-3 spike** is a real ingestion batch, not organic news.
- Matview staleness: `article_entity_mentions` had no refresh until the Hetzner cron (`/etc/cron.d/rig-matview-refresh`, 30-min) was added.

## 6. How to run
```
cd products/osint/design/night-desk
npm install
npm run dev          # app  -> http://localhost:5180
npm run dev:server   # proxy -> :8788 (needed for Fires/Quakes overlays)
```
DB: `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154` then
`docker exec -i rig-postgres psql -U rig -d rig -tA` (pipe SQL via stdin; PowerShell→ssh mangles `-c`).

## 7. The genericity gap (strategic)
The product is meant to serve **any persona/region** (per-user watchlist + RBAC in the real backend).
The prototype is **Telangana/Revanth-hardcoded**: ~97% of the coupling is in `data/*.js` (swappable),
but two structural pieces need work: **MapPage hard-imports the Telangana geojson/centroids**, and
**`persona.js` is only half-wired** (it sets the identity; content files still hardcode). To generalise:
(a) a **region registry** (`{geojson, center, districtData}` resolved from the persona's region —
geoBoundaries gives any country's polygons), (b) route all data through `persona.js` + an API client
keyed by `user_id`, (c) GDELT/geoBoundaries make the map work for any persona with zero per-region config.

## 8. Reference docs
- `products/osint/design/MAP-LAYERS-MASTER.md` · `MAP-FEATURES-CATALOG.md` · `MAP-DATA-SOURCING-PROMPT.md` (global) · `ANALYTICS-DATA-CATALOG.md` · `FIX-entity-mentions-refresh.md`
- Memory: emotion-vs-stance, matview-refresh-cron, CM content correctness, branch divergence.

## 9. Recommended next steps (priority order)
1. **Click-through drill-in** + **AI situation read** (Groq) — most intel value, keys ready.
2. **Animated stance-over-time** in replay.
3. **Genericity** — region registry + finish the `persona.js` seam (unblocks every other persona).
4. Wire **Ships** (AISStream key present) and one keyless context layer (World Bank / WorldPop).
5. Source a working **geocoded news** endpoint to restore the News overlay.

## 10. Broader RIG context & caveats
- Backend = FastAPI + Celery (in-container workers, see root `CLAUDE.md`), Postgres+pgvector on Hetzner.
- Real product has **RBAC** (super-admin `pranavsinghpuri09@gmail.com`); prototype has none.
- Don't lift World Monitor code into a commercial build without a licence (AGPL).
- YouTube IP-reputation: never hit yt-dlp/transcript-api raw from a Hetzner shell.
