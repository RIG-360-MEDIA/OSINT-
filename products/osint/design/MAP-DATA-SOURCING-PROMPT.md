# RIG OSINT — Global Map Data-Sourcing Scout Brief
> Paste this whole file into a fresh Claude / deep-research session (or run it as-is).
> Goal: find data sources, APIs & open-source projects we can layer onto a 3D
> intelligence map for **any region or country on Earth** — including **wildcards**.

---

## YOUR MISSION
You are an **OSINT data-sourcing scout**. Search **GitHub** and **Reddit** exhaustively for
**map-able data sources** (APIs, datasets, scrapers, repos) that add intelligence value to a
3D map — for **any persona, any region, anywhere in the world**. Return a **ranked, verified**
catalog. Bias hard toward **globally-applicable** sources, and toward **surprising-but-real**
wildcards. We are NOT building a single-region app — region-specific sources are low value unless
they are part of a **per-country family** that exists for many places.

## WHAT WE'RE BUILDING (you have no prior context — here it is)
**RIG OSINT "Night Desk"** — a **generic, multi-tenant** personalized political/OSINT intelligence
platform. **Each user defines a persona**: a *primary subject* (a politician, government, company,
organisation, or topic) located **anywhere in the world**, plus a **watchlist** of related entities.
The backend ingests news + social + video + documents globally into PostgreSQL.

The **Map** ("The Theatre") is a **deck.gl + MapLibre GL** 3D console that **adapts to the persona's
geography** at the right administrative level — country → state/province → district → city → point:
- World dark vector basemap; flies into the persona's region on open.
- Regional units as a 3D extruded choropleth (height = a metric, colour = a metric).
- Animated **arcs** for spread/flows; planned time-replay, event, and external layers.
- Stack: React 18 + Vite + deck.gl (`GeoJsonLayer`, `ArcLayer`, `HexagonLayer`,
  `ScatterplotLayer`, `HeatmapLayer`, `TripsLayer`) over a MapLibre basemap.

> **Example seed persona** (one of many): *Government of Telangana / CM Revanth Reddy, India.*
> Treat it as a test case, not the target. Everything must work equally for a US senator, a UK
> mayor, a Nigerian governor, an EU commissioner, or a corporate-risk subject.

## HOW WE JOIN EXTERNAL DATA (any source must hook in via one of these)
**Admin boundary** (country / ADM1 / ADM2 / constituency) · **lat-lng point** · **entity** (a
person/org in the watchlist) · **date/time**. Sources keyed to *standard* admin codes (ISO-3166,
GADM/geoBoundaries IDs) or lat-lng are most valuable because they generalise everywhere.

## WHAT COUNTS AS A HIT
A source that becomes a **map layer** with intelligence value **and generalises across regions**:
geo-granular, **global or wide multi-country coverage** (preferred) or a templated per-country
family, **free / freemium / scrapeable**, joinable by the keys above.

---

## SEARCH TRACK A — GitHub
- **Topics:** `/topics/open-data`, `/osint`, `/geospatial`, `/gis`, `/geojson`, `/datasets`,
  `/satellite-imagery`, `/deck-gl`, `/maplibre`, `/elections`, `/humanitarian`, `/world`.
- **Awesome-lists:** "awesome public datasets", "awesome OSINT", "awesome GIS", "awesome geojson",
  "awesome deck.gl", "awesome open geospatial", "awesome humanitarian data", "awesome election data".
- **Queries:** `world admin boundaries geojson`, `gadm geoboundaries`, `natural earth`,
  `global election dataset`, `acled api`, `gdelt`, `worldpop`, `openaq`, `sentinel api`,
  `viirs nighttime lights`, `netblocks ooni internet shutdown`, `opensky adsb`, `ais ship tracking`,
  `world bank api wrapper`, `opensanctions pep`, `overture maps`, `humanitarian data exchange hdx`.
- Record: stars, last-commit date, license, data type, geo granularity, **coverage scope**.

## SEARCH TRACK B — Reddit
- **Subreddits:** r/OSINT, r/gis, r/datasets, r/dataisbeautiful, r/QGIS, r/openstreetmap,
  r/geopolitics, r/visualization, r/dataengineering, r/javascript (deck.gl), r/webdev, r/MapPorn.
- **Queries:** "global dataset api", "world boundaries geojson", "geocoded events api",
  "free map tiles", "deck.gl layer ideas", "OSINT data sources", "election data by country",
  "satellite api free", "internet shutdown tracker", "flight/ship tracking api".
- Capture: practitioner-recommended tools, hidden gems, **gotchas** (rate limits, paywalls,
  patchy country coverage, stale data), and threads comparing sources.

---

## CATEGORIES TO COVER (all global / multi-country)
**Foundational — boundary & basemap geometry** *(the map must draw ANY region's polygons):*
GADM, geoBoundaries, Natural Earth, OSM admin relations, Who's On First, Overture Maps; global
vector basemaps (Protomaps, OpenFreeMap, MapTiler, Carto, Stadia).
**Geocoded events / conflict:** ACLED, GDELT, UCDP, EM-DAT, ReliefWeb, GenOcide/atrocity trackers.
**Elections / governance:** CLEA, Wikidata politicians/parties, V-Dem, Freedom House, Polity,
OpenSanctions (PEPs/sanctions), parliament/vote APIs.
**Population / demographics:** WorldPop, Kontur, GHSL, HDX, census aggregators.
**Environment / climate:** ERA5/NOAA/OpenWeather, OpenAQ (air), Copernicus/Sentinel, NASA FIRMS
(fires), VIIRS night-lights, WRI Aqueduct (water stress), flood/drought.
**Connectivity / OSINT:** NetBlocks, OONI, IODA, Cloudflare Radar, submarine-cable maps, RIPE Atlas.
**Mobility / movement:** OpenSky & ADS-B (flights), AIS / MarineTraffic (ships), GTFS transit, tolls.
**Economy / trade:** World Bank, UN Comtrade, commodity prices, nightlights-as-GDP proxy, OSM POIs.
**Social / search / media geo:** GDELT GKG, Google Trends by region, Wikipedia pageview geo,
MediaCloud, news APIs, X/Reddit/Telegram geo signals.

**WILDCARDS — lateral, surprising, but global:**
- Internet shutdowns & outages worldwide (NetBlocks/OONI) — "where connectivity died."
- Night-time lights as a development/economic-activity proxy for any region.
- **Live flight & ship tracking** (OpenSky / AIS) — sanctions-evasion, VIP movement, the OSINT classic.
- **Submarine cables + internet exchanges** — the geopolitics of connectivity.
- Global protest / strike trackers; refugee & migration flows (UNHCR).
- Water-stress & reservoir levels (WRI Aqueduct) — resource politics anywhere.
- Religious/festival/holiday calendars per country — event & crowd prediction.
- Commodity / market / mandi prices per country — the "cost of living" map.
- **Cultural output geo** — film/box-office, music, sports sentiment (politically charged in many regions).
- City crime/safety & cost-of-living indices (Numbeo); corruption perception (Transparency Intl).
- Telecom coverage/quality (Ookla); power-grid load/outages; meme/disinformation origin tracking.
- Culturally-specific timing signals (e.g., auspicious-date politics where used).
- **Invent 3+ wildcards of your own** we didn't list.

---

## OUTPUT FORMAT
For each source, one row:
**Name + URL · Type (API/dataset/repo/scraper) · What it provides · Geo granularity ·
Coverage scope (GLOBAL / multi-country / per-country-family / single-region) ·
Boundary-join level (country/ADM1/ADM2/constituency/point/entity/date) · Time
(realtime/historical/static) · Access (free/freemium/paid/scrape) · License ·
Map-layer idea (choropleth/points/arcs/heat/time-replay/extrusion) · Integration effort (S/M/L) ·
Genericity 1–5 (generalises across regions) · Novelty 1–5 · Confidence-it's-real 1–5.**

Group: **Tier 1 (global, build now)**, **Tier 2 (multi-country / nice)**, **Wildcards**.
End with a **Top 10** (weight Genericity heavily) and a **"if you wire only ONE this week"** pick,
plus a one-line note on the **best world admin-boundary source** to power the map for any region.

## QUALITY BAR (non-negotiable)
**Prefer GLOBAL > multi-country > per-country-family > single-region.** Down-rank anything that
only works for one place unless it's a template replicated across countries. Verify each is **real
& maintained** (recent commit / live endpoint). Flag dead, paywalled, or geographically-narrow
sources. **No hallucinated APIs** — if you can't confirm it exists, mark confidence ≤2 and say so.
