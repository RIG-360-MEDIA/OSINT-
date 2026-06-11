# Map — Master Layer Catalog (our data + APIs)

The map ("The Theatre") is **persona-centered and region-adaptive**: it opens flown
into the persona's geography. **Our DB layers = the persona** (their coverage,
stance, events). **API layers = world context** wrapped around the persona — clipped
to the region by default, zoom out for the global backdrop. Everything toggles.
Status: 🟢 shipped · 🔵 build-now (data/key ready) · 🟡 needs-own-key · ⚪ wildcard.

## GROUP 1 — Persona core (RIG database)
| Layer | Powered by | deck.gl | Status |
|---|---|---|---|
| District choropleth — coverage(height) × stance(color) | `article_districts` + `article_stances` | GeoJsonLayer extruded | 🟢 shipped |
| Narrative-spread arcs (district co-mention) | `article_districts` self-join | ArcLayer | 🟢 shipped |
| Issue/topic filter (Politics/Security/Legal/Agri…) | `topic_category` × district | recolor + filter | 🔵 |
| Time-replay — 9 years, daily | `articles.published_at` × district | TripsLayer / animated | 🔵 |
| Animated stance shift (hostility moving) | stance × district × time | animated fill | 🔵 |
| Event layer (⚠ **not map-ready** — see caveat) | `article_events` | IconLayer + filter | 🟠 needs cleanup |
| "Your coverage only" persona filter | watchlist → `article_entity_mentions` | filter toggle | 🔵 |
| Media footprint (which outlets own which districts) | `sources` × district | choropleth | 🔵 |
| Hotspot / surge (rising-coverage velocity) | daily deltas | highlight pulse | 🔵 |
| AI situation read (click a district → what's happening) | DB → Groq/LLM | tooltip/panel | 🔵 |

## GROUP 2 — World context (APIs) — LIVE NOW (key works or keyless)
| Layer | API | Access | deck.gl |
|---|---|---|---|
| **Persona news-mentions, geocoded** (any name → map) | GDELT 2.0 | keyless 🟢 | Scatter/Heat/Arc |
| Active fires / thermal hotspots | NASA FIRMS | key ✅ (proven) | Scatter/Heat |
| Earthquakes (live) | USGS | keyless 🟢 | Scatter |
| Organized-violence events | UCDP | keyless 🟢 | Scatter |
| Humanitarian / disaster reports | ReliefWeb | keyless 🟢 | country feed |
| Weather overlay | Open-Meteo | keyless 🟢 | Heat |
| Country indicators (GDP, etc.) — zoom-out | World Bank | keyless 🟢 | choropleth |
| Live ship positions | AISStream | key ✅ (WS) | Scatter/Trips |
| Economy / energy / markets context | FRED · EIA · Finnhub | keys ✅ | overlays/sidebar |
| Internet shutdowns & outages | OONI · IODA | keyless 🟢 | choropleth/time |
| Region geometry for **any** country | geoBoundaries | keyless 🟢 | base polygons |

## GROUP 3 — Add your own key (empty on the box)
| Layer | API | Note |
|---|---|---|
| Internet outages (richer) | Cloudflare Radar | needs token (OONI/IODA cover this keyless) |
| Curated protest/conflict | ACLED | ⚠ non-commercial license |
| Air quality | OpenAQ | free key |
| Flights | OpenSky / Wingbits | free OpenSky key |

## GROUP 4 — Wildcards (keyless, addable anytime)
VIIRS night-lights (economy/blackout extrusion) · WorldPop / **Kontur H3** population skyline (`H3HexagonLayer`) · TeleGeography submarine cables (arcs) · Marine Regions EEZ (jurisdiction choropleth).

---

### How they combine (persona-first)
- **Default view:** persona region (e.g., Telangana) — Group 1 lit, Group 2 events clipped to the region.
- **Zoom out:** Group 2 fills in the national/global backdrop (World Bank, GDELT, conflict).
- **Click anything:** Groq/LLM reads the underlying rows → a written situation note (faithful, cited).
- **Genericity:** geoBoundaries + GDELT mean the *same* map works for any persona on Earth with zero per-region config.

### Built status (2026-06-03)
- **Shipped & verified live:** district choropleth + 6 surfaces (Stance · Volume · Revanth · Outlets · Surge · Issue), Issue 8-topic sub-filter, **6-week replay scrubber**, narrative arcs, 3D/Flat, hover cards, and **2 live overlays — Fires (NASA FIRMS) + Quakes (USGS)** through our own proxy with reused keys. All on real DB data, World-Monitor-independent.
- **Live-source drift (verified, important):** the "keyless" catalog has rotted — **GDELT geo 404s, UCDP now 401 (needs token), ReliefWeb v1 410 Gone, GDELT DOC 429-throttled.** Only FIRMS (keyed) + USGS (keyless) are reliable right now. The GDELT "News" overlay was built then removed for this reason; re-add when a working geocoded news endpoint is sourced.
- **Run it:** `npm run dev:server` (proxy :8788) + `npm run dev` (app :5180).
- AviationStack key valid but 429; ACLED non-commercial. Re-verify every external endpoint before wiring — they drift.

### ⚠ Event-layer caveat (verified 2026-06-03)
`article_events` is **NOT map-ready as-is**: (1) geo = the *article's* district, not the
*event's* location ("Monsoon reaches Kerala" → tagged Hyderabad); (2) ~70% is
non-political noise (film releases, sports, accidents, celebrity tweets); (3) `is_future`
is unreliable (dates span 2014→2050); (4) 39,990/40,053 rows are un-deduplicated
(clustering never ran). **Use GDELT** (which geocodes to the real event location) for an
events layer instead — or restrict `article_events` to political types
(`protest`/`election`/`arrest`), dedupe, and a sane date window, then render as a
district-level *count of political events in coverage* (not precise pins).
