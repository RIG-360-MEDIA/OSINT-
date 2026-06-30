# Social Intelligence — Feature Strategy & Competitive Analysis

Synthesized with the news-AI architect lens (Aryan Mehta persona) + live research on
5 social-listening firms, 5 OSINT firms, and sycek.io. India-focused OSINT/news-intel wedge.

---

## PART A — Competitor Feature Matrix

### Social-listening firms (brand/marketing-first)
| Firm | Signature features | Their moat |
|---|---|---|
| **Meltwater** | cross-channel (social+print+TV+radio+podcast), 48h forecast, spike→Slack/Teams alerts, Data Streams API, BYO-content | traditional-media footprint |
| **Brandwatch** | 1.7T conversations (2010 archive), official X/Tumblr firehose, "Ask Iris" NL chat, image+logo+sentiment, podcast transcripts | firehose + deepest archive |
| **Talkwalker** | Blue Silk AI, best visual/**video** logo recognition, 90-day forecast, 7 emotions × 192 languages, Wisdom Studio custom assistant | visual AI + language breadth |
| **Sprinklr** | listening wired into full CXM/contact-center, Smart Themes auto-cluster, 450M pts/day, >80% sentiment w/ sarcasm | enterprise CXM integration |
| **Sprout Social** | no-Boolean query builder, Trellis AI teammate, demographics, SMB-friendly | lowest barrier to entry |

### OSINT / threat-intel firms (intelligence-first)
| Firm | Signature features | Their moat |
|---|---|---|
| **Dataminr** | earliest-signal real-time event detection, 50+ LLMs, severity scoring | speed-to-signal |
| **Recorded Future** | Intelligence Graph® (1M+ sources), entity correlation, Insikt human intel, SIEM | knowledge graph + analysts |
| **Babel Street** | 200+ languages native NER, identity resolution, agentic "Insights Investigator", managed attribution | multilingual + tradecraft |
| **Flashpoint** | deep/dark web, PIR-aligned collection, OCR+geo enrich, Echosec geospatial | dark-web depth |
| **LifeRaft/Echosec** | 500+ sources, 1700+ search methods, dossiers/case-mgmt, geospatial, exec protection | breadth + case workflow |

### sycek.io — the direct template (closest competitor)
AI intelligence platform, 7 chainable modules, **credit-based** pricing (never expire), vetted-customers-only.
- **SOCINT module = our exact build:** `social_search` (Twitter/Reddit/YouTube/TikTok/Telegram together), `social_analyze` (hashtag co-occurrence net + influencers + **Narrative Weaponization Score**), `social_intelligence` (CIB bot detection, IOC extraction, geo-inference, velocity-surge), `social_actor_profile` (**cadence-CV bot indicator**, peak hours).
- **STIX 2.1 export**, **MCP server** ("talk to your intel in plain English"), **gamified analyst community** (challenges/bounties/leaderboards).
- Generic/global — **our wedge = India depth they don't have.**

### What they ALL offer (table-stakes to match)
Volume/trend time-series · share-of-voice · sentiment(+emotion) · multilingual · topic clustering · trend detection · NL assistant · real-time alerts · spike detection · dashboards · scheduled reports · Excel/PDF/PPT export · REST API · streaming/webhooks · BI connectors.

### Analyst pain points (the gaps to exploit)
1. **Opaque six-figure pricing** — #1 complaint; prices out smaller teams
2. **Alert overload / noise** — constant tuning needed
3. **False positives** — analysts hand-verify everything
4. **Clunky UI / steep learning curve**
5. **Social-data decay** — X API death broke historical/network tools; tools constantly break
6. **API throttling / access restrictions**
7. **Weak geospatial** in some tools
8. **Limited customization**
9. **Unclear conversation attribution** (who's talking to whom)
10. **Source-verification burden** — analysts must validate quality themselves

---

## PART B — 120 Features (20 × 6 categories)

Tag legend: **[O]** obvious · **[E]** exceptional (others do) · **[X]** out-of-box · **[D]** dopamine · **[P]** pain-killer

### 1. HEAVY NUMERICAL & DATA-ANALYST DATA
1. **[O]** Mention/volume time-series per entity/topic/platform
2. **[O]** Share-of-voice across entities + competitor benchmarking
3. **[O]** Sentiment distribution + sentiment-over-time curves
4. **[O]** Engagement totals (likes/shares/views/upvotes) aggregated per entity/day
5. **[E]** Velocity & acceleration (mentions/hr + 2nd derivative) for spike detection
6. **[E]** Reach/impression estimation (followers × engagement model)
7. **[E]** State-level India geo-heatmap of who's discussing what
8. **[E]** Influence-weighted sentiment (weighted by account reach, not 1-post-1-vote)
9. **[X]** Narrative-propagation diffusion coefficient — measurable speed a narrative crosses platforms (T→Twitter, T+3h→Telegram, T+9h→Reddit)
10. **[X]** Coordinated-behavior index — graph-density score of accounts posting same content in tight windows
11. **[X]** Cadence-CV bot-likelihood distribution across an entity's discussant pool (% likely-automated)
12. **[X]** Live entity co-occurrence matrix + PageRank centrality on the mention graph
13. **[D]** "Narrative weather" map — accelerating/decelerating/mutating stories, real-time
14. **[D]** Virality forecaster — P(breakout in next N hours) per emerging post
15. **[D]** Movers & shakers leaderboard — biggest sentiment/volume swings today
16. **[D]** Real-time pulse gauge — sentiment-velocity needle per entity
17. **[P]** Cross-platform dedup'd counts — no double-counting same claim (fixes inflated numbers)
18. **[P]** Bot-adjusted "true volume" (minus likely-automated) — fixes noise
19. **[P]** Confidence intervals + sample-coverage disclosure on every metric (eval honesty)
20. **[P]** Anomaly auto-flag vs entity's own 30-day baseline (z-score) — fixes alert overload

### 2. INTELLIGENCE TEXTUAL DATA
1. **[O]** Per-post sentiment + emotion classification
2. **[O]** Entity extraction + linking to entity_dictionary
3. **[O]** Daily auto-summary of what's said about an entity
4. **[O]** Topic/theme clustering of posts
5. **[E]** Directed stance (actor→target): who attacks/defends whom
6. **[E]** Claim extraction + cross-source corroboration (claim on N independent accounts)
7. **[E]** Narrative clustering via LaBSE embeddings — storylines not keywords, cross-lingual
8. **[E]** Native-language analysis (Hindi/regional, no translation-loss) — we have LaBSE
9. **[X]** Claim-mutation tracker — diff how a claim is reworded as it crosses communities/languages
10. **[X]** Counter-narrative finder — strongest opposing claim + its carriers per trend
11. **[X]** Narrative Weaponization Score — coordination + toxicity + foreign-link + virality composite
12. **[X]** Copypasta/astroturf fingerprinting — near-dup clustering, Hindi-transliteration-aware
13. **[D]** "Why is this trending?" one-line auto-explainer per spike
14. **[D]** Anomaly-of-the-day — the single weirdest signal each morning
15. **[D]** Quote-of-the-storm — most-amplified direct quote per narrative, attributed
16. **[D]** "Two Indias" view — how opposing cohorts frame the same event side-by-side
17. **[P]** Source-grounded cite-ID'd intel — every claim links to its post (kills hallucination + verification burden)
18. **[P]** Conversation attribution — who's speaking to whom in reply threads (fixes Flashpoint pain)
19. **[P]** Transliteration-normalized entity matching — Hinglish/regional variants → one entity
20. **[P]** Honest "no coverage / low confidence" labels — never filler

### 3. PAYABLE FEATURES
1. **[O]** Tiered API access (rate/quota tiers) — /v1 gateway already built
2. **[O]** Seat-based dashboard subscriptions — RBAC already exists
3. **[O]** Per-entity/topic monitoring packs (pay per watchlist scope)
4. **[O]** Historical data export (CSV/Excel/PDF)
5. **[E]** Credit-based metered intelligence calls — pay per analysis (sycek model)
6. **[E]** Real-time alert subscriptions (webhook/Slack/Telegram) — premium SLA tiers
7. **[E]** White-label/branded reports + embeddable widgets for client resale
8. **[E]** STIX 2.1 / SIEM connector add-on (Splunk/Sentinel/OpenCTI) — enterprise tier
9. **[X]** Intelligence-on-demand bounties — commission a deep investigation (agent + optional human)
10. **[X]** Predictive/forecast feed as premium (virality + election-sentiment leading indicators)
11. **[X]** Pay-per-dossier — on-demand full actor/entity dossier (network + history + risk)
12. **[X]** Data-clean-room — client uploads their list (donors/voters/customers), cross-match vs social, privacy-gated
13. **[D]** Live war-room access during breaking events (premium real-time room)
14. **[D]** Benchmark reports clients flex ("#2 share-of-voice in your sector")
15. **[D]** Instant one-off "pulse check" micro-purchase (no subscription, impulse buy)
16. **[D]** Gamified pro-community tier (challenges/badges/bounties)
17. **[P]** Transparent public self-serve pricing — kills #1 OSINT complaint (opaque contracts)
18. **[P]** Affordable India-SMB tier — undercut firms that price out small teams
19. **[P]** Pay-as-you-go, credits never expire — no lock-in
20. **[P]** Free "anomaly digest" lead-magnet tier → upsell funnel

### 4. EASABILITY (delivery / convenience)
1. **[O]** Daily customized email intel brief per entity/topic
2. **[O]** Slack / Teams alert delivery
3. **[O]** Scheduled PDF/PPT exports
4. **[O]** Web dashboard with saved views
5. **[E]** Telegram bot — query intel + receive alerts in-app
6. **[E]** Natural-language query assistant (Ask-RIG, already built)
7. **[E]** WhatsApp daily brief delivery (huge in India)
8. **[E]** Gmail-connected personalized newsletter — reads tracked entities, sends tailored AM digest
9. **[X]** Brief-to-voice — daily audio intelligence briefing (TTS: Chatterbox/CosyVoice), listen on commute
10. **[X]** Calendar-injected intel — protests/events/spikes auto-added to Google Calendar
11. **[X]** Auto-generated "morning anchor" video brief (script + TTS + visuals) per client
12. **[X]** One-tap "explain this" — forward any tweet/headline to a bot, get full intel context back
13. **[D]** "Breaking for YOU" push — sub-minute alert when your entity spikes
14. **[D]** "Your 7am India pulse" habit-loop daily digest
15. **[D]** Live-updating "story is developing" thread (sports-live-blog for a narrative)
16. **[D]** One-tap shareable auto-cards (stat/quote → branded image)
17. **[P]** 60-second zero-setup onboarding (type entity → working monitor) — kills learning curve
18. **[P]** No-Boolean plain-language query builder (Sprout's edge)
19. **[P]** One-click no-dev integrations (Slack/Telegram/Sheets/Notion)
20. **[P]** Mobile-first delivery (analysts aren't at desks during breaking events)

### 5. MCPs & AGENT WORKFLOWS (our data + agents)
1. **[O]** MCP server exposing intel tools to Claude/Cursor ("talk to your intel")
2. **[O]** Agentic auto-investigation — describe target, agent chains entity→sentiment→network→report
3. **[O]** RAG over the corpus (Ask-RIG) — extended to social
4. **[O]** Scheduled agent that drafts the daily brief autonomously
5. **[E]** Multi-tool chaining — "profile @X, map network, score narrative, export STIX" in one prompt
6. **[E]** Cross-pillar fusion agent — correlate a social narrative with articles + YouTube + newspapers
7. **[E]** Human-in-loop dossier agent — agent drafts, analyst approves (Babel model)
8. **[E]** Agent-built custom monitors — "watch for coordinated pushes against X" → agent sets detection
9. **[X]** Adversarial red-team agent — simulate how a disinfo actor would attack a narrative, pre-empt
10. **[X]** Debate agents — two agents argue opposing cohort positions to stress-test an analyst's read
11. **[X]** Auto-pivot agent — finds the non-obvious common node behind an account cluster (two-hop, automated)
12. **[X]** Self-updating living dossier — agent re-runs nightly, diffs vs yesterday, surfaces changes
13. **[D]** "Ask anything about India right now" agent — instant cited multi-source answer
14. **[D]** Agent-generated "what you missed" recap while offline
15. **[D]** Predictive agent — "what'll likely trend tomorrow + why"
16. **[D]** One-prompt board-ready brief — polished doc in 60s
17. **[P]** Agent auto-verifies each claim against N sources — kills verification burden
18. **[P]** Agent handles platform breakage — finds alt path when a scraper breaks (fixes data-decay)
19. **[P]** Plain-English → complex query via agent — kills clunky-Boolean-UI pain
20. **[P]** Agent-curated noise filter — learns what you ignore, suppresses it (kills alert overload)

### 6. PERSONALIZATION
1. **[O]** Per-user watchlists (entities/topics followed)
2. **[O]** Personalized relevance scoring (relevance v3 exists) — rank by interests
3. **[O]** Saved searches + custom dashboards per user
4. **[O]** Notification preferences (what/when/how)
5. **[E]** Implicit-signal personalization — learn from clicks/reads/dwell (Inshorts/Medium-style)
6. **[E]** Per-user entity-affinity model (two-tower over reading history)
7. **[E]** Geo/language personalization (state-level India + Hindi/regional preference)
8. **[E]** Role-based views (trader sees market-movers; journalist sees blindspots)
9. **[X]** Filter-bubble breaker — deliberately inject the cohort/perspective you're NOT seeing (Ground News blindspot for social)
10. **[X]** Personalized contrarian feed — high-quality dissent against your priors
11. **[X]** "Your blindspot report" — narratives big in communities you never see
12. **[X]** Adaptive brief length — learns 60-word vs 600-word per topic from behavior
13. **[D]** "For You" intelligence feed — TikTok-style endless personalized intel scroll
14. **[D]** Personalized morning streak brief tuned to your open-time
15. **[D]** "Because you follow X" — discover adjacent entities/narratives
16. **[D]** Serendipity injection — one unexpected-but-relevant signal daily (variable-reward)
17. **[P]** Editorial-integrity guardrails — diversity floor so personalization ≠ filter bubble
18. **[P]** Cold-start that works — useful from minute 1, zero history (entity-pick onboarding)
19. **[P]** Cross-device continuity — start on phone, continue on desktop
20. **[P]** Transparent "why am I seeing this?" + one-tap tune (kills black-box distrust)

---

## PART C — Aryan's strategic synthesis

**The wedge.** Competitors split two ways: brand-listening (Meltwater/Brandwatch — consumer sentiment, share-of-voice) and global OSINT (Recorded Future/Babel/sycek — generic, six-figure, vetted-only). **Nobody owns India-depth intelligence.** That's the gap: Hindi/regional transliteration-aware CIB detection, ShareChat/Koo-successor fringe monitoring, an India entity graph already built, cross-pillar fusion (social + articles + YouTube + newspapers — which NONE of them have because they're social-only).

**What's cheap for us (we own the spine):** entities, sentiment, stances, claims, LaBSE narrative clustering, the /v1 gateway, RBAC, Ask-RIG NL assistant, relevance v3, TTS. Most of Categories 1, 2, 4, 6 reuse existing infrastructure. Build these first.

**What's capital-intensive (skip or defer):** visual/video logo recognition (Talkwalker's moat), firehose archives (Brandwatch's 2010 corpus), 200-language coverage (Babel). Don't compete here.

**What's the actual moat:** cross-platform narrative propagation + coordinated-behavior detection + cross-pillar fusion, India-tuned. Sycek proves the market wants it; we do it deeper for one country.

**Eval-first discipline (non-negotiable):** every numerical feature ships with confidence intervals + sample-coverage (feature 1.19). Every textual claim ships cite-ID'd (2.17). A Narrative Weaponization Score with no evaluation harness is "a guess with infrastructure around it" — and in the disinfo domain, confident-wrongness is the catastrophic failure mode. Build the eval harness before the score.

**Build order (MVP → moat):**
1. **Foundation** (reuse spine): volume/sentiment/entity time-series, daily brief, NL query, watchlists — Cat 1/2/4/6 obvious+exceptional.
2. **Differentiator**: CIB detection, narrative clustering+mutation, cross-platform propagation, India-transliteration — Cat 1/2 out-of-box.
3. **Monetize**: tiered API + credits + transparent pricing + STIX export — Cat 3.
4. **Moat/delight**: MCP server, agent workflows, cross-pillar fusion, personalization-with-integrity — Cat 5/6.
</content>
