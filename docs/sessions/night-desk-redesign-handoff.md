# Night Desk — Rooms Redesign Session Handoff

Last updated: 2026-06-09 · Product: `products/osint/` (RIG OSINT "Night Desk")
Test user: `maverick092005+telangana@gmail.com` · principal **Revanth Reddy**
(`9a70e644-5a04-456e-a569-1a9e68aae1ed`) · user_id `03f93124-eec3-46ac-a41e-829cb663b615`.

> **Status: SHIPPED LIVE to Hetzner** (backend `osint-backend` + frontend
> `night-desk-dist`), validated against the test user. **NOT git-committed** —
> the working tree is shared with a concurrent brief-page session (their
> `stories.py`, `top_articles.py`, `App.jsx`, `Sidebar.jsx`, `Login.jsx` are
> dirty). See "Clean commit list" below.

## The correctness spine — directed stance (read first)

`article_stances.actor_entity_id` is **mislabeled: it holds the stance TARGET**
(who the stance is *about*; speaker = the outlet). Verified live (SP
Balasubrahmanyam tagged supportive). So "for/against entity X" = stances where
`actor_entity_id = X`. This was previously applied **only** to `posture.py` +
the Home feeds. This session extended it to the bespoke stance queries in
`war_room.py`, `analytics_page.py`, `dossier.py` (they had no actor filter →
counted stance toward *anyone* → the "Outlets all-positive" bug, wrong NET
STANCE, "sentiment feels stupid"). 13 queries fixed with
`AND st.actor_entity_id = CAST(:pid|:eid AS uuid)` (roster uses `= m.entity_id`).

## What shipped, per room

- **War Room** (`war_room.py` + `pages/WarRoom.jsx`): removed MOMENTUM / ATTACK
  MAP / BLOC / ALLEGIANCE ROSTER (whole "THE FIELD" block). New plain stat bar:
  **ACTIVE ATTACKS · SERIOUS · NEGATIVE STORIES (21d) · TREND** (trend from
  directed `stance_trajectory`). Renamed AMMUNITION→"YOUR BEST LINES",
  PRE-DRAFT→"SUGGESTED REPLY", INTERCEPTS→"WHAT OPPONENTS ARE SAYING", THREAT
  STACK→"ATTACKS ON YOU". `_momentum/_attackmap/_bloc` left as dead private fns
  (harmless; prune later).
- **Analytics** (`analytics_page.py`): removed `rising/tone/events/claims` via an
  output filter (16 modules now). Directed-stance fix repairs Outlets +
  For-vs-Against + battlefield. Frontend is data-driven → no JSX change.
- **Dossier** (`dossier.py` + `pages/Dossier.jsx`): surface `img` in
  `build_entity_file` (was never returned → always "NO IMAGE"); timeline rows
  now carry `{url, src, article_id}`; removed "The ledger · claims about them";
  **principal pinned first** (flag by id, not the insert-guard — was showing
  BJP); frontend default-selects principal + renders portrait + timeline links.
- **Map** (`map_page.py` + `components/MapSections.jsx`): removed "Stance
  gradient" + "Newest on the wire"; added **33 district cards × 5 latest**
  (`_district_feeds`, `districtFeeds` payload). **Gotcha fixed:** `row_number()`
  needed `ORDER BY collected_at DESC NULLS LAST` — NULLS-FIRST default let
  LEFT-JOIN placeholder rows steal rn≤5 (every district showed empty).
- **Dispatch** (`components/ReportDispatch.jsx`): inline PDF viewer + Download via
  **blob-auth** (`authFetch` the bearer-gated `/api/brief/report.pdf` → object
  URL) instead of the teaser card.
- **Report** (`report_builder.py` + `report_render.py`): restructured for lay
  readers — masthead → **On Your Desk Today** (15 news cards w/ thumbnails) →
  **The Big Stories, Explained** (deep-dives: *What happened* / *Why it matters*
  via `synthesize_paragraph` + templated fallback, uncapped Sources line) →
  Who's Talking → Where It's Landing → Mood in Words → What's Coming → The
  Analyst's Read (analysis seeded last). WeasyPrint table-only layout.
- **Sources feature (cross-cutting)**: new `routers/sources_router.py` →
  `GET /api/brief/sources?kind=&value=` (kinds: negative/supportive/neutral/
  outlet/topic/entity; directed, `_BODY_PRESENT`, cap 200) + `components/
  Sources.jsx` wired into War Room cables, Analytics (For-vs-Against + Outlets),
  Dossier. Registered in `main.py`.

## Entity images

`analytics.entity_image(entity_id PK, image_url, attribution, source, ok,
fetched_at)`. Backfilled via Wikipedia REST (`source='wikipedia_backfill_20260609'`).
Coverage **70/72** (was 47, and those 47 weren't even shown pre-fix). Gaps:
**Amazon** (org), **Polavaram** (location) — placeholders OK. Backup:
`analytics.entity_image_bak_20260609`.

## Deploy facts / rollback

- Backend baked → `docker cp` per file + `docker restart osint-backend`. Verified
  prod == `git HEAD` for all changed files (clean `docker cp`); `main.py` was a
  superset of prod's (preserved concurrent `chronicle_router`, added
  `sources_router`). Import-checked in a throwaway process before restart.
- Frontend: `npm run build` → backup → scp `dist/*` to `/root/rig/night-desk-dist/`
  (bundle `index-fYLz0ARY.js` / `index-D8WDvVW_.css`). Hard-refresh to see it.
- **Caches busted** (all four serving these pages): `analytics.home_cache`,
  `analytics.page_cache` (war room/analytics/map), `public.dossier_cache`. Bust
  these after any data/logic change, not just `home_cache`.
- Rollback artifacts (keep ~1wk): `/app/<f>.bak-redesign-20260609`,
  `/root/rig/night-desk-dist.bak-redesign-20260609`,
  `analytics.entity_image_bak_20260609`.

## Known follow-ups

- LLM deep-dive prose used templated fallback today (Groq daily TPD cap hit);
  real prose when tokens reset.
- Dossier timeline can surface an aspirational future-dated event first (2047) —
  pre-existing ordering quirk, not touched.
- Prune dead `_momentum/_attackmap/_bloc` in `war_room.py`.
- **Clean commit list (my files only — exclude the concurrent session's):**
  backend: `war_room.py analytics_page.py dossier.py map_page.py
  report_builder.py report_render.py main.py routers/sources_router.py`;
  frontend: `pages/{WarRoom,Analytics,Dossier}.jsx
  components/{MapSections,ReportDispatch,Sources}.jsx`.
