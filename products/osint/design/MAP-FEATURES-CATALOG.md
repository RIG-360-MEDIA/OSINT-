# Map Features — what the database can *actually* power

Deep-dive of the Hetzner DB (2026-06-02), verified with live queries. Every
feature below is rated by what the data can do **and whether it's trustworthy /
useful** — not just technically possible. Stance always = `article_stances`
(never `register_emotion`).

## The geo data we have (verified row counts)

| Table | Rows | What it gives the map |
|---|---|---|
| `article_districts` | **34,051** | article → Telangana district, 2017→2026 (9 yrs), daily granularity |
| `districts` (TG) | **33** | district names, `centroid_lat/lon`, aliases |
| `article_events` | **264,474** | dated events (type, actors, `is_future`) — joinable to districts via article |
| `article_entity_mentions` | matview | `article_id, entity_id, canonical_name, entity_type` — entity → district |
| `article_stances` | 165k | supportive / critical per article (district mood proxy) |
| `acled_events` | **0 (EMPTY)** | schema ready: `event_date, type, actor1/2, fatalities, lat, lon` — wire ACLED API |
| `social_post_districts` | **0 (EMPTY)** | Reddit/Telegram → district; needs geo-tagging |
| `coverage_gaps_daily` | 31 | per-entity blindspot ratio (not geo) |

Article rows carry `geo_primary`/`geo_secondary` (country/state names: India 12.7k,
US 2.9k, Nigeria 1.9k…) — coarse, but enough for a **world/national backdrop** layer.
No per-article lat/lng — points come from district centroids (or ACLED once wired).

---

## TIER 1 — Build now · real data · high signal

1. **District choropleth (coverage × stance)** — *shipped.* 34k rows. Height = coverage,
   fill = net stance. The base layer.
2. **Issue / topic layers** — `topic_category × district`, verified: Politics 3077,
   Security 1625, Legal 1224, Infrastructure 756, Agriculture 769, Health 681,
   Governance 481, Environment 588. Toggle "show only the AGRICULTURE map" etc.
   *(Drop OTHER 7773 + SPORTS 1423 — noise.)*
3. **Time-replay scrubber** — daily counts, **9 years of history**. Animate coverage
   day-by-day. Verified May 20–Jun 2 (29–681/day). The real version of the fake scrubber.
4. **Animated stance shift** — per-district sup/crit over time. Verified: Hyderabad
   went **89/123 critical (May 25) → 286/140 supportive (May 31)**. "Watch hostility move."
5. **Narrative-spread arcs** — *shipped.* District co-mention (Adilabad↔Komaram Bheem 918…).
6. **Event layer** — **4,255 events** mapped to TG districts, incl. **2,238 future/scheduled**.
   Types: announcement, election, protest, legal, meeting, statement. Plot by district,
   filter by type, **"what's coming" toggle** (is_future) = a genuine intelligence edge.
7. **Persona filter — "your coverage only"** — watchlist-scoped district footprint.
   Verified Revanth: Hyderabad 339, Rangareddy 36, Kumram Bheem 30, Karimnagar 25.
   Toggle: all-Telangana ⇄ watchlist-only.

## TIER 2 — Useful, derive with care

8. **Media footprint** — outlets per district (Hyderabad 178, rural ~20). "Which papers own which turf."
9. **Hotspot / surge** — rising-coverage velocity (last-7d vs prior), derived from the daily series.
10. **World / national backdrop** — `geo_primary` country/state choropleth for the international
    layer when zoomed out (the "national weather" context).

## TIER 3 — Schema ready but EMPTY (wire an API → instant layer)

11. **ACLED protest/conflict points** — table built (`lat, lon, event_type, fatalities`) but **0 rows**.
    Ingest the ACLED feed → real geocoded protest/violence pins. High value, needs the collector.
12. **Social geo** — `social_post_districts` **0 rows**. Needs Reddit/Telegram posts geo-tagged.

## SKIP / NOT TRUSTWORTHY (data-quality limited)

13. **Generic "who owns this district"** (top person per district from raw NER) — **noisy**:
    returned "Ratna De Nag" (Bengali MP) for Adilabad, "Revolutionary Marxist Party" as a
    *person* for Hyderabad, cricketers, etc. Entity-type + disambiguation errors. **Only use
    scoped to the 66 verified watchlist entities** — never the raw mention table.
14. **`coverage_gaps_daily`** — 31 rows, per-entity, not geographic. A side blindspot panel, not a map layer.

---

### Recommended next build order
Issue-layer toggle (2) → time-replay (3) + animated stance (4) → event layer with
future toggle (6) → persona "your coverage" filter (7). Then wire **ACLED** (11) for
the standout external layer. Skip generic entity-turf until NER is watchlist-scoped.
