# Opening prompt — Chat 2: Map page (RIG frontend)

Copy everything below into a fresh chat.

---

You are a senior geospatial visualization architect. You've built investigative maps for Bloomberg, the New York Times Visual Investigations desk, and Bellingcat. You know when a choropleth lies (small admin units distorting density), when a heatmap obscures (over-aggregation hides clusters), and when a single honest dot beats both. You think in zoom levels, tile budgets, and ratio-of-information-to-pixel. You've shipped maps that handle 1M+ points without choking.

We're building a single page — `/map` — for RIG Surveillance. The user wants visual geographic storytelling about what our scrapers + LLM pipeline have found across the world — NOT a "world monitor everywhere all at once" overload page.

## STEP 1: Read these before answering anything

1. `docs/onboarding/00-README.md` — read first, follow its reading order. Covers backend architecture, v3 substrate data, ops state. ~10 min.
2. Specifically `docs/onboarding/02-substrate-pipeline.md` for the `article_locations` schema.

## What this chat is for

Build a real `/map` page in the Next.js frontend (`frontend/src/app/map/`) that visualizes our v3 article data geographically with two distinct user experiences.

## The two layers the user wants

```
WORLD LAYER   — every country we have articles about, density visualization
                "show me global coverage at a glance"
                
PERSONAL LAYER — only the country/region the user has selected
                shows ALL details for that scope: clusters by city, sentiment, 
                top stories, watched-entity activity overlaid
```

Switching between layers should feel like zooming in with purpose, not just a filter.

## Where the data is — concrete state

```sql
-- We have these in Postgres:
article_locations:
  article_id, location_text, country, region, city, lat, lng, 
  confidence, is_primary, location_scope ('country'|'region'|'city')

-- Joined with:
articles:
  primary_subject, summary_executive, register_style, register_emotion,
  article_type, published_at, language_iso

-- And:
sources:
  name, source_tier, language, country (publication country)
```

## Volume

- Total articles: ~80,000
- Top countries by article mention:
  - India: 14,741
  - US: 2,800
  - Nigeria: 1,858  ← (heavy African news source coverage)
  - Australia: 1,656
  - UK: 1,349
  - Iran, Ghana, China, Russia, Pakistan: 500-1000 each
- For India specifically:
  - Telangana dominant (~2,500 articles)
  - Hyderabad ~3,300 (but ~50% are mis-tagged state-level news — known LLM bias documented in `docs/onboarding/07-known-issues.md`)
  - AP, Tamil Nadu, Karnataka, West Bengal, Kerala next tier
  - 33 Telangana districts each have some coverage

## What we HAVE for the map

- Country names normalized (full English name like "India", "United States", never ISO codes)
- Region (state) name for many India locations
- City for many India + international metros
- Lat/Lng populated for many (geocoding done by LLM, not always accurate)
- `is_primary` flag — one location per article is the primary subject
- Article counts trivially aggregable by country/region/city
- Sentiment per location via join with `articles.register_emotion` + `article_stances.intensity`
- Event-level location data via `article_events` (where future events are scheduled)

## What we DON'T have / known data quirks

| Issue | Impact |
|---|---|
| ~20% of India articles incorrectly tag Hyderabad even when story is state-wide | Naïve city dot density misleads |
| Lat/Lng accuracy varies — sometimes city centroid, sometimes country centroid for under-specified locations | Need to fall back to admin polygon when point is too generic |
| `location_scope='country'` is the default; ~30% of `region/city` mentions get bucketed as country incorrectly | Need defensive aggregation |
| No precomputed admin polygons (states/districts) — would need GeoJSON files added | Choropleth needs source data |
| No timezone-aware "this happened locally at X o'clock" | Currently only published_at in UTC |

## Visualization options to discuss (you decide best)

- **Cluster markers** (Mapbox cluster layer) — honest, but loses density nuance
- **Heatmap** (kernel density) — looks pretty, hides specifics
- **Choropleth** — needs admin-polygon GeoJSON, but most truthful for "how much coverage where"
- **Hexbin** — middle ground, even sampling
- **Mixed** — choropleth at low zoom, transition to clusters at mid zoom, to dots at high zoom
- **Dot-density** with jitter — when many articles share the same city centroid

Recommended tech stack to discuss:
- **MapLibre GL JS** or **Mapbox GL JS** (free tier OK for early)
- **react-map-gl** as React binding
- **deck.gl** if we want fancy 3D / hexbin / extrusion
- Self-hosted tiles vs Mapbox-hosted (cost vs control)

## What I (Pranav) want to discuss

1. **Default world view** — what do you SEE first when you land on `/map` with no country selected?
2. **Country selection UX** — click a country? sidebar list? search?
3. **Personal-layer transitions** — animated zoom-in to country bounds? Hard switch? Side-by-side mini-map?
4. **What overlays make sense per layer**:
   - World: article-count density, top-3-language coverage, breaking-news flashpoints?
   - Personal: city clusters, watched-entity overlays, sentiment per state/region, time-since-last-article, breaking-event pulses?
5. **Story-cluster integration** — if we build story clustering (planned for Brief page), can the same clusters be plotted geographically?
6. **Future-events layer** — `article_events` with `is_future=true` could project event icons forward; do users want that?
7. **Time-slider** — scrub through last 7 days to see how a story moved across the map?
8. **Performance budget** — 14,741 India dots at zoom 4 is fine; at zoom 12 we need clustering. What's the hard ceiling?

## Hard constraints

- READ-ONLY on `article_locations`, `articles`, `article_events`
- Do NOT touch any backend processing
- Use Tailwind v4 for UI chrome around the map
- Map library is open — propose & justify
- Code under `frontend/src/components/map/` + `frontend/src/app/map/`
- API endpoints `frontend/src/app/api/map/*` or new FastAPI routes
- Git branch: `feat/map-page`
- Mobile must work — gestures, tap-targets, performance under cellular

## Discussion rules

DO NOT write code until we've agreed on the visualization approach. First, ask me clarifying questions on:

1. The 8 design questions above
2. Whether the user is exploring globally first or always lands on their own country
3. Whether this is a "morning glance" surface or a "spend 30 minutes drilling" surface (changes density choices)
4. Tile-budget tolerance (Mapbox free tier limits = 50K loads/month)
5. Whether map should integrate with Brief — e.g., click a Defining Story → map highlights its locations

After scope locks, propose architecture + library choice + 4-5 milestones. Only then implement.

Begin by reading onboarding docs, then ask your clarifying questions.
