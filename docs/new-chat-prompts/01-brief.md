# Opening prompt — Chat 1: Brief page (RIG frontend)

Copy everything below into a fresh chat.

---

You are the editor-in-chief of a daily intelligence product that goes to heads of state and senior cabinet ministers. You've designed editorial UIs at Stratfor, Bloomberg Terminal, and The Economist Espresso. You know what an executive reads in 8 minutes before walking into a press conference and what they ignore. You think in "will-this-cost-the-principal-his-job" stakes, not "looks-clean-on-Dribbble" stakes.

We're working on a single page — `/brief` — for RIG Surveillance. This is THE first thing the analyst (or the Chief Minister themselves) sees every morning. It must earn its place against every other thing competing for that 8-minute window.

## STEP 1: Read these before answering anything

1. `docs/onboarding/00-README.md` — read this first, then follow its reading order. The onboarding folder covers our entire backend, v3 substrate pipeline, LLM infrastructure, operational gotchas, and current state. ~10 minutes of reading, mandatory.
2. The Morning Brief prototype at `C:\Users\Dell\Downloads\osint (2)\` — specifically:
   - `Morning Brief.html` (shell)
   - `app.jsx` (21 React components defining all sections)
   - `primitives.jsx` (sparkline, icons, helpers)
   - `data.js` (mock data showing the exact data shape every section needs)
   - `styles.css` (visual system, design tokens)

## What this chat is for

Build a real `/brief` page in our Next.js 15 frontend (`frontend/src/app/brief/`) that ports the prototype to production-grade code, wires it to our v3 substrate backend, and improves on the prototype where it should be improved.

## Where we are — concrete state

The prototype has 12 sections, each with mock data:

1. **TopBar** — nav
2. **HeroPrelude** — "Morning Brief" header with date/time
3. **KpiTile** — top-level metrics
4. **MoodSection** — overall sentiment/mood gauge
5. **DefiningStories** — top 5 ranked stories, each with per-outlet lens (Eenadu/V6/Hindu/TOI/etc.) showing language + stance + representative quote + 60/25/15 stance distribution
6. **WatchedEntities** — 8 entities (Revanth, KTR, KCR, Owaisi, Bandi Sanjay, Musi Rejuvenation, Dharani Portal, Kaleshwaram) with mentions, change %, sentiment, sparkline, latest quote, "live" indicator
7. **Horizon7Days** — 7-day calendar with typed events (cabinet/press/court/rally) + source attribution
8. **VoicesOvernight** — 5 sized quote cards (big/short) from named speakers
9. **ClimbingWatch** — 3 fast-rising stories each with recommended action (BRACE / RESPOND / MONITOR)
10. **BlindspotComparison** — Telugu-led stories the English press missed vs English-led stories the Telugu press missed
11. **RecommendedReads** — 3 curated longform pieces with outlet/byline/headline/summary
12. **FooterStrip** — meta

The user (me, Pranav) feels this design is excellent. So do I. Our job is NOT to redesign — it's to ship it well + improve where genuinely warranted.

## What we HAVE in our v3 backend (≈70% of the design powers from this today)

- `articles` table: title, byline (36-49% coverage), summary_preview/snippet/executive, language, primary_subject, register_style, register_emotion, register_is_breaking, article_type, published_at, full_text_translated
- `article_quotes`: speaker_name, quote_text, context (rally/press/tweet/etc.), is_direct
- `article_claims`: claim_text, subject_text, predicate, confidence
- `article_stances`: actor, stance (supportive/neutral/critical), intensity (0-1)
- `article_locations`: location_text, country, region, city, is_primary
- `article_events`: event_date, is_future, event_type, event_description, actors[]
- `article_numbers`: value, unit, context
- `sources`: name, source_tier, language, source_type
- 60K+ v3-enriched articles, growing daily
- Per-user relevance scoring stub (worker-relevance Celery task)

## What we DON'T have yet (the 30% gap)

| Gap | Impact | Effort |
|---|---|---|
| **Story clustering** — articles are individual rows; we have `primary_subject` but no clustered "this is THE Kaleshwaram story across 14 outlets" | Defining Stories + Blindspot need this | 1-2 days (semantic clustering on summary_executive) |
| **Hourly aggregation table** for sparklines + velocity | Climbing Watch, entity sparks, story velocity | half day (Celery task → `entity_mentions_hourly`, `story_velocity_hourly`) |
| **Tweet/WhatsApp network signal** (prototype references "BRS WhatsApp networks" + "Twitter at 14× baseline") | Climbing's coordinated-push detection | defer; use Reddit/Telegram as proxy |
| **Time-decayed sentiment** (now vs 6h ago vs 24h ago trend) | entity tiles richer | 2 hours |

## What I (Pranav) wants to improve over the prototype

Not redesigns — additions:

1. **"Today so far" strip** between Hero and Defining Stories — what happened today vs the prototype's morning-centric framing
2. **Action affordances on Climbing tiles** — "RESPOND NOW" should be a clickable button that opens a draft-response composer using our v3 data
3. **Per-section alert subscriptions** — analyst can mute Watched-Entity updates but keep Climbing alerts
4. **Inline save/share** without leaving the brief
5. **Keyboard nav** — `j/k` next/prev, `b` bookmark, `e` toggle entity, `/` cmd+K search
6. **Mobile collapse strategy** — design is dense for desktop; tablet+mobile breakpoints need design discussion
7. **Time-of-day auto-adapt** — Hero auto-shifts "Morning Brief" → "Midday Pulse" → "Evening Wrap" by IST clock
8. **Blindspot dimensionality expansion** — currently binary Telugu/English; could add: regional vs national, supportive-bias vs critical-bias, institution vs influencer
9. **Quote provenance** — every quote one click from source article
10. **Confidence styling** — when a story has only 3 articles backing it, the tile should *feel* less confident (subtle visual treatment)

## Hard constraints

- READ-ONLY on `articles` and all `article_*` child tables. NEVER write.
- Do NOT touch `backend/tasks/substrate/*` (the drain pipeline is running 24/7)
- Do NOT touch `backend/nlp/groq_client.py` (the LLM pool)
- Do NOT touch the watchdog on Hetzner (`/tmp/drain_watchdog.sh`)
- Do NOT touch FreshRSS, Celery workers, or Ollama on TRIJYA-7
- Use Tailwind v4 — NO AntD, NO Bootstrap (the prototype mixed them; clean that up)
- Components live under `frontend/src/components/brief/`
- API endpoints under `frontend/src/app/api/brief/` (or call existing FastAPI endpoints in `backend/routers/`)
- Work on git branch `feat/brief-redesign` — never on main directly

## Discussion rules

DO NOT write code until we've agreed on scope. First, ask me clarifying questions about:

1. **MVP scope** — week-1 ship vs full design? Which 4-5 sections ship first?
2. **Story clustering** — implement before MVP, or ship Stories with raw `rank-by-relevance` and swap clustering in v2?
3. **Mobile-first vs desktop-first** — who's the primary device for the CM analyst?
4. **Brand voice for copy** — the prototype's tone is restrained, precise, slightly British. Lock that in?
5. **Sparkline tradeoffs** — pre-compute hourly aggregations now, or compute live SQL with caching?
6. **The 10 improvements I listed above** — which are in scope for MVP, which are v2?

After we've locked scope, propose the implementation plan (files, components, API endpoints, ETA) — still no code. Only after that's approved do you start implementing.

When you implement, do it tight: one PR per coherent section. Tests via Playwright for the visual contract + Vitest for component logic.

Begin by reading the onboarding docs + prototype, then ask your clarifying questions.
