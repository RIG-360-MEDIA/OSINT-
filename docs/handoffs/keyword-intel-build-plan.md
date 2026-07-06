# Keyword-Intelligence Product — Complete Build Plan (0 → 100)

**Product.** User types any keyword (person / org / place / event / phrase) from a chosen
**perspective** → gets a live, cross-source, cross-lingual **Dossier** (summary, volume,
sentiment, top content, top/harmful accounts, related entities) → can **track** it for alerts.

**Architecture rules (fixed).**
- **Store-everything = ONLY articles + newspapers** (the 875k+ corpus → instant history).
- **Social + all other OSINT sources = keyword-driven on-demand** (Meltwater model): collect
  only what's searched/tracked, score inline, **persist-from-use**. REMOVE broad social saving.
- **Sentiment is DIRECTED** (toward the keyword), never generic post polarity.

**Verified reality (2026-07-06/07, live DB — drives this plan).**
- News corpus 910k, 28k/day, 81% entity-tagged; `article_stances` 1M (directed, quality).
- `entity_dictionary` 19,385 (type+aliases+party+country) → clean keyword classification.
- Social LIVE but broad/noisy (50k posts: twitter/reddit/telegram/instagram); enrichment ~14%.
- `social_posts` schema RICH: `toxicity`, `weaponization_signals`, `coordination_cluster_id`,
  `sentiment_score`, `emotion`, `entities_extracted` (under-populated but present).
- `notification_rules`/`notification_events` DO NOT EXIST; `velocity_baselines` EMPTY.
- Existing reuse: `backend/sentiment/keyword_sentiment.py` (on-demand niche-keyword sentiment),
  `top_articles.py`/`dossier.py` (dossier pattern), night-desk `Dossier.jsx` + charts kit.

**Validation rule:** each phase has a GATE. Do not advance until the gate passes on live data.

---

## PHASE 0 — Foundation & reality check ✅ DONE
- Verified corpus/social/entity/alert reality vs live DB; corrected false "reuse" assumptions.
- Built search indexes: migration `120_keyword_search_indexes.sql` (pg_trgm GIN on title /
  post_text / stance actor) — applied CONCURRENTLY on prod.
- **GATE ✅:** regex search that timed out now instant (semiconductor 55s→<1s); disk checked (39G free).

## PHASE 1 — Keyword Dossier backend ✅ DONE (commit 11b9d5e)
- `products/osint/backend/keyword_dossier.py` (builder) + `routers/keywords.py` + `main.py`.
- `GET /api/keywords/search?q=&days=` → volume+velocity, directed sentiment distribution, top
  articles (tone), cross-platform social counts+samples, related co-mentioned entities.
- Word-boundary search (kills "Modi"→"Modified"); `make_interval` params (asyncpg-safe).
- **GATE ✅:** live vs prod DB — modi: vol 422/+2.2%, sentiment positive 0.488 (n=7265), social
  1991/4 platforms, related=Indo-Pacific diplomacy; semiconductor→Gujarat/Sanand/Viksit Bharat.

## PHASE 2 — Tasking brain ✅ DONE (commit follows 11b9d5e)
- `tasking_brain.py`: classify (person/org/location/topic) via canonical-or-alias dictionary
  match + India-primary disambiguation tie-break → justified source plan (live vs planned) +
  default perspective. `GET /api/keywords/plan`; merged into `/search`.
- **GATE ✅:** modi→person/BJP/india, reliance→org/india, adani→Gautam Adani/IN/india (disambig
  fix), semiconductor→topic. Known data gap: Indian Hyderabad missing from dictionary.

---

## PHASE 3 — On-demand social + directed sentiment  ⬜ NEXT
**Goal:** social becomes keyword-triggered on-demand (retire broad saving); sentiment computed
inline on the pulled batch + niche-article sentiment reused.
**Steps:**
1. Retire broad `social_watchlist` saving (whole subreddits/standing handles) → keep only
   keyword/entity/tracked targets. (Coordinate with any parallel social-pipeline work.)
2. On-demand collector: a keyword search/track triggers a live pull (cheap_stack collectors,
   ban-safe pacing) → land only keyword-relevant posts → persist-from-use.
3. **Inline directed sentiment scorer** for the pulled batch (fast local multilingual on 4090;
   escalate to two-field LLM for tracked keywords). Score sentiment TOWARD the keyword.
4. Wire existing `backend/sentiment/keyword_sentiment.py` into the Dossier for **niche/topic**
   keywords (not in `article_stances`). Blend media vs public sentiment in the gauge.
**GATE:** search a fresh keyword → relevant social pulled + directed-scored + persisted;
niche keyword (e.g. "semiconductor policy") returns a real sentiment via keyword_sentiment.py;
repeat search served from cache. Verify counts + a scored sample on live data.

## PHASE 4 — Deploy backend + Frontend Keyword Dossier page  ⬜
**Goal:** make Phases 1–3 real and usable.
**Steps:**
1. Deploy: get code onto `/root/rig`, rebuild `osint-backend` image, restart; smoke-test
   `/api/keywords/search` + `/plan` over HTTP. (Outward-facing → checkpoint with user.)
2. Frontend `src/pages/Keywords.jsx` (route in `App.jsx`) — generalize `Dossier.jsx`: free-text
   search + perspective/timeframe controls; reuse Sparkline/RankBars/VerticalGauge/Sources/
   Panel/CountUp; sections = summary, volume, sentiment (media vs public), top content, top
   accounts, related entities, source-plan chips.
**GATE:** load night-desk (preview), search "modi" → dossier renders with real API data;
app imports clean (already verified deploy-ready); no console errors; screenshot proof.

## PHASE 5 — Tracking + alerts + velocity (build from scratch)  ⬜
**Goal:** "track a keyword → early alerts." (Alert tables don't exist; velocity empty.)
**Steps:**
1. Migration: `keyword_watch` (user_id, keyword, classification, perspective, cadence) +
   `keyword_alerts` (watch_id, type[spike|sentiment_flip|new_harmful_actor|new_narrative],
   payload, fired_at, seen_at). Additive/safe.
2. `POST /api/keywords/{q}/track` / `DELETE` / `GET /api/keywords/tracked`.
3. Velocity: populate baselines (rolling mean/stddev of keyword volume) — reuse
   `entity_mention_daily`/`_vs_pct` pattern; compute per tracked keyword.
4. Beat job: re-collect tracked keywords on cadence → diff vs baseline → fire alerts
   (spike / sentiment-flip / new harmful actor). Notifications API + frontend bell.
**GATE:** track a keyword; inject/observe a real spike → `keyword_alerts` row + UI bell; no
duplicate/flapping alerts across two cycles.

## PHASE 6 — Voices/SNA + Harm & Threat Radar  ⬜
**Goal:** who drives a keyword + what's dangerous. (Leverage EXISTING toxicity/weaponization/
coordination_cluster_id columns; top-accounts query already validated.)
**Steps:**
1. Top accounts per platform (validated: modi→ANI/PTI/WION/IndiaToday…) + engagement.
2. Harmful accounts: rank authors by `toxicity` / `weaponization_signals` / membership in a
   `coordination_cluster_id`. Coordinated-cluster surfacing (clusters currently 0 → also
   compute on the on-demand batch).
3. Actor network graph (igraph/Louvain, reuse clustering infra) over reply/mention/co-post →
   hubs, bridges, amplifiers. Endpoint + network view.
4. Harm Radar: rank harmful items (toxicity + coordinated + recycled-media/fact-check) by
   severity; red panel.
**GATE:** for a live keyword — top accounts + ≥1 harmful/coordinated signal surfaced with
evidence; network graph renders roles; harm list ranks by severity. Verify on real data.

## PHASE 7 — Perspective Lens + other-source collectors  ⬜
**Goal:** the moat (India vs US vs CN framing) + expand beyond news/social on-demand.
**Steps:**
1. Perspective: wire national/lingual sources (GDELT global free feed + national engines via
   SearXNG) + framing-divergence (stance by source-origin) leaning on LaBSE → side-by-side
   lenses + blindspot detection.
2. On-demand collectors for the next OSINT source-types the Tasking brain routes to (images /
   company-registry / domain-infra / documents) — one at a time, cheap_stack-style, gated legal.
3. Fill the Tasking-brain "planned" sources as each collector lands (flip status live).
**GATE:** search an event keyword → India vs US/CN framing renders with a real blindspot; at
least one new source-type (e.g. company-registry or domain-infra) returns live data for a
matching keyword.

---

## Cross-cutting
- **Deploy discipline:** osint-backend is baked → rebuild to ship; rig-backend bind-mounted →
  live on worker restart. Prod deploys are checkpointed with the user (outward-facing).
- **Legal gates:** face-search/people-search/breach/dark-web stay off or hard-gated per the
  feature-map boundaries.
- **Verification pattern (reused all session):** validate SQL vs live DB → build → import-check
  in container → run builder in container with real config → commit. No assumptions.
- **Status:** Phases 0–2 DONE+verified+committed & deploy-ready. Phases 3–7 specified with gates.
