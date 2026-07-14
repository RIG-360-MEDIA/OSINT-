# RIG OSINT Agent — Full Feature Inventory (social → now)

**Written 2026-07-10.** Everything built across the OSINT-agent arc, from the social
rebuild through identity footprint. Status is honest: PROVEN/LIVE vs DEFERRED. Grounded in
the memory record + handoff docs — verify live before quoting to a client.

---

## 1. SOCIAL MEDIA — keyword collection (PROVEN)
Framework: `backend/collectors/cheap_stack/` swap-able Method protocol, verified on Hetzner
datacenter IP. Per-platform keyword search:
- **Instagram** — direct `web_profile_info`+`x-ig-app-id` (no relay); global keyword search
  via SearXNG (`site:instagram.com` → shortcodes/handles) + authed feed for fresh posts.
- **TikTok** — tikwm `user/posts` + `feed/search` keyword + HTML fallback.
- **Telegram** — `t.me/s` web, no bot token.
- **Twitter/X** — twscrape (cookies) + Nitter keyword search (only official API is dead/402);
  ~38k live rows.
- **Reddit** — keyword + subreddit search.
- **YouTube** — free box-native transcripts (kome.ai) + innertube keyword search.
- **WeChat** — public Official-Account content-fetch (curl_cffi) + DDG-dork discovery
  (no China IP; title-level).
- **VK** — token-based keyword search (needs free VK token).
- Shared: proximity relevance gate, 90-day freshness cap, persist-from-use.

## 2. FREE NON-SOCIAL OSINT SOURCES (PROVEN, live in osint-backend `/api/keywords/*`)
10 sources, verifier `verify_osint_sources.py` (Indian Army 9/10, Windlass 7/10 honest):
- **SearXNG web** (official-domain derivation) · **Company/GLEIF** (fuzzy resolve, national
  reg-id, hierarchy, match_confidence) · **Infrastructure** (crt.sh subdomains, ip-api ASN,
  CDN) · **Wayback** (yearly timeline + gaps) · **Academic/OpenAlex** (fields, OA pdf) ·
  **Stats/World Bank** (military exp, exports) · **GDELT** (fixed — real global articles) ·
  **Wikipedia/Wikidata** · **Geo/Nominatim** · **Tenders** (TED EU keyword engine + India
  CPPP latest-feed).

## 3. GEOSPATIAL / SATELLITE CHANGE-DETECTION (PROVEN, Phase 1)
`products/osint/backend/satellite/` — free Sentinel imagery + unsupervised change detection,
on-demand, isolated. Optical (NDVI/NDWI/NDBI + CVA) via AWS Earth Search; radar
(VV-backscatter flood) via Planetary Computer Sentinel-1-RTC. Caught 2022 Sindh flood
(radar-through-cloud) + Jewar airport construction. ~10m ceiling (not vehicles). Endpoint/UI
deferred.

## 4. IMAGE / MEDIA VERIFICATION (LIVE — api.rig360media.com/media/)
Reverse-search + fact-check heuristic + EXIF + GPS + ELA tampering signal. Badge on
night-desk dossier feed (cached + on-demand). Fusions: image GPS → satellite change;
image → corpus via dHash index (match by identity, not URL). Signal-not-proof; no deepfake
verdict, no face-search.

## 5. IDENTITY FOOTPRINT (PROVEN, Phase 1)
`verify_identity_footprint.py` — public accounts only. Username=maigret (+false-positive
filter/confidence), email=holehe (breach-boolean DISABLED — HIBP paid), phone=phonenumbers.
Same-username≠same-person caveat surfaced. Off-limits (broker/breach-data/face) NOT built.

## 6. KEYWORD INTELLIGENCE / DOSSIER (backend built; UI HIDDEN — the deferred layer)
- `keyword_dossier.py` (volume, sentiment, top articles/accounts, harmful accounts, related
  entities), `tasking_brain.py` (classify → source plan), keyword tracking/alerts (partial),
  perspective lens, on-demand keyword sentiment (`keyword_sentiment.py`).
- **STATUS: the dossier TAB is hidden from all roles** — it only reads pre-stored data and
  collapses on a fresh keyword. The intelligence/fusion/evidence layer that makes it a real
  product is the **still-deferred next step** (evidence-linking, on-demand trigger, fusion,
  tracking/alerts, re-enable).

## 7. SENTIMENT + CLIENT API (LIVE)
- Sentiment engine v2 (two-field stance+impact, guided JSON); keyword sentiment on-demand
  (cache 0.4s vs 14s cold).
- `/v1` client/partner API (osint-backend): two-field per-pillar sentiment, entity_id,
  drill-down symmetry, source filter, keyword scope, cursors, webhooks. DEPLOYED.

## 8. HARDENING / OPS (LIVE)
Watchdogs so these don't silently die: today-watchdog (`_today_watchdog.sh`), collector
health (`_collector_health.py`), v9-forward systemd watchdog. Backfill lanes + crons.

---

## Honest status summary
- **Collection = comprehensive and proven** across ~19 source types (social + OSINT +
  satellite + image + identity), each verified on real inputs with honest limits labeled.
- **The product/intelligence layer = the remaining gap.** Everything above COLLECTS; the
  layer that FUSES + makes it verifiable + trackable in one client-facing surface (the
  dossier done right) is deferred. That — not another source — is the highest-value next
  build.

## Where the detail lives
- Handoff docs: `docs/handoffs/{keyword-social-rebuild, osint-sources-buildout,
  geospatial-satellite-buildout, image-media-verification-buildout,
  identity-footprint-buildout}-handoff.md`.
- Memory index: `~/.claude/projects/C--Users-Dell-Desktop-rig-surveillance/memory/MEMORY.md`.
