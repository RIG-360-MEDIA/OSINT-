# RIG OSINT — Deep Feature Catalog

_Senior news-AI lens (Aryan Mehta): faithfulness-first, entity-centric, freshness-aware,
personalization-vs-editorial-integrity. Every feature below is mapped to **real data we
hold** and flagged for honesty. Nothing here is a generic "LLM does X" cliché — each is a
mechanic with a data source and a build cost._

## How to read this

- **Buckets** (each category carries the full mix): `[OBV]` obvious baseline · `[EXC]`
  exceptional (best-in-class competitors do it) · `[OOB]` out-of-the-box / nobody-quite-does-this ·
  `[DOP]` dopamine / daily-habit · `[PAIN]` kills a documented user pain.
- **Readiness:** 🟢 deliverable on current data · 🟡 needs a code/schema tweak (named) ·
  🔴 needs a new ingestion pipeline (named) — *be honest with the customer about these.*
- Categories deliberately overlap (a map can be payable); the **lens** differs each time.

## The data we actually stand on (verified 2026-05-27)

128,748 articles (Apr 16–May 31, 9 languages) · `labse_embedding` 768d on 98.8% (pgvector) ·
FTS tsvector · `register_is_breaking` flag · 29.5% dup-detected · `article_entity_mentions`
348k (4,918 entities, surface_forms) + `entity_dictionary` aliases · `article_stances` 99k
(**18 stance labels** + intensity, actor_entity_id) · `article_events` 225k (type, actors[],
date — **only ~9 forward-dated**) · `article_claims` 148k (SPO + embedding) · `article_quotes`
65k (speaker, context_window) · `article_locations` 268k (**lat/lng**) · `article_media` 1.56M ·
`article_links` 5.43M (domain) · `entity_mention_daily` 19k + `_hourly` · `sources`
(type/tier/geo_states/**health_score unused**) · LLM pool (qwen3-32b, faithfulness-gated) ·
relevance core · prefs (watchlist/regions/topics/primary_subject; **unused:**
languages/sources/stance/events/delivery/personality).

**🔴 Empty (need a pipeline, do not promise without backfill):** social (Reddit/Telegram/
Twitter), all `cm_*` (dissent/promises/coalitions/handles), govt_documents, welfare,
power_grid, entity_dossier cache, social baselines.

---

## CATEGORY 1 — Heavy numerical / data-analyst data
### Rebuilt around RELATIONSHIP & POSTURE scoring — the metrics a war-room acts on, not decorative charts.

**The scoring backbone (shared by everything below — read once).**
`article_stances` gives each *actor's* posture — 18 labels (critical / supportive / promotional / neutral …) × intensity 0.1–1.0 — but **no directional target column** (verified). So "how favourable is outlet/journalist X toward person Y" is computed with a **salience proxy**: take articles where Y is the *headline / high-salience subject* (the relevance core already detects this), read the dominant stance × intensity as "how Y was framed," and attribute it to that article's **outlet** (`sources`, with `tier` + `health_score`) and **byline** (`articles.byline` — **66% populated, 85,674 articles**; `author_name` 38%; **6,773 distinct authors**). Three non-negotiable rules keep these honest (Aryan): every score ships with **n + a confidence band** (a journalist judged on 3 pieces is noise, not a verdict), **freshness decay** so last quarter doesn't outweigh this week, and **drill-to-source** (tap the −38 → read the 23 articles behind it). One backfill makes the whole family *exact* instead of proxy: add `target_entity_id` to stance extraction so posture becomes directional (X is critical *of Y*).

**[OBV] — the essential baselines (explained):**

1. **Outlet Favourability Index** `🟢` — A single −100…+100 number per outlet for how it frames *you*: average stance×intensity over your-salient articles, decayed. "*Times of India: −38 toward you (n=41) · Eenadu: +22 (n=63).*" This is the journalist-score idea at outlet level — the at-a-glance "who's for me, who's against me" roster leadership asks for first.

2. **Share-of-Voice %** `🟢` — Daily % of total relevant coverage each actor owns (`entity_mention_daily`). It's the denominator every other metric rides on — "*you = 41% of the conversation, your rival = 33%, climbing.*" Obvious, but it frames dominance.

3. **Stance-mix trend** `🟢` — The critical/neutral/supportive split for a target *over time* (`article_stances`), not a static pie — so you see the supportive band shrinking three days before it becomes a crisis.

4. **Weighted Pressure (not raw counts)** `🟡 tier-weight` — One "how much heat" number = Σ(mentions × outlet-tier × `health_score` × stance-negativity). A hostile front-page in a tier-1 daily outweighs 50 neutral blog posts — raw mention counts lie, this doesn't.

**[EXC] — best-in-class (what competitors charge for):**

5. **Journalist Leaning Score** `🟡 byline-normalise` — *Your flagship, done right.* Per byline: posture toward you (−100…+100), **consistency** (do they swing or are they reliably hostile?), volume (n), and a confidence band. "*Reporter A — hostile, −55, very consistent, n=23 → he's not a swing, don't waste a call. Reporter B — −4, volatile, n=9 → winnable.*" 66% byline coverage + 6,773 authors makes this real now; the only work is normalising names ("By Staff Reporter" / wire dupes).

6. **Friend / Foe / Fence roster** `🟡` — Classify *every* journalist and outlet covering you into **Ally / Neutral / Hostile** with sample size + confidence, sortable, exportable. The literal contact sheet a comms head wants on day one: who to brief first, who to never leak to, who's persuadable.

7. **Allegiance Divergence (you vs your rival)** `🟡` — For each outlet/journalist, the *gap* between favourability toward you and toward your main rival. This separates the genuinely adversarial (anti-you **and** pro-rival) from the fair critics (tough on everyone). The −38 outlet that's −40 to your rival too isn't your enemy; the −38 that's +30 to your rival is. Nobody should treat those the same.

8. **Stance Trajectory / drift** `🟡 slope calc` — The *slope* of an outlet's or journalist's favourability over 30/60/90 days. "*India Today cooling on you: −18 over six weeks.*" Catches an ally turning while you can still fix it — the single most useful early signal for relationship management.

**[OOB] — nobody-quite-does-this:**

9. **Quote-Selection Bias** `🟡` — When an outlet writes about you, do they quote *you* or your *critics*? Ratio from `article_quotes.speaker_entity_id` (you vs adversaries) per outlet. Exposes the subtle hostility stance-scores miss: "*Outlet Z runs a 'neutral' tone but quotes your attackers 4:1 and never you directly.*" That's a hit piece wearing a balanced face.

10. **Attack Origination vs Amplification** `🟡 link rollup` — For a negative narrative, separate *who started it* (earliest timestamp + the inbound `article_links` root) from *who merely echoed it* (5.4M-row link graph). Names the source vs the megaphone — so you pressure the origin, not the 40 aggregators downstream.

11. **Reciprocity / Feud Matrix** `🟡` — A directed actor→actor hostility matrix: who attacks whom, how often, and whether it's mutual or one-way (co-mention + stance polarity). A numeric map of the political conflict graph — "*Rival A attacks you 12×, you've answered 2× → you're losing this exchange on volume.*"

12. **Issue-Ownership Index** `🟡` — Per `topic_category`, who "owns" the favourable narrative = share-of-voice × favourability. "*Law-and-order: you own 62%. Unemployment: opposition owns 71% — that's the battlefield you're ceding.*" Tells a strategist exactly which issue to contest.

**[DOP] — daily-habit hooks:**

13. **"Who flipped overnight"** `🟢` — Each morning, the journalists/outlets whose posture toward you moved most since yesterday — your call-list for the day. A reason to open it at 7am.

14. **First-to-Know lead-time** `🟡` — Hours your brief surfaced a story before its peak (and before a hostile outlet ran it). "*You saw this 6h before The Hindu.*" Legit status metric for an analyst briefing the boss.

15. **Your Pressure Gauge** `🟡 baseline` — One 0–100 needle for "heat on you right now" vs your own 30-day baseline, with an up/down arrow. Glanceable, slightly addictive, and genuinely the first thing a war-room glances at.

16. **Counter-Speed Scorecard** `🟡` — Median hours from an attack to your side's rebuttal appearing in print. "*You're defending 2.3× faster than last week.*" Gamifies narrative agility — the team competes with itself to shrink it.

**[PAIN] — kills a documented pain:**

17. **Target Heat Scoreboard (offense)** `🟢` — Flip the lens onto the *opposition*: per target, volume × negativity × tier = who's under the most fire right now. The attack dashboard — where your pressure is landing, and where a target is escaping unscathed.

18. **Cross-Language Hostility Gap** `🟢` — Favourability toward you in Telugu vs Hindi vs English (`language_iso` + stance). Surfaces the regional-language hit job your English-only monitoring never sees — a top, specific Indian pain ("*you're +10 in English, −44 in Telugu*").

19. **Narrative Half-Life** `🟡 decay fit` — Median time from a story's peak to half its volume. "*This will blow over in ~18h — don't dignify it*" vs "*sticky 6-day crisis — engage now.*" Stops teams from over-firefighting noise and under-reacting to the real thing.

20. **Exposure-Adjusted Risk Score (0–100, calibrated)** `🟡 calibrate first` — The composite early-warning leadership actually asks for: per target, pressure × hostile-reach × acceleration, calibrated against historical blow-ups, with a confidence band and full drill-to-source. *Ships only after backtesting* — an uncalibrated risk number is worse than none.

## CATEGORY 2 — Intelligence textual data

| # | Feature | Bucket | Mechanic + data source | Ready |
|--|--|--|--|--|
|1|Executive BLUF read|`[OBV]`|Daily bottom-line-up-front + ranked findings (exists) — extend multi-entity — LLM+stances|🟢|
|2|On-demand entity dossier|`[OBV]`|Quote+stance+events synthesis per entity (exists `/entity_read`) — add cache|🟢|
|3|"This week's coverage" précis|`[OBV]`|Principal coverage narrative (exists in CM Perspective)|🟢|
|4|Topic briefing|`[OBV]`|What's happening on a topic in the user's region — LLM over relevance set|🟢|
|5|Who's attacking / defending you|`[EXC]`|Stance-grounded narrative with cited quotes, faithfulness-gated — stances+quotes|🟢|
|6|Quote-context restorer|`[EXC]`|Viral quote → original full context + speaker's other statements on the topic — `article_quotes.context_window`+embedding (*kills out-of-context pain*)|🟡|
|7|Framing comparison|`[EXC]`|How tier-A vs tier-B outlets frame the same cluster — embedding cluster + LLM contrast|🟡 cluster job|
|8|Counter-narrative drafter|`[EXC]`|Given an attack cluster, draft a grounded rebuttal with cited facts — claims+quotes+LLM|🟡|
|9|Narrative-DNA decomposition|`[OOB]`|LLM names the 3 competing frames of a story + which actors/outlets push each — cluster+stance|🟡|
|10|Flip-flop / contradiction finder|`[OOB]`|Where an actor's claims conflict over time — `article_claims` SPO+embedding+date|🟡|
|11|"Dog that didn't bark"|`[OOB]`|What an actor is conspicuously *not* addressing vs peers (editorial blindspot) — topic-coverage gaps|🟡|
|12|Synthetic opposition memo|`[OOB]`|Red-team brief written as if from the rival's war-room — stance+events+LLM|🟡|
|13|Morning "situation room" 3-min|`[DOP]`|Top-3 narratives + drivers + risk + horizon, one screen — composite+LLM|🟢|
|14|"Since you last looked" diff|`[DOP]`|Narrative developments only since last session — timestamps+LLM|🟡 session state|
|15|Surprise insight of the day|`[DOP]`|Non-obvious entity connection from co-mention/embeddings — vector+LLM|🟡|
|16|Instant politician dossier|`[PAIN]`|2-minute brief vs 1–2 person-days: quotes, positions, controversies — entity+quotes+stance+events (*top dossier pain*)|🟢|
|17|Expert/voices aggregator|`[PAIN]`|Who-said-what on an issue (academic/industry/oppo) with stance — quotes+stance+`entity_type`|🟡 org-type tagging|
|18|Crisis brief auto-compile|`[PAIN]`|Anomaly fires → LLM assembles what/who/where/severity/suggested response — composite|🟡|
|19|In-brief quote translation|`[PAIN]`|Regional-language quote → English w/ original shown — quotes+LLM (*multilingual pain*)|🟡|
|20|Source-trail narrative|`[PAIN]`|Who broke it, how it spread/mutated, timeline — `article_links`+timestamps+LLM|🟡|

## CATEGORY 3 — Payable features

| # | Feature | Bucket | Mechanic + data source | Ready |
|--|--|--|--|--|
|1|Seat-based team plans|`[OBV]`|3/10/seat tiers, shared watchlists, admin + audit — users/orgs|🟢|
|2|Branded export (PDF/PPTX/CSV)|`[OBV]`|One-click decision-grade report from brief JSON — `python-pptx`/reportlab|🟡|
|3|Managed daily digest|`[OBV]`|Automated email/Slack delivery as a paid tier — delivery|🟡|
|4|Real-time alert tier|`[OBV]`|Daily digest (base) vs real-time watched-entity alerts (pro) — hourly+alerts|🟡|
|5|API / data access tier|`[EXC]`|Read-only → unlimited + webhooks; push to CRM/BI — REST|🟡 API layer|
|6|Decision-grade audit trail|`[EXC]`|Timestamped "we had this on date X" + who-viewed-what — immutable log (*regulatory must-have for govt/PR*)|🟡|
|7|Regional state modules|`[EXC]`|Per-state intelligence priced separately (TN, MH, WB…) — `geo_states`+language (*federal politics = separate WTP*)|🟡|
|8|White-label portal|`[EXC]`|Agencies/consultancies resell under their brand ($50k+ ACV) — multi-tenant theming|🔴 multi-tenant|
|9|Narrative bundles|`[OOB]`|Saved thematic packs ("how is oppo framing RBI", "reshuffle early signals") — cluster+stance templates|🟡|
|10|Speaker-intelligence premium|`[OOB]`|Rising-star detection + influence graph + speaker alerts — quotes+co-mention|🟡|
|11|Rebuttal-as-a-service|`[OOB]`|Pay-per-use grounded counter-narrative draft — LLM+claims (*only-we-can-do*)|🟡|
|12|Pay-per-deep-dossier credits|`[OOB]`|Credits for a full dossier on any entity — `/entity_read` deepened|🟢|
|13|Influence/impact scorecard upsell|`[DOP]`|"Prove your desk's value" exec metric — counts+percentile|🟡|
|14|Weekly "Wrapped" report|`[DOP]`|Shareable exec-facing recap of the week's intel — weekly aggregation|🟡|
|15|First-to-know SLA badge tier|`[DOP]`|<5-min alert guarantee as premium — sub-hourly pipeline|🔴 sub-hourly ingest|
|16|Managed human-curated brief|`[PAIN]`|Analyst-written 3×/week synthesis (high-margin, sticky) — LLM+human QA (*execs pay for synthesis, not raw data*)|🟡|
|17|Crisis war-room mode|`[PAIN]`|Real-time room + escalation as a seat add-on — alerts+composite|🟡|
|18|Compliance / data-residency tier|`[PAIN]`|SOC2 + India residency for govt buyers — infra|🔴|
|19|Tiered watchlist/bundle limits|`[PAIN]`|5 → 50 → unlimited watchlists — prefs storage|🟢|
|20|Election-season campaign module|`[PAIN]`|Constituency + issue intelligence priced for campaigns — geo+stance|🟡|

## CATEGORY 4 — Easability (delivery & integrations)

| # | Feature | Bucket | Mechanic + repo/data | Ready |
|--|--|--|--|--|
|1|Daily Gmail/Outlook newsletter|`[OBV]`|Per-user intelligence email at 06:00 IST — Resend/Postmark + brief JSON|🟡|
|2|Slack/Teams digest + bot|`[OBV]`|Channel digest + alerts — Slack `bolt-python`|🟡|
|3|Google Sheets/Docs export|`[OBV]`|Push brief to a Sheet (analysis) or Doc (reading) — `google-api-python-client`|🟢|
|4|PDF/PPTX briefing deck|`[OBV]`|Auto-deck with charts + map image — `python-pptx`/reportlab|🟡|
|5|WhatsApp Business broadcast|`[EXC]`|Headlines+geo+sentiment to WhatsApp (Indian users live there) — Meta Cloud API|🟡 BSP setup|
|6|Telegram alert bot|`[EXC]`|Real-time watched-entity/shift alerts — `python-telegram-bot`|🟡|
|7|Notion/Confluence live sync|`[EXC]`|Brief as a live database users curate — Notion SDK|🟡|
|8|Calendar .ics horizon|`[EXC]`|Upcoming events → Outlook/Apple calendar — `icalendar` (*note: forward events thin*)|🟡|
|9|n8n/Zapier/Make node|`[OOB]`|Users build their own automations on our brief — webhooks out|🟡|
|10|RSS/webhook outbound|`[OOB]`|Per-watchlist feed for external tools — `feedgen`|🟢|
|11|Auto board-pack in your brand|`[OOB]`|Generated leadership deck w/ charts + map — composite|🟡|
|12|Voice/audio brief (TTS)|`[OOB]`|Morning rundown as a podcast for the commute — summary→TTS|🟡|
|13|"What changed overnight" push|`[DOP]`|Web/mobile push of the overnight diff — diff engine|🟡|
|14|"You're first" scoop push|`[DOP]`|Beat-the-wires alert — hourly velocity|🟡|
|15|One-tap share card|`[DOP]`|Share a brief card to WhatsApp/Slack as image — card render|🟡|
|16|Per-recipient personalized newsletter|`[PAIN]`|Each stakeholder gets their own watchlist email — prefs+delivery (*kills late-night manual WhatsApp summaries*)|🟡|
|17|Crisis auto-escalation|`[PAIN]`|Anomaly → instant WhatsApp/SMS to comms lead — alerts+contacts|🟡|
|18|Per-user cadence scheduler|`[PAIN]`|06:00 daily, hourly during a crisis — scheduler|🟡|
|19|Print-ready minister 1-pager|`[PAIN]`|The red-folder PDF (govt still prints) — PDF render|🟡|
|20|Multi-channel single compose|`[PAIN]`|Same brief to email+Slack+WhatsApp+Notion in one send — delivery hub|🟡|

## CATEGORY 5 — MCPs & agent workflows

| # | Feature | Bucket | Mechanic + repo/data | Ready |
|--|--|--|--|--|
|1|RIG MCP server (our data as tools)|`[OBV]`|Expose articles/entities/stance/quotes/events/geo as MCP tools — FastMCP|🟡|
|2|"How is my CM covered?" agent|`[OBV]`|Conversational query over the brief schema — LangGraph|🟡|
|3|Auto-compile-dossier agent|`[OBV]`|Entity → full dossier doc — CrewAI|🟡|
|4|Scheduled watch agent|`[OBV]`|Monitors watchlist, fires on threshold — cron+alerts|🟡|
|5|Auto-draft-rebuttal agent|`[EXC]`|Attack cluster → grounded counter, faithfulness-gated — LLM+claims|🟡|
|6|Cross-source verifier agent|`[EXC]`|Does a claim hold across N *independent* outlets? (dedup-aware) — links+dup+embedding|🟡|
|7|Entity-expansion deep-research agent|`[EXC]`|Pulls timeline, allies/rivals (co-mention), controversies — composite|🟡|
|8|Deterministic brief-authoring workflow|`[EXC]`|Finder→verifier→synthesizer→critic produces the vetted brief ("story gravity") — orchestration|🟡|
|9|Red-team war-game agent|`[OOB]`|Simulate the opposition's next move from stance+events history — LLM|🟡|
|10|"Connect-the-dots" embedding agent|`[OOB]`|Surfaces non-obvious entity links across stories — vector search|🟡|
|11|Fact-check triage agent|`[OOB]`|Claim virality + prior-claim match → priority queue — claims+embedding|🟡|
|12|Persona-styled output ("brief me like the CM")|`[OOB]`|Uses the **unused `personality` pref** to restyle output — prefs.personality|🟡|
|13|"Ask my brief anything" chat (RAG)|`[DOP]`|Chat over our corpus via embeddings — pgvector+LLM|🟡|
|14|"One thing you must know" DM agent|`[DOP]`|Agent DMs the single must-know item daily — composite|🟡|
|15|Inbound MCP into the user's own Claude/ChatGPT|`[DOP]`|Analysts query our intel inside their own AI workflow — MCP|🟡|
|16|Smart-filter agent (overload killer)|`[PAIN]`|Ranks 500 articles/day → a defensible 10 — relevance core (*top overload pain*)|🟢|
|17|Crisis-response agent|`[PAIN]`|Anomaly → brief + draft statement + stakeholder list — composite|🟡|
|18|Pre-meeting auto-dossier|`[PAIN]`|Calendar attendee list → pre-brief on each — calendar+entity|🔴 calendar ingest|
|19|Legislative/policy watch agent|`[PAIN]`|Bill stage alerts — **needs `govt_documents` backfill**|🔴|
|20|Coordinated-campaign detector agent|`[PAIN]`|Synchronized multi-account push — **needs social backfill**|🔴|

## CATEGORY 6 — Personalization

| # | Feature | Bucket | Mechanic + data source | Ready |
|--|--|--|--|--|
|1|Watchlist relevance scoring|`[OBV]`|Persona-agnostic per-user ranking (exists) — relevance core; wire into every block|🟢|
|2|Region/topic filters|`[OBV]`|Brief scoped to the user's regions/topics — prefs|🟢|
|3|Primary-subject CM Perspective|`[OBV]`|Deep section on the user's principal (exists)|🟢|
|4|Per-user masthead/KPI|`[OBV]`|Stats scoped to the user's world, not global — relevance+counts|🟡|
|5|Role presets (govt/PR/journalist/analyst)|`[EXC]`|Role reshapes layout + signal weighting — prefs.role|🟡|
|6|Adaptive freshness tempo|`[EXC]`|War-room = fast decay, analyst = slow — per-user decay param (Aryan freshness)|🟡|
|7|Stance-lens preference|`[EXC]`|"Attacks on me" vs "policy substance" weighting — **unused `stance` pref**|🟡|
|8|Language weighting|`[EXC]`|Surface Telugu-first for a TG user — **unused `languages` pref**+`language_iso`|🟡|
|9|Implicit behavioral personalization|`[OOB]`|Contextual bandit re-rank from what they expand/click (Aryan, BBC) — needs event logging|🔴 click logging|
|10|Editorial-integrity floor|`[OOB]`|Diversity/echo-chamber guard so personalization doesn't filter-bubble them — source/stance diversity (Aryan)|🟡|
|11|Look-alike watchlist suggestions|`[OOB]`|"Principals like you also watch…" via embedding/co-mention|🟡|
|12|Auto-expanding watchlist|`[OOB]`|Detect rising entities relevant to the user, propose adds — emerging+relevance|🟡|
|13|"Your morning ritual" first screen|`[DOP]`|The single card curated for you on open — composite|🟡|
|14|Personal influence scorecard|`[DOP]`|Your watchlist's footprint vs cohort — counts|🟡|
|15|Coverage-completeness streak|`[DOP]`|"100% of relevant mentions reached you" daily streak — counts|🟡|
|16|Per-stakeholder sub-briefs|`[PAIN]`|CM's brief vs PR-lead's vs policy-desk's from one corpus — multi-profile prefs (*one tool, many roles*)|🟡|
|17|Overload-killer ranked 10|`[PAIN]`|500/day → ranked 10 by relevance×urgency — relevance core|🟢|
|18|Threshold-based personal alerts|`[PAIN]`|Alert when *my* entity breaches *my* threshold — prefs+alerts|🟡|
|19|Constituency-focused brief|`[PAIN]`|District-level brief for a constituency user — `article_districts` (sparse)|🟡|
|20|Personalized horizon|`[PAIN]`|Only upcoming events on the user's entities/regions (exists; gate by prefs) — events (*thin forward data*)|🟢|

## CATEGORY 7 — Map / geospatial

| # | Feature | Bucket | Mechanic + repo/data | Ready |
|--|--|--|--|--|
|1|Live incident point-map|`[OBV]`|268k located articles as clickable points — MapLibre+deck.gl on `article_locations` lat/lng|🟢|
|2|State coverage-volume choropleth|`[OBV]`|Shade states by article volume — `geo_primary`+datameet India GeoJSON|🟡 GeoJSON|
|3|State sentiment/stance choropleth|`[OBV]`|Shade states by avg stance — stances+geo|🟡|
|4|Click-point article popup|`[OBV]`|Headline/date/source on click — lat/lng+meta|🟢|
|5|District sentiment drill|`[EXC]`|Sentiment by district — `article_districts` (24%, sparse)|🟡|
|6|H3 hexbin incident-density heat|`[EXC]`|"Where did incidents cluster?" — `h3-js`+deck.gl HexagonLayer on lat/lng|🟢|
|7|Smart progressive clustering|`[EXC]`|Cluster at low zoom, scatter at high — `supercluster` on lat/lng|🟢|
|8|"Where is my issue hot"|`[EXC]`|Topic-filtered choropleth for a watchlist topic — topic+geo|🟡|
|9|Animated narrative time-slider|`[OOB]`|Play how a story spread geographically over days — lat/lng+timestamp (deck.gl)|🟡 time-agg|
|10|Bivariate map (volume × sentiment)|`[OOB]`|Hue=sentiment, saturation=volume per state — geo aggregates|🟡|
|11|Catchment / radius spatial query|`[OOB]`|"Articles within 50km of city X / inside this boundary" — Turf.js on lat/lng|🟢|
|12|Kepler.gl power-user explorer|`[OOB]`|Export 268k rows; analysts build custom layers/filters — Kepler.gl|🟢|
|13|"Your state at a glance" hero map|`[DOP]`|Login hero map scoped to the user's region — geo+prefs|🟡|
|14|Breaking-geo pulse|`[DOP]`|Pulse animation on located breaking events — `register_is_breaking`+lat/lng|🟡|
|15|Shareable map snapshot card|`[DOP]`|Export a map view as an image card — render|🟡|
|16|Constituency sentiment map|`[PAIN]`|Electoral-district sentiment — needs ECI constituency GeoJSON|🔴 boundary data|
|17|Swing-area detector|`[PAIN]`|Districts with shifting sentiment WoW — district+stance delta (*campaign pain*)|🟡|
|18|Regional-language coverage map|`[PAIN]`|Where Telugu vs English coverage dominates — `language_iso`+geo|🟡|
|19|Protest/unrest spatial early-warning|`[PAIN]`|Spatial clusters of incident-type events — `event_type`+lat/lng cluster|🟡|
|20|Turf-vs-rival catchment compare|`[PAIN]`|Your geographic footprint vs a rival's — geo+entity|🟡|

---

## Aryan's honest red-flags (what NOT to over-promise)

1. **Forward calendar is thin.** Only ~9 future-dated events exist. "Horizon / next-7-days"
   must be framed as *"scheduled items already on the record"*, never a forecast. Don't sell
   prediction off this.
2. **Social is empty in this DB.** Anything needing Reddit/Telegram/Twitter (coordinated-
   campaign detection, virality lag, subcultural early-warning) is 🔴 until backfilled.
   Flag it; don't fake it.
3. **Quantitative facts are sparse** (`article_numbers` 8.8%). Numeric "data-analyst"
   features built on extracted ₹/%/counts need a backfill pass first.
4. **Every LLM surface stays faithfulness-gated.** The most dangerous failure here is
   *confident wrongness* in a govt/PR context. Keep the numeric/citation gate on all prose;
   never let a dossier invent a figure or a quote.
5. **Scores need calibration before they ship.** Net-Sentiment-Index, momentum z-score,
   influence score — build the eval/backtest first. "A score with no evaluation is a guess
   with infrastructure around it." Show the user *why* a number moved (drill-to-source).
6. **Personalization needs an integrity floor.** Don't filter-bubble a war-room into only
   seeing friendly coverage — a diversity floor is the feature that keeps it trustworthy.
7. **`entity_dictionary` resolution is alias-based.** Homonyms (the "shan masood" class of
   mislabel) will recur; entity features need the resolution guardrails we already started.

## Build-order — highest-ROI quick wins (mostly 🟢/light 🟡)

These reuse the relevance core + LLM synth + existing data and ship fastest:

1. **Share-of-Voice + Net-Sentiment time-series** (Cat 1 #1,5) — the analyst hero chart.
2. **Instant politician dossier** (Cat 2 #16) — kills the #1 dossier pain, data-ready.
3. **Live incident point-map + hexbin** (Cat 7 #1,6) — lat/lng is sitting unused; high wow.
4. **Overload-killer ranked-10 + per-stakeholder sub-briefs** (Cat 6 #16,17) — relevance core already does the hard part.
5. **PR-impact ROI dashboard** (Cat 1 #16) — the thing buyers renew for.
6. **Daily Gmail/WhatsApp personalized newsletter** (Cat 4 #1,5,16) — the example the user named; pure delivery on existing brief JSON.
7. **RIG MCP server + "ask my brief" chat** (Cat 5 #1,13) — turns the corpus into an agent-queryable asset; strong differentiation.
8. **Anomaly / silence detector** (Cat 1 #19) — the early-warning competitors charge for.

## Pipelines that unlock the most locked features (if we invest)

- **Social backfill (Reddit/Telegram)** → unlocks ~8 features (virality lag, coordinated-
  campaign, subcultural early-warning, social sentiment).
- **`govt_documents` backfill** → legislative/policy watch, bill-impact, committee alerts.
- **Click/behavior logging** → implicit personalization (bandit re-rank), the BBC-grade
  engine.
- **Baseline tables (per-entity rolling stats)** → all anomaly/silence/momentum scoring.
