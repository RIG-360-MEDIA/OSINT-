# Social Intelligence — Future-Proof Data Layer & Feature Backlog

The governing principle: **extract once, capture maximally, derive forever.**
We build a small set of features now, but the **atomic data + extraction layer** is a
superset designed so every feature below (selected, competitor, or future) can be built
later as a *derivation* — without re-ingesting or re-extracting anything.

---

## 0. The principle — three tiers of data

| Tier | What | Rule | Examples |
|---|---|---|---|
| **CAPTURE-NOW** (irreversible) | facts that exist only at collection time | must store from day 1 — *cannot* be recovered later | engagement snapshots over time, network edges, author state at post-time, raw payload, deleted-post bodies, media URLs |
| **EXTRACT-ONCE** (rich LLM pass) | structured meaning from text | one superset extraction → never re-run for a new feature | sentiment+emotion, entities, directed stance, claims(+embedding), language, geo, summary |
| **DERIVE-ANYTIME** (cheap, downstream) | aggregations, scores, models, delivery | add feature-by-feature later, no schema change | share-of-voice, velocity, anomaly z-scores, forecasts, NWS, personalization, briefs, alerts |

**The whole trick:** push everything possible into DERIVE (so features are cheap later),
and be ruthless about CAPTURE-NOW (so you never lose what you can't get back). Most of
the 60 features you picked are DERIVE-tier — they need the atomic layer to be right, not
to exist yet.

---

## 1. Atomic schema (the "never remake" foundation)

### `social_authors` — account as a FIRST-CLASS entity
*(biggest departure from the article substrate; ~15 of your picks need it)*
```
id bigserial PK
platform, platform_user_id   UNIQUE(platform, platform_user_id)
username, display_name, bio
verified bool, account_created_at
followers, following, post_count        -- current snapshot
influence_score real        -- DERIVED later (nullable)
bot_likelihood real         -- DERIVED later (nullable)
cadence_mean_sec, cadence_cv real       -- posting rhythm (bot signal)
home_geo, home_state, language
first_seen_at, last_seen_at, raw jsonb
```

### `social_author_snapshots` — author metrics over time (append-only)
```
author_id FK, captured_at, followers, following, post_count
```
*Enables follower-velocity, influence-over-time, "rising account" detection.*

### `social_posts` — the atomic post
```
id bigserial PK
platform, platform_post_id              UNIQUE(platform, platform_post_id)
author_id FK -> social_authors
post_text, post_url, posted_at
-- THREAD / NETWORK structure (capture-now)
in_reply_to_post_id  self-FK
quoted_post_id       self-FK
conversation_root_id, thread_depth
forwarded_from_author, forwarded_from_post   -- telegram/retweet origin
-- engagement POINT-IN-TIME (current)
likes, comments_count, shares, upvotes, views, upvote_ratio
-- geo + lang
lang, geo_inferred, geo_state
-- provenance
watchlist_id FK, has_media, media_urls jsonb, raw jsonb
-- substrate (extract-once superset)
summary, sentiment, sentiment_score, emotion,
topic_category, primary_subject,
entities_extracted jsonb, labse_embedding vector(768),
toxicity real, weaponization_signals jsonb,     -- for NWS later
extraction_confidence real, substrate_status, extraction_version,
collected_at, enriched_at
```

### `social_post_metrics` — engagement time-series (append-only) ⚠️ CAN'T RETROFIT
```
post_id FK, captured_at, likes, comments, shares, upvotes, views
```
*Snapshots at T+1h/T+6h/T+24h. This single table is what enables velocity,
virality-forecasting, breakout-detection, and engagement-curve analysis. If you store
only one likes count, all of that is permanently impossible.*

### `social_edges` — the network graph (capture-now) ⚠️ CAN'T RETROFIT
```
src_author_id, dst_author_id, edge_type (reply|mention|quote|retweet|forward),
post_id FK, weight, created_at
```
*Captured free at ingest from reply/mention/forward structure. Even though network
features aren't in the first build, the edges are unrecoverable later. Store them now;
build conversation-attribution / propagation / influence whenever.*

### Substrate child tables (per-post 1:N, FK `post_id ... ON DELETE CASCADE`)
- `social_post_claims` — claim_text, subject/predicate/object, **claim_embedding vector(768)**, **claim_fingerprint** (for corroboration / mutation / counter-narrative)
- `social_post_quotes` — speaker, quote_text, is_direct
- `social_post_stances` — actor, actor_entity_id, target, target_entity_id, stance, intensity *(directed sentiment → who-attacks-whom, two-Indias)*
- `social_post_locations` — text, country, region, city, lat, lng
- `social_post_hashtags` — tag *(structural, regex at ingest)*
- `social_post_mentions` — mentioned_username *(structural → feeds edges)*

### `social_post_entity_mentions` — matview (transliteration-aware resolution)
Unrolls `entities_extracted` → `entity_lookup.name_norm` (Hinglish/Devanagari variants
collapse to one `entity_id`) → `entity_dictionary`. Refreshed by cron.

### Personalization layer (separate, append-only)
- `user_watchlists` — user_id, target_type, target_value, params
- `user_events` — user_id, post_id/entity_id, event_type (view|click|dwell|share), dwell_ms, ts *(implicit signals → for-you, relevance, adaptive brief length)*
- `user_prefs` — notification rules, learned brief-length, channel prefs

### Derivation layer (built on top — add anytime, no schema change)
Rollup matviews (volume / share-of-voice / sentiment-over-time), anomaly baselines,
forecast outputs, NWS scores, alert configs, brief templates. **None of these block the
atomic layer; all are derivations.**

---

## 2. Capture-now vs derive-later — the decision table

| Capability | Needs (atomic) | Tier |
|---|---|---|
| Volume / share-of-voice / sentiment-over-time | timestamped posts + entity links + sentiment | DERIVE |
| Velocity / acceleration / virality forecast | **`social_post_metrics` snapshots** | CAPTURE-NOW |
| Influence-weighted sentiment | **`social_authors.followers` + influence** | CAPTURE-NOW |
| Conversation attribution / who-talks-to-whom | **`social_edges` + thread refs** | CAPTURE-NOW |
| Claim corroboration / counter-narrative / mutation | **claim_embedding + fingerprint** | EXTRACT-ONCE |
| Narrative clustering / two-Indias | post + claim embeddings + stances | EXTRACT-ONCE |
| State-level geo-heatmap | `geo_state` per post/author | EXTRACT-ONCE |
| Transliteration entity matching | `entity_lookup` variants | EXTRACT-ONCE |
| Bot-likelihood / cadence | **`social_author_snapshots` + cadence stats** | CAPTURE-NOW |
| Personalization / for-you / relevance | **`user_events`** | CAPTURE-NOW |
| Deleted-post intelligence | **`raw` + body stored before deletion** | CAPTURE-NOW |
| Confidence intervals / honest-no-coverage | `extraction_confidence` + coverage counts | EXTRACT-ONCE |

Everything in **DERIVE** is a query/model away anytime. Everything in **CAPTURE-NOW**
is gone forever if not stored at ingest. That's the line the schema is drawn around.

---

## 3. Full feature backlog (✓ = you selected it for early build)

### A. Numerical / data-analyst
✓ volume time-series · ✓ share-of-voice+benchmark · ✓ sentiment-over-time · ✓ engagement totals · ✓ velocity+acceleration · ✓ state-level geo-heatmap · ✓ influence-weighted sentiment · ✓ virality forecaster · ✓ confidence-intervals/coverage · ✓ anomaly-vs-baseline ·
reach/impression estimation · narrative-propagation diffusion coefficient · coordinated-behavior index · cadence-CV bot-% · live PageRank centrality · narrative-weather map · movers-&-shakers leaderboard · real-time pulse gauge · cross-platform dedup'd counts · bot-adjusted true volume
*(competitor: predictive KPI/topic-volume forecast 48h–90d · audience demographics · historical trend archive)*

### B. Intelligence / textual
✓ post sentiment+emotion · ✓ entity extraction+linking · ✓ daily entity summary · ✓ topic clustering · ✓ directed stance · ✓ claim+corroboration · ✓ LaBSE narrative clustering · ✓ native Hindi/regional · ✓ counter-narrative finder · ✓ why-trending explainer · ✓ anomaly-of-the-day · ✓ two-Indias view · ✓ source-grounded cite-ID · ✓ conversation attribution · ✓ transliteration entity match · ✓ honest no-coverage labels ·
claim-mutation tracker · Narrative Weaponization Score · copypasta/astroturf fingerprint · quote-of-the-storm
*(competitor: image/logo/video recognition · podcast/audio transcription · irony/sarcasm detection · Smart-Themes auto-cluster · 192-language emotion)*

### C. Payable
✓ tiered API · ✓ seat subscriptions · ✓ historical export · ✓ breaking-event war-room ·
credit-metered calls · premium alert subscriptions · white-label reports · STIX/SIEM connector · intelligence-on-demand bounties · forecast feed product · pay-per-dossier · data-clean-room · benchmark flex-reports · pulse-check micro-purchase · gamified pro-community · transparent self-serve pricing · India-SMB tier · credits-never-expire · free anomaly lead-magnet
*(competitor: BYO-content ingest · BI connectors · managed/finished-intelligence service)*

### D. Easability / delivery
✓ daily email brief · ✓ Telegram bot · ✓ NL assistant (Ask-RIG) · ✓ WhatsApp brief · ✓ Gmail-connected newsletter · ✓ calendar-injected intel · ✓ breaking-for-you push ·
Slack/Teams · scheduled PDF/PPT · brief-to-voice audio · morning-anchor video · forward-a-tweet→context · developing-story live thread · shareable cards · 60-sec onboarding · no-Boolean builder · one-click integrations · mobile-first
*(competitor: BI/Tableau/PowerBI connectors · CRM/Zendesk/Salesforce integration)*

### E. MCP / agents
✓ MCP server · ✓ agentic auto-investigation · ✓ RAG over corpus · ✓ autonomous brief agent · ✓ multi-tool chaining · ✓ agent-built monitors · ✓ predictive trend agent · ✓ plain-English→query ·
cross-pillar fusion agent · human-in-loop dossier agent · adversarial red-team agent · debate agents · auto-pivot agent · self-updating living dossier · what-you-missed recap · agent claim-verification · agent scraper-self-heal · agent noise-filter
*(competitor: Babel agentic Insights Investigator · Sprinklr next-best-action)*

### F. Personalization
✓ per-user watchlists · ✓ personalized relevance (v3) · ✓ saved searches/dashboards · ✓ notification prefs · ✓ implicit-signal learning · ✓ role-based views · ✓ filter-bubble breaker · ✓ adaptive brief length · ✓ for-you feed · ✓ because-you-follow · ✓ why-am-I-seeing-this · ✓ cross-device continuity ·
two-tower entity-affinity · geo/language personalization · personalized contrarian feed · blindspot report · streak brief · serendipity injection · editorial-integrity diversity floor · cold-start onboarding

### + Additions I'd bank into the layer now (cheap to capture, valuable later)
- **`source_reliability`** per author/domain — a credibility score slot (every OSINT firm has it; you'll want it)
- **`is_deleted` / `deleted_at`** — flag posts that vanish (deletion is itself intelligence)
- **`edit_history` jsonb** — capture edited posts (edits are signal)
- **`coordination_cluster_id`** — nullable slot to tag a post into a detected CIB cluster later
- **`narrative_id`** — nullable FK to a narrative/saga (reuse your saga layer for social)
- **`language_confidence`** + **`is_translated`** — Indic-NER honesty
- **`reply_sentiment_delta`** — how a post shifts the conversation (derivable from edges + child sentiment)

None change the build scope; they're columns/slots that make tomorrow's features a query
instead of a migration.

---

## 4. Extraction layer — ONE superset pass

`GROQ_SYS_SOCIAL` emits a single structured JSON per post covering the EXTRACT-ONCE tier
(so no textual feature ever needs a re-run):
`language(+confidence) · sentiment(label+score) · emotion · topic · primary_subject ·
entities[] · directed_stances[] (actor→target) · claims[] (text+s/p/o) · quotes[] ·
locations[] · toxicity · weaponization_signals`

Structural capture at INGEST (no LLM — cheap, deterministic):
`engagement metrics · author state · thread/reply/quote refs · forwarded-from ·
hashtags (regex) · mentions (regex) · media URLs · raw payload · language detect`

Post-extraction enrichment (derive, async):
`claim_embedding + fingerprint · labse_embedding · entity resolution (matview) ·
edges built from mentions/replies · metrics snapshot scheduled (T+1h/6h/24h)`

Lifecycle mirrors the other pillars: `pending → processing → ok | extract_failed | junk`,
`extraction_version`, junk-guard on <25-char/link-only posts.

---

## 5. Why this survives every future feature
- Want **network analysis** in 6 months? Edges already stored → just query.
- Want **virality forecasting**? Metric snapshots already accruing → train on them.
- Want **CIB detection**? cadence + edges + fingerprints already there → run the detector.
- Want **personalization**? user_events already logging → fit the model.
- Want a **new platform** (ShareChat/Koo)? Same atomic schema, new collector → done.
- Want **NWS / dossiers / STIX**? All derivations over claims+stances+edges+authors.

The atomic layer is the contract. Features are renters on top of it.

---

## 6. Data-acquisition strategy (what we scrape, and how)

Social is an INFINITE universe — unlike news (bounded sources), we cannot scrape
"everything." We scrape by INTEREST, not by source. Three feeds, blended:

1. **Standing core corpus** — a curated, always-scraped set of top India entities,
   key accounts, major subreddits, big Telegram channels, important hashtags
   (~200-500 items). Bounded, we control it, covers ~80% of any India-news interest.
   → what every NEW user sees instantly, day one, no setup.
2. **Trending / discovery capture** — whatever is spiking now (Twitter trends, hot
   subreddits, viral Telegram), even off-list. → the "what's happening now" + For-You feed.
3. **Demand-driven expansion** — when a user/client tracks something new, add it to the
   scrape set + one-time backfill, then collect forward. → the long tail; scales with
   paying demand, not with the whole internet.

A user can also NAME an account/person → we pull their posts (backfill + forward).
Depth caps: Twitter ~recent 800-3200 (platform limit), Instagram full public grid (slow),
Reddit recent, Telegram FULL history. Private accounts = impossible (any tool).

## 7. BAN-SAFETY — a hard, non-negotiable constraint

"Never get banned" outranks "get the data fast", always. Enforced architecturally so it
cannot be violated even by accident:

- **One central rate governor per account.** EVERY request (live or backfill) passes
  through it. The safe rate is a hard CEILING, never a target. No code path bypasses it.
- **Backfill is a low-priority background trickle**, never a dump. It uses only the budget
  left after safe live collection. A huge account may take hours/days to backfill — that is
  the accepted trade. The present is always covered (forward collection from second one).
- **Per-platform safe ceilings:** Twitter paced w/ gaps; Instagram 1 call/5s residential
  relay only; Reddit spaced; Telegram obeys flood-wait (telethon auto-sleeps).
- **Circuit breakers everywhere.** Any rate-limit signal (429 / flood-wait / challenge) →
  stop that account + exponential backoff. Never push through a warning. (IG relay already
  does this; apply to all four.)
- **Spread load across multiple scraper accounts** so none is hammered.

> The rate governor is a wall, not a speed limit. Backfill trickles; it never bursts; it
> stops the moment a platform frowns.

## 8. Scheduling — start simple, architect for adaptive
Per-platform fixed timers now (Option A); `social_watchlist` carries `priority` +
`next_check_at` + `avg_activity` from day 1 so adaptive priority polling (hot entities fast,
cold slow) drops in later with NO schema change. Telegram live-streaming (telethon events)
can be added for real-time early-warning at zero budget cost.
</content>
