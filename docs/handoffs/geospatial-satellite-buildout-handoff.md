# Geospatial / Satellite Change-Detection Buildout — Full Handoff

**Written 2026-07-07.** Hand this + the kickoff prompt to a new chat for full context.
Read top-to-bottom first. Sibling handoffs (already done, same discipline):
`docs/handoffs/keyword-social-rebuild-handoff.md`,
`docs/handoffs/osint-sources-buildout-handoff.md`.

---

## 0. One-paragraph situation

RIG Surveillance is a keyword/entity OSINT platform. Social collection + 10 free
non-social OSINT sources are built + proven. This phase adds **satellite
change-detection** — the client picks a location and sees how it physically changed
over time (new buildings, construction, military camps, flooding, deforestation, port
activity). Unlike the other phases, **this is genuinely NEW — no existing code in the
repo.** It's also a heavier build. Do it in the same disciplined, honest, verify-first
way, and keep it CHEAP: free government imagery, on-demand (pull only a location someone
asks about), store only results — never warehouse the archive.

## 1. Hard rules (do not violate)

- **VERIFY against the live source — never trust docs or my cutoff-era claims.** Access
  terms for free imagery services change; confirm CURRENT free-access before building on
  a source.
- **No fabrication.** Never claim a change was detected without the actual before/after
  imagery + result. Paste real output. Report trusted / unverified / failed separately.
- **Prove on TWO locations** — one with a KNOWN change (e.g. a documented construction
  site / a flooded area with a known date) so you can confirm the model actually catches
  a real change, AND one niche/fresh. Not one cherry-picked site.
- **Free / no-paid-imagery this phase.** Sub-meter paid imagery (Maxar/Planet) is out of
  scope — flag where it would be needed, don't half-buy it. Secrets/tokens via env vars.
- **On-demand + persist-from-use** (same rule as social/OSINT — `project_social_keyword_driven`):
  pull imagery ONLY for a location a user queries; compute; store only the result
  (heatmap/summary), not the raw pixels. Do NOT build a data lake.
- **Low blast radius:** this is external read-only imagery + a compute job. It does NOT
  touch `rig-backend` core ingest. Build it isolated (new module/service or in
  osint-backend), httpx/rasterio/torch only.
- **Off-limits:** nothing here is people-tracking — it's places, not persons. Keep it
  that way.

## 2. The honest capability ceiling (state this to the user, don't oversell)

- **Free imagery = ~10m/pixel** (Sentinel-2) or radar (Sentinel-1, sees through cloud).
- 10m CAN detect: new buildings, runways, dams, construction, military camps,
  flooding, deforestation, land-use change, coarse port/berth activity —
  i.e. "did something BIG physically change at this location, and when?"
- 10m CANNOT: count vehicles, identify aircraft types, read plates — that needs
  sub-meter PAID imagery. Say so honestly; that's the boundary of the free tier.
- Realistic value: free gets ~70% of the change-detection story a client asks for, for
  ~$0. Reach for paid only when a specific target needs sub-meter counting.

## 3. The building blocks (search-derived — VET before relying)

**Free imagery access (pick after verifying current terms):**
- **Microsoft Planetary Computer** — hosted STAC API + signed asset URLs, free open
  data; `planetary-computer` + `pystac-client` Python packages. NOTE: MS restructured
  the offering (added a paid "Pro" tier + changed the compute Hub) — you don't need the
  Hub (run compute on our own box), but CONFIRM the open data API is still free.
- **AWS Open Data — Sentinel-2 COGs** — same free imagery, different host; fallback if
  Planetary Computer terms tightened.
- **Google Earth Engine** — free for research/non-commercial, does compute for you, but
  heavier lock-in + licensing constraints for a commercial product (check the license).
- Imagery is **Cloud-Optimized GeoTIFF (COG)** → read ONLY the pixels for the AOI
  (area of interest) via range requests; a 5km×5km site × 2 dates × a few bands = tens
  of MB transient, not GB.

**Change-detection code (vet stars / last-commit / license — some academic repos are
dead):**
- `satellite-image-deep-learning/techniques` — the master curated INDEX, start here.
- `likyoo/change_detection.pytorch` — pip-installable CD library, most "just works".
- `open-cd` (OpenMMLab-style) — production model zoo.
- OSCD (Onera Satellite Change Detection) — standard benchmark built on free Sentinel-2.
- `acgeospatial/awesome-earthobservation-code` — broader EO tooling list.

## 4. The plan

**Phase 0 — research + vet (do FIRST, no code).** Verify CURRENT free-access terms for
Planetary Computer vs AWS Sentinel-2 bucket. Vet the top 2-3 CD repos (stars, activity,
license, does-it-run). Come back with a ranked "use THIS imagery source + THIS model"
recommendation before building. (A research agent is ideal here.)

**Phase 1 — minimal proof-of-concept.** `verify_satellite_change.py`: input = lat/lon +
two dates (+ optional AOI box) → fetch the two Sentinel scenes for that AOI from the
chosen free source → run the chosen CD model → output a change map/score + the two
source images. Runs on dev AND the box. **Proof bar:** ≥2 locations, one with a KNOWN
documented change (confirm it's caught) + one niche; real before/after + result shown,
honest resolution limit stated. Nothing fabricated.

**Later (deferred):** on-demand endpoint (`/api/geo/change?lat=&lon=&from=&to=`) in
osint-backend, slot into the tasking brain (a location keyword → offer change-detection),
persist results, surface in the dossier/map UI, fuse with news ("satellite change +
news timing = event verification").

## 5. Definition of done (Phase 1)

`verify_satellite_change.py` run on the box, on 2 locations (one known-change), output +
imagery pasted back, real change caught on the known site, honest ~10m ceiling stated.
No fabrication. THEN wire the on-demand endpoint + UI.

## 6. Context to read first

- Sibling handoffs (§ intro) — same discipline.
- Memory `~/.claude/projects/C--Users-Dell-Desktop-rig-surveillance/memory/`:
  `project_social_keyword_driven.md` (on-demand/persist-from-use HARD rule),
  `feedback_no_fabricated_results.md`, `MEMORY.md` (index).
- CLAUDE.md (repo root) — topology, deploy, foot-guns.
- Note: `products/osint/backend/geo_collector.py` already does place→lat/lon
  (Nominatim) — reuse it to turn a place NAME into the coordinates this phase needs.
