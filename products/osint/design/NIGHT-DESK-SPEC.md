# NIGHT DESK — RIG OSINT design system & build spec

> Concept name is cosmetic (changeable). "Night Desk" = the overnight
> intelligence news-desk that compiles a cinematic briefing while you sleep.
> Cinematic intelligence briefing · deep rough-black · professional-yet-colorful ·
> newspaper structure (Adminator density) + Framer skin (glass depth, hero tilt,
> liquid mask, options bar). Built from the user's 27-question brief.

## Who it's for (drives every decision)
Govt communications teams, PR/reputation firms, political war-rooms, policy
analysts. They must **trust** the data (it informs real decisions) and **read it
fast** (overload is the enemy). So: density + verifiability + zero fabrication.

## The feel
A classified newspaper rendered in glass on a black film-grain desk. Not a SaaS
dashboard. Not a slot machine. A briefing you'd hand a chief of staff at 6am.

---

## Design tokens

### Canvas & texture (answer 2,12 — deep black, rough, animated)
- `--black: oklch(0.045 0.006 270)` near-pure black, faint cool cast
- Film-grain SVG noise overlay (soft-light, ~.22) + vignette
- Animated background: very slow drifting noise + a low-opacity deep-tone aurora
  mesh (steel/violet at ~6% alpha) that breathes — "dark that looks like animation"
- Newsprint engraving texture only on the Home masthead

### Surfaces (answer 13a+13b,14 — glass + depth, NO rendered 3D)
- `--paper: oklch(0.12 0.012 270)` glass panel base
- Glass = translucent + backdrop-blur + 1px top highlight + tiered drop-shadows
- Depth tiers: t1 cards (subtle), t2 raised, t3 hero (deep shadow + glow)

### Ink & color (answer 9,10,11 — keep signal meaning, professional yet colorful)
- `--bone: oklch(0.96 0.008 85)` warm off-white (newsprint), `--muted 0.66`
- ONE editorial accent: `--gold: oklch(0.82 0.14 85)` (press highlight)
- Signal palette (meaning preserved, refined not neon):
  - hostile `oklch(0.64 0.22 25)` · ally `oklch(0.78 0.15 165)`
  - rival `oklch(0.68 0.20 320)` · cool/info `oklch(0.74 0.13 235)`
- Charts: duotone gradient fills of the signal palette — vibrant but disciplined,
  never rainbow. Color only where it carries meaning.

### Type (answer 21,22 — one readable display, numbers NOT giant)
- Display: **Newsreader** (serif, newspaper, high readability) — headlines/masthead
- Body/UI: **Geist Sans** (clean grotesk)
- Figures/labels: **Geist Mono** — used inline, never as giant glowing hero numbers

### Motion (answer 13,15,19,20 — I choose: refined-cinematic)
- Page transition: filmic fade + 1.5% scale (a cut, not a slide)
- Hero panel only: cursor-parallax tilt (rotateX/Y) — answer 15
- Count-ups on Analytics figures; stagger-reveal on scroll
- Liquid-mask hover on imagery (Dossier + Home lead photo) — answer 17
- Magnetic primary actions; options-bar filter pill — answer 18
- Tasteful, not gimmicky; one cinematic moment per screen

---

## Information architecture — 5 dense pages (answer 4)

Left sidebar nav, icons+labels, collapsible (answer 5). Full-bleed, whole-screen
width (answer 8). Adminator-level density (answer 7). NO top KPI ribbon (answer 6).
Single persona hardcoded: Revanth Reddy / Telangana (answer 24). Mock data lives in
a `data/` layer shaped exactly like the real endpoints so wiring later is trivial.

### 1 · HOME — "The Front Page" (answer 4-home)
A real newspaper front page in a webapp: textual, medium-density, readable, with
icons + interactive tells. NOT a KPI grid.
- **Masthead**: NIGHT DESK · subject · dateline · replay window · "confidence HIGH"
- **Lead story**: executive BLUF as a serif lead column + liquid-mask hero image
- **Columns** (newspaper grid): Defining Stories, Voices Overnight, Climbing
  Stories, **Narrative DNA** (`narrative_dna` — the 2-3 competing frames fighting
  to define you, colour-coded by share), Counter-Narrative, "The One Thing"
- **Sidebars**: breaking ticker (register_is_breaking), mood line (sentiment),
  cross-language tell, "dog that didn't bark" silence box
- Every story = headline + 1-line dek + source chip + stance dot + "open" → drawer
- **Why**: customers start their day here; the newspaper metaphor makes 15 signals
  feel like an effortless read, not a dashboard to decode. Endpoints: executive,
  stories, voices, climbing, mood, emerging, counter-narrative.

### 2 · ANALYTICS — "The Numbers Room" (answer 4-analytics)
All quantitative intelligence, in depth, with charts — AND a verifiability spine.
- Charts (real shapes): area (coverage trend), donut (share-of-voice), diverging
  bars (outlet favourability), heat bars (target heat), sparklines (per-metric),
  small-multiples (stance trajectory, counter-speed, narrative half-life,
  cross-language gap, issue ownership, allegiance divergence, quote-selection bias)
- **Data-verification system** (answer: "a way they can verify if the data is
  right" + "understand each data"):
  1. Every figure is a `StatWithVerify` — click → **Verify drawer** showing:
     definition · formula · source tables · window + as-of · sample size **n** ·
     **confidence chip** · and the actual underlying articles/quotes that produced it
  2. Inline `ⓘ method` tooltip — plain-English "what this is"
  3. `n=` + confidence badge on every metric (thin samples visibly hedged)
  4. "View sources (N) →" drills to the exact rows counted
  5. Per-panel as-of timestamp + window
  - This is the Aryan-Mehta faithfulness lens: a govt analyst can defend every
    number to their boss. No black-box stats.
- **Why**: trust is the product. A number you can't trace is a liability.

### 3 · DOSSIER — "The Registry" (answer 4-dossier)
Select any entity or place; see everything our DB knows.
- Left: searchable entity/place filter (people, orgs, districts) with type facets
- Right: dossier — photo (liquid-mask), canonical name + aliases, role, timeline of
  coverage, stance-toward-subject, top quotes, top/most-hostile sources,
  co-mention network (ally/rival), favourability, LLM dossier read (cite-gated)
- Place mode: district card → local sentiment, top stories, lat/lng mini-map
- Endpoints: entities, entity_read, search_entities, mentions, quotes, stances
- **Why**: war-rooms work entity-first ("what's the posture on KCR / in Khammam?").
  This is the investigate surface.

### 4 · MAP — "The Theatre" (answer 4-map; features to be built)
Geospatial intelligence, beautiful + useful (never "plain stupid").
- 3D-tilted India/Telangana choropleth (article_locations lat/lng, 268k rows)
- District sentiment shading (signal palette) · story pins that cluster/expand
- "Where pressure lands" heat overlay · hover a district → mini-dossier
- Time-scrubber (replay clock) to watch coverage move across the map
- **Why**: politics is geographic; a map answers "where" instantly. Built fresh.

### 5 · DISPATCH — "Reports & Delivery" (answer 5 — my call)
Home for the report + Gmail + export features you flagged.
- Compose the briefing → live **newspaper-style PDF preview**
- Channels: **Gmail send** (the connector we built), PDF export, newsletter
- **Schedule** cadence (daily 6am etc.) + recipient list
- **Archive**: every past brief, searchable (brief history)
- Hooks for MCP server + smart-filter / coverage-QA agents
- **Why**: monitoring is worthless if it doesn't ship. This closes the loop and
  gives report/gmail a real home. (Alt: a "War-Room" strategy page — say the word.)

Product story, one verb per page: **Read → Analyze → Investigate → Locate → Deliver.**

### Global (every page)
- Command search (⌘K) = the **`coverage_qa`** agent ("Ask anything about your
  coverage" — plain-English Q&A grounded in the corpus) · options-bar filter
  (time-range / topic / language) — answer 18
- `narrative_dna` also surfaces as a panel in **Analytics** (narrative fingerprint)
- Export + Send-brief in header (magnetic) · sidebar collapse

---

## Tech (answer 26 — my call)
- React 18 + **Vite** + **framer-motion** (tilt/parallax/transitions)
- **Recharts** (or visx) for real chart shapes
- CSS design tokens (no rainbow utility soup); many small files (<400 lines each)
- No three.js (answer 13 = a+b only) → light, runs anywhere, still deeply 3D-feeling
- `data/` mock layer mirrors real endpoint JSON → later wiring = swap mock for fetch
- New app at `products/osint/design/night-desk/`; delete `dispatch-proto/`

## Build order (answer: flagship first)
1. **HOME** flagship — nail the look together → you confirm
2. Analytics (+ verify system) → 3. Dossier → 4. Map → 5. Dispatch
