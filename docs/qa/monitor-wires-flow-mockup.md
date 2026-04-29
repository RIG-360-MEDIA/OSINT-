# Top of the Wires — Flowing / Live / Critical (mockup)

> Replacement for the static 5-card highlights row. Two-pane: an
> auto-rotating "story of the moment" card on the left, a live desk
> summary on the right.

---

## Layout (full-width, on top of the shelves)

```
┌─────────────────────────────────────────────────────────────────────┐
│ TOP OF THE WIRES · live                              ●LIVE  03:14 │
├──────────────────────────────────┬──────────────────────────────────┤
│ STORY OF THE MOMENT (2/3)        │ DESK SUMMARY (1/3)               │
│                                  │                                  │
│ № 01   ●CRITICAL                 │ The morning's wires are          │
│                                  │ dominated by the Telangana       │
│ Caste-survey backlash spreading  │ caste-survey backlash, moving    │
│ from Reddit (124 posts, +43% vs  │ from Reddit chatter into         │
│ baseline) to vernacular print    │ vernacular print and headed for  │
│ (Mana Telangana, p.9). Cabinet   │ cabinet review on 30 Apr.        │
│ review scheduled 30 Apr.         │ Heatwave alert remains the       │
│                                  │ silent pressure point — 95 of    │
│ Articles 3 · Paper 1 · Social 2 │ world's 100 hottest cities are   │
│ Filed 12 min ago                 │ in India, including several in   │
│                                  │ Telangana, but no GHMC heat-    │
│ ◀  ●●●●●  ▶                      │ action protocol has been issued. │
│                                  │                                  │
└──────────────────────────────────┴──────────────────────────────────┘
            8-second auto-advance (paused on hover)
```

---

## Left pane — Story-of-the-Moment card

A larger card showing ONE top story at a time, much richer than the
five small static cards. Auto-rotates through the top 5 every **8 seconds**;
pauses on hover; ◀ ▶ keys or dot-pagination to jump.

Each card shows:

- **№ 01–05** (newsroom rank numeral, italicised serif)
- **Criticality pill**: `●CRITICAL` / `●WATCH` / `●QUIET` — color-coded
  oxblood / gold / slate. Computed deterministically (see below).
- **Synthesis prose** — 2–3 sentences combining what each pillar said
  about this story, NOT just the headline. Built client-side from the
  pillar evidence already fetched (no LLM round-trip per card).
- **Source-mix ribbon**: e.g. `Articles 3 · Paper 1 · Social 2` so the
  reader sees at a glance how cross-corroborated the story is.
- **Filed Xm ago** — recency stamp.
- **Click** → opens the dominant pillar's room scoped to this story.

Transition between cards: subtle 200ms slide-fade. New cards arriving
slot in with a brief glow on the LIVE indicator.

### Criticality scoring (rule-based, instant)

```
score = 0.30 × pillar_diversity      // 1 pillar = 0.2, 4+ pillars = 1.0
      + 0.25 × recency               // <1h = 1, <6h = 0.6, <24h = 0.3
      + 0.20 × volume_spike          // posts/articles vs 7-day baseline
      + 0.15 × max_tier              // T1 article present = 1, else 0.5
      + 0.10 × sentiment_extremity   // |sentiment| → magnitude
```

Mapping:
- `score ≥ 0.75` → **CRITICAL** (oxblood pill, story has wide
  cross-pillar corroboration AND recent AND volume spike)
- `0.45–0.75` → **WATCH** (gold pill)
- `< 0.45` → **QUIET** (slate pill)

No LLM. Computed on every poll from the data we already have.

---

## Right pane — Live Desk Summary

A 4-6 sentence flowing prose panel. Sources:
1. **First sentence**: pulled from `/api/brief/today` SITUATION STATUS
   (today's LLM-generated synthesis — already cached in DB).
2. **Subsequent sentences**: dynamically appended based on what's
   happening in the live shelves — "X new social posts on caste survey
   in last hour", "GHMC heat-action plan still absent from primary
   sources today", etc. These are template-filled, no LLM.

Critical numerical signals are highlighted inline:
- `+43%` (volume spike) → oxblood weight
- `0 today` (absence) → gold italic
- timestamps → underline on hover

Updates every 60s when the poll cycle runs. Smooth fade-in for new
sentences; oldest sentence at bottom fades out as new ones arrive at
top — gives a "ticker" feel without being noisy.

---

## "Flowing" mechanics — three layers of motion

1. **Card auto-rotation** (8s per story, 5 stories cycle)
2. **Summary sentence cycling** (1 new sentence every 60s, oldest fades)
3. **LIVE indicator pulse** (subtle 2.2s pulse, brightens briefly on
   each successful poll)

All three respect `prefers-reduced-motion`. No autoplay video, no
distracting strobe, no marquee scroll.

---

## What this replaces / why

The current 5-card row is **static, equal-weight, no synthesis**. A
reader scans 5 headlines and gets no sense of:
- Which story matters most right now
- Whether a story is corroborated across pillars
- What the day's overall pressure-level is

This redesign adds three things the current row lacks:
- **Criticality ranking** — explicit visual hierarchy
- **Cross-pillar synthesis per story** — not just a headline
- **Live motion** — the dashboard feels like a wire desk, not a frozen
  morning paper

---

## Implementation cost

- `WiresMomentCard.tsx` (auto-rotating card + criticality scorer): ~180 LOC
- `WiresDeskSummary.tsx` (live prose with templated sentence cycling): ~140 LOC
- Replace `HighlightsBand.tsx` with a 2-pane layout that hosts both: ~80 LOC
- CSS keyframes for the slide-fade + pulse: ~40 LOC

**Total: ~440 LOC. ~1 day focused build.** No backend changes — uses
the same 5 pillar feeds + `/api/brief/today` we already poll.

---

## Stretch (post-demo)

- Click a criticality pill → opens a small panel showing why this story
  scored CRITICAL (the rule breakdown — cross-pillar count, +volume,
  recency).
- "Pin" a story to keep it in view — useful when an investor asks
  "tell me more about that one".
