# Daily Media Briefing — rebuild specification

Client: **Information & Public Relations, Government of Telangana** (via VeriDeck).
Replaces the current "Daily State Intelligence Brief" (`report_builder.py`).
Living document — one section agreed at a time, nothing built until all sections
are agreed, because later sections may demand data earlier ones did not.

Status key: **AGREED** · **OPEN** · **BLOCKED**

---

## 1. Product-level decisions — AGREED

| Decision | Value |
|---|---|
| Name | **Daily Media Briefing** |
| Masthead | Telangana · Information & Public Relations |
| Brand | **Robin Osint** lockup in header; "A product of RIG 360 Media & News Pvt. Ltd." in footer |
| Banned words | intelligence, surveillance, monitoring, OSINT (body copy), classification |
| Banned word | **"yesterday"** — never appears anywhere |
| Window | **One calendar day, 00:00–23:59 IST.** Not rolling 24h |
| Media | Websites + newspapers + TV, **pooled in every section** except §6 which compares them |
| Languages | English and Telugu |
| Look | White, print-first, professional. Serif body, sans labels, tabular figures |
| Delivery | On-screen editable + PDF export |
| Reader | DIPR Commissioner and press officers |
| Section naming | Plain speech only. A reader must know the contents from the name alone |
| Tone of copy | **Descriptive, never prescriptive.** State what is; never instruct |
| Citations | Every claim carries a bracketed reference to §10 |

### Renderer — OPEN

WeasyPrint cannot support click-to-remove or inline editing, and is weak on Telugu
shaping. Recommendation: **headless Chromium (Playwright)** server-side, rendering the
same HTML the user edited on screen. ~300 MB in the container, ~1.5 s per render.

---

## 2. Section list — AGREED

Key Numbers strip sits above §1, unnumbered, with no heading and no standfirst.
Removable from the export rail (shown as `·`).

| # | Section |
|---|---|
| — | Key Numbers (strip) |
| 1 | Daily Brief |
| 2 | The Big Stories |
| 3 | Coverage by Topic |
| 4 | How Each Scheme Was Covered |
| 5 | Coverage by District |
| 6 | Newspapers, TV and Websites Compared |
| 7 | Figures Quoted in the Press |
| 8 | Which Outlet Said What |
| 9 | All Stories, with Links |

**Removed 2026-07-24:** "What Each Side Said" (contested-quote pairs) — cut at client
request. Sections renumbered 7→Figures, 8→Outlets, 9→Annexure. NOTE: the machine-
translation risk it raised (`quote_text_en` is 100% empty corpus-wide; English is
build-time MT via `i18n.attach_en`) still applies anywhere else quotes are shown
translated (e.g. §2 The Big Story quote element).

**Removed from the old report:** Risk Heatmap, Early-Warning Signals, Stakeholder
Impact, Recommended Actions, Top Stories (absorbed into §1/§2/§6).

---

## 2a. Section 1 — Daily Brief — AGREED (design), prototype done

**Format:** 6 points, each a **5–6 line detailed paragraph** (not a headline). Each
point states: what happened concretely (who/what/where) · the one-clause government
angle · how far it spread (per medium) · who is absent from the coverage · citations
into §10 · tags (department · topic · tone · outlet count · languages).

Descriptive only, never prescriptive. No "coverage-speak" (no "metrics", "adverse
share", "sentiment trend"). Written from article/clip/clipping TEXT, never from
statistics — this is the fix for the old brief, whose `_facts_blob()` fed the LLM
numbers and got unattributable prose ("law and order metrics have surged…").

**Pipeline (extends the sentiment pipeline):**
```
WIDE NET (SQL)  ->  ABOUTNESS GATE (prompt)  ->  EVENT-MERGE (own)  ->  RANK  ->  PICK 6  ->  WRITE each from its own items  ->  VERIFY every fact cites an item
```

**Scope decision: government-relevant only.** National stories are excluded by the
aboutness gate, not carried in a spare slot. Justified by the noise finding below.

### Prototype findings — 22 July 2026 (00:00–23:59 IST), verified live

**The outlet filter is ~87% noise.** Outlet-based selection returned 1,611 items;
only ~210 were datelined to Telangana. Top items by raw breadth were Delhi Metro
closures, David Warner's drink-driving case, a Vedanta–Gujarat oil ruling, West
Bengal rain — all from Telangana-covering national outlets, none about Telangana.
Ranking by breadth alone would lead the brief on Delhi Metro.

**Content filter disagrees with outlet filter in BOTH directions.** geo_primary =
Telangana/Hyderabad returned 259 (clean), of which 49 came from outlets NOT tagged
Telangana — real Telangana stories the outlet filter misses. Neither filter alone
is correct → cheap wide net (outlet OR geo_primary OR district OR scope entity OR
keyword) then the prompt's aboutness gate is the real decision.

**Grouping is broken and articles-only.** The v8 clusterer split 9 bandh articles
across 6 clusters — two from the SAME outlet (Mana Telangana) in different clusters.
`story_cluster_members_v8` has only `article_id`: it cannot see TV or newspapers at
all. → build our own event-merge from the prompt's structured `event` object; do
NOT reuse v8.

**Cross-media spread, measured (Chalo Lok Bhavan protest):**
web **10 distinct outlets** + TV **3 channels** + newspaper **7 reports** ≈ a 20-item,
three-media event. The articles-only prototype had called it "4 outlets" — understated
5×.

**Print lags one calendar day (structural, not a bug).** The 24 July bandh was
announced ON the 22nd → strong on web, **zero in print and zero on TV** for the 22nd,
because that day's newspapers were printed before the announcement existed. Web/TV
break in hours; print carries the next morning. The report must NOT read "0 print"
as "print ignored it". §6 must account for this or print looks asleep daily.

**Event-merge robustness requirements** surfaced by the data:
- same event named differently: "Chalo **Lok** Bhavan" (print) vs "Chalo **Raj**
  Bhavan" (TV title)
- same event in Telugu and English across pillars
- crude keyword matching over- and under-counts (matched "Bandhan Bank", "bank
  holidays", an Ola/Uber strike on "bandh"/"బంద్") — the merge must key on the
  structured event fields (actors + action + date + place), not title text.

### Data-shape notes for the build
- Three media, three tables: `articles` (web), `clippings` (newspaper, col
  `body_text`/`body_text_translated`), `youtube_clips_v2` (TV, cols `video_title`,
  `summary`, `transcript_segment`).
- 22 July volumes: web 1,686 · newspaper 1,210 · TV 526 ≈ 3,400 items/day pooled.

### Still open for §1
- Prototype the OWN event-merge on 22 July across all three media (show the 6 final
  points with real cross-media spread).

### TV data shape — RESOLVED 2026-07-23
`youtube_clips_v2` stores **segments, not broadcasts**: 799 rows / 48h but only 336
distinct `video_id` (avg segment 1,186 chars). One bulletin = several rows.
**Mandatory rules:**
- Every TV spread/reach count dedupes to distinct `video_id` (or `channel_id`),
  never raw rows — else TV is overcounted ~2.4×.
- For sentiment, all segments of one `video_id` are judged as ONE item.

---

## 2b. Section 2 — The Big Story — AGREED (Choice A: deep-dive)

**One story, a full dedicated page, deep.** Resolves the §1/§2 collision: §1 is the
whole day shallow (6 points); §2 is the single dominant story deep. It will almost
always be §1's Point 1, expanded — intended, not redundant.

### Step 1 — pick the story (reproducible, fixed score)
Computed after the §1 event-merge so the same day always yields the same pick:
`reach (distinct owners, TV deduped to videos) ` dominant
`+ independence (distinct owners not feeds) + government-weight + tenacity (ran all
day vs one burst)`. Highest score wins.

### Step 2 — page built entirely from that story's merged item set
Every element computed from the items; nothing generated free-hand.

| Element | Data source |
|---|---|
| A. Spine (one line: what it is) | merged set, verified |
| B. Spread bar (graph) web/TV/np | item set by pillar+owner, **TV deduped to video_id** |
| C. Timeline "how it moved" (graph) | `collected_at` per item — **collection time, hour granularity, print-lag labelled** |
| D. Tone split for this story (graph) | sentiment verdicts filtered to the set |
| E. Quotes, gov vs opposition, side by side | `article_quotes`/`clipping_quotes`/`youtube_clip_quotes` (speaker, text, `quote_text_en`) |
| F. "Who is missing" — no gov voice line | absence check over all quotes in the set |
| G. Numbers in play | `article_numbers` (value, unit, context) |
| H. Every source, cited | item list → §10 |

### Accuracy guarantees
Reproducible pick · every value traces to an item · article quotes verifiable via
`char_offset_start/end` · TV deduped · timeline honestly labelled as collection-time
(morning/afternoon/evening, not minute) · "no government voice" is a computed fact.

### Caveat (on the page, not hidden)
Timeline uses `collected_at` (scrape time), not publish time — reliable to the hour,
not the minute. True publication timing would need a separate ingest change.

### Data availability per pillar — VERIFIED live on 22 July 2026

Two sources feed every element: **CORPUS** (facts already stored — counts,
timestamps, quotes, numbers; no model touches them) and **PROMPT** (judgements —
aboutness, tone, which event; each checked against a real sentence).

| Element | Source | Kind |
|---|---|---|
| What the story is (spine) | PROMPT | judgement |
| Which event an item belongs to (merge) | PROMPT | judgement |
| Spread counts (web/TV/np) | CORPUS | fact — counting |
| Timeline | CORPUS | fact — `collected_at` |
| Tone split | PROMPT (sentiment engine) | judgement |
| Quotes text/speaker | CORPUS | fact — pre-extracted |
| Quote = gov or opposition | PROMPT + roster | judgement |
| "No government voice" | CORPUS | fact — absence over quotes |
| Numbers (₹, counts) | CORPUS | fact — pre-extracted |
| Source links | CORPUS | fact |

**Rule of thumb:** counting / timestamps / quotes / numbers → CORPUS (accurate, no
model). What-is-it / about-gov / good-or-bad / same-event → PROMPT (checked vs text).

**Per-pillar availability (verified 22 Jul):**

| | Websites | Newspapers | TV |
|---|---|---|---|
| Quotes | yes (29,741; +EN, +char offsets) | yes (542) | yes (471) |
| Numbers | yes (`article_numbers`, 66,799) | **yes (`clipping_numbers`, 1,535)** | **NO table** |
| Speaker→entity id | ~25% | 0% | 0% (no column) |
| Speaker NAME in text | yes | yes | yes |

**Corrections to earlier assumptions (both were wrong):**
- Numbers are NOT web-only — newspapers have `clipping_numbers`. Only **TV** lacks a
  numbers table (`youtube_clip_numbers` does not exist).

**"No government voice" check — method fixed by this finding.** Speaker→entity_id is
empty for print and TV, so the check CANNOT use id-matching. It matches the stored
`speaker_name` against the ROSTER. Names are present and real (22 Jul print sample
included minister *Ponnam Prabhakar*). Therefore the roster is not only the sentiment
filter — it is the **join key** for the government-voice check across all three media,
and MUST carry every name variant + Telugu spelling or ministers who spoke are missed.

### Gaps on the record
| Gap | Consequence | Fix |
|---|---|---|
| TV has no extracted numbers | figures spoken only on TV are lost (§2 G, §8) | run number extraction on `youtube_clips_v2` — new work, deferred |
| Speakers not id-linked (print/TV) | gov-voice check goes by name via roster | no extra work IF roster is complete |

---

## 3a. Section 3 — Coverage by Topic — AGREED

Government coverage split into the client's topics. **No department column.** All
three media. Per topic, the single best item from EACH medium, shown with its image.

### Topics (11) — client's 9 + two the real data demanded
Politics · Governance · Security · **Law & Order** · Infrastructure · Health ·
Agriculture · Social · Finance · Environment · **Employment/Exams**

Topic is assigned **by the prompt** (closed list of 11), not the corpus
`topic_category` — the corpus tag is news-desk taxonomy, noisy, national, and on
every article. Prompt assignment gives the client's vocabulary, government-only, and
no extra call (done while judging tone).

### Layout — per topic block
- Header: topic name · item count split (web N · TV N · newspaper N) · net tone + bar
- Three cards, one per medium, each = the top item of that medium for that topic:

| Card | Image source | Fill (22 Jul) | Text/data shown |
|---|---|---|---|
| Top Article | `articles.thumbnail_url` | 92% | headline · outlet · time · tone dot · cite |
| Top TV Clip | `img.youtube.com/vi/{video_id}/hqdefault.jpg`; plays via `embed_url` on screen | 100% | title · channel · duration · tone dot |
| Top Cutting | `clippings.clipping_image_b64` (scanned image, ~76 KB) | **100%** | headline · paper · `page_number` · tone dot |

- Footer: "all sources → §10".

**"Top" per medium:** item whose event has widest spread, tie-break tone strength
then recency. Blocks sorted by volume; red bars draw the eye regardless of size.

### On-screen vs PDF
On screen: TV card plays inline (`embed_url`); rows expandable to 3–4 more stories.
PDF: static images, one cutting per topic (~850 KB total for 11 — acceptable; showing
ALL cuttings would balloon the file, so top-one-per-topic is also the size guard).

### Data sources
Counts/images/timestamps = CORPUS. Topic label + tone + which-item-is-top = PROMPT.
Lead/top item depends on the event-merge (shared unbuilt piece).

### Image availability — VERIFIED 22 Jul
`articles.thumbnail_url` 1490/1611 · `clippings.clipping_image_b64` 1210/1210 (~76 KB
avg) · `youtube_clips_v2.video_id` 204/204 (thumbnail derivable, embeddable).

---

## 4a. Section 4 — How Each Scheme Was Covered — AGREED

**The only section on a 7-DAY rolling window**, deliberately breaking the one-day
rule. Schemes are ongoing programmes, not daily events; a single day gives 1–8
mentions (noise), a week gives a real trend. Verified 7-day volume (English keywords
only — Telugu adds more): Kaleshwaram 351, Indiramma 128, Mission Bhagiratha 29,
Mahalakshmi 21, Rythu Bharosa 16, then a long quiet tail (Gruha Jyothi 2, Cheyutha 1).

### Detection
Corpus-side keyword match (EN + Telugu variants) against the scheme list. Reliable
for distinctive names (Kaleshwaram, Gruha Jyothi). **Generic names over-match**
("Mahalakshmi" = goddess/temple; "Cheyutha" = ordinary Telugu) → need scheme-context
disambiguation (co-occurring gov/scheme terms) or they inflate.

### Per-scheme block (active schemes)
- Header: scheme · 7-day mentions · 3-media split (web/TV/np) · net tone
- **Tone-over-time trend**: 7 bars, **height = daily volume, colour = that day's net
  tone (green→red)**. Shows loudness and direction together. (Data: sentiment verdicts
  grouped by day.)
- **Three media cards** (same as §3): top article (`thumbnail_url`), top TV
  (`video_id` thumbnail, `embed_url` plays on screen), top cutting
  (`clipping_image_b64`). Each: headline · outlet · tone dot · cite.
- Footer: all sources → §10.

### Volume-gated treatment (auto, per scheme)
| Daily volume | Treatment |
|---|---|
| Active (enough/day) | full block: tone trend + 3 cards |
| Moderate | single net tone + 3 cards, NO daily trend |
| Quiet (<~5 / week) | collapsed into one "Quiet this week: …" line, named not dropped |

Never draws a 7-day tone trend on ~2 stories/day — same discipline as the sentiment
confidence gate.

### Findings that shaped it (7-day, verified)
- TV dominates the hot scheme: Kaleshwaram TV 245 vs web 99 — the week's controversy
  is a *television* story; the media split is itself information.
- The 7-day window is essential: daily, Kaleshwaram=15/Indiramma=8 would be noise.

### Dependencies
Sentiment engine (per-item, dated) for the tone trend + card dots; scheme detection
(keyword EN+TE) for membership + top item. No new data — all downstream of specced
pieces.

---

## 5a. Section 5 — Coverage by District — AGREED

One-day. Tile map + top-10 table. Each district shows **top critical AND top positive
story, side by side** (per the client's original ask); empty slot shows "—", never
invented.

### Map
Tile grid (equal-size squares in rough geographic position), coloured by each
district's **net tone** (green→red). Deliberately NOT a real boundary map — hand-drawn
district shapes would be subtly wrong, and a wrong map in a government doc is worse
than an honest diagram. True outline is a later option (needs district boundary
GeoJSON, verified against the 33 `districts` names).

### Depth
Table: top critical + top positive per district as cited text links (scannable, fits).
On screen: click a district → expands to 3 media cards for its biggest story.
Print: table + map only. (33 districts × pos/neg × 3 media = too many cards for a page.)

### Data caveats — MUST be stated on the section
- **39% of stories carry no district** (22 Jul: 977/1611 tagged). The map shows where
  coverage LOCALISED, not all government coverage. Statewide stories (a cabinet
  decision, a statewide bandh) belong to no district and won't appear here.
- **Multi-tag:** articles average 1.85 districts (1807 tags / 977 articles), so
  district counts SUM TO MORE than the story count. Must be labelled or it won't
  reconcile with §1.
- 31 of 33 districts appeared on 22 Jul.

### Data sources
District tags = CORPUS (`article_districts` → `districts`, `state_code='TG'`). Tone +
top-story selection = PROMPT/sentiment engine. Cards reuse §3 image sources.

---

## 6a. Section 6 — Newspapers, TV and Websites Compared — AGREED

Same government coverage, sliced by **medium** not topic. The only section where the
three are pulled apart; the value is **divergence** (blindspot detection), invisible
everywhere else because everywhere else they are pooled.

Verified 3-media shape (22 Jul): web 1611 items / 20 outlets · TV 204 videos / 23
channels · newspaper 1210 / 36 papers. **Print has the MOST distinct voices (36)**,
web the fewest — online = more stories, print = more outlets.

### Layout
- Three panels (web / TV / newspaper): outlets · net tone + bar · most favourable item
  · most critical item (all cited).
- Small 3-bar chart of net tone so the gap is seen before read.
- **Divergence readout** (the point of the section): one computed sentence — biggest
  tone gap between two media + the story driving it.
- **Per-topic divergences**: up to two, shown ONLY when both media clear a volume
  threshold on that topic (e.g. "On Kaleshwaram TV −61 vs print −5"). Honest where
  thin, sharp where solid.

### Two structural truths — handled on the page, NOT hidden
- **Print lag:** a fresh story is web+TV first, print next morning. If print is thin on
  a fresh story, say **"not yet in print"**, NEVER "print ignored it" — opposite
  meanings. The divergence sentence must use the honest read.
- **TV fragments:** every TV count here is distinct `video_id`, never raw rows, else TV
  reads 2.4x too loud and every divergence number is wrong.

### Data sources
Counts/outlets = CORPUS (TV deduped by `video_id`, print by paper). Tone + top items =
sentiment engine. Divergence = computed from the three net scores + biggest shared story.

---

## 7a. Section 7 — What Each Side Said — AGREED (half-page, all 3 media)

Government quotes vs opposition quotes, real + direct + bilingual, roster-verified.
**All three media** — verified on 22 Jul: web (Bhatti on drought, Harish Rao on pumps)
AND newspaper (Uttam Kumar Reddy on barrages, KTR on Godavari water) both carried the
day's contested water/irrigation issue; TV had volume (471 quotes) but thinner
name-match. Each quote card labels its medium (web / newspaper / TV).

### Shape (graceful degrade — the honest structure)
- **1 contested pair** when the day yields one (gov line + opposition line on the SAME
  issue, from the event-merge) — the hero block. 22 Jul had a real one (water/barrages).
- **+ 2-3 "also on record"** real quotes to fill honestly.
- Some days **no clean pair** -> just two columns, never forced/invented.
- Half-page, not full — thin by nature (see filter yield below).

### Hard filters (or it looks amateur — all seen in real data)
- exclude quotes containing `@`/social markers (many `article_quotes` are scraped
  tweets — e.g. Dharmendra Pradhan's tweet appeared 5x on 22 Jul)
- de-dup identical quote text (re-scrapes: "forwarded to IIT Bombay" appeared 2x)
- `is_direct = true` only
- roster-gate speakers -> Telangana gov + Telangana opposition ONLY (22 Jul noise
  included Nara Lokesh/AP-TDP, JP Nadda/national, cricketers, Donald Trump 32x)

### Filter yield (honest)
From 9 named gov/opposition figures across all of 22 Jul, only ~4 clean direct
non-tweet roster-valid quotes survived on web; newspaper added more (barrages cluster).
So §7 is REAL but LIGHT — half-page, degrades gracefully.

### Translation risk (bilingual requirement)
`quote_text_en` is **0% populated corpus-wide** — English side does NOT exist in
storage. Must machine-translate at build time (`i18n.attach_en`, already used by the
old report). Mitigations, mandatory: original script ALWAYS shown (the record);
English marked as translation beneath; direct quotes only; verified vs source. This is
the one place the report attributes MT words to a named politician — DIPR can correct
in the editable on-screen version before send.

### Speaker-name normalisation
Same person appears many ways ("Uttam Kumar Reddy" / "N. Uttam Kumar Reddy" / "Uttam").
Roster variant-handling (already required for the gov-voice check) resolves it here too.

### Data sources
Quotes/speaker = CORPUS (all 3 quote tables, `is_direct`). English = build-time MT.
Side = roster. Pairing = event-merge.

---

## 8a. Section 8 — Figures Quoted in the Press — AGREED

Numbers the government gets asked to confirm — money, beneficiaries, targets — each
with its context sentence + source cite.

### The selection rule IS the section
Extraction is clean (value + unit + context). **Raw figures are ~50% noise** (22 Jul:
movie budgets "Sambarala Eti Gattu ₹70-80cr", startup Series C ₹510cr, "CJP Instagram
followers"). A figure qualifies ONLY if (1) its parent story passed the aboutness gate
AND (2) it ties to a scheme/department/government subject. Same gate as everywhere.

### Layout — grouped by kind
MONEY / PEOPLE / TARGETS. Each row: number · context sentence (makes it usable +
verifiable) · source cite. Real 22 Jul keepers: ₹2,500cr two irrigation projects,
₹800cr Education Hub, 16 lakh water-security beneficiaries, ₹5 lakh farmer compensation.

### Allegation flag (⚠)
Figures inside a claim ("*alleged* ₹1,400cr contractor payment to BRS") get a ⚠ — the
number is contested, not confirmed. Press officer must know stated-vs-alleged.

### Two-media only — MUST be stated on the section
`article_numbers` + `clipping_numbers` exist; **TV has NO number extraction** (no
`youtube_clip_numbers` table). A figure spoken only on TV won't appear. Label the
section "from press and print" so it is not read as exhaustive.

### Data sources
Figures = CORPUS (`article_numbers`/`clipping_numbers`: value, unit, context). Which
qualify = aboutness gate + scheme/dept tie. Allegation flag = claim context.

---

## 9a. Section 9 — Which Outlet Said What — AGREED

Per-outlet table: how each covered the government, and which way it leaned. Answers
"who is against us this week." One row per **media house**, split by medium beneath.

### Brand identity — the key decision
Same media house appears across pillars with different strings (verified 22 Jul):
web "TV9 Telugu" / TV "TV9 Telugu Live"; web "V6 Velugu" / TV "V6 News Telugu";
web "HMTV" / TV "hmtv Telugu News". **Merge to one house, show TV vs web as sub-rows.**
A house's broadcast and website can lean differently (actionable). Needs a curated
**outlet-identity alias map** (client-reviewable, same pattern as the roster).

### Columns
- ON GOVT: items about the government (aboutness gate), not total output.
- TONE + NET: for/against split + score — THE "who's against us" signal (22 Jul:
  Namasthe Telangana would stand out hostile).
- 7-DAY sparkline: outlet's lean over the week — one bad day is noise, a week of red
  is a hostile outlet. **Cannot exist on launch** — needs 7 days of stored verdicts;
  column appears after a week of running.
- Sub-rows per medium where a house runs both (TV9-TV vs TV9-web).

### Sort
Default by volume; one-click "most hostile" re-sort = the question the section exists
to answer.

### Data sources
Items/outlet/medium = CORPUS. About-govt + tone = engine. Brand merge = outlet-identity
map. 7-day trend = accumulated stored verdicts (empty at launch).

---

## 10a. Section 10 — All Stories, with Links — AGREED

The annexure every `[N]` citation points to. Almost entirely CORPUS (no engine).

### Link resolves by medium (verified 22 Jul)
- Web: 100% valid http URLs -> [open]
- TV: 100% valid YouTube URLs -> [watch]
- Newspaper: **0 public URLs** (only `source_pdf_path` on the box). No web link needed —
  use `clipping_image_b64` (100% filled) + paper + `page_number` -> [view cutting].

### Layout
Per entry: ref number · headline · outlet · **medium** · **language** · time · link.
Medium + language labels matter for a bilingual gov client (Telugu print vs English web
is part of judging a source).

### Decisions
- **PDF: cited sources only** (every `[N]`, in order of appearance) — tight, all
  referenced. **On-screen: full list** (~200-300 government-relevant items/day).
- **Order by reference number** so `[12]` jumps to entry 12 — makes citations navigable.

### Data sources
All CORPUS — URLs, titles, outlets, timestamps, languages, cutting images. Report adds
only the reference number + ordering.

---

# ============ ALL 10 SECTIONS + STRIP AGREED (2026-07-24) ============

Design phase complete. Section-by-section decisions locked above. What remains is the
shared machinery every section depends on, then build + validate.

## Cross-cutting pieces every section needs (build order)
1. **The roster** (~150 names, EN+TE, variants) — used by: sentiment filter, gov-voice
   check, §7 side-assignment, speaker-name normalisation. Single most leveraged artefact.
   CLIENT-APPROVED. Blocks the entire engine.
2. **Fixed department list** (~24) + **topic list** (11) + **scheme list** (EN+TE
   variants) — closed vocabularies emitted by the prompt. Block §3/§4/§5/§8 grouping.
3. **Outlet-identity map** (brand merge across pillars) — blocks §9, helps §6.
4. **The sentiment/judgement engine** (LIST->FILTER->JUDGE(+event,+topic,+dept)->VERIFY
   ->MERGE->STORE->COUNT->TEST) — the core; every tone/verdict/aboutness call.
5. **The event-merge** (own, all-3-media, structured event fields) — blocks §1 lead
   selection, §2 entirely, §3/§4/§5 top-item, §7 pairing. Do NOT reuse v8 (articles-only,
   under-merges).
6. **Renderer** — Playwright/Chromium for edit + export + Telugu shaping (vs WeasyPrint).

## Standing rules that touch every section
- Calendar day 00:00-23:59 IST (except §4 = 7-day rolling).
- All 3 media pooled everywhere except §6 (compares them).
- TV always deduped to distinct `video_id`; segments of one video judged as one item.
- Print lags one day — never read "0 print" as "print ignored it".
- Headline-only sources (if re-enabled) excluded from tone/quotes/figures.
- Every number traces to a corpus item; every judgement verified against real text.
- Descriptive, never prescriptive. No "coverage-speak". No "intelligence"/"yesterday".

## Known gaps carried into build
- TV has no number extraction (§8 is web+print only) — deferred.
- Speakers not id-linked in print/TV — handled by roster name-match.
- `quote_text_en` 0% populated — §7 English is build-time MT (risk: MT words on named
  politicians; original always shown; editable before send).
- 9 outlets IP-blocked incl. Sakshi/Hindu — headline-only via Google News, currently
  disabled per client (no proxy).
- 137 headline-only trial articles still in corpus — pending deletion.
- Persona still not applied by live code (Sports leaks in; 466-vs-72 watchlist gap).

## Validation gates before ship
- Sentiment: 50 hand-labelled items, >=80% agreement, print scored separately.
- Event-merge: its own validation set (the 22 Jul bandh = 9 articles/6 clusters is a
  known test case).
- Roster + all vocab lists: client sign-off.

---

## 3. The sentiment engine — AGREED

Applies to every section that carries tone. Replaces `article_stances` **for this
report only**; other consumers keep using the old table.

### Why the old one is abandoned

Live example, in the database today — *"BLOs protest Revanth Reddy's remarks, wear
black badges"* (Telangana Today). Stored stances:

| Actor | Stance | Intensity |
|---|---|---|
| A Revanth Reddy | critical | 0.3 |
| Booth Level Officers | supportive | 0.5 |

`lean = avg(POL × intensity) = ((−1×0.3) + (+1×0.5)) / 2 = +0.1` → **counted as
favourable coverage.** A protest against the Chief Minister is recorded as good news.
The engine measures the mood of speakers, not the portrayal of the government.

Compounding data problems, all verified 2026-07-23:

- `clipping_stances.actor_entity_id` — **100% NULL** (37,774 rows)
- `article_stances.actor_entity_id` — **61% NULL** (1,769,159 rows)
- `youtube_clip_stances` — **no entity column at all**
- Actor names include countries, job titles and junk (`article`/`Article`, 825 rows)
- Intensity scales differ per pillar (0.58 / 0.80 / 0.78 averages) — not poolable
- TV uses a different vocabulary (`supports`/`opposes`/`criticises`/`praises`) that
  maps to zero under the current `POL` expression

### The pipeline

```
LIST  ->  FILTER  ->  JUDGE  ->  VERIFY  ->  STORE  ->  COUNT  ->  TEST
```

**Step 0 — Roster.** ~150 names: CM, ministers, departments, state bodies, plus
opposition, in English and Telugu with every spelling variant. Seeded from the
client's own scope document (Allies 49 → government, Opposition 30, Watched 116 →
institutions after removing districts, Neutral 271 → discarded, mostly AP).
Client-approved. **BLOCKS EVERYTHING.**

**Step 1 — Filter.** Active Telangana source, inside the calendar day, mute terms
applied (see §4). ~1,700 items/day.

**Step 2 — Judge.** One call per item. Aboutness and verdict answered together, in
the same call, because they need the same reading and splitting them lets the two
answers contradict each other. Prompt: `briefing-tone-prompt.md`.

Returns:
```json
{ "about_government": true, "verdict": "critical", "strength": "strong",
  "evidence": "<sentence copied verbatim>", "lands_on": "<department>",
  "confidence": 0.93 }
```

**Step 3 — Verify.** Search the item's own text for the evidence sentence. Absent →
verdict discarded, item marked unjudged. A model can assert a confident wrong
verdict; it cannot fabricate a quote from a document it misread.

**Step 4 — Store.** One permanent row per item, with model and prompt version.
**Never recomputed** — fixes the current behaviour where three clicks produce three
different reports.

**Step 5 — Count.**

> **Net = (favourable − critical) ÷ (favourable + critical)** — range −100 to +100

**Step 6 — Test.** 50 hand-labelled items. Ship at ≥80% agreement. Kept permanently
as a regression set. **Print scored separately** — clippings median 440 chars, so a
good pooled score could hide a bad print score.

### Rules agreed

| Rule | Decision |
|---|---|
| Judge portrayal, not mood | Bad news ≠ critical unless the government is blamed |
| Impartially-reported attacks | Still **critical** |
| Court ruling against the state | **Critical** (client's call) |
| Centre-vs-state disputes | **Context-dependent** — state pressing/winning = favourable, refused = critical, unclear = neutral |
| Government praising itself | Judge the item's portrayal, not the speaker's mood |
| Verdict form | **Label** (favourable/critical/neutral), never a numeric score |
| Strength (strong/mild) | **Ranking only** — never in the maths |
| Confidence | **Gate, not weight.** <0.6 → "unclear", counts nowhere. Never fractional stories |
| Intensity scores | **Ignored entirely** — incomparable across pillars |

---

## 4. Mute terms — AGREED, with a required split

Stored in `analytics.org_api_scope.mute_terms` (14 entries, org
`31ad3fa9-25eb-4b3c-8a56-360696fc680a`). **They cannot be applied literally as
stored** — the list mixes search terms with instructions to a human.

**Group A — safe literals**, word-boundary matched on title + body:
`Telangana film`, `trailer`, `box office`, `OTT`, `cinema`, `IPL`, `fantasy league`

**Group B — DANGEROUS as literals, must NOT be blunt-matched:**

| Term | Why |
|---|---|
| `review` | Kills "Cabinet review meeting", "policy review", "CM reviews irrigation projects" — core government coverage |
| `serial` | Kills "serial killer" crime reporting |
| `song` | Over-broad; hits cultural and political-campaign coverage |

Use these only in combination with an entertainment topic signal, never alone.

**Group C — judgement rules, folded into the prompt as exclusions:**
- "Telangana (US city/community references)"
- "unrelated people named Revanth/Reddy"
- "historical archive or exam-preparation pages with no current-government relevance"

Sports is separately excluded via `user_brief_prefs.topics.exclude = ["SPORTS"]`, so
cricket/IPL are handled twice.

---

## 5. Key Numbers strip — AGREED

Four tiles. Unnumbered, no heading, no standfirst, above §1.

### Tile 1 — Total Stories
Count of every item from an active Telangana source inside the calendar day, after
mute terms. Three-segment bar sized to real shares, labelled Websites / Newspapers /
TV. No filtering sub-line.

### Tile 2 — Biggest Subject
Largest `lands_on` group among items judged *about the government*, with the
runner-up beneath. **Requires the fixed department list** (§6 below).

### Tile 3 — Sentiment
Net score (−100…+100), two-sided bar, and the counts: `124 for · 194 against ·
425 took no side`. Denominator always visible. Never a one-sided percentage.

### Tile 4 — Top Outlet, each medium
**One outlet per medium** — the highest volume of government-related items for
newspapers, for television, for websites, each with its count. Ranked by **volume**,
not hostility.

---

## 6. Fixed department list — AGREED, to be drafted

Free-text department names produce "Irrigation", "Irrigation Dept" and "I&CAD" as
three rows, splitting one department's counts three ways. `lands_on` must be a
closed vocabulary. Feeds Tile 2, §3 and §4.

Draft list (to confirm against the Telangana secretariat's own department names):
Agriculture · Animal Husbandry · Civil Supplies · Education · Endowments · Energy ·
Environment & Forests · Finance · General Administration · Health & Family Welfare ·
Home · Industries & Commerce · Information Technology · Irrigation (I&CAD) ·
Labour & Employment · Municipal Administration & Urban Development · Panchayat Raj &
Rural Development · Revenue · Roads & Buildings · Social Welfare · Transport ·
Tribal Welfare · Women & Child Welfare · Youth Affairs

---

## 7. Ingest state — resolved 2026-07-23

Recorded in full at `rig-knowledge-base/01-rig-surveillance-backend/issues.md` I-26.

- Circuit breaker was a one-way door (`is_active=false` invisible to the weekly
  reset). **Fixed**, deployed, restarted.
- 37 healthy sources re-enabled. Telangana active sources **34 → 72**.
- **Eenadu** converted to HTML scraping — RSS is gone (410). Full Telugu text,
  ~5,530 chars average.
- `html_collector` title bug fixed — titles were derived from URL slugs, so Eenadu
  articles arrived titled `126130246`. Now reads `og:title`.
- 7 Google-News-relayed outlets (Sakshi, The Hindu, Indian Express ×2, News18 ×2,
  ZeeNews) were wired then **disabled at client request** — headline-only, no body.
  `sources.headline_only` (migration 117) retained for future use.

### Consequences for this report
- **9 outlets remain unreachable**, incl. Sakshi and The Hindu — datacenter IP
  blocked at CDN. Restoring them needs a residential proxy (~$2–6/month, declined).
- 137 headline-only articles remain in the corpus from the trial — **pending removal**.

---

## 8. Open items

| Item | Blocks |
|---|---|
| **Roster (~150 names, EN + TE)** | The entire sentiment engine |
| Fixed department list confirmation | Tile 2, §3, §4 |
| 50-item validation set | Shipping |
| Renderer choice (Playwright vs WeasyPrint) | §1 editing + export |
| `transcript_segment` — whole broadcast or fragment? | All TV verdicts |
| Delete 137 headline-only articles | Clean corpus |
| Sections 1–10 detailed design | Build |
| Google News title suffix / region noise | Only if relays are re-enabled |

---

## 9. Known risks

1. **Print is the weakest pillar.** Clippings median 440 chars — a headline and a
   paragraph. Expect more "unclear". Validate print separately.
2. **TV may be fragments.** Column named `transcript_segment`; unverified.
3. **The roster is the single point of failure.** Wrong or stale names silently
   mis-classify everything downstream. It must be client-approved and dated.
4. **Only 21 of 72 sources were producing before the fix** — steady state after the
   repair still needs observing over several cycles.
5. **`entity_dictionary.party` is dirty** — `INC`/`Indian National Congress`/
   `Congress` are separate values; 254 entities carry no party. This is why the
   roster replaces party inference rather than depending on it.
