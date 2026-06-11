# `rig-news` Frontend — Complete Feature Audit

**Location:** `C:/Users/Dell/Desktop/rig-news/` (separate Next.js 15 app)
**Status of integration:** ALL DATA IS MOCKED. Zero API calls exist anywhere in the codebase. Every page reads from static `.ts` data files (`*-data.ts`, `MINUTE_STORIES`, `LONG_READS`, `STORIES`, etc.). This is the **design layer waiting to be wired** to our backend.

Legend:
- ✅ Data + endpoint ready — wire today
- 🟡 Data ready, needs small wiring task
- 🟠 Needs a new computation pipeline (~1 day)
- 🔴 Needs bigger build (1-3 days)
- ⚪ Out of scope / can't do
- 🎨 Pure frontend (no backend dependency)

---

## Page 1 — `/` (Landing)

| Feature | Status | Notes |
|---|---|---|
| TopAnnouncement banner | 🎨 | Static marketing |
| Nav with wordmark | 🎨 | Brand only |
| Hero section | 🎨 | Marketing copy |
| ValueProps · HowItWorks · ExploreIntro | 🎨 | Marketing |
| Section{Minute/Digest/AllSides/LongRead/LongView/Queue} (6 promos) | 🎨 | Marketing |
| Final CTA + Footer | 🎨 | Marketing |

**Backend impact: zero.** Pure marketing page.

---

## Page 2 — `/today` (Newsstand picker)

| Feature | Status | Notes |
|---|---|---|
| Chalkboard with today's date | 🎨 | Client-side `new Date()` |
| 6 publication cards w/ hover-tilt 3D | 🎨 | Pure animation |
| **Each card shows TODAY's headline** for that mode | 🔴 | Needs: `GET /api/today/headlines` returning {minute, digest, all-sides, long-read, long-view, queue} top headline each |
| Wordmark | 🎨 | |

---

## Page 3 — `/minute` (TikTok-style cards, 60 sec each)

| Feature | Status | Notes |
|---|---|---|
| Stack of swipeable story cards | 🎨 | Framer-motion |
| `MINUTE_STORIES` array — title, summary, category, color | 🔴 | Needs `GET /api/minute/stories` — top 15-20 stories from event_clusters by importance_score, with one-line summary |
| Time-saved counter ("210 sec saved per story") | 🟡 | Computed clientside |
| Category color theming | 🟡 | Needs category→color map agreed with article_type |
| ThumbnailRail (mini-map of all 20 cards) | ✅ | Just renders array |
| CelebrationScreen ("you read N today") | 🎨 | Client tracking |
| Keyboard navigation | 🎨 | |

**Backend gap: 1 endpoint `/api/minute/stories`. ~3 hours.**

---

## Page 4 — `/digest` (Personalized 5-story morning email)

| Feature | Status | Notes |
|---|---|---|
| 7-step onboarding wizard | 🎨 | Pure state machine |
| Step 1: Topic picker | 🔴 | Needs `GET /api/digest/topics` — taxonomy from article_type + canonical_event_type |
| Step 2: Topics to AVOID picker | 🎨 | Same data, opposite intent |
| Step 3: Tone picker (editor, scholar, friend…) | 🎨 | Pure UI choice, persisted to user_profiles |
| Step 4: Time-slot picker (morning, lunch, evening) | 🎨 | Cron config |
| Step 5: Email collection | 🟡 | Already have user.email from supabase |
| Step 6: Gmail-preview rendered LIVE | 🔴 | Needs `POST /api/digest/preview` with {topics, avoid, tone, count: 5} → returns 5 stories with LLM-written prose in chosen tone |
| `storiesFor(topics)` selector | 🟠 | Backend: filter event_clusters by canonical_event_type matching topics, rank by importance_score |
| `pickArchetype()` (matches you to reader-type) | 🎨 | Pure clientside derivation |
| **Daily email delivery** | 🔴 | Needs Celery task + SES/Resend integration |

**Backend gap: 3 endpoints + daily delivery cron + LLM rewrite-to-tone task. ~3 days.**

---

## Page 5 — `/all-sides` (Ground News-style bias view)

| Feature | Status | Notes |
|---|---|---|
| STORIES array (30 items) with left/center/right counts | 🔴 | Needs `GET /api/all-sides/stories` — event_clusters with per-source political-bias attribution |
| **Bias counts per story** (3 left, 2 center, 4 right) | 🔴 | **Need a source→political_bias mapping table** — DOES NOT EXIST YET. Requires 1-time tag of all 333 sources |
| Hero story w/ multi-source coverage | ✅ | Use event_clusters.source_count |
| Blindspot stories ("only right covers this") | 🟠 | SQL: clusters where all sources land in one bias bucket |
| DAILY_BRIEFING text | 🔴 | Same brief generator as `/brief` |
| TRENDING_TOPICS | ✅ | T6 entity_mention_daily |
| REGIONS panel | ✅ | article_locations |
| topGrid · latestPicks · moreStories slices | ✅ | Just pagination |

**Backend gap: source-bias mapping (1-day manual + ongoing) + 1 endpoint. ~2 days.**

---

## Page 6 — `/long-read` (Washington-Post-style)

| Feature | Status | Notes |
|---|---|---|
| LONG_READS array (30+ articles) | 🟡 | Filter article_type IN ('analysis', 'explainer', 'opinion', 'interview') |
| LIVE_NEWS ticker | ✅ | Latest articles polled |
| MOST_READ panel | 🔴 | Needs `article_view_log` table to track which articles get clicks — DOES NOT EXIST |
| FEATURES cards | 🟡 | Curated/editorial picks; needs an admin-tagged "featured" flag |
| PODCASTS section | ⚪ | We don't ingest podcasts (YouTube transcripts exist but no audio extraction) |
| Lead / hero / leftStack / centerStack / moreList layout slices | ✅ | Just rendering |
| Climate · Culture · Profiles sections (topic bands) | 🟡 | Filter articles by primary_subject or article_type |
| Latest 4 sidebar | ✅ | Newest articles |
| Section-specific article detail pages `/long-read/[slug]` | 🔴 | Needs article slug routing + content render endpoint |

**Backend gap: most_read tracking + podcast pipeline + article detail endpoint. ~3 days for everything.**

---

## Page 7 — `/long-view` (Magazine flip-book)

| Feature | Status | Notes |
|---|---|---|
| 3D page-flip animation | 🎨 | Framer-motion |
| Cover page | 🟠 | Needs an "issue of the day" generation — biggest story + cover headline |
| Contents page | ✅ | List of 10 article titles |
| 10 article pages | 🟡 | Long-form analysis articles, 1 per page; use article_type='analysis' |
| Back cover | 🎨 | Static |
| Keyboard arrows / click-to-turn | 🎨 | |
| Article body rendering | ✅ | We have full_text_translated for v3 articles |
| Per-article images | 🟡 | We have article.image_url from RSS |

**Backend gap: cover generation + issue assembly task. ~2 days.**

---

## Page 8 — `/queue` (Saved-for-later)

| Feature | Status | Notes |
|---|---|---|
| User's saved articles | 🔴 | Needs `user_saved_articles` table (article_id, user_id, saved_at) — DOES NOT EXIST |
| Save/unsave button on every article (across all pages) | 🔴 | Needs `POST /api/queue/save` + `DELETE` |
| Time-to-read calculator | 🎨 | Clientside word count |
| "47 stories ready" counter | ✅ | Once table exists |

**Backend gap: user_saved_articles table + 2 endpoints. ~half day.**

---

## Page 9-11 — `/onboarding`, `/signin`, `/signup`

| Feature | Status | Notes |
|---|---|---|
| Auth shell | ✅ | Already have Supabase wired |
| Onboarding profile capture | 🟡 | Likely just writes to user_profiles |

**Backend impact: minimal. Auth already works.**

---

## Cross-cutting features (used on multiple pages)

| Feature | Status | Notes |
|---|---|---|
| Wordmark + Nav | 🎨 | |
| Top announcement banner | 🎨 | |
| Bookmark/Save button | 🔴 | Same as Queue |
| Share button | 🎨 | Web Share API |
| Read-progress tracker | 🔴 | Needs `article_read_log` |
| Reader auth state (M avatar) | ✅ | Supabase |
| Dark/light theme toggle | 🎨 | |
| Search (top-bar) | 🔴 | Same RAG-on-corpus we identified for `/brief` |
| Notifications | 🟡 | Watchlist matcher pattern from T7 |
| Multi-language toggle | ✅ | We have language_detected; can show only certain langs |

---

## Backend tables we'd need to CREATE

| Table | Why | Effort |
|---|---|---|
| `user_saved_articles` | Queue feature | 5 min migration |
| `user_topic_subscriptions` | Digest personalization | 10 min migration |
| `user_tone_preference` | Digest tone | 1 column on user_profiles |
| `article_view_log` | Most-Read panel | 10 min migration |
| `source_political_bias` | All Sides bias coloring | **1-day MANUAL tagging of 333 sources** |
| `daily_brief` | The /today + Digest writer cache | 10 min migration |
| `daily_brief_subscription_delivery` | Email digest delivery log | 10 min |
| `editor_featured_articles` | Long-Read Features panel | 10 min |

---

## Backend tasks we'd need to BUILD

| Task | What it does | Effort |
|---|---|---|
| `tasks.minute.generate` | Picks top 20 stories every morning, generates 60-sec summaries | 1 day |
| `tasks.digest.generate_per_user` | For each subscriber, picks 5 stories matching topics, rewrites in chosen tone, queues email | 1-2 days |
| `tasks.digest.send_email` | Renders MJML or React-email template, sends via Resend/SES | 1 day |
| `tasks.all_sides.compute_bias_distribution` | Per multi-source cluster, count left/center/right; flag blindspots | 1 day (after source_bias table exists) |
| `tasks.long_view.assemble_issue` | Daily: pick 10 long-form pieces + write cover headline + contents | 1 day |
| `tasks.brief.generate` | Already designed; writes morning brief prose | 1-2 days |
| `tasks.long_read.compute_most_read` | Daily aggregation of article_view_log | 30 min |

---

## Endpoints we'd need to BUILD

```
GET  /api/today/headlines             — 6 mode headlines for /today
GET  /api/minute/stories              — 20 stories for /minute
GET  /api/digest/topics               — topic taxonomy
POST /api/digest/preview              — live preview while onboarding
GET  /api/digest/today?user_id=       — today's digest for this user
POST /api/queue/save                  — save article
DELETE /api/queue/save/:id            — unsave
GET  /api/queue                       — list saved articles
GET  /api/all-sides/stories           — 30 stories with bias counts
GET  /api/long-read/sections          — homepage data
GET  /api/long-read/article/:slug     — single article body
GET  /api/long-view/today             — today's magazine issue
POST /api/notifications/mark-read     — notification bell
POST /api/ask                          — RAG over today's corpus
POST /api/share                        — share with attribution
GET  /api/brief/today                 — Morning Brief (the original /brief)
```

**Total: 17 new endpoints + 8 new tables + 7 new Celery tasks**

---

## Bottom-line summary

| Category | Count |
|---|---|
| ✅ Buildable today with existing data + small wiring | 18 features |
| 🟡 Small wiring on top of existing data | 14 features |
| 🟠 Needs new pipeline computation (~1 day each) | 7 features |
| 🔴 Bigger builds (1-3 days each) | 14 features |
| 🎨 Pure frontend / no backend | 22 features |
| ⚪ Can't do without new source type | 1 feature (podcasts) |

## What we CAN do that's not in the boss's mockup

These would be nice-to-haves we could surface FROM existing data:
- Contradictions panel (we have `article_contradictions` table, mostly empty but pipeline now scheduled)
- Trending entities live ticker (T6 entity_mention_daily already populated)
- Source quality scorecard (we already have /observe panels for this)
- Geo heatmap (article_locations clean and ready)
- Story importance ranking (T5 importance_score already computed every 30 min)

## What we CAN'T do (genuinely blocked)

| Feature | Why blocked |
|---|---|
| Podcasts section | We don't ingest audio. Would need a separate podcast-fetcher pipeline + Whisper transcript. |
| (Everything else has a path) | |

---

## Recommended build order

1. **Week 1 (foundation):** brief_daily migration + writer task + `/api/brief/today` + `/api/minute/stories` + `/api/today/headlines` → these unlock 4 pages at once
2. **Week 2 (engagement):** user_saved_articles + queue endpoints + notification bell + RAG `/api/ask` → makes the app sticky
3. **Week 3 (digest):** Topic taxonomy + digest preview + email delivery (this is the highest-effort single feature, ~3-4 days)
4. **Week 4 (depth):** All-Sides (after source bias tagging) + Long-Read article pages + Long-View issue assembly
5. **Week 5 (polish):** Most-read tracking, view logs, share-attribution, multi-day archive

**Total: ~4-5 weeks of focused backend work to fully light up the boss's frontend with real data.**

The frontend itself is essentially done (~9 polished pages with animations, theming, mock data). What's missing is purely the bridge.
