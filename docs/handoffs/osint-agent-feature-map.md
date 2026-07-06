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
