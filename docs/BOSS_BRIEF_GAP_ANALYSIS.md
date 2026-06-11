# Boss's OSINT Brief Frontend — Feature Gap Analysis

**Source:** `C:\Users\Dell\Desktop\OSINT BRIEF FRONTEND\` (1,600-line app.jsx + 382-line data.js + 47 React components + 281 KB styles.css)

**Subject of the brief:** Telangana political intelligence focused on CM Revanth Reddy; tracks 8 entities (Revanth, KCR, KTR, Bandi Sanjay, Owaisi, Dharani, Musi, Kalesh).

**Verdict at a glance:** Of **47 component features**, **18 are READY**, **20 need NEW AGGREGATION** (data exists, no endpoint yet), **9 need NEW LLM WORK** (synthesis prompts, no current source). **0 are impossible.**

---

## Section 1 — Top Bar + Masthead

| Feature | Status | Backend / Why |
|---|---|---|
| TopBar with date / refresh / SEND REPORT | ✅ READY | UI-only |
| LiveDot + Countdown to next refresh | ✅ READY | UI-only |
| BriefMasthead (Tuesday, 13 May 2026 · 06:00 IST) | ✅ READY | UI-only |
| SystemStatusBand ("System online · 247 sources · 98.7% integrity") | ✅ READY | Maps to `/api/observe/corpus-overview` + `/source-scorecard` |
| KPI tiles: Articles parsed (247) / Outlets (18) / Languages (3) / Sentiment (-0.4) | ✅ READY | All four already in `corpus-overview` |

---

## Section 2 — Defining Stories (Top 5)

| Feature | Status | Backend / Why |
|---|---|---|
| Story rank + headline + summary | ✅ READY | `event_clusters` ordered by `importance_score` (T5) |
| Stance dot per story | ✅ READY | `article_stances` aggregated per cluster |
| Spark (24h velocity per story) | ⚠️ AGGREGATION | New: bucket `article_events.collected_at` by hour per cluster |
| Metrics (articles × outlets × vs%) | ✅ READY | `event_clusters.article_count, source_count` + entity_mention surge |
| Coverage breakdown (crit / neu / sup %) | ⚠️ AGGREGATION | Compute from `article_stances` per cluster |
| Lens cards (1 quote per outlet, with stance + language) | ⚠️ AGGREGATION | Join `article_quotes` × `article_stances` per cluster |
| Cite blocks (3 outlets per story with article counts) | ⚠️ AGGREGATION | Group `article_events` by source per cluster |
| Principal quote per story | ✅ READY | `article_quotes` top-confidence per cluster |
| Thumbnail | ⚠️ AGGREGATION | `articles.og_image` exists; pick best per cluster |
| ImpactRing (visual score) | ✅ READY | `importance_score` from T5 |

---

## Section 3 — Voices Overnight

| Feature | Status | Backend / Why |
|---|---|---|
| MediaVoiceItem (editorial quotes, with stance) | ⚠️ AGGREGATION | Join `article_quotes` with stance-tagged outlets |
| OppVoiceItem (opposition figures' quotes) | ⚠️ AGGREGATION | Filter quotes where speaker is a politician (use entity_dictionary) |
| QuoteCard (large featured quote of the morning) | ✅ READY | Top quote in last 12h by importance |

---

## Section 4 — CM / Counter-Messaging panels

These are Telangana-political-context specific (Counter Messaging = mapping opposition narratives vs CM messaging):

| Feature | Status | Backend / Why |
|---|---|---|
| CmDriving (which narrative CM is pushing) | 🆕 NEED LLM | New prompt: synthesise CM's narrative thrust from his quotes |
| CmInlineSentiment | ⚠️ AGGREGATION | Sentiment of articles ABOUT CM |
| CmOppPressure (opposition counter-narrative strength) | 🆕 NEED LLM | New scoring: opposition quote weight × source reach |
| CmPerspective (broader frame) | 🆕 NEED LLM | LLM synthesis of CM's positioning |
| CmVoicesGrid (sentiment grid of voices on CM) | ⚠️ AGGREGATION | Stance × speaker matrix |
| OutletBiasSnapshot (per-outlet bias vs CM) | ⚠️ AGGREGATION | Avg stance per source on Revanth-tagged articles |

---

## Section 5 — Watched Entities (8 cards)

| Feature | Status | Backend / Why |
|---|---|---|
| WatchedEntityCard (name, role, init avatar) | ✅ READY | Hardcoded entity list (Telangana 8); meta from `entity_dictionary` |
| 24h mention curve sparkline | ✅ READY | `entity_mention_daily` (T6) — already has daily aggregate |
| Mention count + % change vs baseline | ✅ READY | T6 has 7-day baseline + surge_ratio |
| Sentiment score per entity | ⚠️ AGGREGATION | Avg `article_stances.intensity` for entity's articles |
| Latest quote with stance + context | ✅ READY | Most-recent `article_quotes` where speaker = entity |
| "Live" badge if active in last hour | ✅ READY | Check `entity_mention_daily` today vs hour |
| WatchSummary (overall watch-list health) | ⚠️ AGGREGATION | Roll-up of 8 entities' surge_ratios |

---

## Section 6 — Climbing Stories (trending up rapidly)

| Feature | Status | Backend / Why |
|---|---|---|
| 3 climbing items with mention count, vs%, window (4H/5H/6H) | ✅ READY | T6 `surge_ratio` with hour-window query |
| Recommendation chip ("BRACE FOR EVENING BULLETIN") | 🆕 NEED LLM | New prompt: tactical advice based on surge pattern |

---

## Section 7 — Blindspot Analysis

| Feature | Status | Backend / Why |
|---|---|---|
| Telugu-led vs English-led story split | ⚠️ AGGREGATION | Group `event_clusters` by majority language of contributing articles |
| Top Blindspots panel | ⚠️ AGGREGATION | Stories covered in one language community, missing in the other |
| Blindspot Comparison (T-count vs E-count per story) | ⚠️ AGGREGATION | Pivot of above |
| BlindspotKeyInsights (qualitative) | 🆕 NEED LLM | Summary of why this gap matters |
| NarrativeGapOverview | 🆕 NEED LLM | LLM synthesis of structural narrative gaps |
| NarrativeDiversityScore | ⚠️ AGGREGATION | Shannon diversity of stance + language mix |

---

## Section 8 — Horizon (7-day forecast)

| Feature | Status | Backend / Why |
|---|---|---|
| 7-day calendar (TUE-MON) with events per day | ✅ READY | `article_events` where `is_future=TRUE` (T12 cleaned), grouped by date |
| Event chip with type (cabinet / press / court) + source | ⚠️ AGGREGATION | Need `event_type` tagging — partial in `canonical_event_type` |
| ForecastPulse (narrative forecast for the day) | 🆕 NEED LLM | New prompt: predict next-24h news drivers |
| HorizonOutlook (one-paragraph forward look) | 🆕 NEED LLM | Same |

---

## Section 9 — Emerging Signals / Network / Mood

| Feature | Status | Backend / Why |
|---|---|---|
| EmergingSignals (low-volume, high-rise-rate entities) | ✅ READY | T6 — entities with `is_new` flag + high surge_ratio |
| NetworkPanel (entity co-mention graph) | ⚠️ AGGREGATION | New query: entity-pair co-occurrence in same article |
| MoodSection (overall corpus sentiment) | ⚠️ AGGREGATION | `article_stances` rolled up by hour |
| Waveform (sentiment time-series) | ⚠️ AGGREGATION | Same as above, hourly buckets |
| AtmosphereLayer (visual gradient backdrop) | ✅ READY | UI-only |
| MiniIndia (state-level mention heat-map) | ⚠️ AGGREGATION | `article_locations.region` grouped by state |

---

## Section 10 — Recommended Reading

| Feature | Status | Backend / Why |
|---|---|---|
| 4-6 long-form pieces from major outlets, with byline + word-count + stance | ⚠️ AGGREGATION | Filter `articles` where `article_type='analysis'` or `'opinion'`, length > 800 words |

---

## Footer

| Feature | Status |
|---|---|
| FooterStrip (sign-off line) | ✅ READY (UI-only) |

---

## Tally

| Category | Count | What it means |
|---|---|---|
| ✅ **READY** | 18 | Wire to existing endpoint; pure frontend work |
| ⚠️ **AGGREGATION needed** | 20 | Data is there; need new SQL aggregation endpoint |
| 🆕 **NEW LLM SYNTHESIS** | 9 | Need new LLM-call helper + maybe scheduled task |
| ❌ **CAN'T DO** | 0 | None impossible. |

---

## Critical missing CONTENT pieces (not features)

1. **Per-entity sentiment scores** — `article_stances.intensity` exists but isn't per-entity-aggregated yet
2. **Speaker → entity_dictionary link** — known broken; doesn't block this UI but limits "show me all quotes from KCR"
3. **English vs Telugu narrative gap analysis** — entirely new pipeline
4. **CM-specific counter-messaging logic** — Telangana political domain knowledge needed in prompts
5. **Tactical recommendations** ("BRACE FOR EVENING BULLETIN") — new LLM prompt + heuristics

---

## Recommended execution order

1. **Phase A (1-2 days):** Build the 20 aggregation endpoints. Pure SQL/Python, no LLM. Unblocks ~80% of the brief.
2. **Phase B (3-5 days):** Wire 18 ready + 20 aggregations into the boss's frontend (mostly find-and-replace mock data → real API).
3. **Phase C (1 week):** Build the 9 LLM-synthesis pieces — CM/Driving, Blindspot Insights, Forecast Pulse, Tactical Recs. Each is a new prompt + a daily Celery task.
4. **Phase D (ongoing):** Refine, test on real data once T4 finishes filling claims.

**Net:** the brief is **buildable in ~2 weeks** with current data + small LLM additions. **Nothing in the boss's mockup is infeasible.**
