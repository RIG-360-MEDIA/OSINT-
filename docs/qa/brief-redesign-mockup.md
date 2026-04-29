# Brief Page — Redesign Mockup (Step-through edition)

> Concept sketch. Not built yet. Examples below use real entities and
> headlines retrieved by the live RAG against this branch's database
> (Telangana Chief Secretary user, 27 Apr 2026).

---

## The shape of the experience

The user opens the Brief at 06:30 IST and sees **one screen**: At a Glance.
Three sentences and a pulse line — readable in 30 seconds. From there
they step forward through nine focused sections, one screen at a time.
Each step has a single job; nothing competes for attention.

```
   ┌──────────────────┐
   │   At a Glance    │  ← landing screen, 30-second read
   └────────┬─────────┘
            │  next ▶
   ┌────────▼─────────┐
   │  Day's Movers    │  ← 5-7 multi-source cards
   └────────┬─────────┘
            │
   ┌────────▼─────────┐  Primary Sources · Print Press · Public Pulse
   │   …7 more …      │  On The Wires · Entities · Signals to Watch
   └────────┬─────────┘  Silence Map · Decision Queue
            │
   ┌────────▼─────────┐
   │  Source coverage │
   └──────────────────┘
```

Always-visible elements:
- **Header pulse band** (sticky): pillar counts + confidence chip + step indicator (3 / 10).
- **Bottom nav**: ◀ Prev · Step indicator · Next ▶
- **Side rail** (collapsible on mobile): jump-to any section.

Why step-through: a senior official doesn't read 10 sections sequentially —
they read At a Glance, then *jump* to whatever the lead indicator pulled
their attention toward. The wizard pattern makes the jump explicit and
avoids overwhelming a single scroll.

---

## Visual language (across the whole experience)

### Typography
- **Display serif** for section titles (continuing the existing
  newsroom feel) — generous size, tight tracking.
- **Body serif** for prose, ~18px, line-height 1.6 for comfortable
  reading on phone or laptop.
- **Sans-serif** ONLY for chips, counts, and metadata — never for
  body prose. Keeps the "intelligence brief" texture.

### Pillar palette
Each data pillar gets one colour, used consistently across chips,
underlines, dividers, and pulse bars. The palette is muted enough to
work on a long-read page; saturation rises only for action chips.

| Pillar | Hex (light) | Hex (dark) |
|---|---|---|
| Article | `#1a1a1a` ink | `#e8e6df` paper |
| Govt doc | `#7a1f1f` oxblood | `#c45a5a` rust |
| Newspaper | `#7a5a2e` sepia | `#c79a5a` parchment |
| Social | `#1f5a7a` slate-cyan | `#5aa8c4` sky |
| Video | `#5a2e7a` violet | `#a574c4` orchid |

Two text contrasts per pillar so the system works in both light and
dark modes without introducing a new system. Every text sample meets
WCAG AA (4.5:1) on its background; chips and underlines meet 3:1 for
non-text contrast.

### Layout
- Single column on phone (≤ 600px).
- Two-column on tablet (600-1100px) — primary content + side rail.
- Three-column on desktop (≥ 1100px) — left side rail, primary
  content, right metadata rail.
- Reading width capped at ~70 characters of body text. The page stays
  comfortable on a 27" monitor.

### Motion
- Fade-up reveal on scroll (160ms, ease-out) for each section.
- No parallax. No autoplay video.
- A single "step" transition between sections: 240ms slide, respects
  `prefers-reduced-motion`.

### Iconography
Pillar icons are simple line glyphs (newspaper, scroll, broadsheet,
chat-bubble, play-circle). Used consistently as chip prefixes and in
the side-rail navigation.

---

## Accessibility (built in, not retrofitted)

- Every section has a real `<h2>` heading and a stable `id` so the URL
  reflects the active step (`/brief#day-movers`, `/brief#pulse`).
- Side-rail is a `<nav>` with `aria-current="step"` on the active
  section.
- Chips are `<button>`s with `aria-label` describing the source kind
  and date; they open the popover with a real focus ring.
- Tab order matches reading order; arrow-keys move between steps;
  `Esc` closes the popover or returns to At a Glance from a deep step.
- All colour-coded information has a redundant text or shape cue
  (chip label spells out "Article" / "Social" / etc.) — colour is
  never the sole channel.
- Vernacular print clippings show original language **and**
  translation; both are exposed to screen readers with `lang="te"` /
  `lang="ur"` etc.
- Pulse bars expose their numeric values to assistive tech via
  `<meter>` or equivalent — not just visual bars.
- Confidence chip has a real explainer panel that opens on click,
  not just a tooltip — accessible via keyboard.
- "Skip to At a Glance" hidden link as the first focusable element.

---

## Step-by-step walkthrough

Each step below is described as the user would experience it: what's
on screen, what they can do, what evidence backs it.

### Step 1 of 10 — AT A GLANCE  *(landing)*

```
╔═════════════════════════════════════════════════════════════╗
║  THE BRIEF                                                  ║
║  Mon 27 Apr 2026  ·  06:30 IST                              ║
║                                                             ║
║  30 articles  ·  5 govt orders  ·  6 newspaper clippings    ║
║  12 social signals  ·  3 video clips                        ║
║                                                             ║
║  Confidence: ON THE RECORD · 81%        [Refresh] [History] ║
╚═════════════════════════════════════════════════════════════╝

The Hyderabad Metro takeover dominates today's intelligence picture
— IRFC has sanctioned a ₹13,615 cr loan and new board members take
office 1 May 〔Article〕. The SEEEPC caste-survey results have drawn
sharp opposition criticism, with the BRS dismissing methodology in
Telugu Telegram channels and Mana Telangana print 〔Social ▸ Paper〕.
A nationwide heatwave alert is intensifying — 95 of the world's 100
hottest cities are in India — but no GHMC heat-action protocol has
been issued 〔Article ▸ Govt absence〕.

What needs your attention today
  ▲ Tue 28 Apr — HC counter due (MLA disqualification)
  ▲ Fri 1 May  — New Metro board takes office

                                 Continue ▶  to the Day's Movers
```

Three flowing sentences. Inline `〔…〕` pills on the right of each
clause name the evidence pillars; click any pill → tooltip with the
strongest snippet. The "What needs your attention" mini-list is
extracted from § 10 (Decision Queue) and shown here so the official
gets the day's actions before scrolling further.

The Continue button is the only forward affordance on this screen —
keeps cognitive load minimal.

### Step 2 of 10 — THE DAY'S MOVERS

5-7 cards in a single column. Each card has the pillar pulse on a
narrow strip down the left side (vertical chips like a newspaper-
section bar), and the synthesis prose to the right.

```
┌──┬──────────────────────────────────────────────────────────┐
│📰│ ① HYDERABAD METRO TAKEOVER FINALISED                     │
│📄│                                                          │
│💬│ The Telangana government cleared the share-purchase      │
│  │ agreement with L&T and IRFC has sanctioned a ₹13,615 cr │
│  │ loan to fund the acquisition. Mana Telangana's 25-Apr   │
│  │ edition warns of cost-overrun risk citing Kaleshwaram   │
│  │ parallels. Telegram channels are amplifying toll-fare   │
│  │ anxiety from commuters.                                  │
│  │                                                          │
│  │ Articles 3 · Paper 1 · Social 2          ▾ See sources  │
└──┴──────────────────────────────────────────────────────────┘
```

The pulse strip is a quick visual indicator: more chips = more
corroborated story. Empty chips (greyed) = pillar has no evidence
for this story — also informative.

"See sources" expands a drawer below the card listing every cited
item (numbered article, paper edition + page, social post + URL,
etc.) with its individual snippet. No popover stack — explicit,
keyboard-navigable.

### Step 3 of 10 — PRIMARY SOURCES  *(what the State said)*

```
THE STATE'S OWN PAPER TRAIL                       5 documents today
─────────────────────────────────────────────────────────────

📄 GHMC                                            26 Apr · p.1
   Tender — User Charges & Penalties
   What it does: Schedule of revised parking and ground-water
   user charges across GHMC zones. Penalty multipliers for
   non-compliance with conservation byelaws.
                                                       Open PDF →

📄 GHMC                                            25 Apr
   Notification — Conservation works
   What it does: Authorises restoration of the old Zanana wall
   and Puranapoor Darwaja under the heritage conservation list.
                                                       Open PDF →

📄 Telangana High Court                            24 Apr
   Direction — GHHPC to act on Chiran Fort demolition
   in two weeks
                                                       Open order →
```

Each row is a real govt-doc record. The "What it does" line is the
LLM's 1-sentence summary using the existing `intel_json.what_it_does`
field. Empty list state explicitly says "No new orders or
notifications today" rather than disappearing — absence is a signal.

### Step 4 of 10 — THE PRINT PRESS

```
THE VERNACULAR DESK                            6 clippings today
─────────────────────────────────────────────────────────────

┌─────────────────────────────────┐ ┌─────────────────────────────────┐
│ MANA TELANGANA · Telugu · 25Apr │ │ MANAM · Telugu · 25 Apr · p.3   │
│                                 │ │                                 │
│ "ప్రభుత్వం అన్నీ గుడ్డిగా"    │ │ "ప్రజాభివృద్ధే లక్ష్యం"          │
│ chesthondhi                     │ │ Praja-abhivruddhe lakshyam      │
│                                 │ │                                 │
│ "The govt is doing everything   │ │ "People's development is the    │
│  blindly"                       │ │  goal"                          │
│                                 │ │                                 │
│ Mentions  KCR · KTR · Harish    │ │ Mentions  Revanth Reddy · CMO   │
│                                 │ │                                 │
│ Read full clipping →            │ │ Read full clipping →            │
└─────────────────────────────────┘ └─────────────────────────────────┘
```

Original headline + transliteration + translation, all visible
together. `lang="te"` / `lang="ur"` etc. on the original strings
so screen readers don't try to read Telugu as English. "Mentions"
chips are clickable filters — clicking "KCR" in the Mana Telangana
card scopes the brief to that entity for the rest of the
session.

### Step 5 of 10 — PUBLIC PULSE  *(live, refreshable)*

This screen has a small "Refresh now" affordance because volume bars
go stale. The base brief is a snapshot from 00:30 UTC; the user can
re-query Pulse + Silence as of *now*.

```
THE PUBLIC PULSE                          [↻ Refresh as of 06:31]

┌────────────────┐ ┌────────────────┐ ┌────────────────┐
│ REDDIT         │ │ TELEGRAM       │ │ TWITTER        │
│ ████████ 124   │ │ ████████ 692   │ │ ███      22    │
│ ▲ +43% / 7-day │ │ ▼ -8%  / 7-day │ │ ▼ -12% / 7-day │
│                │ │                │ │                │
│ Sentiment ▼    │ │ Sentiment ▼    │ │ Sentiment —    │
│                │ │                │ │                │
│ Top topic:     │ │ Top topic:     │ │ Top topic:     │
│ Caste survey   │ │ BRS criticism  │ │ Metro fares    │
│ ratings        │ │ of CM Revanth  │ │                │
│                │ │                │ │                │
│ Sample post:   │ │ Sample post:   │ │ Sample post:   │
│ "12 lakh opted │ │ "BRS dead body │ │ "Metro toll    │
│  for No Caste, │ │ … new party in │ │  hike inevit-  │
│  system is a   │ │  state? — CM   │ │  able after    │
│  joke"         │ │  Revanth"      │ │  ₹13k cr loan" │
│                │ │                │ │                │
│ Open Signal →  │ │ Open Signal →  │ │ Open Signal →  │
└────────────────┘ └────────────────┘ └────────────────┘
```

Volume bars use `<meter>` for screen readers. Sentiment arrows use
both colour AND glyph (▲ ▼ —) so colourblind users get the same
information. "Open Signal Room" hand-off goes to the existing
`/signals` page filtered by platform.

### Step 6 of 10 — ON THE WIRES  *(video clips)*

```
NEWS CHANNEL EVIDENCE                              3 clips today
─────────────────────────────────────────────────────────────

▶ V6 NEWS · LIVE · 0:34
  "BRS dead body. What's the use of a new party in the state?"
                                  — CM Revanth Reddy on KCR
  Entity tag: K. Chandrashekar Rao
                                                Watch from 0:34 →

▶ DD NEWS TELANGANA · 6:12
  "Digital Health Cards for All — Minister announcement"
  Entity tag: Damodar Rajanarasimha
                                                Watch from 6:12 →

▶ Siasat TV · 3:20
  "Telangana govt lifts transfer ban, issues guidelines for
   moving employees"
  Entity tag: Telangana Government
                                                Watch from 3:20 →
```

Each clip has a quoted line from the transcript (already translated),
the matched entity, and a deep-link that jumps the embedded player to
the timestamp. Player is lazy-loaded only when the user opens it —
saves bandwidth on the morning load.

### Step 7 of 10 — ENTITIES TODAY  *(per-person dossiers)*

A grid of cards, one per monitored entity that received coverage
today. Sorted by total mention count.

```
┌──────────────────────────────────────────────────────────────┐
│ A. REVANTH REDDY                                  CM · INC   │
│                                                              │
│ Today: announced the Hyderabad Metro takeover share-         │
│ purchase pact and confronted KCR over BRS rebuilding         │
│ rumours.                                                     │
│                                                              │
│ 📰 6  📄 2  💬 4  📺 1            Sentiment ▲ +0.12          │
│                                                              │
│ Most-cited quote (Telugu, translated):                       │
│ "BRS is a dead body — what's the use of a new party?"        │
│                                                              │
│ Open dossier →                                               │
└──────────────────────────────────────────────────────────────┘
```

Each pillar count is a clickable chip that filters the entity
dossier to that pillar. "Sentiment" is computed across all today's
mentions, weighted toward social where sentiment is most measurable.

### Step 8 of 10 — SIGNALS TO WATCH  *(forward-looking, social-led)*

The hardest section conceptually. Each signal names its **trajectory**
and a **threshold** for when the user should re-engage.

```
SIGNALS — WHAT'S MOVING UNDER THE SURFACE

⚑ Caste-survey backlash is moving from Reddit (124 posts, +43%)
  to Telegram (38 posts, +21%). Print picked it up Apr 25 (Mana
  Telangana, Manam).
  Trajectory: 2-3 days from a TV-debate cycle.
  Threshold to re-check: 200+ Reddit posts OR appearance on
  three-or-more national English channels.

⚑ "Metro toll" sentiment cluster appearing on Twitter alongside
  the IRFC loan announcement. No press coverage yet. 22 posts in
  the last 12h.
  Trajectory: latent — needs an English-language verified handle
  to break out.
  Threshold: 60+ posts or one verified-handle post.

⚑ Maoist surrender (47 cadres) — coverage uniformly positive in
  English press, low engagement in social so far.
  Trajectory: government will likely seek a follow-up surrender
  cycle within 30 days.
  Threshold: any negative incident attributed to surrendered
  cadres, or any public-safety challenge in surrender districts.
```

Each signal is a small card with the same anatomy. Trajectory and
threshold are *required fields* — if the LLM can't propose one, the
signal isn't included.

### Step 9 of 10 — SILENCE MAP  *(coverage anomalies, refreshable)*

```
WHAT'S NOT BEING COVERED

SILENT TODAY (you usually see this)
  · Andhra Pradesh delimitation debate
    0 articles · 0 social vs 7-day avg of 8/day
    Last coverage: 25 Apr
                                                    Investigate →

  · Kaleshwaram CBI probe
    0 articles since 21 Apr
                                                    Investigate →

LOW vs BASELINE
  · Hyderabad police law-and-order
    2 articles vs avg 6 · 0 paper · 0 social
    Anomaly score: 0.74 (high)
                                                    Investigate →
```

Each "Investigate" link opens the relevant pillar room with a
pre-built filter (entity + last-30-days range). The silence detection
itself runs on the user's article-view history + an anomaly score
that compares today's coverage volume to the user's typical day.

### Step 10 of 10 — DECISION QUEUE  *(actionable)*

```
THIS WEEK'S DECISIONS                          5 items pending

Tue 28 Apr  Telangana HC: MLA disqualification counter due
            Source: Telangana Today, 16 Apr 2026
                                                  Open article →

Wed 29 Apr  GHMC notification window closes for old-monument
            conservation tender
            Source: GHMC notification, 25 Apr 2026
                                                  Open document →

Thu 30 Apr  Cabinet review of caste-survey reservations math
            Source: SEEEPC briefing, 17 Apr 2026
                                                  Open article →

Fri  1 May  New Hyderabad Metro board takes office
            Source: Telangana govt notification, 26 Apr 2026
                                                  Open article →
```

Each item links back to the primary source. The dates are extracted
from articles and govt docs by a small named-entity-recognition pass
on date phrases — date phrase + nearby verb ("hearing", "deadline",
"due", "takes office", "issued") → calendar item.

### Footer — SOURCE COVERAGE (always present)

A pillar-by-pillar count list with one-click jumps to each room.
Confidence-chip explainer is here too (distance histogram, retrieval
method, pillar coverage breakdown).

```
SOURCES USED TODAY
─────────────────────────────────────────────────────────────
📰 30 articles      from 18 publications        Coverage Room →
📄  5 govt orders   GHMC · Telangana HC         Document Room →
📰  6 clippings     2 newspapers (Telugu)       Newspaper Room →
💬 12 signals       Reddit · Telegram · Twitter Signal Room →
📺  3 video clips   3 channels                  Clip Room →
```

---

## Live vs static — the hybrid model

| Component | Live or static |
|---|---|
| At a Glance prose | Static — generated at 00:30 UTC daily |
| Day's Movers cards | Static |
| Primary Sources | Static |
| Print Press | Static |
| **Public Pulse** | **Live — `↻ Refresh now` widget** |
| On The Wires | Static |
| Entities Today | Static |
| Signals to Watch | Static |
| **Silence Map** | **Live — refreshable** |
| Decision Queue | Static |

Reasoning: prose generation costs LLM tokens and benefits from a
single morning generation. But Pulse and Silence are the lead-
indicator surfaces — by mid-afternoon a 06:30 snapshot is stale.
The refresh widget re-runs only the SQL aggregations (no LLM), so
it's cheap and instant. User pays nothing extra.

---

## What this design refuses to do

- **No infinite scroll.** Step-through forces the user to make a
  decision after each section: continue, or jump elsewhere.
- **No tooltips that block content.** Popovers anchor below their
  trigger; never overlay paragraph text the user is reading.
- **No autoplay video.** Ever.
- **No pop-up modals.** Drawers slide in from the right; can be
  dismissed with `Esc` or a click outside.
- **No "AI confidence" without an explainer.** The confidence chip
  is interactive; click → see the breakdown.
- **No skeuomorphic newspaper textures.** Typography and layout do
  the work; no fake folds or fake page-curls.
- **No lossy compression of evidence.** Every chip is a real link to
  the underlying article / doc / post / clip. Nothing is summarised
  into oblivion.

---

## Implementation cost (rough order)

| Component | LOC | Notes |
|---|---:|---|
| Router multi-source fetch | ~80 | Reuses existing retrieve_relevant_* |
| Brief generator: 4 new section prompts | ~120 | Section by section |
| Volume / baseline aggregation (Pulse) | ~60 | SQL + small endpoint, no LLM |
| Silence Map anomaly scoring | ~80 | Compares today vs user 14-day avg |
| Decision Queue date extraction | ~50 | NER pass over articles + govt docs |
| Frontend: 10 step components | ~600 | One per section |
| Step-through navigation + a11y harness | ~150 | Side rail, sticky pulse, keyboard handlers |
| DB: extend `briefs` with per-pillar counts | ~30 | Migration |
| Refresh-now endpoints (Pulse, Silence) | ~80 | SQL only, very cheap |
| **Total** | **~1,250** | One focused 3-4 day build |

The retrieval primitives are already in `rag_engine.py` from the
Analyst work. The Brief just doesn't call them.
