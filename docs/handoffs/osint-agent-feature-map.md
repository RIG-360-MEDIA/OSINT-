# RIG — Worldwide OSINT Agent: Feature Map

**Vision:** An autonomous intelligence agent. User enters any keyword (person, place,
company, phone, domain, image, anything). The system's **Tasking brain** decides — per
target, per country, per language — which of the world's sources to hit, then collects
**latest + historical**, fuses everything onto one **entity case-file / graph**, and
delivers it **live + as history**. Worldwide scope, every language (LaBSE cross-lingual
engine is the moat), per-jurisdiction legality.

**Three collection tiers** (the source decides, not preference):
- **Pillars** — store-everything, filter-later (articles/YT/social/newspapers — already built).
- **Search-on-demand + persist** (~90% of awesome-osint) — query per keyword, keep every
  result so history accretes from use.
- **List-feeds → promote to store-everything** (~10%) — RSS, sanctions/PEP, leak/court bulk.
- **Tier 0 — don't touch** — dark web, breach-dumps, paywalled-no-API (legal/mission risk;
  the line moves per target-country under GDPR/PDPA/etc.).

This doc is the running catalogue of concrete features per awesome-osint category. Built
incrementally, one category at a time.

Cross-cutting lens applied to every category: **× the whole world · × every language ·
× per-jurisdiction legality.**

---

## 1. General Search
*(Google, Bing, Yandex, Baidu, Naver, DuckDuckGo, Brave, Mojeek, Seznam, Sogou…)*
**Tier:** Search-on-demand + persist. Practical front-end: existing `rig-searxng`.

**Discovery features**
1. **Beyond-corpus keyword reach** — surface every indexed-web page mentioning a target,
   beyond RIG's own feeds.
2. **Multi-engine parallel query** — one keyword → Google+Bing+Yandex+Baidu+Naver+DDG at
   once via SearXNG. *(Buildable now — already in stack.)*
3. **Auto source-discovery → self-expanding corpus** — new domains that repeatedly mention
   targets get promoted into pillar collectors. RIG grows its own source list. *(Highest
   leverage in this category.)*

**Intelligence features**
4. **Cross-engine / cross-jurisdiction diff** — compare Google.com vs Google.de vs Yandex
   vs Baidu → censorship / takedown / reputation-laundering detector.
5. **National-engine routing** — Tasking brain queries the engine that owns the target's
   home web (Baidu=CN, Naver=KR, Yandex=RU).
6. **Emergence / time-slice detection** — date-windowed queries reveal *when* an entity
   first appeared online ("materialized from nothing in Q2").
7. **Narrative-origin trace** — verbatim phrase → earliest indexed appearance across engines.

**Language & fusion features**
8. **Cross-lingual keyword expansion** — auto-translate/transliterate the keyword into the
   target's native languages, query native engines, merge results back via LaBSE.
9. **SERP entity extraction → graph** — every result page entity-tagged and folded into the
   case-file; a search grows the graph, not just a link list.

**Memory & monitoring features**
10. **Persistent results + change detection** — store each snapshot; re-runs show what
    appeared / vanished / changed.
11. **Standing watch (live mode)** — save a keyword as a monitored query; alert on genuinely
    new worldwide results.

**Effort:** #2,#5 now (SearXNG) · #1,#9,#10 small · #3,#8,#11 medium/high-payoff ·
#4,#6,#7 differentiators (nobody ships these).
**Limit:** free multi-engine is rate-limited; volume needs API keys or throttled/queued
progressive querying.

---

## 2. Google Dorks
*(advanced operators: site:, filetype:, intitle:, inurl:, intext:, cache:, AROUND(), plus
Bing/Yandex/DuckDuckGo operator equivalents; dork libraries like Exploit-DB GHDB, DorkSearch)*
**Tier:** Search-on-demand + persist. Works identically across every country's web —
a dork is language-agnostic and jurisdiction-agnostic.

**Precision-retrieval features**
1. **Operator-templated queries** — the agent auto-builds dorks from a target's type:
   `"Name" filetype:pdf`, `site:gov.* "Company"`, `intitle:"index of" "Target"`. Turns a
   plain keyword into a surgical query set.
2. **Exposed-document hunting** — `filetype:pdf|xlsx|docx|pptx` scoped to a target → pull
   filings, budgets, contracts, leaked internal docs the target never meant indexed.
3. **Directory / open-index discovery** — `intitle:"index of"` → exposed file servers,
   backups, and directories tied to a target's infrastructure.
4. **Government / official-record scoping** — `site:gov / site:gob.* / site:gouv.* /
   site:go.jp` per country → pull only authoritative sources for that jurisdiction.
5. **Login-page / infra footprint** — `inurl:login / inurl:admin / inurl:dashboard` on a
   target's domains → maps their exposed attack/entry surface (attribution, not intrusion).

**Cross-engine dork features**
6. **Engine-diverse dorking** — same dork logic via Yandex/Bing/DuckDuckGo operators, since
   each indexes files Google misses (esp. non-Western + de-indexed content).
7. **Dork-library automation** — draw from GHDB / curated dork sets, auto-parameterised with
   the target keyword. A catalogue of "what to look for" runs on any new target.

**Creative / different**
8. **Auto-dork generation by entity type** — Tasking brain maps target class → dork recipe:
   person→resumes/social/leaks, company→filings/tenders/exposed-docs, domain→infra/backups.
9. **Leak / breach-adjacent discovery (legal side)** — dorks that surface *publicly indexed*
   exposed data (misconfigured buckets, open spreadsheets) — the legal, no-breach-dump path
   to the same intelligence.
10. **Persistent dork-watch** — save a dork as a standing query; alert when a *new* exposed
    document/page matching it appears (early-warning on leaks about a target).

**Effort:** #1,#2,#4 small (query templating over SearXNG) · #7,#8 medium (dork library +
type-routing) · #10 medium (watch loop).
**Limit:** dorking is the fastest way to get an IP/API blocked — heavy operator queries
trip bot-detection hard. Must be low-rate, queued, rotated. Ethically/legally: only
*publicly indexed* content; surfacing exposed data ≠ authorised to exploit it.

---

## 3. Main National Search Engines
*(Baidu/Sogou=CN, Yandex=RU, Naver/Daum=KR, Seznam=CZ, Goo=JP, Parseek=IR, Yandex.TR,
Coccoc=VN, plus regional Google TLDs)*
**Tier:** Search-on-demand + persist. This is the category that *makes* worldwide scope real
— it's the execution arm of "National-engine routing" (#1.5).

**Sovereign-web access features**
1. **See the web Google can't** — Baidu indexes the Chinese web that's dark to Google; Yandex
   owns Cyrillic; Naver owns the Korean blog/café ecosystem Google barely touches. For a
   target inside those spheres, the national engine is the *only* real view.
2. **Auto home-web routing** — Tasking brain maps target nationality/language → the engine
   that owns that web. "Chinese official" → Baidu+Sogou+Weibo-search, not Google.
3. **Native-script querying** — query in Hanzi/Cyrillic/Hangul/Arabic directly (via keyword
   expansion #1.8), because national engines rank native-script queries far better.

**Intelligence-from-difference features**
4. **Censorship-delta detection (state-level)** — what Baidu *refuses* to return about a CCP
   official, or Parseek about an Iranian entity, is itself intelligence. Diff national-engine
   results vs Google → map what each *government* is suppressing.
5. **Propaganda-surface capture** — national engines surface the *officially sanctioned*
   narrative first. Capturing that top-of-results = capturing the state's preferred story,
   to contrast against independent sources (feeds disinfo/narrative analysis).

**Creative / different**
6. **Regional-platform discovery** — national engines index regional platforms (Weibo, VK,
   Naver Café, Coccoc) your pillars don't know exist → auto source-discovery (#1.3) at
   *global* scale, per country.
7. **Cross-border alias bridging** — a target's name renders differently per language/script;
   national-engine results in native script surface aliases/spellings that English search
   never links — critical for global entity resolution.

**Effort:** #1,#2,#3 small-medium (SearXNG supports Baidu/Yandex/Naver engines already) ·
#6 medium · #4,#5 differentiators.
**Limit:** national engines block foreign IPs aggressively and often need in-country egress
(proxy/residential in-region) + native-script queries to work at all. Some (Baidu) actively
poison/withhold for non-native clients. Realistically needs per-region proxy infrastructure.

---

## 4. Meta Search
*(SearXNG, Carrot2, Zapmeta, etc. — engines that query many engines at once and merge results)*
**Tier:** Search-on-demand + persist. **You already own the answer: `rig-searxng` is in your
stack.** This category is less "new sources" and more "the aggregation layer under #1–#3."

**Aggregation features**
1. **Single-call world query** — one keyword → many engines merged/deduped in one response.
   The practical execution layer for multi-engine (#1.2) and national routing (#1.5/#3.2).
2. **Engine-set profiles** — pre-defined engine bundles per target type/region (a "China
   profile" = Baidu+Sogou+Weibo; an "EU profile" = Google.de+Bing+Mojeek). Tasking brain
   picks the profile.
3. **Self-hosted = no per-query API bill** — SearXNG scrapes engines you don't have keys for;
   your own instance means no metered cost and full query-log control (privacy + persistence).

**Intelligence features**
4. **Result clustering (Carrot2-style)** — auto-group a keyword's results into topics/themes
   → instant "what facets exist about this target" map before any human reads a page.
5. **Cross-engine rank-fusion as a confidence signal** — a result that ranks high across
   *many independent* engines is more trustworthy than a single-engine hit → corroboration
   scoring baked into discovery (mirrors your independent_source_count logic).

**Creative / different**
6. **Meta-engine as the anti-filter-bubble instrument** — because it blends engines with
   different biases/censorship, the *merged* view is harder for any single actor to
   manipulate → a manipulation-resistant discovery surface.
7. **Private querying** — self-hosted meta search means the agent's queries don't leak the
   investigation to Google/Bing (no query fingerprint tying RIG to a target). Operational
   security feature, not just cost.

**Effort:** #1,#2,#3 now (SearXNG live) · #4 small (add clustering) · #5 small · #6,#7 config.
**Limit:** SearXNG reliability depends on upstream engines not blocking it — heavy use gets
individual engines rate-limited/captcha'd; needs proxy rotation + engine health-monitoring.
Merged relevance is weaker than a single native engine's own ranking.

---

## 5. Privacy Focused Search Engines
*(DuckDuckGo, Brave Search, Startpage, Mojeek, MetaGer, Searx public instances)*
**Tier:** Search-on-demand + persist. Value is less "new content" and more **independent
indexes + OPSEC + un-personalised results.**

**Un-personalised-result features**
1. **Bias-free baseline** — these don't personalise or filter by your history, so they return
   the *same* neutral result set every time → a clean, reproducible baseline to diff against
   Google's personalised/localised results (sharpens censorship-delta #1.4).
2. **Independent indexes** — Mojeek and Brave crawl their *own* indexes (not Google/Bing
   rebrands) → genuinely different coverage; catches pages the big two dropped or never had.

**OPSEC features**
3. **Trace-free querying** — the agent investigates without building a profile at the engine
   → no query fingerprint linking RIG to a target (reinforces #4.7 at the engine level).
4. **De-Google'd corroboration** — confirm a finding on engines with no shared index/bias so
   corroboration is truly independent, not three mirrors of one crawler.

**Creative / different**
5. **"What Google forgot" detector** — Startpage returns Google results *without* the
   right-to-be-forgotten / localised suppression layer in some cases → surface entries that
   personalised Google hides. Pairs with censorship-diff as a takedown detector.
6. **Consensus-vs-outlier read** — run a keyword across privacy engines with *independent*
   indexes; agreement = solid fact, lone-engine hit = fringe/planted → a built-in
   noise/deception filter at discovery time.

**Effort:** all small — these are just more engines behind SearXNG (#4). Config, not build.
**Limit:** most privacy engines are thin re-skins of Bing/Google (only Mojeek/Brave have
truly independent indexes), so "diversity" is partly illusory. Lower coverage depth; best as
a corroboration/OPSEC layer, not a primary discovery engine.

---

## 6. Data Breach Search Engines
*(HaveIBeenPwned, DeHashed, Snusbase, LeakCheck, IntelX, Dropbase, breach-dump search)*
**Tier:** ⚠️ **MOSTLY TIER 0 — DO NOT INGEST.** A thin legitimate sliver exists; the rest is a
legal/reputational landmine for a commercial worldwide product. Handle with a hard policy gate.

**The legal line (per-jurisdiction, moves per target):**
- Trafficking / storing breached PII (passwords, dumped DBs) = illegal or actionable under
  GDPR / India DPDP / CFAA-adjacent laws in most jurisdictions. **Never store breach dumps.**
- The line is *existence-of-exposure* vs *content-of-exposure*. Knowing an email appeared in
  a breach (metadata) is defensible; possessing the leaked password/records is not.

**Legitimate sliver (allowed, metadata-only)**
1. **Exposure-existence check (HIBP-style)** — "does this email/domain appear in known
   breaches, yes/no + which breach + date." Metadata only, no credentials. Legal, and
   genuinely useful: tells you an entity's account was compromised / when.
2. **Breach-timeline as an event signal** — a target org appearing in a fresh breach is an
   *event* worth flagging (like any news event) — the fact, not the data.
3. **Domain-exposure monitoring (defensive)** — watch *your own* / a client's domains for new
   breach appearances → legitimate defensive-security feature.

**Creative / different (still legal)**
4. **Breach-as-corroboration-of-existence** — a breach record confirms an account/identity
   *existed* at a point in time (the metadata), useful to corroborate an entity is real /
   active — without ever touching the leaked contents.
5. **Coordinated-exposure pattern** — multiple linked entities appearing across the *same*
   breaches can hint at shared infrastructure/affiliation (from breach *names/dates*, not
   contents).

**Effort:** #1,#2,#3 small (HIBP has a clean, licensed API — the one legitimate vendor path).
**Limit / policy:** treat the whole category as **default-deny**. Only HIBP-style
existence-metadata via a *licensed* API. Hard-block ingestion of any dump content, passwords,
or records. This must be a coded policy gate, not a guideline — one stored breach dump is an
existential legal risk for a commercial global product.

---

## 7. Specialty Search Engines
*(Shodan, Censys, ZoomEye, GreyNoise, BinaryEdge, FOFA, Wigle, PublicWWW, IntelTechniques,
Recon.dev, SearchCode-style verticals — engines that index a *specific data domain* deeply)*
**Tier:** Search-on-demand + persist. **The most underrated category on the list** — these
are narrow but go *deep* where general engines are shallow.

**Infrastructure-intelligence features**
1. **Internet-asset lookup (Shodan/Censys/ZoomEye)** — given a target org/domain/IP → every
   exposed device, service, port, cert, banner they run worldwide. Maps a target's *physical
   and digital infrastructure footprint* — servers, cameras, ICS, cloud assets.
2. **Certificate / passive-DNS pivoting** — a TLS cert or favicon hash links seemingly
   unrelated domains/IPs to the *same* owner → attribution of hidden/shadow infrastructure.
3. **Tech-stack fingerprinting (PublicWWW/Wappalyzer-class)** — find every site running the
   same tracking ID / analytics code / template → surfaces a network of sites run by one
   operator (disinfo networks, sockpuppet farms, shell-company web presence).

**Physical-world features**
4. **Wireless/geo (Wigle)** — map Wi-Fi/cell networks by SSID/BSSID to physical locations →
   corroborate a target's presence/movement (feeds geolocation fusion).
5. **Exposed-camera / IoT geo** — Shodan surfaces public-facing cameras/devices by location →
   situational awareness around a target site (legal, public-facing only).

**Creative / different**
6. **Shared-infrastructure network graph** — the *crown feature*: pivot from one domain →
   cert/IP/tracking-ID/favicon → all co-located assets → build the **hidden ownership graph**
   nobody declared. This is how you unmask a disinfo network or a shell-company web from one
   seed. Lands directly on your entity graph.
7. **Change-over-time on infra** — persist Shodan/Censys snapshots → detect when a target
   spins up new servers, opens ports, or migrates hosting (pre-event / operational-tempo
   signal — infra changes often precede visible action).
8. **GreyNoise "is this noise or targeted"** — distinguish internet-background-noise from
   deliberate activity aimed at/from a target → separates signal from scan-noise.

**Effort:** #1,#2 small-medium (Shodan/Censys have clean licensed APIs) · #3,#6 medium
(pivot logic + graph) · #7 medium (snapshot diffing).
**Limit:** these APIs are paid and quota-limited (Shodan/Censys/FOFA). Deep infra pivoting
edges toward "recon" — stay strictly on *passively-indexed public* data; never active-scan a
target yourself (that crosses into intrusion/illegality in many jurisdictions).

---

## 8. Dark Web Search Engines
*(Ahmia, Torch, onion-lookup, OnionScan, dark.fail — index engines over Tor/.onion)*
**Tier:** ⚠️ **TIER 0 — DO NOT CRAWL/INGEST.** Narrow *metadata* use only, via third-party
intel feeds — never operate Tor crawling from your own infra.

**Why default-deny for a commercial worldwide product:**
- Content is disproportionately illegal (CSAM, drugs, weapons, stolen data). Crawling/storing
  it exposes you to possession/distribution liability in most jurisdictions.
- Running Tor crawl infra from RIG ties your operation to that traffic. Legal + reputational
  exposure far outweighs the intel for a *general* OSINT product.

**Legitimate sliver (metadata / vendor-mediated only)**
1. **Mention-existence via licensed CTI feeds** — "is this entity/domain/email named on known
   dark-web markets/forums?" delivered by a vendor that crawls under *their* legal umbrella
   (Recorded Future / Flashpoint / Intel471-class). You buy the *finding*, not the content.
2. **Onion-service metadata (onion-lookup)** — existence/uptime/metadata of a .onion service
   without fetching its content → attribution/monitoring, not consumption.
3. **Leak early-warning (fact only)** — flag that a target is *being discussed* for a leak —
   the event, routed through a vendor, contents never stored.

**Creative / different (still hands-off)**
4. **Cross-surface identity bridging** — a vendor-supplied darknet *handle* reusing a
   username / PGP key / crypto address seen on the clearnet → link a surface identity to a
   darknet one via the *identifier*, never the marketplace content.

**Effort:** #1,#3 = integrate a licensed CTI vendor API (buy, don't build) · #2 small.
**Limit / policy:** **never self-host Tor crawling.** Dark-web intel = purchased vendor
findings + public identifiers only. Hard pipeline gate against storing .onion content. Stays
*off* unless a client's mission (threat-intel/fraud) specifically justifies a subscription.

---

## 9. Visual Search and Clustering Search Engines
*(Google Lens, Yandex Images, Bing Visual, TinEye, PimEyes, PicTriev, Carrot2-style visual
clustering, Search4Faces, Berify)*
**Tier:** Search-on-demand + persist. **Opens the entire image/face dimension** — a new
modality (needs a vision pipeline, not LaBSE text). High "how did they find that" payoff.

**Reverse-image features**
1. **Reverse-image lookup** — given a photo → everywhere that image (or near-dupes) appears
   online. Finds the original source, other contexts, and reposts of a target's image.
2. **Cross-engine reverse search** — Yandex ≫ Google for faces/non-Western content; TinEye
   for exact-match + oldest-copy. Route by need: Yandex=faces/similar, TinEye=provenance.
3. **Image-provenance / first-appearance** — TinEye's "oldest" sorts to the *earliest* copy →
   detect when/where an image really originated (catches recycled/miscaptioned imagery).

**Face-centric features (⚠ jurisdiction-sensitive)**
4. **Face → profiles (PimEyes/Search4Faces)** — a face → other photos of the same person
   across the web/social → identity resolution from an image alone.
5. **Same-person clustering** — group all images of one individual across sources into one
   identity node (feeds the entity graph with a *visual* identity).

**Verification / deception features**
6. **Miscaption / recycled-image detector** — the *killer feature*: an image posted as
   "today in country X" that reverse-search shows was published 3 years ago elsewhere →
   instant fake-news / staged-event flag. Direct feed to your disinfo mission.
7. **Sockpuppet face detection** — reverse-search a profile photo; if it's a stock image, an
   AI-generated face, or a stolen photo reused across accounts → coordinated-inauthentic
   -behaviour signal.
8. **Visual near-dup clustering** — cluster an event's images to see how one photo mutated/
   spread → visual narrative-propagation map (image analogue of narrative-origin #1.7).

**Creative / different**
9. **Cross-modal fusion anchor** — a geolocated/timestamped image becomes a hard fact node
   that corroborates (or breaks) text claims → part of the "impossible-coincidence" detector.
10. **AI-generated-image detection** — flag synthetic/deepfake imagery around a target →
    manufactured-evidence early warning.

**Effort:** #1,#2,#3 medium (reverse-image APIs / scraping Yandex-Bing) · #4,#5 medium + vision
model · #6 medium (high payoff) · #10 medium (add a detector model). Needs a **vision service
on the 4090** (CLIP-class embeddings + a detector), separate from the LaBSE text pipeline.
**Limit / policy:** **face search is the sharpest legal edge on the whole list** — PimEyes-
style FRT on *private individuals* is banned/illegal in parts of the EU/US-states and toxic
under GDPR/BIPA. Gate face-search to *public figures / legitimate investigative purpose*;
default-deny on private persons. Reverse-image (non-face) is far safer and broadly legal.

---

## 10. Similar Sites Search
*(SimilarSites, SitesLike, SimilarWeb)*
**Tier:** Search-on-demand + persist. Small category, one genuinely clever use.

**Discovery features**
1. **Related-site expansion** — a target's website → other sites of the same niche/audience →
   discover competitors, mirrors, and the surrounding ecosystem you didn't know to look for.
   Feeds auto source-discovery (#1.3).
2. **Audience-overlap (SimilarWeb-class)** — sites sharing audience/traffic sources → hints at
   coordinated promotion or a shared operator.

**Creative / different**
3. **Coordinated-network mapping** — the clever one: "similar sites" + shared analytics/ad IDs
   (#7.3) → surface a *cluster of look-alike outlets* run by one hand (fake-news farms,
   astroturf blog networks, mirror propaganda sites). Similarity seeds it; infra fingerprint
   confirms it.
4. **Mirror / evasion detection** — find clones of a banned/blocked site under new domains →
   track a target evading takedowns.

**Effort:** #1,#2 small · #3 medium (join with infra fingerprinting).
**Limit:** "similarity" is a content/traffic heuristic, often noisy and SEO-marketing grade.
Only becomes real intelligence when *joined* with infra fingerprinting (#7) — alone it's weak.

---

# ★ SYNTHESIS (categories 1–10) — free-only, most-impactful-first

**Scope of this synthesis:** free tools only (no paid APIs), legality set aside to see raw
capability. The point: what *emerges* when you fuse 1–10 on top of RIG's existing entity graph
+ LaBSE cross-lingual engine.

**The free backbone = SearXNG (you already run it).** Multi-engine, national engines, privacy
engines, meta search, and dork queries ALL execute through one self-hosted instance at zero
per-query cost. Add free infra sources (crt.sh cert-transparency, free passive-DNS, Wappalyzer,
Shodan/Censys free tiers) and free reverse-image (Yandex, TinEye free, Google Lens). That's the
entire stack below — free.

**What we've actually designed (one line):** a free, self-hosted, worldwide, cross-lingual
*discovery + attribution* engine that turns one keyword into a persisted, self-corroborating
entity file — and grows its own source list while doing it.

## The 6 emergent super-features (ranked by impact)

1. **★ Coordinated-network / disinfo unmasking (THE crown).** Fuse dorks (#2) + infra
   fingerprint via free crt.sh certs + shared tracking/ad IDs (#7.3, PublicWWW free) +
   similar-sites (#10) → the **hidden-ownership graph** of look-alike outlets, sockpuppet
   farms, mirror-propaganda networks — from ONE seed. Fuses the most categories, nobody
   ships it, ~free. Lands on your entity graph. **Build first.**

2. **★ Recycled / miscaption image detector.** Reverse-image (#9, Yandex+TinEye free) → an
   image posted as "today" that first appeared years ago = instant fake-news flag. Free,
   killer for the disinfo mission, plugs into narrative analysis.

3. **★ Auto source-discovery → self-growing corpus (#1.3/#3.6).** New domains that keep
   naming targets get promoted into pillar collectors. Compounding, free, feeds EVERY pillar.
   The flywheel — the more it runs, the more it knows worldwide.

4. **Censorship / takedown delta (#1.4/#3.4/#5.5).** Cross-engine + cross-jurisdiction +
   national-engine diff → what each Google-locale / Baidu / Yandex HID. A worldwide state-
   censorship + reputation-laundering detector. Free (all via SearXNG).

5. **Emergence + change-over-time (#1.6/#7.7/#10).** Persist every snapshot → detect when an
   entity/site/server *appeared* or *changed* → pre-event / operational-tempo signal. Free
   (it's just storage + diff).

6. **Narrative-origin trace (#1.7).** Verbatim phrase → earliest indexed copy across engines →
   where a narrative was born before it spread. Free.

## The single most impactful thing overall
**The self-growing worldwide entity graph** = (auto source-discovery #3) feeding (one-keyword
world sweep, backbone) feeding (coordinated-network + image + censorship detectors #1/#2/#4)
— all persisted, all cross-lingual, all free on SearXNG + crt.sh + reverse-image. Everything
else is a feature; THIS is the compounding machine.

## Free vs freemium honesty
- **Truly free / self-hosted:** SearXNG (all search categories), crt.sh certificate transparency,
  Wappalyzer, reverse-image (Yandex/TinEye-free/Lens), narrative + emergence + persistence logic.
- **Free-tier-capped (usable, throttled):** Shodan, Censys, FOFA, PublicWWW, Wigle, HIBP.
- **Only real cost is survival infra:** proxy/residential egress + rotation so SearXNG and
  dorks don't get blocked — that's the true bottleneck, not licensing.

## Plain-English summary (first 10 categories)
You type one thing (name / company / place / website / photo). The system:
- **Searches the whole world at once** — Google + every country's own engine (Baidu, Yandex,
  Naver), in every language, translated back for you.
- **Finds hidden documents** — PDFs/filings/contracts put online but never meant to be found.
- **Finds new sources by itself** — remembers sites that mention your targets and starts
  watching them (gets wider on its own).
- **Reverse-searches any photo** — finds everywhere it appears; flags fake/recycled images
  ("posted as today, actually 3 years old").
- **Unmasks hidden website networks** — proves 50 "different" sites are one operator via shared
  tech fingerprints (propaganda / fake-news farms).
- **Maps a target's online setup** — all their sites/servers, even the separated ones.
- **Spots censorship** — compares countries' engines to reveal what was hidden/deleted.
- **Shows when something appeared** and **where a rumor started.**
- **Remembers everything** (file grows over time, shows what changed) and **watches** (pings
  you when something new appears anywhere).
The magic = it all feeds ONE growing file per target, in every language, and warns on change.
Mostly free (own search box, free photo-search, public records); only real cost = anti-block infra.

---

## 11. Document and Slides Search
*(DocumentCloud, Free-Full-PDF, Find-PDF-Doc, Offshore Leaks (ICIJ), RECAP/CourtListener,
Scribd, SlideShare, Google Docs/Slides indexes)*
**Tier:** Mixed — on-demand for search sites; **ICIJ Offshore Leaks + RECAP court bulk =
promote to store-everything.** One of the highest-value categories for real investigations.

**Document-retrieval features**
1. **Cross-repository document hunt** — one keyword → matching PDFs/DOCX/PPTX/XLSX across
   DocumentCloud, Scribd, SlideShare, free-PDF indexes → the actual primary-source files, not
   articles *about* them.
2. **Leaked/primary-source pull** — ICIJ Offshore Leaks (Panama/Paradise/Pandora), court
   filings via RECAP/CourtListener → hard evidence: shell companies, officers, filings, rulings.
3. **Slide-deck intel** — pitch decks / internal presentations on SlideShare/Scribd → orgs
   leak strategy, financials, org-charts in slides they forget are public.

**Extraction / fusion features**
4. **Full-text + entity extraction on documents** — run your substrate over pulled docs →
   names/orgs/amounts/dates become graph nodes; a filing becomes structured intelligence.
5. **Cross-modal corroboration** — a claim in the news confirmed (or broken) by the actual
   filing PDF → primary-source verification of secondary reporting.
6. **Table/figure extraction** — pull budgets, ownership tables, signatory lists out of PDFs
   into structured rows (feeds financial/ownership analysis).

**Creative / different**
7. **Metadata mining (the tradecraft gem)** — PDF/DOCX metadata leaks author name, org,
   software, creation/edit timestamps, sometimes file paths → attribute *who really wrote* a
   "anonymous" document and when. Unmasks leaks and forgeries.
8. **Document-network graph** — link documents that share authors / templates / metadata /
   named entities → reveal a paper trail nobody connected (same author behind "independent"
   reports).
9. **Version/forgery detection** — diff document versions + metadata inconsistencies → flag
   doctored or backdated files.

**Effort:** #1 medium (multi-repo search) · #4,#6 medium (doc parse + your substrate — largely
reuses existing pipeline) · #2 = ingest ICIJ/RECAP bulk (store-everything) · #7 small-medium
(exiftool-class metadata parse, high payoff).
**Limit:** many "free PDF" indexes are spammy/low-quality; Scribd/SlideShare gate downloads
behind login/paywall. Real gold (ICIJ, RECAP, DocumentCloud) is clean and mostly free. OCR
needed for scanned docs (you already have newspaper OCR to reuse).

---

## 12. Threat Actor Search
*(ThreatActorUsernames, MISP, MITRE ATT&CK, AlienVault OTX, ThreatFox, Malpedia, APT
group trackers)*
**Tier:** Mostly on-demand + persist; some feeds (OTX/ThreatFox) → store-everything. Niche
(cyber), but the *techniques* transfer directly to your disinfo-network work.

**Cyber-attribution features**
1. **Actor/handle lookup** — a username/alias/email → known threat-actor profiles, aliases,
   TTPs, associated campaigns and infrastructure.
2. **IOC pivoting** — an indicator (domain/IP/hash/handle) → all campaigns/actors linked to
   it → attribution graph from a single selector.
3. **Alias-cluster resolution** — one actor's many handles across forums/markets merged into
   one identity (the same selector-bridging trick, applied to adversaries).

**Cross-over to YOUR mission (the real value)**
4. **Disinfo-operator attribution** — treat propaganda/influence networks like threat actors:
   the same TTP/infra/handle-reuse tradecraft unmasks *information* operators, not just malware
   ones. Directly powers your coordinated-network detection (#7.6/#10.3).
5. **Campaign-tracking model** — reuse the "actor → campaign → infrastructure → victims" schema
   to model "influence-actor → narrative → site-network → amplifiers." A ready-made graph
   ontology you can adopt wholesale.
6. **Handle-reuse bridging** — an operator reusing a username/PGP/wallet across cyber AND social
   → link a disinfo persona to a known actor identity.

**Creative / different**
7. **State-actor overlap map** — cross-reference APT/influence-op trackers → surface when a
   disinfo network shares infrastructure/handles with a known state cyber actor → attribution
   of state-sponsored information operations.
8. **TTP fingerprinting for narratives** — as malware has behavioural signatures, influence ops
   have posting-cadence / template / cross-post signatures → fingerprint and match recurring
   operators across campaigns.

**Effort:** #1,#2 small (OTX/MISP/ThreatFox have free APIs) · #4,#5 medium (adopt the ontology
into your graph) · #7,#8 = differentiators built on your existing clustering.
**Limit:** most content is cyber-security-specific — direct value to a *political* OSINT product
is the transferable *method and ontology*, not the malware data itself. Adopt the framework;
don't drown in IOC feeds you won't use.

---

## 13. Live Cyber Threat Maps
*(Kaspersky Cybermap, FortiGuard, Checkpoint ThreatMap, Digital Attack Map, Radware)*
**Tier:** Mostly **skip** (visual dashboards, not ingestible). One narrow real use.

**Honest read:** these are marketing eye-candy — animated globes of attack traffic, meant to
look impressive on a SOC wall. Almost no queryable, entity-level intel behind them.

**The one real use**
1. **Macro attack-tempo context** — aggregate "attacks spiking from/to country X right now" as
   a *background situational* layer, not target-level intel. Useful only as ambient context
   (e.g. corroborate a broader cyber-conflict narrative around an event).
2. **Underlying-feed capture** — some (Radware/Digital Attack Map via Arbor) expose the *data
   feed* behind the map → that feed, not the animation, is the only ingestible part.

**Effort:** trivial-but-low-value. Not worth prioritising.
**Limit:** no keyword/entity search, no attribution, no persistence value. Pretty, shallow.
Recommendation: **skip for the agent**; if you ever want the ambient layer, grab the raw feed
behind one map, ignore the rest.

---

## 14. File Search
*(FilePursuit, search-that-hosts open directories, FTP/HTTP index search, eDonkey/torrent
metadata search, "index of" engines, File Chef, Mmnt)*
**Tier:** Search-on-demand + persist. Genuinely useful — hunts *files* the open web hosts
but doesn't link to.

**Exposed-file features**
1. **Open-directory / index hunt** — a keyword → files sitting on misconfigured public
   servers and open directories (docs, media, archives, backups) that no page links to.
2. **Filetype-targeted retrieval** — pull specific formats about a target (PDF/XLSX/ZIP/media)
   straight from hosts, bypassing search-engine ranking → the raw file, not the article.
3. **Media/asset discovery** — images/video/audio files tied to a target sitting on open
   hosts → feeds the visual + video pipelines.

**Intelligence features**
4. **Exposed-backup / leak discovery (legal side)** — surface publicly-exposed backups, DB
   dumps, config files that are *openly indexed* → the no-breach-dump path to leaked material
   (same discipline as dork #2.9 — public-index only, never exploit).
5. **File → metadata → attribution** — every pulled file runs through metadata mining (#11.7)
   → author/org/timestamps → who put it there.

**Creative / different**
6. **Standing exposed-file watch** — monitor for *new* files about a target appearing on open
   hosts → early-warning on leaks/dumps before they're noticed and spread.
7. **Cross-host file-cluster** — the same file (by hash) appearing on multiple hosts → maps
   distribution/mirroring of a document or dataset.

**Effort:** #1,#2 small-medium (query file-index engines) · #5 reuses metadata parse · #6 medium
(watch loop).
**Limit:** heavily spam/junk-laden; open-directory results are noisy and often dead links.
Torrent/eDonkey metadata skews to piracy — filter hard. Value concentrated in #4 (exposed
docs) + #5 (attribution); treat the rest as low-signal.

---

## 15. Pastebins
*(Pastebin, Ghostbin, Rentry, PrivateBin, Paste.ee, + paste-aggregators like PSBDMP,
Pastebin-scraper feeds)*
**Tier:** **Store-everything (monitor the firehose)** for aggregators; on-demand for lookups.
Small category, classic early-warning source.

**Monitoring features**
1. **Keyword/selector paste-monitoring** — watch the public paste firehose for a target's
   name/domain/email/handle → catch leaks, dumps, claims the moment they're posted.
2. **Leak early-warning** — pastes are where credential dumps, doc leaks, and "we hacked X"
   announcements land *first*, before news → hour-zero alerting (the metadata/existence, not
   the stolen contents — same policy gate as #6).
3. **Historical paste search (PSBDMP)** — search *past* pastes mentioning a target → recover
   leaks/claims already posted and forgotten.

**Intelligence features**
4. **Claim-of-responsibility capture** — hacktivist/ops groups announce actions in pastes →
   attribute events to actors, track campaigns (ties to threat-actor #12).
5. **Coordination artifact** — pastes used to share target lists, scripts, talking-points →
   evidence of coordinated activity (disinfo/brigading playbooks).

**Creative / different**
6. **Selector-bridging via pastes** — a paste often bundles handles + emails + wallets +
   domains together → one paste can *link multiple identities* of a target in a single blob →
   powerful entity-resolution seed.
7. **Narrative-seed detection** — coordinated talking-points dropped in pastes before a
   campaign launches → catch an influence op at the *planning* stage, not the spread stage.

**Effort:** #1,#2 small-medium (Pastebin scraping API + PSBDMP) · #6 medium (parse+link) ·
#7 medium (pattern detection).
**Limit:** Pastebin heavily rate-limits/removed its public scraping API for free tier; much
monitoring now needs paid Pastebin PRO or third-party aggregators. High noise (spam/code).
Ephemeral — pastes get deleted fast, so monitoring must be near-real-time to catch them.

---

## 16. Code Search — SKIPPED (user deprioritised)
*(GitHub/GitLab/Grep.app/SearchCode/PublicWWW-code — leaked-secret & attribution source.
Revisit later if a client mission needs credential-leak or dev-attribution work.)*

---

## 17. Major Social Networks
*(FB, Instagram, X/Twitter, TikTok, LinkedIn, Reddit, VK, Telegram, YouTube — the platforms
themselves as intelligence surfaces)*
**Tier:** Pillars for the ones you already ingest (Reddit/Telegram/Twitter/IG = store-
everything). This entry = the *extra OSINT* you extract from social BEYOND raw ingestion.
The per-platform sections that follow cover platform-specific tricks.

**Content-intelligence features (cross-platform)**
1. **Profile → full identity picture** — a handle → bio, history, posts, media, followers,
   following → who they are and what they care about, resolved to an entity node.
2. **Cross-platform identity linking** — same person across FB+X+IG+TikTok via username reuse,
   bio/link overlap, profile-photo reverse-search (#9), writing style → merge into one identity.
3. **Post-history mining (latest + historical)** — full timeline of what a target said, when →
   feeds stance/sentiment, position-change-over-time, contradiction detection.

**Network-intelligence features (the real power)**
4. **Social network graph** — who follows/mentions/replies-to whom → map a target's real
   network: allies, amplifiers, inner circle, funders. This is the graph social media is FOR.
5. **Amplifier / bot-cluster detection** — accounts that reliably co-amplify a target →
   coordinated-inauthentic-behaviour + astroturf detection (ties to #7/#10 network unmasking).
6. **Community/faction mapping** — cluster a target's network into communities → see which
   camp/movement/party they belong to and who bridges factions.

**Behavioural / temporal features**
7. **Posting-pattern analysis** — cadence, timezone, active-hours → infer location, automation
   (bot vs human), and operational tempo.
8. **Sentiment & stance at scale** — reuse your existing article_stances engine on social →
   directed sentiment (who attacks/supports whom) across the network.

**Creative / different**
9. **Deleted-content / edit capture** — snapshot posts continuously → recover what a target
   *deleted* or edited → the "what they tried to unsay" signal (negative-space, social edition).
10. **Geolocation from posts** — cues in images/captions/check-ins → place a target in
    space/time (feeds cross-modal fusion #9.9).
11. **Emergence/coordination timing** — many accounts posting the same line in a tight window →
    detect a campaign *launching* in real time.

**Effort:** #1,#3,#8 = mostly reuse your pillars + substrate · #4,#5,#6 medium (graph build on
data you already collect) · #9 medium (continuous snapshot) · #2,#10 medium + reverse-image.
**Limit:** platform APIs are locked-down/paywalled (X, FB, IG) — you already fight this with
relays (IG session-death, Twitter ban-pool). Deleted-content + network mapping are the highest-
value, hardest-to-buy features; per-platform ToS/rate-limits dominate feasibility (next sections).

---

# ★ COLLECTION TECHNIQUES — beyond proxies/relays (the cheap unlock)

**Core insight:** proxies are for looking like *many different people*. Most OSINT collection
only needs to look like *one real browser* (TLS impersonation) or to *not hit the platform at
all* (frontends/archives). RIG has been paying the "many people" proxy tax on jobs that needed
neither. Stack these → proxy/account spend shrinks to a last-mile fraction.

**1. TLS/JA3 fingerprint impersonation — `curl_cffi` / `curl-impersonate`**
Plain `requests` is blocked because its TLS handshake ≠ a browser (Cloudflare fingerprints
JA3/JA4 + HTTP/2 frame order in ms). `curl_cffi` replicates Chrome's exact TLS/HTTP2 signature
→ many sites that block `requests` pass it through with **no proxy**. Cheapest "stop looking
like a bot" upgrade; drop-in library. *Doesn't beat JS challenges (see #6).*

**2. Self-hosted alternative front-ends**
Open-source mirrors that extract clean content, no auth: **Nitter** (X), **Invidious/Piped**
(YouTube), **Redlib** (Reddit), **ProxiTok** (TikTok). Public instances are dying (Nitter
"abandoned", rate-limited) → **self-host your own** and get their battle-tested extraction on
your box.

**3. RSS-Bridge (self-hosted)**
General scraper framework → converts hundreds of sites (incl. social) into RSS. Point RIG's
EXISTING pillar RSS collector at it → no-API platforms flow into the pipeline already running.
Lowest-effort win for RIG specifically.

**4. Archives instead of live sites — zero blocking**
**Wayback Machine** + **Common Crawl** already crawled the web. For *historical* data, query
them, not the live platform → no blocks, no proxy, and it IS the "historical scrape" the
product needs. Common Crawl = petabytes free.

**5. Official no-auth side-doors**
oEmbed/embed endpoints (YouTube/Twitter/IG), guest tokens (temp anon tokens the web player
uses), JSON-LD/sitemaps baked in for SEO, search-engine cache. Official data, no auth, no ban.

**6. Stealth browsers (only for JS-challenge walls)**
`nodriver` / `undetected-chromedriver` / Playwright-stealth. Efficient pattern: solve the
challenge ONCE, grab the `cf_clearance` cookie, hand it to fast `curl_cffi` for thousands of
cheap follow-ups.

**7. Real-cookie reuse**
Log in once in a real browser, export session cookies, feed the scraper → indistinguishable
from browsing (YouTube relay already does this; generalise it).

## Which trick solves which problem platform
| Platform | Primary technique | Proxy still needed? |
|---|---|---|
| **YouTube** | Self-host Invidious/Piped + cookie relay + Common Crawl (history) | Rarely |
| **Twitter/X** | Self-host Nitter + guest-token + Wayback (history) | Low |
| **Instagram** | curl_cffi + real-cookie aged session + oEmbed public; stealth fallback | Yes for live private — far less |
| **TikTok** | Self-host ProxiTok + curl_cffi | Sometimes |
| **Reddit** | Free API + Redlib fallback | No |
| **VK / Telegram** | Free official APIs | No |
| **LinkedIn/FB** | Paid per-lookup API (don't self-scrape) | N/A (buy) |

## Cheapest slick stack (near-zero proxy)
curl_cffi everywhere · self-hosted Nitter/Invidious/RSS-Bridge → existing RSS pipeline ·
Common Crawl+Wayback for all history · oEmbed/guest tokens for public data · stealth browser
only as JS-challenge fallback (cookie-cached) · proxies + aged accounts ONLY for last-mile
live IG/TikTok private data.

## Money — cheapest tier
Near-$0/mo + ~$50 one-time (aged IG accounts). Reuse owned residential boxes (YT relay laptop,
TRIJYA workstations on home lines) as free residential egress. Free official APIs: VK, Telegram,
Reddit. Add ONE ~$30/mo mobile proxy only if IG volume strains. Skip LinkedIn/FB until budget.
Real recurring cost is human maintenance (~5–10 h/wk), not tools.

**Sources:** curl_cffi (brightdata/datahut), curl-impersonate, alternative-front-ends
(github mendel5), Nitter, RSS-Bridge, Common Crawl.

## ★ VERIFIED LIVE (2026-07-06) — code: backend/collectors/cheap_stack/
Built + tested standalone modules (browser_fetch/oembed/archive/frontends). No proxy, no key.
**Free-core 5/5 PASS:** curl_cffi TLS bypass (200 off Cloudflare) · YouTube oEmbed · Wayback
latest+history · Common Crawl index (CC-MAIN-2026-25).
**Social scorecard (free methods, live):**
- ✅ PASS: YouTube (oEmbed), Twitter/X (oEmbed), Telegram (t.me/s preview ~19 posts).
- 🟡 PARTIAL: Instagram/VK/Facebook (public page loads, full data login-walled; VK proper =
  free official API token).
- ❌ FAIL(free): Reddit anon .json 403 — BUT free OAuth API works (already used); TikTok
  (drops non-browser); LinkedIn (paid only).
**Verdict: 5/9 platforms genuinely free (YT, Twitter, Telegram, +Reddit/VK via free tokens).
Paid last-mile only for IG, TikTok, FB, LinkedIn.**
Not yet wired into Celery/pillars; verified on Windows dev box (re-test on Hetzner datacenter IP).

## ★ HARD-PLATFORM EXTRA METHODS — verified live 2026-07-06 (verify_hard.py)
Two problem children cracked open FREE:
- ✅ **Instagram** — `web_profile_info?username=X` + header `x-ig-app-id: 936619743392459`
  returned real data (@instagram 685M followers, 8511 posts). Fixes the "empty edges" issue
  (app-id header is the unlock). CAVEAT: datacenter IPs 403 on first request; residential IP
  capped ~200/hr; IG rotates doc_id → breaks every 2-4wk. Needs residential egress + swap-able
  interface. On Hetzner (datacenter) will likely 403 — route via residential relay.
- ✅ **TikTok** — `tikwm.com/api/user/info?unique_id=X` 3rd-party free API returned code=0.
  (Direct HTML UNIVERSAL_DATA blob FAILED — TikTok drops connection.) CAVEAT: 3rd-party you
  don't control; wrap behind interface.
- 🟡 **VK** — page-scrape JS-walled; real path = FREE official API token (api.vk.com).
- 🟡 **WeChat** — Sogou Weixin (weixin.sogou.com) reachable = THE public-account OSINT route;
  public Official Accounts only (personal = app-only), anti-crawl heavy, needs parse. Also
  wechat2rss / wechat_db_parser as alt routes.
- ❌ **Facebook** — mbasic still login-walled; paid last-mile.

**Updated: 7/10 platforms have a FREE method** (YT, Twitter, Telegram, IG*, TikTok*, Reddit,
VK; *=residential/3rd-party caveat). WeChat partial (public accts). Only Facebook + LinkedIn
truly need paid. Key constraint is residential egress + swap-able method interfaces, NOT money.

## ★ REAL COLLECTORS BUILT + VERIFIED E2E — 2026-07-06
Framework: base.py (Collector + swap-able Method protocol + normalized ProfileResult + Egress
proxy routing). Files: instagram.py, tiktok.py, wechat.py, verify_collectors.py.
Design: each platform = ordered list of Methods (primary first); a broken method is swapped/
reordered without touching callers; every method returns the SAME normalized ProfileResult;
Egress(proxies=...) routes blocked platforms through residential exit on datacenter hosts.
**End-to-end live PASS (normalized interface, direct egress):**
- ✅ Instagram @instagram → 685,835,829 followers, 8511 posts, verified (web_profile_info+app_id)
- ✅ TikTok @tiktok → 94,696,680 followers, 1546 posts, verified (tikwm_api; html_universal_data
  fallback wired)
- ❌ WeChat 腾讯 → Sogou returns EMPTY result shell (not captcha) from non-China residential IP.
  Cookie-priming (homepage→search on one session) added but insufficient: Sogou soft-blocks by
  geo/trust. Collector code correct; needs China-IP OR aged-cookie session. Alt routes to add
  as Methods: wechat2rss, wechat_db_parser (local client DB). Personal accts = app-only always.
## ★ PIPELINE ADAPTER + HETZNER VERIFICATION — 2026-07-06 (DONE)
pipeline_adapter.py emits the EXACT social_posts dict shape (platform, platform_post_id,
author_username, post_text, post_url, upvotes, comment_count, posted_at) — drop-in for
social_task, no schema change. Functions: collect_instagram_posts (web_profile_info edges),
collect_tiktok_posts (tikwm /user/posts), collect_telegram_web (t.me/s — NO bot token, upgrade
over current bot-API telegram). verify_pipeline.py = dry-run shape check (no DB write).
**VERIFIED LIVE on BOTH Windows dev + Hetzner rig-backend (datacenter IP): 3/3 PASS**, real
content (IG captions, TikTok titles, TG posts). curl_cffi 0.15.0 present in container.
SURPRISE (verify-don't-assume): IG web_profile_info PASSED from Hetzner datacenter IP — earlier
403 prediction WRONG at low volume. Residential egress still advised at scale (~200/hr IP cap).
Hetzner scorecard: IG✅ TikTok✅ YouTube✅ Twitter✅ Telegram✅ ; Reddit=free OAuth(existing);
VK=free token; WeChat/FB/LinkedIn=hard.
**Remaining hookup (not yet applied to prod):** import the 3 adapter fns into social_task loop
over the watchlist → existing sentiment/entity/insert path handles the rest. Code on box at
/root/rig/backend/collectors/cheap_stack/ (bind-mounted, live in container).
**Still to add:** fallback Methods (instagrapi IG, wechat2rss WeChat); VK official-API method.

## ★ WeChat re-probed 2026-07-06 — splits into 2 problems
- **CONTENT = SOLVED (free):** mp.weixin.qq.com public article pages fetch fine via curl_cffi
  (200, 53KB real content). If we HAVE a public-account article URL, RIG pulls + parses it free.
- **DISCOVERY = BLOCKED from our IPs:** Sogou returns empty shell even with cookie-prime +
  zh-CN headers (soft geo/trust block, non-China IP). Public RSSHub /wechat = 403. werss.app
  reachable (200) but needs signup/biz-id.
- **To fully enable WeChat:** (a) China-region residential proxy for Sogou discovery, OR
  (b) seed known public-account article URLs → content fetch works today, OR (c) paid
  werss/wechat2rss (bind account biz-id). Personal accounts = app-only always.
- Verdict: WeChat is CONTENT-ready, DISCOVERY-blocked. The proxy budget's one real WeChat need
  is a CN residential exit for the Sogou discovery step only.

## ★ WeChat FREE discovery FOUND 2026-07-06 — no China IP, no cost (proven live)
The workaround: skip Sogou entirely — Western engines already index public WeChat articles.
- ✅ **DuckDuckGo `site:mp.weixin.qq.com <keyword>`** returned real mp.weixin.qq.com/s/ article
  URLs (2 from one query, no China IP). THE free discovery route.
- Bing returned page but 0 usable links for the dork; DDG is the winner.
- freewechat.com = reachable public WeChat mirror (100KB home) — viable BACKUP discovery route.
- Production: existing SearXNG fans the same `site:` dork across DDG+Google+Bing+Yandex → far
  more links per query than raw DDG.
**COMPLETE FREE WeChat pipeline:** discovery via site:dork (SearXNG/DDG) → content via
curl_cffi fetch of mp.weixin.qq.com/s/ pages. Both halves free. CN proxy no longer required.
(Personal accounts still app-only — public Official Accounts only, which is the OSINT-relevant part.)

---

## 18. Domain & IP Research + DNS
*(whois/RDAP, crt.sh, SecurityTrails, ViewDNS, HackerTarget, dnsdumpster, Shodan/Censys,
subfinder/amass, BGP/ASN tools, SPF/DKIM/DMARC lookups)*
**Tier:** Search-on-demand + persist. **Highest attribution-value, cleanest-free category on
the list.** Fully automatable, legal, lands directly on the entity/infra graph.

**Resolution & ownership features**
1. **WHOIS/RDAP lookup** — registrant (where not GDPR-redacted), registrar, create/expiry dates,
   nameservers. RDAP (rdap.org) = the modern free/structured whois.
2. **Full DNS record pull** — A/AAAA/MX/NS/TXT/CNAME/SOA → mail provider, hosting, verification
   tokens, infra map of a domain.
3. **ASN / netblock ownership** — which org owns the IP range → attributes hosting to a real
   entity (BGP/ASN tools).

**Infra-graph features (the crown)**
4. **Certificate transparency (crt.sh — FREE, unlimited)** — every TLS cert ever issued for a
   domain → instant subdomain + related-domain discovery. The single best free pivot.
5. **Subdomain enumeration** — crt.sh + subfinder/amass → the full attack/asset surface a
   target exposes (dev, staging, admin, regional subdomains).
6. **Reverse IP / shared-host** — other domains on the same IP → co-located assets (weak alone;
   strong with dedicated IPs).
7. **Passive DNS (historical resolutions)** — SecurityTrails/DNSDB → what a domain resolved to
   OVER TIME → catch infra moves, hidden origin behind Cloudflare, past hosting.

**Attribution / historical features**
8. **Reverse WHOIS** — all domains registered by the same email/name/org → unmask a network of
   domains one actor owns (pre-GDPR + leaked data still rich).
9. **Historical WHOIS** — who owned it BEFORE privacy protection → the original registrant.
10. **Email-security records (SPF/DKIM/DMARC)** — mail infra + provider fingerprint; DMARC
    reporting addresses sometimes leak internal domains.

**Creative / different**
11. **Origin-behind-CDN unmasking** — passive DNS + cert history + Shodan favicon/JA3 → find the
    REAL server IP hiding behind Cloudflare → deanonymize a "protected" target's host.
12. **Disinfo-network infra graph** — shared registrant + shared cert + shared NS + same
    hosting → prove N "independent" sites are one operator (the #7/#10 crown, DNS-side).
13. **Infra change-watch** — persist DNS/WHOIS/cert snapshots → alert when a target changes
    hosting, adds a subdomain, or renews under a new name (pre-event / operational-tempo signal).

**Effort:** #1,#2,#4 small (free: RDAP, dig, crt.sh) · #5,#8,#11,#12 medium (pivot logic + graph)
· #7 needs SecurityTrails/DNSDB (freemium) · #13 medium (snapshot diff).
**Limit:** GDPR gutted WHOIS registrant data (2018+) — much is redacted; historical/reverse
WHOIS + leaks fill the gap but are freemium. Passive DNS depth is the main paid line. crt.sh +
RDAP + live DNS cover ~70% of value for free.
**Cheapest-free core:** crt.sh (certs/subdomains), RDAP (whois), live DNS (dig), Shodan free
tier — enough for the infra-graph crown feature (#12) at zero cost.

**Plain-English:** digs into a target's INFRASTRUCTURE (servers/domains/mail), not their words.
Find who registered a site + who owns the server; find hidden sub-sites via free cert records;
see who owned it before they hid + the real server behind Cloudflare; PROVE N "independent"
sites are one operator via shared registration/server/cert (the payoff); watch for infra
changes. Infrastructure doesn't lie. Mostly free, no ban risk.

---

## 19. Keywords Discovery and Research
*(Google Trends, Google/Bing autocomplete, AnswerThePublic, Keyword Tool, Ubersuggest,
AlsoAsked, Reddit/YouTube keyword tools)*
**Tier:** Search-on-demand + persist. A SUPPORT category — it doesn't collect intel itself,
it makes every OTHER collector smarter by expanding what to search for.

**Query-expansion features (the real use)**
1. **Keyword/alias expansion** — a target term → related terms, spellings, co-occurring words →
   feeds broader, less-missable queries into every search/social/WeChat collector (pairs with
   cross-lingual expansion #1.8). Fewer blind spots from one narrow keyword.
2. **Autocomplete mining** — Google/Bing/YouTube autocomplete for a name → what the public
   ACTUALLY searches about them → surfaces associations, scandals, aliases you didn't know.
3. **"People also ask" / AlsoAsked** — the question-graph around a target → the concerns,
   controversies, and links the public associates with them.

**Trend/temporal features**
4. **Search-interest over time (Google Trends)** — when did interest in a target/topic spike →
   corroborate events, detect emergence, map attention lifecycle.
5. **Geographic interest** — where a term is searched most → regional salience of a target/topic.
6. **Rising vs declining** — breakout terms around a topic → catch an emerging narrative early.

**Creative / different**
7. **Autocomplete manipulation detection** — suspiciously scrubbed or seeded autocomplete for a
   target → reputation-management / astroturf signal (pairs with censorship-diff #1.4).
8. **Narrative-vocabulary discovery** — the exact phrasing a community uses for a topic →
   generate native-language search terms an outsider wouldn't guess (critical worldwide).
9. **Demand-side intelligence** — what people search reveals public concern/intent that no
   published article states → a read on sentiment/attention that content alone misses.

**Effort:** #1,#2,#3 small (autocomplete endpoints are free/unofficial) · #4,#5,#6 small
(Google Trends via pytrends) · #7 medium.
**Limit:** not an intel SOURCE — it's a query optimizer + attention gauge. Google Trends is
relative (no absolute numbers) and noisy for low-volume/regional terms. Autocomplete APIs are
unofficial and rate-limited. Value is multiplying other collectors, not standalone.

---

## 20. Web History and Website Capture
*(Wayback Machine, archive.today/archive.ph, Common Crawl, Time Travel/Memento, CachedView,
Perma.cc, Stillio/screenshot-capture)*
**Tier:** Search-on-demand + persist; Common Crawl bulk = store-everything. Your FREE,
unblockable route to HISTORICAL data. Partly proven live already (Wayback + Common Crawl).

**Retrieval features**
1. **Historical snapshots (Wayback)** — any URL as it looked on any past date → recover deleted/
   edited pages, old versions, vanished sites. VERIFIED live in cheap_stack.
2. **Capture-on-demand (archive.today)** — freeze a live page NOW into a permanent, tamper-proof
   snapshot → evidence preservation before a target deletes it.
3. **Common Crawl bulk** — petabyte web corpus → query historical pages at scale without
   crawling anything yourself. VERIFIED live (index CC-MAIN-2026-25).
4. **Memento aggregation** — one query across ALL archives (Wayback + archive.today + national
   libraries) → maximum historical coverage.

**Change-detection features (the real power)**
5. **Deleted/edited-content recovery** — diff current page vs archived → what a target REMOVED
   or quietly changed (the negative-space signal, web edition).
6. **Timeline reconstruction** — all captures of a page → how a site/claim evolved over time →
   catch backdating, walked-back statements, scrubbed history.
7. **Emergence detection** — first-ever capture of a domain → when a site/entity actually
   appeared (corroborates #1.6).

**Creative / different**
8. **Evidence preservation for volatile targets** — auto-archive a page the moment it's found →
   court/report-grade proof that survives deletion (archive.today is tamper-evident).
9. **Scrub / takedown detection** — page existed in archive but now 404/changed → someone
   erased it → reputation-laundering / censorship signal (pairs with #1.4, #18.13).
10. **Bypass live blocks** — can't scrape a live site (paywall/geo/ban)? Pull the archived copy
    instead → free, unblockable collection (already a cheap_stack pillar).

**Effort:** #1,#3 done (cheap_stack archive.py) · #2,#4 small · #5,#6,#9 medium (diff logic).
**Limit:** archives are incomplete (not every page/date captured); JS-heavy/dynamic pages often
archive poorly; Common Crawl lags weeks-months (not for "latest"). Great for HISTORY + proof,
not real-time. archive.today has its own rate-limits/captcha for heavy capture.

---

## 21. Language Tools
*(Google/DeepL Translate, transliteration tools, script converters, language detection,
romanization, dialect/slang dictionaries)*
**Tier:** Support category (not a source). Multiplies EVERY collector's worldwide reach.
For RIG this partly overlaps existing infra (LaBSE cross-lingual embeddings, translation).

**Cross-lingual reach features**
1. **Query translation/transliteration** — target term → native scripts/spellings (Hanzi/
   Cyrillic/Arabic/Devanagari) → hit national engines + local social in the RIGHT words
   (powers #1.8, #3.3, WeChat discovery, national routing).
2. **Language/script detection** — auto-tag incoming content's language → route to the right
   parser/model (fixes the measured language_iso 32%-missing gap).
3. **Romanization/name variants** — one person's name across scripts/spellings (محمد/Mohammed/
   Muhammad; Xi Jinping/习近平) → critical for global entity resolution (the "same person, many
   spellings" problem).

**Comprehension features**
4. **Content translation for analysts** — foreign articles/posts → analyst's language (you
   already have gist/summary translation ~92%; full-body ~33%).
5. **Dialect/slang normalization** — regional slang, code-words, transliterated chat →
   canonical terms → don't miss content hidden in local vernacular.

**Creative / different**
6. **Code-word / euphemism decoding** — communities use coded language to evade detection
   (political euphemisms, dog-whistles, leetspeak) → a slang layer surfaces what keyword search
   misses. High value for extremist/disinfo monitoring.
7. **Translationese / MT-detection** — text that reads machine-translated → flag content mass-
   produced by a foreign influence op (a coordinated-inauthentic-behaviour tell).
8. **Cross-script alias bridging** — link identities that only match once transliterated →
   feeds the entity graph across languages (pairs with #3.7).

**Effort:** #2,#3 small (langdetect/transliteration libs) · #1 reuses translation infra · #6,#7
medium (dictionaries + classifier). Much overlaps RIG's existing LaBSE/translation stack.
**Limit:** MT quality is weak for low-resource languages, poetry, heavy slang, and code-words
(the exact places intel hides). Translation ≠ understanding — nuance/sarcasm/context lost.
Not a source; a reach + comprehension multiplier. Overlaps existing infra — don't rebuild.

---

## 22. Image Search
*(Google Lens, Yandex Images, Bing Visual, TinEye, Karma Decay, Pixsy, SauceNAO)*
**Tier:** Search-on-demand + persist. Overlaps #9 (Visual Search); this entry = the pure
image→web lookup layer. Needs the vision service on the 4090, not LaBSE text.

**Reverse-lookup features**
1. **Reverse image → all appearances** — a photo → everywhere it (or near-dupes) appears online
   → find the original source, every repost, and the contexts it's used in.
2. **Engine routing** — Yandex ≫ Google for faces/non-Western/regional imagery; TinEye for
   exact-match + oldest copy; SauceNAO for illustrations/anime → route by image type.
3. **Crop/partial match (Yandex/Lens)** — match on a fragment (a logo, a face, a building) even
   when the rest of the image differs.

**Provenance / verification features**
4. **First-appearance / provenance (TinEye oldest)** — earliest copy of an image → when/where
   it really originated → catch recycled or miscaptioned photos (the #9.6 killer, image-search
   side).
5. **Miscaption detector** — "photo from today" that reverse-search dates years back elsewhere →
   instant fake-news flag. Highest-value, legal, feeds disinfo mission.

**Creative / different**
6. **Object/landmark/text-in-image search (Lens)** — identify a building, product, sign, or
   read text inside a photo → geolocation + entity leads FROM an image (pairs with geospatial).
7. **Logo/uniform/insignia matching** — match unit patches, party logos, corporate marks →
   attribute affiliation from imagery (conflict/OSINT staple).
8. **Cross-image entity clustering** — same object/scene across many posts → track how a visual
   spreads and mutates (visual narrative-propagation, #9.8).

**Effort:** #1,#2,#4 medium (reverse-image via Yandex/TinEye/Bing — some free, some API) · #6
medium (Lens/vision model) · #5 medium, high payoff. Needs 4090 vision service (CLIP + OCR).
**Limit:** Google Lens has no clean free API (scrape or paid); face-focused matching = the
GDPR/BIPA legal edge (gate to public figures, #9). Reverse-image works best on distinctive
images; generic/low-res photos return noise. OCR-in-image quality varies by script.

---

## 23. Image Analysis
*(EXIF viewers, FotoForensics/ELA, Forensically, InVID/WeVerify, Ghiro, Sherloq, deepfake
detectors, ShadowFinder/SunCalc for chrono-geolocation)*
**Tier:** Processing layer (on a collected image), not a search source. Extracts intel FROM
the pixels. Needs the 4090 vision service. This is where an image becomes hard evidence.

**Metadata features**
1. **EXIF/metadata extraction** — camera, device, software, timestamps, and (if present) GPS
   coordinates baked into a photo → who/what/when/WHERE from the file itself.
2. **Metadata → attribution** — device/software fingerprint links photos to the same source/
   camera → tie images to one creator (pairs with doc metadata #11.7).

**Forensic / authenticity features**
3. **Manipulation detection (ELA/Forensically)** — error-level analysis, clone detection, noise
   analysis → flag photoshopped/edited images.
4. **Deepfake / AI-generated detection** — flag synthetic faces/scenes → manufactured-evidence
   early warning (pairs with #9.10).
5. **Video frame forensics (InVID/WeVerify)** — keyframe extraction + per-frame reverse search →
   verify/debunk video, the video-side of the miscaption detector.

**Geolocation features (the crown)**
6. **Visual geolocation (chrono-geolocation)** — deduce location from shadows+time (ShadowFinder/
   SunCalc), signage, architecture, vegetation, license plates → place an unlabeled photo in the
   world. The Bellingcat signature skill.
7. **GPS-from-EXIF** — when coordinates survive → exact location instantly.
8. **Landmark/scene recognition** — vision model IDs the place → geolocation without metadata.

**Creative / different**
9. **Cross-modal fusion anchor (THE payoff)** — a geolocated + timestamped image becomes a HARD
   fact node that corroborates or BREAKS text claims → the "impossible-coincidence" detector
   (#9.9). Image forensics is what makes fusion trustworthy.
10. **Staged-event detection** — forensics + geolocation + reverse-search together → prove a
    "spontaneous" scene was staged/recycled (disinfo debunking, evidence-grade).
11. **Chrono-consistency check** — do shadows/weather/foliage match the CLAIMED date/place? →
    catch fabricated timing.

**Effort:** #1,#7 trivial (exiftool) · #3,#5 medium (forensic libs/InVID) · #4 medium (detector
model on 4090) · #6,#8 hard (vision + reasoning — the genuinely hard, high-value bit).
**Limit:** platforms STRIP EXIF on upload (most social kills GPS) — metadata gold is rare on
social imagery. Visual geolocation is hard, often needs human-in-loop. Deepfake detection is an
arms race (never 100%). Forensics gives probability, not proof — flag, don't conclude.

---

## 24. Video Search and Other Video Tools
*(YouTube/Google video search, InVID/WeVerify, Amnesty YouTube DataViewer, yt-dlp, Whisper
ASR, Invidious, TikTok/Bilibili/Rumble/Odysee search, keyframe/thumbnail reverse-search)*
**Tier:** Search-on-demand + persist; YouTube pillar = store-everything (already yours).
Builds on your existing Clips pillar. Needs 4090 for ASR/vision.

**Discovery features**
1. **Cross-platform video search** — a keyword → matching videos across YouTube + TikTok +
   Rumble + Odysee + Bilibili → beyond the one platform you already index.
2. **Metadata extraction (yt-dlp/DataViewer)** — upload time, uploader, description, exact
   publish timestamp, thumbnails → who posted what, when (Amnesty DataViewer gives precise
   upload time YouTube hides).
3. **Channel/uploader mapping** — a channel → its full catalogue, subscribers, linked accounts →
   network + output-tempo of a video propagandist.

**Content-intelligence features**
4. **Transcription (Whisper ASR)** — speech→text in any language → make video searchable/entity-
   taggable like articles (you already do YouTube transcripts; extend to any platform + any
   language locally on 4090).
5. **On-screen text/OCR + scene tags** — read banners/chyrons/signs in-frame + tag scenes →
   structured intel from the visual track, not just audio.
6. **Translated transcript** — foreign-language video → analyst-readable (pairs #21).

**Verification / forensic features**
7. **Keyframe reverse-search (InVID)** — extract keyframes → reverse-image each → catch reused/
   miscaptioned/recycled video (the video miscaption detector, #23.5).
8. **First-upload / provenance** — earliest copy of a clip across platforms → original source vs
   re-upload → debunk "new footage" that's old.
9. **Deepfake/synthetic-video flag** — flag manipulated video (arms race; pairs #23.4).

**Creative / different**
10. **Speaker/voice fingerprinting** — match a voice across videos → attribute anonymous/
    voice-over clips to a known person (you have TTS/voice infra to draw on).
11. **Live-event geolocation from video** — frames → chrono-geolocation (#23.6) → place a video
    in space/time → conflict/event verification.
12. **Coordinated-upload detection** — same clip posted across many channels in a tight window →
    influence-op amplification signal (video-side CIB).

**Effort:** #1,#2 small (yt-dlp/DataViewer) · #4 = extend your YT ASR to all platforms/langs on
4090 · #7,#8 medium · #10,#11 hard. Reuses Clips pillar + relay infra heavily.
**Limit:** video is the HEAVIEST to process (download+ASR+vision = GPU/time cost); non-YouTube
platforms need the same relay/anti-block treatment as social; ASR weak on noisy audio/dialects;
deepfake detection never certain. Highest compute-cost category — prioritise by target value.

---

## 25. Academic Resources and Grey Literature
*(Google Scholar, Semantic Scholar, CORE, BASE, arXiv/SSRN, ResearchGate, ORCID, patents
[Google Patents/Espacenet/Lens.org], think-tank/NGO/govt reports, dissertations, standards)*
**Tier:** Search-on-demand + persist; open-access feeds (arXiv/CORE) = store-everything.
Underrated: deep, credible, structured intel that news never surfaces.

**Discovery / retrieval features**
1. **Scholarly search** — a person/org/topic → papers, preprints, citations, affiliations →
   who researches what, funded by whom. Semantic Scholar/CORE/OpenAlex have FREE APIs.
2. **Grey-literature pull** — think-tank/NGO/govt/industry reports (the non-peer-reviewed but
   authoritative layer) → the analysis that shapes policy, rarely in news.
3. **Patent search** — filings by person/company → tech capabilities, R&D direction, hidden
   subsidiaries/inventors (Espacenet/Lens.org free) → capability & intent intelligence.
4. **Author/researcher profiling (ORCID/Scholar)** — a researcher's full output, coauthors,
   institutions → expertise + network graph.

**Network / attribution features**
5. **Coauthor & citation graph** — who collaborates/cites whom → research networks, influence,
   and (for dual-use topics) capability-transfer paths.
6. **Affiliation & funding tracing** — acknowledgements/grants → who FUNDED the work → follow-
   the-money for research and think-tank output (bias/sponsor attribution).
7. **Institution mapping** — link researchers → labs → parent orgs/states → attribute a program
   to a country/entity (dual-use/proliferation relevance).

**Creative / different**
8. **Capability/intent early-warning** — patents + preprints reveal what an org is BUILDING
   before it's announced/deployed → anticipatory intelligence (pre-event, technical edition).
9. **Expert identification** — find the real subject-matter experts on any topic/region →
   sourcing, verification, and the Expert-Search category (#28) for free.
10. **Sponsored-narrative detection** — think-tank report + its funder + the media echo → trace
    a manufactured policy narrative from paper → press (pairs disinfo mission).
11. **Front-org / talent-spotting signals** — unusual affiliation clusters around sensitive
    tech → surface possible front institutions or acquisition targets.

**Effort:** #1,#4 small (OpenAlex/Semantic Scholar/CORE free APIs) · #3 medium (patent APIs) ·
#5,#6,#7 medium (graph build) · #8,#10 medium+reasoning.
**Limit:** paywalls (Elsevier/paid journals) block full text — abstracts + open-access (arXiv/
preprints/OpenAlex) cover a lot but not all. Grey literature is scattered (no single index) —
needs per-source discovery. Slow-moving (not real-time). Niche vs mass-media reach, but far
higher credibility-per-item.

---

## 26. Geospatial Research and Mapping Tools
*(Google Earth/Maps, Sentinel Hub/EO Browser, USGS EarthExplorer, Planet, Mapillary/Street
View, OpenStreetMap, SunCalc/ShadowFinder, SkyTruth, Overpass/OSM query, Zeemaps, FIRMS fire)*
**Tier:** Search-on-demand + persist; some feeds (fire/AIS/weather) = store-everything.
Major category. Pairs with RIG's existing district-map + article_districts layer.

**Location-resolution features**
1. **Coordinate/place lookup** — name/address → coordinates + map context; reverse → what's at
   a coordinate (OSM/Overpass = free structured place data: buildings, roads, POIs).
2. **Street-level imagery (Street View/Mapillary)** — ground-truth a location; corroborate a
   geolocated photo (#23.6) against reality.
3. **Basemap + POI enrichment** — attach a target/event to real-world features (infrastructure,
   borders, facilities) → context your district layer doesn't have.

**Satellite / change-detection features (the power)**
4. **Satellite imagery (Sentinel/USGS free; Planet paid)** — view any place; FREE Sentinel-2 at
   ~10m, ~5-day revisit → monitor sites without being there.
5. **Change detection over time** — compare dated imagery → new construction, troop/vehicle
   buildup, destruction, environmental change → the satellite-OSINT crown.
6. **Live event feeds** — FIRMS (fires/thermal = explosions/burning), AIS (ships), ADS-B
   (aircraft) → real-time activity over a geography.

**Analytical features**
7. **Chrono-geolocation assist (SunCalc/ShadowFinder)** — sun position/shadows for a date+place
   → verify/derive when-where of a photo (pairs #23.6).
8. **Facility/pattern monitoring** — watch a specific site (base, port, plant, border) for
   activity changes → operational-tempo / pre-event signal.

**Creative / different**
9. **Multi-sensor site fusion** — satellite + fire/AIS/ADS-B + social geolocation + news over
   ONE location+time → the geospatial "impossible-coincidence" detector (movement/buildup an
   adversary can't hide across sensors).
10. **Movement-pattern analysis** — vessel/aircraft tracks over time → routes, rendezvous, dark-
    ship gaps (AIS-off = evasion signal) → smuggling/sanctions/military intelligence.
11. **Infrastructure-change early-warning** — new construction at a sensitive site before it's
    reported → anticipatory intelligence (physical edition).
12. **Worldwide district/region layer** — extend RIG's AP+TG district model to any country
    (seed gazetteer via OSM) → the Map goes global.

**Effort:** #1 small (OSM/Overpass free) · #4,#5 medium (Sentinel/EO Browser free; automation
harder) · #6,#10 medium (AIS/ADS-B/FIRMS feeds) · #9 hard (multi-sensor fusion). Extends the
existing Map/district infra.
**Limit:** free satellite (Sentinel ~10m) too coarse for vehicles/people — high-res is PAID
(Planet/Maxar); revisit gaps miss fast events; cloud cover blocks optical; imagery analysis
needs vision + skill (semi-manual). Geospatial is powerful but the most compute-and-skill-heavy
after video.

---

## 27. News
*(Google News, GDELT, Event Registry, NewsAPI, Media Cloud, national/regional outlets, wire
services, RSS/FreshRSS, aggregators)*
**Tier:** PILLAR — store-everything. **This IS RIG's core (875k articles, ~20.9k/24h).** This
entry = what the awesome-osint News category ADDS beyond your current pillar.

**What you already do (don't rebuild)**
- RSS/HTML ingest of 2,039 sources, substrate extraction, LaBSE, entities, stance, clustering,
  district tagging. Core is solved. Below = gaps to close for WORLDWIDE news.

**Coverage-expansion features (the additions)**
1. **GDELT global feed** — near-real-time events from world news in 100+ languages, geocoded +
   actor-tagged, FREE → instant worldwide coverage beyond your 2,039 curated sources.
2. **Event Registry / Media Cloud** — cross-source event clustering + outlet metadata → dedupe
   and map which outlets carry which story (corroboration at scale).
3. **Auto-source discovery → self-growing corpus** — new outlets surfaced by search (#1.3)
   auto-promoted → source list grows worldwide without hand-curation.
4. **Wire-service + national-outlet ingest** — extend beyond India/regional to global tier-1 +
   each country's domestic press (pairs national routing #3).

**Analytical features (leverage your engine)**
5. **Cross-source corroboration** — same event across N independent outlets → your
   independent_source_count, globally.
6. **Narrative/framing divergence** — how DIFFERENT countries' press frame one event → compare
   state vs independent vs foreign framing (disinfo/propaganda analysis at scale).
7. **Breaking-event detection** — sudden multi-source spike on a topic → real-time alerting.

**Creative / different**
8. **Framing-divergence map** — one event, every country's coverage side by side → visualize
   whose narrative differs → surface propaganda + information operations (your differentiator).
9. **Source-bias/ownership overlay** — tag each outlet by owner/state-affiliation → weight
   coverage by independence (who's really speaking).
10. **First-report attribution** — which outlet broke a story first → trace narrative origin
    from the news side (pairs #1.7).
11. **Coverage-gap / silence detection** — an event covered everywhere EXCEPT one country's
    press → detect state suppression (negative-space, news edition).

**Effort:** GDELT (#1) small + huge payoff (free global feed) · #2 medium · #6,#8 medium (reuse
clustering+stance) · #9 medium (ownership dataset). Mostly EXTENDS existing pillar.
**Limit:** GDELT is broad but noisy/shallow (event tuples, not full text); global full-text
needs the same scraping/anti-block as everything; paywalled outlets (FT/WSJ) blocked; framing
analysis needs quality translation (#21). Core already strong — this is worldwide breadth +
bias/framing depth, not a rebuild.

---

## 28. News Digest and Discovery Tools
*(Ground News, Feedly/Inoreader, Techmeme, AllSides, Memeorandum, SmartNews, Google/Bing News)*
**Tier:** Support/output layer, not a raw source. Overlaps RIG's Brief pillar. About SURFACING
+ FRAMING-AWARENESS, not collection.

**Discovery features**
1. **Trending/surfacing** — what's rising across outlets now → prioritise which events matter
   (feeds Tasking + Brief).
2. **Cross-outlet clustering (Techmeme-style)** — one story + all outlets covering it in one
   view → instant corroboration + who's carrying it.
3. **Feed aggregation (Feedly/Inoreader)** — OPML/RSS management = the plumbing under your pillar.

**Bias/framing features (the real value — Ground News model)**
4. **Bias-labeled coverage (Ground News/AllSides)** — same story tagged left/center/right +
   source-independence → SEE the framing spectrum per event.
5. **Blindspot detection** — stories one side/country covers and the other IGNORES → coverage-gap
   as a first-class feature (pairs #27.11).
6. **Coverage-ratio metrics** — attention an event gets vs its importance → over/under-covered.

**Creative / different**
7. **Automated intelligence brief** — YOU already do this (Brief pillar): ranked, per-user,
   cited → this category validates the model; extend to per-target/per-region briefs.
8. **Bias-spectrum + blindspot as a PRODUCT** — Ground News proves users PAY for "who frames this
   how + what's hidden." Your stance+clustering+source-bias engine generates it natively
   worldwide → a sellable differentiator.
9. **Narrative-emergence radar** — a story rising in fringe/foreign outlets BEFORE mainstream →
   early-warning on narratives about to break (pairs #1.7, #19.6).

**Effort:** #1,#2 small (reuse clustering) · #4,#5 medium (source-bias dataset + your stance) ·
#7 = extend Brief · #8 medium (packaging). Mostly reuses/extends existing engine.
**Limit:** not a source — a surfacing/framing layer riding your collectors. Bias labels are
subjective (AllSides/Ground News have methodology debates). Digest tools are Western/English-
centric → worldwide blindspot detection is YOUR opportunity, not theirs.

---

## 29. Fact Checking
*(Snopes, PolitiFact, FullFact, AFP Fact Check, Google Fact Check Explorer/ClaimReview,
Poynter IFCN, Hoaxy, Bellingcat, regional fact-checkers [Alt News, Boom, etc.])*
**Tier:** Search-on-demand + persist; ClaimReview feed = store-everything. Directly targets the
"credibility ABSENT" gap in the DB-reality doc — RIG has NO credibility/misinfo table today.

**Verification-lookup features**
1. **Claim → prior verdicts (Google Fact Check API)** — a claim → existing fact-check rulings
   across orgs (ClaimReview markup) → "has this been debunked?" instantly. FREE API.
2. **Cross-checker aggregation** — one claim across Snopes/PolitiFact/AFP/regional → consensus
   verdict + who rated what → weight by fact-checker independence.
3. **Regional fact-checker ingest** — India (Alt News/Boom), and each country's IFCN-signatory
   checkers → worldwide, native-language debunk coverage.

**Detection features**
4. **Claim extraction + matching** — pull checkable claims from your corpus (you have
   article_claims) → auto-match against known false-claim databases → flag recycled misinfo.
5. **Misinformation spread tracking (Hoaxy)** — how a false claim propagates across accounts/
   outlets → the diffusion network of a specific hoax.
6. **Recycled-hoax detection** — an old debunked claim resurfacing → flag immediately (pairs
   image miscaption #22.5, since much misinfo is recycled media).

**Creative / different (fills the credibility gap)**
7. **Credibility layer for RIG (the missing table)** — combine: source-tier + fact-check hits +
   cross-source corroboration + stance-dispersion → a DERIVED credibility score per claim/
   article. Not "truth", but a defensible "how-corroborated / has-it-been-debunked" signal.
8. **Claim-provenance + debunk-lag** — first appearance of a claim vs first debunk → measure how
   long misinfo ran unchecked (and where debunks DON'T reach).
9. **Coordinated-falsehood detection** — same false claim seeded across many sources in a window
   → information-operation signal (pairs CIB detection #7/#12).
10. **Debunk-gap map** — claims spreading in languages/regions with NO fact-checker coverage →
    where misinfo runs free → high-value blindspot for a worldwide product.

**Effort:** #1 small (Google Fact Check API free) · #2,#3 medium (aggregate + regional feeds) ·
#4 reuses article_claims · #7 medium (scoring model) · #5 medium (Hoaxy).
**Limit:** fact-checkers are SLOW + cover a fraction of claims (long tail unchecked); their
verdicts carry their own bias/politics (transparency needed); coverage collapses in non-English/
small regions (the debunk-gap). Fact-checking VERIFIES known claims — it does NOT establish
truth of novel ones. Build a "corroboration/debunk" signal, never a "truth" verdict.

---

## 30. Data and Statistics
*(World Bank, IMF, UN Comtrade/UNdata, Eurostat, national statistics offices, Our World in
Data, Humanitarian Data Exchange, ACLED, GDELT, data.gov portals, Google Dataset Search)*
**Tier:** Mostly store-everything (bounded official datasets) + on-demand query. Structured-
facts layer — hard numbers to GROUND and corroborate narrative intel.

**Reference-data features**
1. **Official indicators lookup** — economy/trade/demographics/health for a country/region via
   free APIs (World Bank/IMF/Eurostat) → factual baseline for any place-based analysis.
2. **Trade-flow data (UN Comtrade)** — who exports/imports what, to whom → supply chains,
   sanctions-evasion, dependency (you already use SIPRI/Comtrade in the Windlass product).
3. **Conflict/event data (ACLED)** — geocoded political-violence events → ground-truth for
   conflict/security analysis; joins your Map/district layer.

**Grounding / corroboration features**
4. **Claim-vs-data check** — a claim ("exports collapsed", "unemployment up") → check against
   the actual official series → corroborate or debunk with hard numbers (pairs #29).
5. **Anomaly/trend detection** — official series over time → flag statistical outliers/breaks
   → the "something changed here" quantitative signal.
6. **Baseline for negative-space** — what SHOULD be there statistically vs what's reported/
   missing → detect suppressed or manipulated official numbers.

**Creative / different**
7. **Narrative-vs-reality gap** — compare media/state NARRATIVE sentiment against the actual
   economic/conflict DATA → surface propaganda ("everything's fine" while indicators crater).
   A genuine, quantifiable disinfo signal.
8. **Trade-graph for entity fusion** — Comtrade + company data → who trades with whom → economic
   network layer on the entity graph (sanctions/front-company relevance).
9. **Official-statistics manipulation flag** — implausible smoothness/breaks in a state's own
   numbers → possible data manipulation (compare to satellite/independent proxies #26).
10. **Structured-fact grounding for the agent** — hard numbers the autonomous agent cites to
    anchor claims → reduces hallucination, raises confidence/traceability.

**Effort:** #1,#2 small (World Bank/Comtrade free APIs) · #3 medium (ACLED) · #4,#7 medium
(join narrative + data) · #9 hard. Partly reuses Windlass (SIPRI/Comtrade) work.
**Limit:** official data LAGS (months/years) — not for real-time; authoritarian states' own
numbers are suspect (that's a feature to detect, not trust); granularity often national, not
local; joining messy data → entities is real work. Grounds narrative intel; isn't a live source.

---

## 31. Web Monitoring
*(Visualping/Distill/ChangeDetection.io, Google Alerts, RSS watchers, Talkwalker/Mention/Brand24,
Hoaxy, page-diff tools, keyword-alert services)*
**Tier:** Operational LAYER over all collectors, not a source. THE backbone of the live/ambient
vision — turns one-time collection into standing watches + alerts.

**Change-watch features**
1. **Page/site change detection** — watch any URL → alert on ANY change (text/structure) →
   catch edits, deletions, new postings the moment they happen (self-host ChangeDetection.io).
2. **Keyword/entity standing watch** — monitor a term across search/social/news → alert on new
   mentions worldwide → the "set a watch, get tapped on the shoulder" feature (#1.11 generalized).
3. **New-content triggers** — new article/post/filing/paste about a target → real-time push into
   the pipeline (event-driven, not just scheduled polling).

**Alerting / triage features**
4. **Threshold/spike alerts** — sudden volume/sentiment/velocity change on a topic → early
   breaking-event + coordinated-activity detection.
5. **Multi-source alert fusion** — dedupe alerts across collectors → one notification per real
   event, not N per source (signal, not noise).
6. **Priority routing** — rank alerts by target importance + confidence → surface the vital 1%
   (the human-in-the-loop "most relevant, traceable" principle).

**Creative / different (this IS the ambient agent)**
7. **Standing intelligence watch** — the whole product's live half: every entity in the graph
   gets a persistent watch across all sensors → anomaly = alert. Ambient, anticipatory (#the
   vision's "warn me about the future" mode).
8. **Change-as-signal** — a target editing/deleting a page, changing infra (#18.13), scrubbing a
   profile → the ACT of change is the intel, captured before/after (negative-space, live).
9. **Cross-sensor event assembly** — a satellite change + a news spike + a social burst on the
   same target+time auto-assembled into ONE alert → live "impossible-coincidence" detector.
10. **Tripwire entities** — plant watches on low-profile shell companies/domains/handles → get
    alerted the moment they activate (dormant→active = high-value early signal).

**Effort:** #1 small (self-host ChangeDetection.io) · #2,#3 medium (wire watches over collectors)
· #4,#5,#6 medium (alert engine) · #7,#9 = the hard, high-value orchestration (the ambient agent).
**Limit:** monitoring at scale = the anti-block/rate-limit problem multiplied (many standing
polls) — needs the cheap-stack egress discipline; alert FATIGUE is the real failure mode (tune
thresholds + fusion or users drown); event-driven beats polling but few sources push. This
category is where "aggregator" becomes "living intelligence" — the operational core of the vision.

---

# ── PEOPLE / IDENTITY BLOCK (32–40) ──
Investigating a PERSON, not a topic. ⚠️ Sharpest privacy/legal edge on the list — gate hard to
PUBLIC FIGURES / legitimate investigative purpose; default-deny targeting private individuals
(the persona guardrail + GDPR/DPDP). These are lookups on identifiers people made public.

## 32. Username Check
*(Sherlock, Maigret, WhatsMyName, Social-Analyzer, Snoop, user-searcher, Namechk, 600+-site
scanners like Trace)*
**Tier:** Search-on-demand + persist. The classic selector-pivot: one handle → presence
everywhere. Fully automatable, mostly free (open-source scanners).

**Enumeration features**
1. **Handle → presence map** — one username → every platform where it exists (Sherlock/Maigret
   cover 600–3000 sites) → a target's full cross-platform footprint from one selector.
2. **Existence + profile-URL harvest** — direct links to each found account → feed straight into
   the social collectors (#17) for content.
3. **Variant generation** — permute a handle (dots/underscores/numbers/l33t) → catch alt/backup
   accounts the exact string misses.

**Identity-resolution features (the real value)**
4. **Cross-platform identity linking** — same handle across sites = strong same-person signal →
   merge into ONE entity node (the core of global entity resolution).
5. **Selector bridging** — join with email/phone/image reuse → collapse many identities into one
   real person (pairs #33/#36/#37; the case-file spine).
6. **Alias discovery** — a known handle → linked/reused handles elsewhere → uncover pseudonyms
   and sockpuppets.

**Creative / different**
7. **Sockpuppet-network detection** — handle-reuse patterns across coordinated accounts →
   information-operation attribution (pairs CIB #7/#12).
8. **Reuse-confidence scoring** — rare/distinctive handle = high same-person confidence; common
   handle = low → attach a confidence score, never assume (honest resolution).
9. **Handle-provenance timeline** — earliest appearance of a handle across platforms → when an
   online identity was born (pairs #1.6 emergence).

**Effort:** #1,#2 small (Sherlock/Maigret are free CLI) · #3 small · #4,#5 medium (graph merge +
scoring) · #7 medium.
**Limit:** ⚠️ same handle ≠ same person (common names collide — hence confidence scoring #8);
scanners produce false positives (dead/parked profiles) — verify before asserting; many sites
now block automated existence checks. Powerful for PUBLIC personas / investigations; must NOT be
used to target/stalk private individuals — hard gate.

---

## 33. People Investigations
*(Pipl, Spokeo, PeekYou, BeenVerified, TruePeopleSearch, Socialcatfish, 411/192, Intelius,
FastPeopleSearch, national people-directories)*
**Tier:** Mostly analyst-launchpad (paywalled/manual), NOT bulk-ingest. ⚠️ BRIGHTEST privacy
line on the list — dedicated people-aggregators sell compiled personal profiles.

**What the category does**
1. **Name → compiled profile** — aggregators merge public records + data-broker data into one
   dossier: addresses, relatives, phones, emails, age, associates.
2. **Reverse lookups** — phone/email/address → the person behind it.
3. **Cross-source people-graph** — relatives/associates/co-residents → a person's real-world
   network.

**How RIG should treat it (the honest position)**
4. **Analyst-launchpad, not ingestion** — these are paywalled, ToS-locked, US-centric brokers.
   RIG does NOT bulk-ingest them. At most: a gated panel that pre-fills a lookup for an analyst
   on a PUBLIC-FIGURE investigation, result folded back manually.
5. **Public-record path instead** — the legitimate, ingestible version is OFFICIAL public
   records (court/corporate/electoral — see Company #38, Documents #11), not broker aggregation.

**Creative / different (legitimate framing)**
6. **Reframe to the real goal** — "understand a person" is usually served by PUBLIC surfaces:
   their public statements (social #17), official filings (records), professional footprint
   (#38), network (#39 SNA) → build the picture from public acts, not broker PII.
7. **Data-broker exposure check (defensive)** — show a CLIENT what's exposed about THEM/their
   org on people-search sites → legitimate defensive/privacy service (opt-in, about self).

**Effort:** deliberately LOW — this is a policy boundary, not a build target.
**Limit / POLICY:** ⚠️ **default-deny.** Data-broker aggregation of private individuals =
GDPR/DPDP/FCRA landmine; many brokers are legally contested. RIG's line: collect PUBLIC acts of
PUBLIC figures + OFFICIAL public records — NOT compiled broker dossiers on private people. This
category is mostly a boundary marker: know it exists, route around it to official records.

---

## 34. Email Search / Email Check
*(Hunter.io, EmailRep, Have I Been Pwned, Holehe, Epieos, mailfloss/verifiers, Gravatar,
GHunt for Google accounts)*
**Tier:** Search-on-demand + persist. A cleaner, more defensible selector than people-search —
email is a strong unique identifier that pivots widely.

**Verification / discovery features**
1. **Deliverability/validity check** — is an address real/active (SMTP/MX verification) → filter
   fake vs genuine contacts.
2. **Account discovery (Holehe/Epieos)** — email → which platforms have an account registered to
   it (via forgot-password/existence oracles) → a target's service footprint from one email.
3. **Breach-existence (HIBP)** — email appears in which known breaches + when → metadata only
   (policy gate #6: existence, never dumped contents).

**Attribution / enrichment features**
4. **Email → identity (EmailRep/Gravatar/GHunt)** — reputation, linked profiles, Gravatar photo,
   Google-account public data (name, photo, reviews, maps contributions) → put a face/name to an
   address.
5. **Pattern inference (Hunter)** — an org's email format (first.last@) → derive/verify staff
   addresses → org-structure mapping (corporate intel).
6. **Selector bridging** — email links to usernames/phones/breach records → collapse identities
   into one person (the case-file spine, pairs #32/#37).

**Creative / different**
7. **Sockpuppet/persona unmasking** — a "burner" email reused as recovery on a "real" account →
   bridge an anonymous persona to a real identity via the shared selector (the classic move).
8. **Org attack/asset surface** — Hunter-derived staff emails → map an organization's people from
   its domain (pairs domain #18, company #38).
9. **Registration-timeline signal** — account-existence across services + breach dates → when an
   identity became active (pairs emergence #1.6).

**Effort:** #1,#2 small (Holehe/Epieos free CLI) · #3 small (HIBP licensed API) · #4 medium
(GHunt/EmailRep) · #5 small (Hunter freemium) · #6 medium (graph).
**Limit:** ⚠️ existence-oracles are increasingly rate-limited/blocked (platforms hardened forgot-
password leaks); Hunter/EmailRep freemium-capped; verifying an email ≠ identifying its owner
(confidence, not proof). Gate to legitimate investigation; email of a private individual is still
personal data under GDPR/DPDP — public-figure / org-context focus.

---

## 35. Phone Number Research
*(Truecaller, NumLookup, Numverify, libphonenumber, PhoneInfoga, Sync.me, WhatsApp/Telegram
presence checks, HLR lookups)*
**Tier:** Search-on-demand + persist. A strong selector — but the most privacy-sensitive of the
identifiers and increasingly walled. ⚠️ tight gating.

**Validation / metadata features**
1. **Format/validation (libphonenumber/Numverify)** — is it valid, what country, carrier, line
   type (mobile/VoIP/landline) → basic vetting, no personal data. Cleanest tier.
2. **Carrier / geography** — origin country + carrier → coarse location + provider context.
3. **Reputation/spam flags** — is it flagged spam/scam/robocall → useful for fraud/scam-network
   analysis (defensible, aggregate).

**Discovery / linking features**
4. **Account presence (PhoneInfoga)** — number tied to WhatsApp/Telegram/other accounts (via
   presence checks) → a target's messaging footprint from a number.
5. **Reverse lookup (Truecaller/Sync.me)** — number → crowd-sourced name → identity lead
   (⚠️ this is the privacy-hot part — crowdsourced from contact-book uploads).
6. **Selector bridging** — phone links to email/username/accounts → collapse into one identity
   (case-file spine, pairs #32/#34).

**Creative / different**
7. **Scam/fraud-network mapping** — cluster numbers by spam-report patterns + carrier + reuse →
   map a fraud or robocall operation (aggregate, defensible, high-value).
8. **Messaging-footprint linkage** — WhatsApp/Telegram presence + profile photo (reverse-image
   #22) → bridge a number to a visual identity.
9. **Bulk-registration detection** — many numbers from one carrier/block tied to coordinated
   accounts → sockpuppet/bot-farm signal (pairs CIB).

**Effort:** #1,#2 small (libphonenumber free, Numverify freemium) · #3 medium · #4 medium
(PhoneInfoga free but flaky) · #5 = paid/ToS-heavy (Truecaller).
**Limit:** ⚠️ reverse-name lookup (Truecaller/Sync.me) is built on scraped contact-books —
legally/ethically fraught, ToS-locked, and personal data → treat as analyst-launchpad on public
figures only, NOT bulk. Presence-check APIs (WhatsApp) actively hardened/blocked. A number is
personal data everywhere. Cleanest use is #1/#3/#7 (validation + fraud), not identity lookup.

---

## 36. Vehicle / Automobile Research
*(VIN decoders, license-plate lookups, national vehicle registries [DVLA/Vahan], fleet/ADS-B
+ AIS for aircraft/vessels, dashcam/traffic-cam OSINT, auction/history sites)*
**Tier:** Search-on-demand + persist. Niche selector, jurisdiction-bound, but a few sharp angles
— especially where it bridges into geospatial movement (#26).

**Lookup features**
1. **VIN decode** — VIN → make/model/year/specs/manufacture plant → identify a vehicle from a
   number (mostly free, non-personal).
2. **Plate → vehicle (registry-dependent)** — some jurisdictions expose basic vehicle data by
   plate (UK DVLA, India Vahan); many don't → what's legally public varies wildly by country.
3. **History/auction records** — VIN → ownership-count/accident/mileage/auction history → a
   vehicle's past (non-personal facts).

**Intelligence / movement features (the real value)**
4. **Plate/vehicle in imagery** — read plates + identify make/model in photos/video/CCTV (OCR +
   vision #23) → place a specific vehicle at a place+time → corroborate presence/movement.
5. **Fleet & aircraft/vessel tracking (ADS-B/AIS)** — aircraft (tail number) + ships (IMO/MMSI)
   → real-time + historical movement → the HIGH-value part (jets/yachts/cargo of targets).
6. **Convoy/pattern analysis** — repeated vehicle appearances across geolocated media → routes,
   escorts, operational patterns.

**Creative / different**
7. **Elite-asset tracking** — a target's private jet (tail #) / yacht (MMSI) → movements, timing,
   who they meet where → oligarch/official accountability (the "which jet, whose, going where"
   staple; feeds #26 movement).
8. **Sanctions/dark-fleet detection** — vessels going AIS-dark near sanctioned ports → evasion
   signal (pairs #26.10).
9. **Vehicle-as-entity-node** — tie a specific vehicle/vessel/aircraft to an owner-entity →
   movement becomes an attribute of the entity graph.

**Effort:** #1 small (VIN decoders free) · #5,#7,#8 small-medium (ADS-B/AIS free feeds — reuse
#26) · #4 medium (plate OCR + vision) · #2 varies (registry-dependent).
**Limit:** ⚠️ plate/registry lookup exposes an individual → heavily restricted/illegal in many
countries (personal data); gate hard, jurisdiction-aware. Plate-OCR at scale = surveillance risk
— public-figure/vehicle-of-interest only. Aircraft/vessel tracking is the clean, high-value,
public part (tail#/MMSI are public); car-plate lookup is the gated part. Lean into the former.

---

## 37. Expert Search
*(ORCID/Google Scholar, ExpertFile, ProfNet/HARO, conference speaker lists, industry
associations, LinkedIn, think-tank rosters, Muck Rack for journalists)*
**Tier:** Search-on-demand + persist. Largely overlaps Academic (#25.9); the distinct value is
FINDING the right knowledgeable people for sourcing, verification, and network mapping.

**Discovery features**
1. **Topic/region → experts** — a subject → the recognized specialists (via publications #25,
   speaker rosters, associations) → who actually KNOWS this, ranked by credibility.
2. **Journalist/analyst finder (Muck Rack)** — who covers a beat/region → local reporters + their
   work → sourcing + on-the-ground knowledge for any geography.
3. **Institutional-expert mapping** — link experts → their orgs/think-tanks/funders → whose
   expertise serves whose agenda (bias/sponsor context, pairs #25.6).

**Verification / sourcing features**
4. **Claim verification routing** — a technical claim → the experts who could confirm/refute →
   direct human-in-loop verification (the agent surfaces WHO to ask).
5. **Credibility weighting** — rank a source's expertise by track record/citations/affiliation →
   don't treat all "experts" equally (honest sourcing).

**Creative / different**
6. **Manufactured-expert detection** — a "expert" pushing a narrative with NO real track record/
   thin credentials → astroturf/front-expert flag (pairs disinfo mission).
7. **Expertise-network graph** — who's cited/quoted alongside whom on a topic → the real
   knowledge network + its gatekeepers/echo chambers.
8. **Local-fixer discovery** — for worldwide reach, find in-region experts/journalists who can
   contextualize content the agent can't fully parse → human layer for hard regions.

**Effort:** #1,#2 small (reuse #25 + Muck Rack) · #3,#7 medium (graph) · #6 medium (track-record
check). Mostly reuses Academic + LinkedIn/Company data.
**Limit:** not an intel source — a SOURCING/verification aid; "expert" is subjective and gameable
(credential-washing); best contacts are often paywalled (LinkedIn/Muck Rack); human-in-loop by
nature (it points to people, doesn't collect). Value = better verification + native-region
context, not standalone collection.

---

## 38. Company Research
*(OpenCorporates, national registries [MCA/Companies House/SEC EDGAR], OpenOwnership, OpenSanctions,
Aleph/OCCRP, ICIJ, GLEIF/LEI, Crunchbase, court records, procurement/tender DBs, patents #25)*
**Tier:** Search-on-demand + persist; open registries + sanctions/LEI = STORE-EVERYTHING.
⭐ HIGHEST-VALUE identity category — clean, legal, structured, lands directly on the entity graph.
The corporate-intel spine (relevant to your Windlass/Tridel corporate-OSINT product).

**Registry / ownership features**
1. **Company → official record** — registration, status, incorporation date, address, directors,
   filings (OpenCorporates + national registries) → the authoritative entity, not a scrape.
2. **Beneficial-ownership (OpenOwnership/registries)** — who REALLY owns it behind the corporate
   veil → the person controlling the entity.
3. **Officers/directors graph** — director → all their other companies → a person's corporate
   network (co-directorships = the classic shell-company pivot).
4. **LEI/GLEIF** — global legal-entity IDs → resolve the SAME company across countries/datasets
   (cross-border entity resolution for firms).

**Risk / attribution features**
5. **Sanctions/PEP screening (OpenSanctions)** — is the entity/owner sanctioned or a politically-
   exposed person → risk + political-exposure flag (FREE, bulk).
6. **Investigative-graph (Aleph/OCCRP, ICIJ)** — cross-reference against leak datasets + curated
   investigations → hidden connections journalists already mapped.
7. **Financials/filings (SEC EDGAR etc.)** — public filings → ownership, subsidiaries, risk
   disclosures, related-party transactions.

**Creative / different (the payoff for RIG)**
8. **Shell-company / hidden-network unmasking** — shared directors + addresses + owners + filing
   agents → prove a web of "separate" companies is ONE beneficial owner (the corporate twin of
   the disinfo-infra graph #7/#18; lands on the entity graph).
9. **Politician↔business fusion** — link a political figure to companies (direct/family/proxy) →
   conflict-of-interest + corruption intelligence (core for your political-OSINT mission).
10. **Procurement/tender graph** — who wins govt contracts + their corporate/political ties →
    follow-the-money on state spending (huge for regional political OSINT).
11. **Sanctions-evasion network** — sanctioned entity → newly-formed linked companies (front
    detection) → pairs trade data #30 + vessel tracking #36.

**Effort:** #1,#5 small (OpenCorporates/OpenSanctions free-ish APIs) · #2,#3,#8 medium (ownership
graph build) · #6 medium (Aleph API) · #10 medium (per-country tender DBs). Reuses Windlass work.
**Limit:** registry coverage/quality varies wildly by country (some open+free, some paywalled/
offline/corrupt); beneficial-ownership often opaque or newly re-hidden post-transparency-rollbacks;
OpenCorporates rate-limits bulk. But the FREE core (OpenCorporates + OpenSanctions + OpenOwnership +
ICIJ) already delivers the shell-network + politician-business fusion crown features. TOP build
priority alongside domain/infra (#18) and social.

---

## 39. Job Search Resources
*(LinkedIn Jobs, Indeed, Glassdoor, national job boards, company careers pages, contractor/gov
job portals)*
**Tier:** Search-on-demand + persist. Minor/support — but job postings leak surprisingly
useful ORGANIZATIONAL intelligence (the "what a company is really doing" tell).

**Org-intelligence features (the real use)**
1. **Hiring-signal analysis** — what roles a company is posting → what they're BUILDING/expanding
   (a surge in ML/hardware/regional hires reveals strategy before any announcement).
2. **Tech-stack leakage** — job reqs list exact tools/systems/clearances → a company's internal
   stack + capabilities (pairs infra #18, capability #25.8).
3. **Location/expansion signal** — new postings in a new city/country → physical expansion before
   it's public.

**Culture / people features**
4. **Glassdoor sentiment** — employee reviews → internal morale, leadership, turnover, sometimes
   candid operational detail → org-health intelligence.
5. **Org-structure inference** — role titles + reporting lines in postings → map internal
   hierarchy/departments (pairs company #38, email-pattern #34.5).

**Creative / different**
6. **Capability/intent early-warning (HR edition)** — clearances, niche skills, or dual-use roles
   posted → what an org is quietly gearing up to DO (anticipatory; pairs #25.8, #38).
7. **Front-org / cover-employer tells** — a "company" with implausible hiring (no real product,
   sudden sensitive-skill demand) → possible front (pairs shell-company #38.8).
8. **Insider-risk / departure signal** — mass backfilling of a team → an exodus underway → org
   instability signal.

**Effort:** #1,#2 small (careers-page/board scrape) · #4 medium (Glassdoor gated) · #6,#7 medium
(pattern). Cheap add-on to company research.
**Limit:** minor standalone value; LinkedIn/Glassdoor login-walled (paid last-mile); postings are
noisy + often generic/aspirational (not always real intent); heavily Western/corporate-skewed.
Best as an ENRICHMENT signal on company research (#38), not a primary source.

---

## 40. Q&A Sites
*(Quora, Stack Exchange/Overflow, Reddit-AskX, Yahoo Answers archives, national Q&A [Zhihu=CN,
Baidu Zhidao], niche help forums)*
**Tier:** Search-on-demand + persist; some (Stack Exchange) = store-everything (open data dumps).
Minor but a candid, self-disclosure-rich content source. Closes the people/identity block.

**Content features**
1. **Topic/expertise mining** — questions+answers on a subject → who knows what, common concerns,
   niche knowledge not in news/articles.
2. **Self-disclosure harvest** — people reveal a LOT answering questions (location, job, habits,
   opinions) → candid personal/professional detail (⚠️ gate to public figures).
3. **Zhihu (CN) / regional Q&A** — the candid Chinese/regional discussion layer → what people
   actually think/ask domestically (pairs WeChat/national #3; hard for Western tools).

**Intelligence features**
4. **Expertise/opinion signal** — reasoned answers reveal genuine expertise + sentiment on a
   topic → sourcing (#37) + authentic public opinion (vs performative social).
5. **Entity/association mentions** — Q&A text → entity extraction → feeds the graph like any text.

**Creative / different**
6. **Candid-sentiment layer** — Q&A is lower-performance than social (people ask to KNOW, not to
   posture) → often more honest opinion signal → better read on real public concern.
7. **Zhihu narrative-monitoring** — track Chinese public discourse/framing on a topic on Zhihu →
   domestic-opinion intelligence Western OSINT misses (high differentiator, pairs WeChat).
8. **Emerging-concern radar** — spikes in questions about a topic/entity → rising public interest/
   worry before it hits news (pairs #19.4 demand-side).

**Effort:** #1,#4,#5 small (Stack Exchange free API + data dumps; Quora scrape) · #3,#7 medium
(Zhihu anti-crawl, needs cheap-stack + national handling) · #6,#8 medium.
**Limit:** minor reach; Quora login-walls content; Zhihu is anti-crawl + China-IP-sensitive (like
WeChat — use search-engine site-dork route); answer quality varies wildly (anecdote ≠ fact). Value
is candid opinion + regional (esp. Zhihu) discourse, not authoritative fact.

---

## 41. Social Network Analysis
*(Gephi, Maltego, NetworkX/igraph, Hoaxy, graph DBs [Neo4j], community-detection, centrality
tooling)*
**Tier:** ANALYSIS layer over collected data, not a source. ⭐ Ties directly to RIG's entity-graph
spine — this is the discipline that turns collected nodes into INTELLIGENCE. You already run
igraph/Louvain for story clustering; SNA generalizes it to actors.

**Structure features**
1. **Network construction** — turn collected relations (follows/mentions/co-directors/co-mentions/
   shared-infra) into one graph → the target's real network across sources.
2. **Community detection** — cluster the graph (Louvain/igraph — you already do this) → factions,
   camps, movements, echo chambers a target belongs to.
3. **Centrality/influence ranking** — who's central/bridging/gatekeeping → the REAL influencers
   (not follower-count vanity; structural power).

**Actor-role features (the payoff)**
4. **Role identification** — hubs (leaders), bridges (connectors between groups), amplifiers,
   peripherals → WHO DOES WHAT in a network → prioritize targets by structural role.
5. **Broker/gatekeeper detection** — nodes connecting otherwise-separate clusters → the people who
   move info/money/influence between worlds (highest-value nodes).
6. **Coordination detection** — unnaturally dense/synchronized subgraphs → bot-nets, sockpuppet
   rings, CIB (the graph proof of #7/#17.5/#32.7).

**Creative / different (the vision's spine)**
7. **Cross-modal one-graph fusion** — merge social + corporate (#38) + infra (#18) + comms into
   ONE actor graph → a person's followers + shell companies + servers + contacts in a single map
   → THE entity-fusion vision made literal.
8. **Influence-flow / diffusion** — trace how a narrative/money/instruction propagates through the
   network over time → origin → amplifiers → reach (pairs #1.7, #29.5).
9. **Hidden-tie inference** — predict unstated relationships from structure (link prediction):
   "these two aren't publicly connected but the graph says they should be" → investigative leads.
10. **Network-change / anomaly watch** — a new central node, a merging of two clusters, a sudden
    tie → structural early-warning (pairs monitoring #31).

**Effort:** #1,#2,#3 = REUSE your igraph/Louvain stack on actor data · #4,#5 medium (role metrics)
· #6 medium (coordination scoring) · #7 hard (cross-modal schema — the big one) · #9 hard (link
prediction). Heavily leverages existing clustering infra.
**Limit:** garbage-in (bad entity resolution → wrong graph — resolution #32/#34 must be solid
first); mega-graphs get computationally heavy + hairball-unreadable (need filtering/thresholds,
like your SIZE_NET guard); correlation ≠ causation (structural proximity isn't proof of ties).
This is the ANALYTICAL core that makes every collected source pay off — top-tier priority.

---

## 42. Maritime
*(MarineTraffic, VesselFinder, AIS Hub, Equasis, IMO/GISIS, Global Fishing Watch, ITU MMSI,
port-authority data, Lloyd's List)*
**Tier:** Search-on-demand + persist; AIS live feed = store-everything. Standalone slice of
geospatial (#26) + vehicle (#36) — but distinct enough (sanctions/trade/security) to stand alone.
Fully public identifiers (IMO/MMSI), high-value, mostly free-core.

**Vessel-identity features**
1. **Ship lookup (IMO/MMSI/name)** — vessel → type, flag, tonnage, build, current+historical
   position, port calls (MarineTraffic/VesselFinder) → the vessel entity + its movements.
2. **Ownership/management (Equasis/IMO GISIS)** — registered owner, operator, manager, flag
   history → who CONTROLS the ship behind flags-of-convenience (the maritime shell-game).
3. **Flag/class/inspection history** — flag changes, detentions, class society → risk +
   evasion-behavior profile.

**Movement / behavior features (the crown)**
4. **Live + historical tracking (AIS)** — real-time position + full track history → where a
   vessel is and has been → the core capability (free-core via AIS).
5. **Port-call analysis** — sequence of ports visited → trade routes, cargo inference, sanctioned-
   port visits.
6. **AIS-gap / dark-ship detection** — vessel goes AIS-dark (transponder off) → evasion signal;
   correlate with satellite (#26) to catch what it hid (sanctions/smuggling staple).

**Creative / different**
7. **Sanctions-evasion detection** — dark-fleet vessels + STS (ship-to-ship) transfers + flag-
   hopping + shell-owner (#38) → prove oil/arms sanctions evasion (a top real-world OSINT use).
8. **Trade-flow ground-truth** — actual vessel movements vs declared trade data (#30) → detect
   under-reported / hidden trade (pairs Comtrade).
9. **Vessel↔owner↔entity fusion** — link ship → owner company → beneficial owner → the entity
   graph → a person's/state's maritime assets as graph nodes.
10. **Illicit-fishing / incursion detection (Global Fishing Watch)** — fishing in protected/
    disputed waters → environmental + geopolitical (South China Sea-type) intelligence.

**Effort:** #1,#4 small-medium (MarineTraffic/AIS — free tier + paid depth) · #2 medium (Equasis
free registration) · #6,#7 medium (gap detection + satellite correlate) · #9 medium (fuse #38).
**Limit:** live/global AIS depth + history is largely PAID (MarineTraffic/Spire premium; free tier
limited/delayed); AIS is self-reported → spoofable + can be switched off (the dark-ship problem —
also the signal); coastal AIS coverage patchy mid-ocean (satellite AIS = paid). Free-core (basic
AIS + Equasis + IMO) covers identity + recent movement; deep history/dark-fleet = paid. High-value
for sanctions/trade/security missions specifically.

---

## 43. Threat Intelligence (distinct from Threat Actor #12)
*(Recorded Future, AlienVault OTX, MISP, abuse.ch/ThreatFox, VirusTotal, GreyNoise, CISA KEV,
CVE/NVD feeds)*
**Tier:** Feeds = store-everything; lookups = on-demand. Cyber-security category — mostly
OFF-MISSION for political OSINT; a thin transferable sliver + a defensive product angle.
**Transferable / usable sliver**
1. **IOC feeds (OTX/ThreatFox, free)** — malicious domains/IPs/hashes → overlaps infra (#18) for
   disinfo/attack-infra attribution; useful only where a target has cyber infrastructure.
2. **VirusTotal (free-tier) domain/file rep** — a domain/file's malicious history → attribution
   + risk context on a target's assets.
3. **Defensive product angle** — monitor a CLIENT's own domains/brand for threats → legitimate
   sellable defensive service (like breach #6.3).
**Verdict:** adopt the *method/ontology* (as #12) + the free IOC/VT lookups where a target has
cyber infra; do NOT build a full CTI stack for a political-OSINT product. Mostly skip unless a
client mission is threat-intel/fraud.

---

# ── SKIP-TIER (utility / learning, NOT ingestible sources) ──
These awesome-osint categories are TOOLS you use or RESOURCES you read — not data sources to
collect. One combined note; no per-category build.

- **Browsers / Offline Browsing** — investigation browsers (Tor Browser, containers, HTTrack for
  offline copies). *Use:* an isolated, fingerprint-managed browser profile for the analyst console
  + stealth-browser layer (#technique 6). Operational hygiene, not a source.
- **VPN Services / Privacy & Encryption Tools** — the analyst's OPSEC layer (VPN, PGP, secure
  comms) + part of the egress/anti-block infra. *Use:* investigation OPSEC + residential/rotating
  egress. Supports collection; isn't collection.
- **Infographics & Data Visualization** — Gephi/Flourish/Tableau/Kepler. *Use:* the OUTPUT/present
  layer for the entity graph, SNA (#41), maps (#26). You already have night-desk viz; adopt for
  graph/network rendering. Presentation, not intake.
- **Gaming Platforms (Steam/Xbox/PSN) / Music Streaming (Spotify/Last.fm)** — public-profile
  lookups only; niche lifestyle/association signal on a specific target. Very low priority; gate
  to public figures. Not a mission source.
- **OSINT Videos / OSINT Blogs / Other Resources / Related Awesome Lists** — LEARNING material
  (Bellingcat guides, tradecraft blogs, other curated lists). *Use:* method reference + source
  discovery for expanding the map later. Not ingestible.

**Skip-tier verdict:** Browsers/VPN/Privacy = OPSEC + egress infra (real, but plumbing). Infographics
= the viz/output layer (reuse night-desk). Gaming/Music = niche public-profile only. Videos/Blogs/
Lists = learning + future-source discovery. None are primary collection targets.
