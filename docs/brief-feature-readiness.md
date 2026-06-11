# `/brief` Frontend — Feature × Data-Readiness Audit

Based on the **Morning Brief** screenshot (RIG OSINT, dark theme, "Daily Intelligence Synthesis"). One-page reading-room aesthetic with rich inline citations and live header. Items below grouped by feature visible in the design, mapped to our backend data state.

Legend
- ✅  Data + endpoint ready — buildable today
- 🟡  Data ready, needs a small wiring task
- 🟠  Data ready, needs a NEW pipeline/task to compute
- 🔴  Data NOT ready yet — depends on T4/T9/T10 finishing
- ⚪  Out of scope / can't do without new external integration

---

## 1. Top navigation bar

| Sub-feature | Status | Notes |
|---|---|---|
| RIG OSINT logo / wordmark | ✅ | Static asset |
| **"Ask anything about today…"** search box | 🟠 | Needs a RAG/Analyst endpoint that retrieves over today's clean corpus. Vectors + embeddings ready (LaBSE), but no `/api/brief/ask` endpoint yet. |
| ⌘K keyboard shortcut | ✅ | Pure frontend |
| **Send Report** button | 🟠 | Needs PDF generation task (Celery) + delivery (email via SES/Resend or one-click download) |
| Download icon (top right) | 🟡 | Same PDF endpoint, no email step |
| Notification bell with red dot | 🟡 | We have `entity_mention_daily` + `user_watched_entities`; need a `user_notifications` write step (T7 design already exists) |
| User avatar (M) | ✅ | Supabase session — already wired in our middleware |

## 2. Status strip below header (the 4 readouts)

| Sub-feature | Status | Notes |
|---|---|---|
| **SYSTEM ONLINE · Source integrity 98.7%** | 🟠 | "Integrity %" needs an aggregate — e.g. (sources non-stalled / total sources) × (substrate_ok / total articles). Easy SQL. |
| **N SOURCES MONITORED + language list** | ✅ | `sources` table count + `language_detected` distinct values |
| **LAST UPDATED date/time** | ✅ | `brief_daily.computed_at` (needs that table — see §5) |
| **NEXT REFRESH IN · Refreshing…** | 🟠 | Polling or SSE; trivial frontend pattern; backend just returns next-cron timestamp |

## 3. Hero metric cards (4 cards with sparklines)

| Card | Status | Source query |
|---|---|---|
| **Articles Parsed (247)** | ✅ | `COUNT(*) FROM articles WHERE collected_at >= today_start AND substrate_status='ok'` |
| **Outlets (18)** | ✅ | `COUNT(DISTINCT source_id)` same window |
| **Languages (3) + per-lang counts** | ✅ | `GROUP BY language_detected` — we already do this in /observe |
| **Sentiment (−0.4 + arrow)** | 🟠 | We have `article_stances` with stance buckets (neutral/supportive/critical). Need a scalar: `(supportive − critical) / total`. New helper, ~30 lines. |
| **Sparklines on each card** (7-day trend) | 🟠 | Needs a `brief_metric_daily` table populated by the daily aggregator (T6 pattern). Trivial. |

## 4. Overnight Summary block (prose + entity links + citations)

| Sub-feature | Status | Notes |
|---|---|---|
| **LLM-generated prose summary** | 🔴 | We don't yet have a "today's brief" generation task. Needs a new Celery beat task that takes top-N stories + top quotes + top entities and asks an LLM to write 2-3 paragraphs. The DATA inputs are all ready; the WRITER step is the missing piece. |
| **Inline entity links** ("Musi Rejuvenation", "KTR", "Eenadu", etc.) | 🟡 | We have entity names in subject_text + speaker_name + actors[]. Just need a per-entity page (`/entity/{slug}`) that lists everything about that entity. Text-search query, no FK needed. |
| **Numbered citations [1] [2]** | 🟡 | Brief writer task emits citations referencing article IDs; frontend hyperlinks them to article-detail page. |
| **Source-tagged hyperlinks** (Eenadu, V6 News, Sakshi rendered as links) | ✅ | Already have sources table with stable IDs |

## 5. Quote of the Day block

| Sub-feature | Status | Notes |
|---|---|---|
| **Featured pull quote with attribution** | ✅ | `article_quotes` with speaker_name (T6 surfaced top speakers). Selection: longest/most-quoted speaker today. Trivial SQL. |
| **Quote styling (large serif italics)** | ✅ | Pure frontend |

## 6. Background processing pipeline (what's missing under the hood)

| Required task | Status |
|---|---|
| **Daily Brief Generation Task** (the LLM that writes the prose) | 🔴 NOT BUILT — biggest single gap |
| Brief Storage table `brief_daily` | 🔴 NOT BUILT — needs migration 057 |
| Brief endpoint `/api/brief/today` | 🔴 NOT BUILT |
| `/api/brief/ask` RAG endpoint | 🔴 NOT BUILT |
| Brief PDF render task | 🔴 NOT BUILT |
| User notifications wiring | 🟡 Designed (T7), not built |
| Per-entity page | 🟡 Easy build with text queries |

---

## Summary verdict

| Category | Count | What it means |
|---|---|---|
| ✅ Ready today | 9 | Banner stats, language counts, quote of the day, source list, citations linking |
| 🟡 Small wiring | 6 | Notification bell, PDF download, entity pages, sparklines |
| 🟠 Needs ~1 day of work each | 6 | RAG search, integrity %, sentiment scalar, brief generator, ask-endpoint, refresh-timer |
| 🔴 Bigger build (1-3 days each) | 5 | brief_daily table + writer task + endpoint, PDF render, /api/brief/ask |
| ⚪ Can't do without external | 0 | Nothing in this design needs something we lack |

## Build order (suggested)

1. **`brief_daily` migration + writer task** (1 day) — this unlocks everything else
2. **`/api/brief/today` + frontend `/brief` page using it** (1 day) — visible immediate result
3. **Quote of the day + sentiment scalar + integrity %** (half day)
4. **Sparklines + 7-day metric series** (half day)
5. **Entity pages + clickable citations** (1 day)
6. **PDF render + Send Report button** (1 day)
7. **RAG "Ask anything about today" endpoint** (1-2 days)
8. **Notifications bell** (half day)

**Net: ~7-8 days of focused work to render this exact design with live data.**

---

## What I haven't seen yet

The screenshot you shared is just the top of the page. There's almost certainly more below (story list, geo, trending, etc.). If you share:
- More screenshots of the scrolled-down content
- Or the figma / design file
- Or the page code your boss wrote

…I can extend this audit page-by-page and identify any **deeper** features (story importance ranking, contradiction surfacing, multi-day archives) that may need extra backfill we haven't budgeted for.
