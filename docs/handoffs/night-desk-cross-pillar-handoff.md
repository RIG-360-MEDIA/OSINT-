# Night-Desk Fixes — Session Handoff (2026-06-21)

Paste the prompt below into a new chat to continue with full context.

---

## CONTINUATION PROMPT

I'm continuing work on the **RIG Surveillance** project (multi-pillar intelligence
aggregator). Working dir: `C:\Users\Dell\Desktop\rig-surveillance`. Branch:
`feat/ask-rig-chat`. I'm on Windows 11 / PowerShell + Git-Bash.

### What you can access (use freely)
- **Hetzner production server (SSH):**
  `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154`
- **Postgres (in Docker on Hetzner):**
  `docker exec rig-postgres psql -U rig -d rig -c "<SQL>"`
  - Simulation clock: queries use `analytics.now_sim()` (NOT real wall time).
  - Per-user brief prefs live in `analytics.user_brief_prefs` (keyed by Supabase
    `user_id`). There is a SECOND, non-overlapping user table `public.user_profiles`
    (the known "2-system" split — accounts in one are not in the other).
- **Two backend containers:**
  - `osint-backend` — the night-desk API (FastAPI, listens on container port 8000,
    proxied by Caddy). **BAKED image, NOT bind-mounted.** Code lives at `/app/*.py`
    and `/app/routers/*.py` INSIDE the container.
  - `rig-backend` — ingestion/Celery only. This one IS bind-mounted from `/root/rig`.
- **Caddy:** dockerized as `rig-caddy`, Caddyfile at
  `/root/rig/infrastructure/Caddyfile`. Live site: `https://desk.rig360media.com`
  (frontend served at `/`, night-desk API under `/osint`).
- **Frontend (Vite night-desk):**
  `products/osint/design/night-desk/` — build with `npm run build`, deploy dist to
  `/root/rig/night-desk-dist` (served by rig-caddy). Local dev: `npm run dev` →
  http://localhost:5180 (points at prod API via `VITE_BRIEF_API=https://desk.rig360media.com/osint`).

### Deploy procedure for osint-backend (because it's baked, not mounted)
1. `scp -i ~/.ssh/rig_hetzner <file> root@178.105.63.154:/tmp/`
2. `docker cp /tmp/<file> osint-backend:/app/.../<file>`
3. `docker restart osint-backend`
4. `docker commit osint-backend osint-backend:latest`  ← REQUIRED for durability
   (changes are lost on container recreate without this).
- To test an authed endpoint inside the container, mint a JWT with the secret from
  the container env (`OSINT_SUPABASE_JWT_SECRET` / `SUPABASE_JWT_SECRET`), set
  `sub` = a `user_id` from `analytics.user_brief_prefs`, then
  `docker exec osint-backend curl -s -H "Authorization: Bearer <tok>" http://localhost:8000/...`

### What was just fixed (all LIVE + committed to image)
Night-desk had 8 reported issues; the 3 deep ones plus a route bug:

1. **Dispatch showed 0 stories** — `report_builder.py` built `_rep` via an INNER JOIN
   on `article_districts`/`districts`, but the district tagger never ran in prod
   (0 of 1702 TG articles tagged). FIX: dropped the district join; now gates only on
   `sources.geo_states @> ARRAY[<state>]`. Verified n24 = 1702 (was 0).

2. **Analytics relevance bleed** — `analytics_page.py` built `_univ` from ANY
   watchlist co-mention, so national stories leaked into quote/claim/figure cards.
   FIX: added a `_detail` temp table restricted to the PRINCIPAL entity
   (`article_entity_mentions.entity_id = pid`); the 3 detail cards (quotes/claims/
   numbers) now join `_detail`, broad cards still use `_univ`.

3. **Cross-pillar clips/cuttings empty** — TWO causes:
   (a) `relevance.py` `_PILLAR_SQL` had a hard `entities_extracted IS NOT NULL AND
   jsonb_typeof='array'` filter dropping ~41% of clips. FIX: removed it, made the
   `ent` CTE NULL-safe with a CASE → title-only matches now surface.
   (b) **The real blocker:** deployed `routers/home.py` was an OLD version with NO
   `/api/brief/cross-pillar` route → frontend got 404 → `.catch()` → empty. FIX:
   deployed current `home.py` (adds `/cross-pillar` + `/clipping-image/{id}`).
   Verified live: `GET /api/brief/cross-pillar → 200, clips=6 cuttings=6` for all
   5 real personas.

Also fixed earlier in the session (frontend, deployed to night-desk-dist):
- Breaking ticker stuck on "Loading…" → `ticker_router` was not imported/mounted in
  `main.py`; added it. Title-slug junk cleaned in `Ticker.jsx`.
- War Room stats blank → backend `war_room.py` station dict keys didn't match what
  the frontend reads (`activeAttacks/serious/negStories/trendLabel/trendTone`); aligned.
- Chronicle missing from nav → added to `App.jsx` (PAGES/SLUGS), `Sidebar.jsx` NAV,
  `lib/ui.jsx` icon.
- Wrong YouTube channels → `data/channels.js`: removed stale pinned live IDs, replaced
  V6 with T News Telugu, rely on `live_stream?channel=ID` self-heal.

### Files modified locally (NOT yet git-committed)
Backend: `products/osint/backend/report_builder.py`, `relevance.py`,
`analytics_page.py`, `routers/home.py`, `main.py`, `war_room.py`,
`routers/ticker_router.py`.
Frontend: `products/osint/design/night-desk/src/` — `App.jsx`, `Sidebar.jsx`,
`Ticker.jsx`, `data/channels.js`, `lib/ui.jsx`, `pages/Home.jsx`.

### Open / next
- These are deployed to prod (osint-backend image committed + dist deployed) but NOT
  git-committed. Decide branch + commit when ready.
- 2-user-system split (`analytics.user_brief_prefs` vs `user_profiles`) is unresolved:
  an account with no brief-prefs row shows empty everything. Separate work item.
- District tagger not running in prod (left Dispatch broken originally) — may want to
  fix the actual pipeline rather than only the query workaround.

Please confirm you can reach the server and DB, then I'll tell you the next task.
