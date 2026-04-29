# Brief Page — Monitoring Mode (companion to Intelligence Mode)

> Concept sketch. Not built yet. Sibling of `brief-redesign-mockup.md`
> (Intelligence Mode = the existing 10-step wizard).

---

## The shape of the experience

The Brief page becomes **bi-modal**, with a header toggle just like
day/night mode:

```
[ INTELLIGENCE  •  MONITORING ]   ☼/☾
   synthesis        live feed
```

- **Intelligence** = the 10-step wizard we already built — synthesis, prose,
  cited multi-source analysis. The "what does it mean" view.
- **Monitoring** = a real-time feed of top tier-1 / tier-2 items across
  five pillars. The "what's coming in right now" view.

The toggle is a sliding pill (matches day/night affordance). State
persists in `localStorage` so a user who lives in Monitoring stays there
between visits.

---

## Monitoring layout — top to bottom

### Header band (sticky, shared with Intelligence Mode)

```
┌──────────────────────────────────────────────────────────────────┐
│ THE BRIEF                Mon 27 Apr · 06:30  [Intel ● Monitor] ☼ │
│ ────────                                                         │
│  ●LIVE   12 new since you opened   30 art  4 doc  10 soc  …      │
└──────────────────────────────────────────────────────────────────┘
```

A **pulsing green dot + "LIVE"** label in the top-left tells the user
the page is updating. A "X new since you opened" counter sits to its
right; clicking it scrolls back to top and fades the new cards in.

### Top Highlights row — the 5 hero cards (above the fold)

A single row of 5 hero cards, equal width, edge-to-edge. These are the
**five highest-scoring items across ALL pillars** for the day, not five
items from any one pillar. So you might see: article, newspaper,
govt-doc, social, video — or all articles if articles dominate today.

```
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│ ●NEW   │ │        │ │        │ │ ●NEW   │ │        │
│ ARTICLE│ │ GOVT   │ │ PAPER  │ │ SOCIAL │ │ VIDEO  │
│        │ │        │ │        │ │        │ │        │
│ Metro  │ │ GHMC   │ │ Mana   │ │ V6 LIVE│ │ KCR-   │
│ takeov │ │ Tender │ │ Telang │ │ "BRS   │ │ Revanth│
│ ₹13615 │ │ Charges│ │ KCR    │ │  dead  │ │ stand- │
│ cr loan│ │ p.1    │ │ warned │ │  body" │ │ off    │
│        │ │        │ │        │ │        │ │        │
│ T1·06:12│ │ T1·05:48│ │ T1·05:22│ │ T1·06:05│ │ T1·05:30│
└────────┘ └────────┘ └────────┘ └────────┘ └────────┘
```

Each card has a **vertical color strip on the left** (pillar color), a
small **`●NEW`** badge if it landed in the last 60 minutes, and a
**tier chip + filed-time** at the bottom. Click → opens the relevant
pillar room scoped to that item.

### The five pillar feeds

Below the highlights row, **five sections**, each a horizontal-scroll
strip of cards (think "shelf" — like Netflix rows). One pillar each.
Order is by user value, not alphabetical:

  1. **Articles** — RSS / web reporting (the biggest river)
  2. **Newspaper editions** — vernacular print clippings (Telugu / Urdu)
  3. **Social signals** — Reddit · Telegram · Twitter
  4. **Video clips** — YouTube transcripts
  5. **Govt documents** — orders, tenders, notifications

Each section has the same anatomy:

```
┌──────────────────────────────────────────────────────────────────┐
│ § ARTICLES        ● 3 new in last hour              View all → │
│                                                                  │
│   ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐  →     │
│   │ T1     │ │ T1·NEW │ │ T1     │ │ T2     │ │ T2     │        │
│   │ Metro  │ │ Caste  │ │ TGRTC  │ │ Heat   │ │ Maoist │        │
│   │ takeov │ │ survey │ │ strike │ │ alert  │ │ surren │        │
│   │ ₹13615 │ │ 12 lak │ │ enters │ │ India  │ │ 47 cad │        │
│   │  · BL  │ │ · TT   │ │ · HBL  │ │ · NDTV │ │ · Hindu│        │
│   └────────┘ └────────┘ └────────┘ └────────┘ └────────┘        │
└──────────────────────────────────────────────────────────────────┘
```

Card anatomy (consistent across all five sections):
- Pillar-colored top border (4px)
- **Tier chip** top-left (T1 / T2 only — tier 3 hidden by design)
- **`●NEW`** badge if landed in last 60 minutes
- Headline (display serif, 2-3 lines, truncated with ellipsis)
- Source name (small caps sans-serif)
- Time-ago (e.g. "12 min ago", "2 h ago")
- Hover → shows a 200ms popover with snippet + CTA chip
- Click → opens the relevant pillar room scoped to that item

**Section header anatomy:**
- Pillar icon + section name (display serif)
- Live count badge: `● 3 new in last hour` — the dot pulses subtly
- "View all →" link to the relevant pillar room (Coverage, Newspaper,
  Signal, Clip, Document)

### Empty / quiet states

Each section has graceful empty states, **never just whitespace**:

- *No new items in last 24h:* small italic note "Quiet hour — last
  update 4h ago" with a "Check back" timer.
- *Pillar is between collection cycles:* "Next sync in 12 min" hint.

Absence is itself a signal — the dashboard says so explicitly.

---

## Real-time mechanism

Three options, in increasing complexity:

| Mechanism | Effort | Latency | Trade-off |
|---|---|---|---|
| **30-second polling** | lowest | 30s avg | Simplest. Good enough for a daily-brief surface. |
| **Server-sent events** | medium | <1s | One-way push from server. Fine for read-only feeds. |
| **WebSocket** | high | <1s | Overkill — we don't need bidirectional. |

**Recommendation: polling.** The user is checking "what came in" once
every few minutes, not watching a live stream. Polling at 30s with
diff-based card insertion is plenty.

A single aggregated endpoint:
`GET /api/brief/monitor/feed?since=<timestamp>&geo=<…>`
Returns 5 arrays of cards (one per pillar) plus the 5 hero highlights,
filtered to T1/T2 and the user's geo / entity profile. The client diffs
against its current state and animates new items in.

---

## Visual language carry-over

All five pillar colors, typography, and chip patterns from the
Intelligence Mode redesign carry over. **The same component library
serves both modes** — that's what makes the toggle feel native. Side-
by-side, the brief feels like one product with two lenses.

---

## A11y notes

- Toggle is `<button role="switch" aria-checked="true|false">` with
  `aria-label="Switch between Intelligence and Monitoring views"`.
- Live region: the "X new since you opened" counter is `aria-live="polite"`
  so screen readers announce updates without interrupting reading.
- New-card animation respects `prefers-reduced-motion`.
- Each card is a real `<a>` so keyboard tab order = visual order.
- Time-ago text is rendered server-side; never relies on JS-only.

---

## Refused / deferred

- **No autoplay video** in monitoring cards (matches Intelligence rule).
- **No infinite scroll** — each shelf is bounded (top 8-12 cards), then
  "View all →" hands off to the pillar room.
- **No notification sound** by default — opt-in only via the user's
  profile preferences.
- **Tier 3 deliberately hidden** from monitoring per requirement; it
  remains available in the pillar rooms but not in this dashboard.

---

## Implementation order (when you give the go-ahead)

1. Mode toggle component + localStorage persistence (~80 LOC)
2. `/api/brief/monitor/feed` aggregator endpoint (~120 LOC)
3. `MonitoringDashboard.tsx` — hero row + 5 shelves (~500 LOC)
4. Live-update polling hook with diff-based card insertion (~80 LOC)
5. Empty / quiet state components (~60 LOC)
6. Wire toggle into existing `BriefWizard` so users can flip back (~30 LOC)

**Total: ~870 LOC, ~2-3 day focused build.** Reuses the entire pillar
palette and card patterns from Intelligence Mode.
