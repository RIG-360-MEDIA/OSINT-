# RIG News — Product Requirements Document (v1)

> **Investor-demo build.** Frontend-only webapp with hardcoded backend. Showcases the full vision of a personalized, multi-format news platform. Built to look like a real shipped product, not an AI demo.

---

## 1. Product Overview

**RIG News** is a personalized news webapp where every story can be consumed in 6 distinct visual formats, each inspired by a top-tier news/publishing site. Readers pick their interests once and get a custom feed; each story can be toggled between formats (Quick Read, Full Story, All Sides, Timeline, Quotes, By the Numbers).

This v1 is a fully-polished frontend demo, built for investor pitching. Backend is hardcoded — 50+ stories live as JSON files with all 6 format variants pre-generated. Auth is stubbed. The app looks and feels like a real shipped product.

---

## 2. Vision

**Thesis:** Different readers want different formats; different stories deserve different formats. Today's news sites force ONE format on every reader and every story. RIG News lets the reader choose, and lets the story evolve over time with new formats unlocking as it matures.

**Target users (demo):**
- Personalized B2C reader — picks interests (India politics, finance, sports, tech, world, etc.), picks default reading format, consumes a custom feed.
- Investor — can navigate the full app end-to-end and feel a real, defensible product.

**Differentiation (for investor pitch):**
- Multi-format presentation per story (industry-first)
- Bias-comparison across language presses (Telugu / Hindi / English) visible in All Sides tab
- Living Story pages that grow as news evolves (Day-of-story counter visible)
- Polished design that doesn't smell of AI

---

## 3. Brand Identity — Faithful Clones (Option B)

**Approach:** Each format tab is a near-pixel clone of its inspiration site. Click into "Quick Read" and you LITERALLY feel teleported to Inshorts. Click "Full Story" and it feels like Medium. The dopamine hit per tab > brand cohesion. The only persistent RIG News element on a story page is a thin **format-switcher strip** at the very top.

### House style (non-story pages)

For pages that aren't story views — marketing homepage, sign-up flow, app homepage, topics, search, following, settings, profile — we need a "house style" distinct from any of the 6 clones:

- **Aesthetic:** Apple News × Flipboard magazine-feel × Linear sharpness
- **Typography:** Inter for UI, Charter / Source Serif for editorial moments
- **Palette (light):** cream `#F8F5F0` bg, charcoal `#0F1419` text, signal red `#E63946` accent
- **Palette (dark):** charcoal `#0F1419` bg, cream `#F8F5F0` text
- **Cards:** photo-heavy, large radii (16px), generous whitespace
- **Dark mode:** full support, default = system preference

### Format-switcher strip (the persistent connector)

A thin (40px desktop, 32px mobile) strip at the top of every story page. The ONLY brand element on a story page.

```
[RIG News]  Story title (truncated...)              [Quick Read | Full Story | All Sides | Timeline | Quotes | By the Numbers]   [☀/🌙]  [♥ Follow]
```

- Background: charcoal in light mode, even darker in dark mode
- "RIG News" wordmark on left → click returns to /app homepage
- Active format underlined + brighter color
- Available formats solid; unavailable formats greyed out
- Right side: dark mode toggle + follow-this-story heart
- Below this 40px strip: 100% inspiration-clone experience

### Clone fidelity per tab

| Tab | Inspiration | Clone fidelity |
|---|---|---|
| **Quick Read** | Inshorts.com | Red `#FF3535`, full-bleed image cards, vertical scroll-snap, big sans, "read more" red link, Inshorts-style header replaced with RIG-News-Quick Read wordmark in same position |
| **Full Story** | Medium.com | Medium's serif (Charter/Source Serif), narrow column, drop caps, reading-time meter, sticky-side claps/save bar, gray/black palette, Medium-style top nav (logo + search + bell + save) |
| **All Sides** | Ground.news | Bias spectrum bar visual, "Coverage Details" sidebar, source pills with circular logos, "Blindspot" panels, Ground-News-style top nav |
| **Timeline** | NYT "How It Happened" interactive features | NYT-style serif (GT Sectra / Tiempos open-alt), sticky date headers, big scrollytell sections, photo-anchored events, italic gray captions, NYT-style header |
| **Quotes** | Bloomberg.com + FT.com | Bloomberg orange/black palette, Bloomberg-style ticker top, FT-style cream bg variant, two-col quote grid, source-tier badges |
| **By the Numbers** | The Pudding + FT Vis | Pudding's playful sans (often bold/quirky), scroll-triggered chart animations, big-format numbers, bold contrasting palette |

**Critical rule:** Inside a tab, the experience is the clone. The 40px strip on top is the only RIG News presence. Switching tabs = jarring (intentionally).

---

## 4. Information Architecture

```
/                              Marketing homepage (logged out)
/auth/login                    Login (stubbed)
/auth/signup                   Sign-up step 1 (email/password)
/auth/signup/interests         Sign-up step 2 (pick topics)
/auth/signup/style             Sign-up step 3 (pick default format)
/app                           Personalized homepage (logged in)
/app/topics                    Topic browser (all topics)
/app/topics/[slug]             Single topic feed
/app/story/[slug]              Story page with 6 format tabs
/app/following                 Stories the user follows
/app/search                    Search
/app/settings                  Settings page
/app/profile                   Profile (stubbed)
```

---

## 5. Page-by-Page Specifications

### 5.1 Marketing homepage (`/`)

**Goal:** Convert visitor → sign-up. Investor-ready hero.

Layout:
- **Hero:** Brand tagline ("News, your way.") + animated headline rotator + primary CTA → Sign-up
- **Feature blocks (3):** one per representative format with mini-mockup screenshots
- **Sample story cards (3):** preview a fully-rendered story card
- **Why RIG News (3 points):** "Read it your way" / "See every side" / "Stories that evolve"
- **Footer**

### 5.2 Sign-up flow

**Step 1 (`/auth/signup`):**
- Email + password fields
- Google sign-in button (stub — any click logs you in as "Raj")
- Already a member? → Login

**Step 2 (`/auth/signup/interests`):**
- 32 topic tiles in a grid (India Politics, Telangana, Karnataka, US Politics, Finance, Crypto, Climate, Cricket, Football, Tech, AI, Defense, Health, Education, Energy, World Affairs, etc.)
- Pick minimum 3, maximum 8
- Tile = icon + label + sample headline preview on hover

**Step 3 (`/auth/signup/style`):**
- 6 format cards, each with:
  - Format name
  - One-line description
  - Mini-mockup preview (animated GIF or CSS animation)
- Pick 1 as default
- "You're in" → redirect to `/app`

### 5.3 App homepage (`/app`)

**Layout (top to bottom):**

1. **Top nav** (brand chrome — always visible)
2. **Hero strip:** 2-3 large cards (today's top stories in user's interests)
3. **"Today's quick reads"** — horizontal-scroll row of small Quick Read-style cards (fast hits)
4. **"For you"** — mixed feed of medium cards in user's interests
5. **"Evolving this week"** — older Stories that just got new updates (the unique selling point)
6. **"By topic"** — grouped by user's picked topics (4-5 cards per topic, "see all" link)
7. **Footer**

**Each story card shows:**
- Hero image (optional)
- Headline
- 2-line preview (Full Story intro)
- Badges: format availability dots, source count, day-of-story, "updated Nh ago"
- Hover: shows previews of available formats

### 5.4 Story page (`/app/story/[slug]`)

**Layout (faithful-clone mode):**
- **40px format-switcher strip** (sticky top, charcoal bg) — the ONLY RIG News brand element
  - Left: RIG News wordmark (click → /app)
  - Center: story title (truncated)
  - Right: 6 format buttons + dark toggle + follow heart
- **Below the strip: 100% inspiration-clone experience**
  - Active tab's full mini-site renders below
  - Each clone has its own header (visually authentic to inspiration), own typography, own colors, own footer
  - No brand chrome bleeding through — the clone owns the viewport below the 40px strip
- Default active tab = user's preferred format (override if not available for this story)
- Toggle between tabs = strip persists, body re-renders into a different clone

### 5.5 Topic page (`/app/topics/[slug]`)

- Topic header (name, description, count of stories, count of sources covering it)
- Filter chips: format availability, date range, story depth
- Card feed sorted by recency or relevance

### 5.6 Following page (`/app/following`)

- List of stories user follows
- Updated-since indicators ("3 new takes since you last read")
- Quick-mark-as-read button

### 5.7 Search page (`/app/search`)

- Search bar with autocomplete
- Results: stories matching query, opens in user's preferred format
- Filters: date, topic, format availability, source language

### 5.8 Settings page (`/app/settings`)

Sections:
- **Topics:** add/remove
- **Default reading format:** picker (6 options)
- **Languages for bias comparison:** checkbox list (English / Hindi / Telugu / Tamil / Marathi / etc.)
- **Dark mode:** Auto / Light / Dark
- **Notifications:** email digest day (Sun/Mon/Wed), push toggle
- **Account:** name, email (stubbed)
- **Subscription:** "Free" badge with "Upgrade" CTA (stubbed)

### 5.9 Profile page (`/app/profile`)

Stubbed — show "Raj Mehta" + stats (stories read this week, formats used most, topics most-followed).

---

## 6. Format Tab Specifications (Faithful Clones)

> Each tab below is a near-pixel clone of its inspiration site. Brand chrome is absent. Only the 40px format-switcher strip persists at the top.

### 6.0 Format-switcher strip (persistent across all tabs)

- 40px tall (32px mobile), sticky top of viewport
- Background: charcoal `#0F1419` (light mode) / `#0A0D11` (dark mode), white text
- Left: small "RIG News" wordmark (12px, geometric sans) → click returns to /app
- Center: story title (truncated with ellipsis on overflow)
- Right (in order):
  - 6 format buttons (Quick Read | Full Story | All Sides | Timeline | Quotes | By the Numbers)
  - Active button: brighter color + 2px bottom border in clone's primary color
  - Unavailable formats: 40% opacity, no hover
  - Vertical separator
  - Dark/light toggle (sun/moon icon)
  - Follow-this-story heart icon
- Animation: tab switch triggers fade-cross between clone bodies (~200ms)

### 6.1 Quick Read (Inshorts faithful clone)

**Goal:** 60-second consumption. Dopamine-hit. **Should feel indistinguishable from Inshorts at first glance.**

Clone elements:
- **Top header bar** (below 40px strip): mimics Inshorts header — "RIG News Quick Read" wordmark in Inshorts' red `#FF3535`, search icon, hamburger menu (non-functional for demo)
- **Card layout:** full-viewport-height cards, vertical scroll-snap (one card per screen on desktop, one per swipe on mobile)
- **Each card:**
  - Top 50% = full-bleed hero image
  - Bottom 50% = white background with:
    - Headline (28-32px, sans-serif heavy weight, Inter Display)
    - 60-word body in normal weight
    - Source attribution + timestamp ("Composed from 12 sources · 2h ago")
    - Red "Read full story →" link (opens Full Story tab via format strip)
- **Side arrows** (desktop) or swipe gestures (mobile) to move between cards
- **Color:** Inshorts red `#FF3535`, pure white bg, near-black text
- **Typography:** Inter Display / similar geometric sans
- **Mobile behaviour:** card-stack swipeable like the Inshorts app

Animation: card transitions are smooth slide-in from bottom, image parallax on scroll.

### 6.2 Full Story (Medium faithful clone)

**Goal:** Deep ~1500-word read. **Should feel indistinguishable from Medium.**

Clone elements:
- **Top header** (below 40px strip): mimics Medium nav — "RIG News" wordmark (Medium-style serif), search icon, notification bell, "Save" icon, profile avatar (stubbed)
- **Reading time meter:** "8 min read" at top of article in Medium's gray
- **Article layout:**
  - Narrow column (~680px max width, centered)
  - Headline: 42-48px serif (Source Serif Pro or Charter)
  - Subhead: 22-24px serif italic, lighter gray
  - Body: 20-21px serif, line-height 1.58, color `#292929` (Medium's text gray)
  - **Drop cap** on first letter (60px+ size, lifted into the column)
  - Pull-quotes: giant serif italic, centered, with vertical bar on left
  - Hyperlinks: green underline (Medium's signature)
  - Inline images with italic gray captions
- **Sticky left rail** (desktop): claps (heart) count, save bookmark, share icon — Medium's signature interaction
- **Author byline:** "Composed from 12 sources · May 18" with avatar (sources expand on click)
- **Bottom of article:** tag pills + "Recommended next" section in Medium's card style
- **Color palette:**
  - Light: white bg, near-black text, Medium green `#1A8917` for links
  - Dark: Medium's dark variant `#191919` bg, white text
- **Typography:** Source Serif Pro (or Charter) body; sans for nav

Animation: standard Medium scroll behavior, no fancy entrance animations.

### 6.3 All Sides (Ground News faithful clone)

**Goal:** Show same story framed differently. **Should feel indistinguishable from Ground.news.**

Clone elements:
- **Top header** (below 40px strip): mimics Ground News nav — "RIG News All Sides" wordmark in Ground's clean sans, search, "My News", profile (stubbed)
- **Article hero:**
  - Headline (32-36px, Inter, semi-bold)
  - **Bias bar visualization** under headline: horizontal stacked bar showing source distribution (Left blue / Center gray / Right red), with percentages
  - **Coverage Details strip:** "23 sources covering · 60% English / 25% Hindi / 15% Telugu · Bias: 35L / 30C / 35R"
- **Body layout (two-column on desktop, stacked on mobile):**
  - **Main column:** neutral story summary + numbered facts list
    - Each fact has tags: ✓ "All sides agree" / ⚠ "Contested" / ⊘ "Omitted by [side]"
  - **Right sidebar:** Coverage Details
    - Bias bar (vertical, sticky)
    - Language donut
    - Top sources list (logos + names + lean badges)
- **Three-panel section:** "What the Left says" / "What the Center says" / "What the Right says"
  - Each panel: colored top border (blue/gray/red), 2-3 sentence summary, "from N sources" footer
- **Blindspot panel** (Ground News' signature): "What the Left isn't covering" / "What the Right isn't covering" — distinct visual treatment
- **Per-source coverage cards:** small cards with source logo, name, lean pill, language tag, their headline for this story — clickable to expand
- **Language toggle:** tabs at top — English | Hindi | Telugu — switches per-source cards to that language's coverage
- **Color palette:**
  - Left: `#2563EB` blue
  - Center: `#6B7280` gray
  - Right: `#DC2626` red
  - Bg: white / near-black in dark mode
- **Typography:** Inter throughout (Ground News leans clinical/journalistic)

Animation: bias bar fills in on scroll-into-view; panel cards fade in staggered.

### 6.4 Timeline (NYT "How It Happened" faithful clone)

**Goal:** Show story unfolding chronologically. **Should feel indistinguishable from NYT's interactive long-form features.**

Clone elements:
- **Top header** (below 40px strip): NYT-style nav — "RIG News Timeline" in NYT's signature serif (Cheltenham/Imperial alternates), section links (none functional), "RIG-NEWS" all-caps date strip
- **Article opener (hero):**
  - Full-width hero image (cinematic, often dark)
  - Headline overlaid in white NYT-style display serif (48-60px)
  - Standfirst paragraph below in NYT's gray sans
  - Byline: "By RIG News Staff · Updated May 18, 2026"
- **Scrollytell timeline body:**
  - **Sticky date chips** at left edge of column as user scrolls — large white-on-charcoal date pills (DAY 1 / DAY 2 / etc.)
  - Each day-section: large date heading, 2-3 events
  - **Each event:**
    - Headline (24-28px serif)
    - Description paragraph (18px serif body)
    - Anchor image (full-width or right-aligned, with italic gray caption)
    - Source attribution at bottom (small gray)
  - Pull-quotes inline (giant serif italic, indented)
- **Optional map widget** (when geo data exists): right-rail sticky map showing event locations as you scroll
- **End-of-thread:** "As of [latest date]" + "Follow this story" CTA
- **Color palette:**
  - Light: white bg, near-black text, NYT-style gray captions
  - Dark mode variant: NYT's dark theme (`#121212` bg, white text)
  - Sepia variant available as a reading-mode toggle (warm cream bg)
- **Typography:**
  - Headlines: GT Sectra or Tiempos Headline (NYT Cheltenham alternative)
  - Body: Source Serif Pro
  - UI: Inter

Animation: parallax on hero image; date chips slide into sticky as you scroll past each day; images fade-in on enter-viewport.

### 6.5 Quotes (Bloomberg + FT faithful clone)

**Goal:** Foreground the people speaking. **Should feel indistinguishable from Bloomberg / FT.**

Clone elements:
- **Top header** (below 40px strip): Bloomberg-style — black bg, "RIG News Quotes" in Bloomberg's signature orange `#FF6600`, ticker-style scrolling story metadata below ("23 SOURCES · 47 QUOTES · UPDATED 2H AGO")
- **FT-style cream bg variant** as default (light mode): salmon-cream `#FFF1E5` (FT's pink-paper color), black text — instant FT recognition
- **Article hero:**
  - Headline in FT's Financier Display serif (32-40px, bold)
  - Subhead in gray sans
  - Author byline + timestamp Bloomberg-style
- **Quote grid layout:**
  - 2-col on desktop, 1-col on mobile
  - Each quote card:
    - Quote text in large serif italic (24-28px, FT Financier Display)
    - Decorative pull-quote mark before text
    - Speaker block below:
      - Circular photo (48px)
      - Speaker name (bold sans)
      - Role / title (gray sans)
      - Source publication + date (small gray)
    - Source-tier badge (gold/silver/bronze for tier 1/2/3 sources)
- **Counter-narrative section:** "Two views on [issue]" — two quotes side-by-side with colored top borders (green vs red, or blue vs orange depending on lens)
- **Filter chips** at top: "All quotes" / "Politicians" / "Experts" / "Critics" / "Officials"
- **Click quote → expanded modal** with full speech context, surrounding paragraph, source article link
- **Color palette:**
  - FT salmon-cream `#FFF1E5` bg
  - Bloomberg orange accent `#FF6600`
  - Black text
  - Dark mode: deep charcoal bg with FT-orange accent retained
- **Typography:**
  - Headlines + quotes: FT Financier Display (or GT Sectra Fine alternative)
  - Body: Inter
  - Numbers/ticker: Inter Mono

Animation: ticker scrolls continuously at top (CSS-only); quote cards stagger-fade on scroll; expanded modal has subtle zoom-in.

### 6.6 By the Numbers (The Pudding faithful clone)

**Goal:** Foreground the numbers, data-storytelling. **Should feel indistinguishable from The Pudding's scrollytell articles.**

Clone elements:
- **Top header** (below 40px strip): Pudding-style minimal — "RIG News By the Numbers" wordmark in a quirky display sans (something playful like Recoleta or DM Serif Display), tiny nav links
- **Hero section:**
  - Huge format number splash ("₹85,000 cr") — 200-400px size, bold, sometimes colored
  - Caption below in smaller sans explaining the number
  - Standfirst paragraph
- **Scrollytell body** (the Pudding signature):
  - **Sticky chart column** (left or right depending on section) — as user scrolls, the chart animates / changes to reflect the body narrative on the other side
  - Body column has narrative paragraphs that "drive" the visualization
  - **Examples:**
    - Section 1: Trend over time → sticky line chart fills in as user scrolls; body explains years 2022-2026
    - Section 2: Comparison across states → sticky bar chart with bars highlighting as user scrolls; body discusses each state
    - Section 3: Distribution / share → sticky donut animates segments as user scrolls
- **"Where this number came from" trace box:** stylized data-detective panel — first appearance date, originating source, propagation chain
- **"Who's disputing it" panel:** opposing claims with mini charts comparing each side's figure
- **Inline annotations:** small footnote-style references that highlight on hover (Pudding's signature)
- **Color palette:**
  - Bold contrasting: bright accent (yellow `#FACC15`, or pink `#EC4899`, or teal `#14B8A6`) — varies per chart
  - Off-white bg `#FAFAF7`
  - Black text
  - Dark mode: deep navy bg with bright accents retained
- **Typography:**
  - Headlines: DM Serif Display or Recoleta (quirky display)
  - Numbers: Inter Mono (big size) or DM Serif for hero numbers
  - Body: Inter
  - Captions: Inter Tight

Animation: scroll-triggered chart fills (`framer-motion useScroll`); number counters animate on enter-viewport; chart segments highlight in sync with text section currently in viewport.

---

## 7. Design System

### Typography

- **Brand chrome / UI:** Inter (or Söhne if licensed)
- **Full Story body:** Charter or Source Serif Pro
- **Quick Read headlines:** Inter Display (700-800 weight)
- **All Sides:** Inter (clinical)
- **Timeline headlines:** GT Sectra or Tiempos Headline
- **Quotes pull-quotes:** Playfair Display or Source Serif Pro
- **By the Numbers numbers:** Inter Mono / JetBrains Mono

### Color tokens

**Light mode:**
```
bg-primary:   #F8F5F0  (cream)
bg-secondary: #FFFFFF  (white)
text-primary: #0F1419  (charcoal)
text-secondary: #4A5560 (warm gray)
accent:       #E63946  (signal red)
border:       #E5E7EB
pulse-accent: #FB3640
compass-left: #2563EB
compass-center: #6B7280
compass-right: #DC2626
thread-bg:    #F5EFE6  (sepia)
```

**Dark mode:**
```
bg-primary:   #0F1419
bg-secondary: #1A1F26
text-primary: #F8F5F0
text-secondary: #9CA3AF
accent:       #FB3640
border:       #2D3640
pulse-accent: #FF4B5C
compass-left: #60A5FA
compass-center: #9CA3AF
compass-right: #F87171
thread-bg:    #1F1A14
```

### Spacing & radius

- 4px base unit (Tailwind defaults)
- Border radius: 8px standard cards, 16px hero cards, 999px pills
- Shadows: subtle multi-stop, dark-mode aware

---

## 8. Data Schema

Mock data lives in `/data/stories/*.json`. Each story:

```json
{
  "id": "story_001",
  "slug": "telangana-cabinet-reshuffle-may-2026",
  "title": "Telangana's cabinet reshuffle: power moves before 2027",
  "hero_image": "/images/story_001_hero.jpg",
  "topics": ["india-politics", "telangana"],
  "languages": ["en", "hi", "te"],
  "day_of_story": 7,
  "last_updated": "2026-05-18T10:00:00Z",
  "first_published": "2026-05-11T09:00:00Z",
  "source_count": 23,
  "sources": [
    {"name": "The Hindu", "tier": 1, "language": "en", "lean": "center"},
    {"name": "Eenadu", "tier": 1, "language": "te", "lean": "center"}
  ],
  "formats": {
    "pulse": {
      "headline": "Cabinet reshuffle: 5 ministers out, 3 newcomers in",
      "body_60_words": "...",
      "hero_image": "/images/story_001_pulse.jpg"
    },
    "long_read": {
      "headline": "...",
      "subhead": "...",
      "body_markdown": "...",
      "reading_time_min": 9,
      "pull_quotes": [{"text": "...", "speaker": "..."}],
      "citations": [{"para_id": 1, "sources": ["src_id_1", "src_id_2"]}]
    },
    "compass": {
      "bias_split": {"left": 0.35, "center": 0.30, "right": 0.35},
      "language_split": {"en": 0.60, "hi": 0.25, "te": 0.15},
      "agreed_facts": ["Five ministers dropped from cabinet"],
      "contested_facts": ["Whether KCR personally vetoed names"],
      "left_says": "...",
      "right_says": "...",
      "omitted_by_right": "...",
      "omitted_by_left": "...",
      "per_source": [
        {"name": "The Hindu", "lean": "center", "lang": "en", "headline": "..."}
      ]
    },
    "thread": {
      "events": [
        {
          "date": "2026-05-12",
          "description": "BRS leadership meeting at Pragathi Bhavan",
          "image": "/images/story_001_day1.jpg",
          "sources": ["src_id_1"]
        }
      ]
    },
    "voices": {
      "quotes": [
        {
          "text": "...",
          "speaker": "K.T. Rama Rao",
          "role": "BRS MLC",
          "photo": "/images/speakers/ktr.jpg",
          "source": "The Hindu",
          "date": "2026-05-14"
        }
      ]
    },
    "ledger": {
      "headline_number": {"value": "₹85,000 cr", "context": "outlay debated"},
      "trends": [{"label": "Year", "data": [2022, 2023, 2024, 2025, 2026], "values": [40000, 52000, 65000, 78000, 85000]}],
      "comparisons": [{"label": "Telangana", "value": 85000}, {"label": "Andhra Pradesh", "value": 72000}],
      "trace": [{"source": "The Hindu", "date": "2026-05-12", "first_appearance": true}],
      "disputed_by": [{"source": "Eenadu", "claim": "Actual figure is ₹72k cr"}]
    }
  }
}
```

**50+ stories** spread across topics: India politics, US politics, finance/markets, tech, climate, sports, world affairs, hyperlocal (Telangana/Karnataka/Mumbai).

Supporting data files:
- `/data/topics.json` — 32 topics with metadata
- `/data/sources.json` — source registry (name, tier, language, lean)
- `/data/users.json` — stub user (Raj Mehta)
- `/data/speakers.json` — speaker profiles for Quotes tab

---

## 9. Tech Stack

- **Framework:** Next.js 15 (app router, RSC where useful)
- **Language:** TypeScript strict mode
- **Styling:** Tailwind CSS + CSS modules for per-format theming
- **Components:** shadcn/ui as base; custom for format tabs
- **Animation:** Framer Motion
- **Charts:** Recharts + custom D3 for Timeline + By the Numbers
- **State:** Zustand for user prefs + localStorage persistence
- **Auth:** stubbed (localStorage user object)
- **Data loading:** JSON files imported at build time, with story-loader utility
- **Images:** local in `/public/images` (sample stock from Unsplash/Pexels with attribution)
- **Fonts:** Inter, Charter (or Source Serif), GT Sectra (or Tiempos open-alt), Inter Mono — via Next.js font loader
- **Dev:** `npm run dev`
- **Demo build:** `npm run build && npm start` for fully static investor demo

---

## 10. Folder Structure

```
rig-news/
├── app/
│   ├── (marketing)/
│   │   └── page.tsx                       # /
│   ├── auth/
│   │   ├── login/page.tsx
│   │   ├── signup/page.tsx
│   │   ├── signup/interests/page.tsx
│   │   └── signup/style/page.tsx
│   ├── app/
│   │   ├── layout.tsx                     # app shell with nav
│   │   ├── page.tsx                       # /app homepage
│   │   ├── topics/
│   │   │   ├── page.tsx
│   │   │   └── [slug]/page.tsx
│   │   ├── story/
│   │   │   └── [slug]/page.tsx
│   │   ├── following/page.tsx
│   │   ├── search/page.tsx
│   │   ├── settings/page.tsx
│   │   └── profile/page.tsx
│   └── layout.tsx                         # root layout
├── components/
│   ├── brand/
│   │   ├── logo.tsx
│   │   ├── top-nav.tsx
│   │   ├── footer.tsx
│   │   └── dark-toggle.tsx
│   ├── cards/
│   │   ├── story-card-hero.tsx
│   │   ├── story-card-medium.tsx
│   │   └── story-card-small.tsx
│   ├── formats/
│   │   ├── quick-read/                    # Inshorts-themed (Quick Read tab)
│   │   ├── full-story/                    # Medium-themed (Full Story tab)
│   │   ├── all-sides/                     # Ground News-themed (All Sides tab)
│   │   ├── timeline/                      # NYT-themed (Timeline tab)
│   │   ├── quotes/                        # Bloomberg-themed (Quotes tab)
│   │   └── numbers/                       # Pudding-themed (By the Numbers tab)
│   └── ui/                                # shadcn primitives
├── data/
│   ├── stories/                           # 50+ story JSONs
│   ├── topics.json
│   ├── sources.json
│   ├── speakers.json
│   └── users.json
├── lib/
│   ├── format-themes.ts                   # per-tab theme tokens
│   ├── story-loader.ts                    # load + parse story JSON
│   ├── auth-stub.ts                       # fake auth
│   └── user-store.ts                      # zustand store
├── public/
│   └── images/                            # hero images, speaker photos
├── styles/
│   ├── globals.css
│   └── format-themes.css                  # per-tab CSS overrides
├── tailwind.config.ts
├── tsconfig.json
├── package.json
└── README.md
```

---

## 11. Sprint Plan (14 days — extended for faithful clones)

**Sprint 0 — Day 1: Scaffold**
- Init Next.js 15 + TS + Tailwind + shadcn + Framer Motion + Recharts
- Folder structure
- House style design tokens (colors, typography, spacing)
- House style components: Top nav, Footer, Dark toggle, Story cards
- Tailwind config + globals.css

**Sprint 1 — Days 2-3: Data + Auth + Marketing/App shell**
- Mock data schema + 10 seed stories with all 6 format payloads
- Auth stub with localStorage user
- Marketing homepage (house style)
- Sign-up 3-step flow (email/Google → interests → default format)
- App homepage feed (house style: Apple News × Flipboard)

**Sprint 2 — Days 4-5: Story page shell + Quick Read clone**
- Story page wrapper
- **40px format-switcher strip** (the persistent connector)
- **Quick Read** = Inshorts faithful clone (red, full-bleed cards, scroll-snap, mini-site nav)

**Sprint 3 — Days 6-7: Full Story clone**
- **Full Story** = Medium faithful clone (Medium nav, serif, drop cap, narrow column, sticky claps rail, byline)
- Citations system

**Sprint 4 — Days 8-9: All Sides clone**
- **All Sides** = Ground News faithful clone (bias bar, Coverage Details sidebar, three-panel "what each side says", Blindspot panel, language toggle, per-source cards)

**Sprint 5 — Days 10-11: Timeline + Quotes clones**
- **Timeline** = NYT "How It Happened" clone (NYT serif, scrollytell, sticky date chips, hero image parallax, optional map)
- **Quotes** = Bloomberg/FT clone (FT salmon-cream bg, Bloomberg orange accents, ticker, quote grid, counter-narrative section)

**Sprint 6 — Days 12-13: By the Numbers clone + Other app pages**
- **By the Numbers** = Pudding clone (sticky scrollytell charts, hero number splash, animated counters)
- Topics page, Following page, Search page, Settings page, Profile page (all house style)

**Sprint 7 — Day 14: Polish + Demo prep**
- Mobile responsive pass (laptop-first, mobile graceful)
- Dark mode QA across all 6 clones + house style
- Fill 50 stories with full mock data
- Investor demo script walkthrough rehearsal
- Performance pass (image optimization, lazy-load clone tabs)

---

## 12. Investor Demo Script (5-7 min)

1. Land on marketing homepage → "Sign up free"
2. Walk through 3-step sign-up (interests → default format → done)
3. App homepage loads → "this is custom to me"
4. Tap a story → opens in Full Story (their chosen default)
5. **Toggle tabs in sequence:** Quick Read (60-sec hit) → All Sides (bias check) → Timeline (timeline) → Quotes (quotes) → By the Numbers (numbers)
6. Each tab is a polished, distinct experience — emphasize: SAME story, 6 ways
7. Show "Evolving this week" section → "stories grow over time"
8. Navigate to Finance topic → different story, same 6 formats
9. Settings → change default to Quick Read → back to feed → cards now open in Quick Read
10. Search "Adani" → results page
11. Toggle dark mode → "every tab respects it"
12. Close with: "This is the demo. Backend mocked. Real version uses RIG Surveillance's enriched corpus."

---

## 13. Out of Scope (v1) + Legal/IP Notes

**Out of scope:**
- Real backend / LLM generation pipeline (formats are pre-generated and frozen)
- Real user accounts / Stripe / payments
- Real auth (Google sign-in is stubbed)
- Comments / social features
- Native mobile app (responsive web only)
- Multi-language UI (English-only UI; multi-language CONTENT in All Sides is part of the mock data)
- Real push notifications (visual only)
- Analytics
- SEO / SSR optimization
- Accessibility audit (basic ARIA but not WCAG-AA certified)

**Legal/IP notes — IMPORTANT for post-investor-demo planning:**
- Faithful clones of Inshorts / Medium / Ground News / NYT / Bloomberg / FT / The Pudding are **gray-area design homage**. Acceptable for an internal investor demo (you're showing the vision, not shipping a public product).
- **For real public launch, we MUST dial back the most distinctive trademarked elements:**
  - Replace exact brand colors with adjacent palettes (e.g., FT salmon-cream → adjacent peach; Bloomberg orange → adjacent amber)
  - Replace inspiration logos / wordmarks with RIG News equivalents
  - Replace signature UI flourishes that may be design-patent protected (Medium's claps interaction, Ground News' specific bias bar visual, NYT's exact scrollytell patterns)
  - Maintain the *spirit* of each inspiration without copying defended-element visuals
- **Stock images** must be CC0 / Unsplash-licensed / Pexels-licensed with attribution as needed
- **Speaker photos** for Quotes tab: use placeholder silhouettes or licensed stock; do not scrape real politicians' photos without permission
- **All "Composed from N sources" attribution must include real source publication names** with proper editorial-fair-use treatment

---

## 14. Open questions

- **Brand name:** "RIG News" confirmed by user, but earlier statement was "RIG has nothing to do with this." Confirm before logo design.
- **House style preference:** I'm proposing "Apple News × Flipboard × Linear" for non-story pages. Veto/accept?
- **Stock images:** Unsplash / Pexels OK? Some news stories need contextual photos (politicians, events) — handle with placeholder + ALT text.
- **Speaker photos:** Use placeholder silhouettes vs. trying to source real photos?
- **Inshorts card-stack on desktop:** vertical scroll-snap (one card per screen) or horizontal swipe via arrow keys? Recommending scroll-snap.
- **Investor pitch deck:** Out of scope for this build, but the demo itself is the deck.

---

## 15. Change log

- **v1 (initial):** A+B hybrid (unified shell + themed interiors)
- **v1.1 (current):** Pivoted to Option B — pure faithful clones with 40px persistent format-switcher strip. Each tab = mini-site clone of its inspiration. Sprint extended 10 → 14 days. Legal/IP notes added.

---

*End of PRD v1.1. Awaiting "go" to scaffold the Next.js project.*
