# 06 — Work Log (session of 2026-06-05)

Everything below is DONE and deployed to prod unless marked otherwise.

## A. YouTube clips ingestion — diagnosed + re-enabled
- **Symptom:** clips stopped ~2026-05-25. User insisted it was a deliberate stop,
  not an IP issue. **Confirmed correct.**
- **Root cause:** commit **`63de8a8`** ("observe data-quality audit", 2026-05-22)
  removed three things from `backend/celery_app.py`: the `youtube_task` import,
  the `tasks.collect_youtube` route, and the `collect-youtube-every-2h` Beat
  entry. Deployed ~05-25 = the exact ingestion cliff.
- **Fix:** re-inserted all three on the Hetzner build source via an idempotent
  patch script (`infrastructure/patch_reenable_youtube.py`), rebuilt + restarted
  `rig-backend`. Task is registered, scheduled every 2h, runs.

## B. YouTube cookies (caption transcripts work; audio still blocked)
- Wired `YOUTUBE_COOKIES_PATH=/app/youtube-cookies.txt` (already in `.env.prod`,
  used by rig-backend) and mounted the user-provided cookie jar
  `/root/rig/secrets/youtube_cookies.txt` **read-write** into `rig-backend`
  (yt-dlp needs to rewrite the jar; a read-only mount caused `Errno 30`).
  Compose patch: `infrastructure/patch_cookie_mount.py`. Pristine backup kept at
  `/root/rig/secrets/youtube_cookies.orig.txt`. The folder is git-ignored.
- **Result:** caption-based transcripts now ingest (clips count climbed). The
  **yt-dlp AUDIO path is still bot-blocked** ("Sign in to confirm you're not a
  bot") even WITH valid cookies — that's YouTube BotGuard rejecting the
  datacenter IP. Caption-less videos can't be transcribed without a residential
  proxy → **HOLD** (see 07/08).
- A test proxy container `rig-ytproxy` + a ufw rule (port 4417) exist from an
  earlier experiment; **on HOLD** (the proxy made audio worse). Can be torn down.

## C. Rebrand "Night Desk" → "ROBIN-OSINT"
- Renamed all user-visible branding + comments across the SPA + server utils +
  docs (`index.html` title, Login wordmark, Sidebar footer, design-system header,
  `proxy.mjs`/`check-keys.mjs`, `.env.example`, `package.json`/lock,
  `WALKTHROUGH.md`, the team guide). The on-disk **folder stays `night-desk/`**
  and Caddy paths (`/srv/night-desk`, `/root/rig/night-desk-dist`) are unchanged
  (renaming them would break the build/serve).
- **Rebuilt the frontend** (`.env.production` pins `VITE_BRIEF_API=/osint`) and
  redeployed to `/root/rig/night-desk-dist` (in-place content swap; backup at
  `night-desk-dist.bak`). Verified live: title = ROBIN-OSINT, assets 200,
  `/osint/api/me` = 401 (auth works).

## D. Docs produced
- `products/osint/design/night-desk/WALKTHROUGH.md` — developer reference.
- `…/WALKTHROUGH-team-guide.html` + `…/ROBIN-OSINT-Team-Guide.pdf` — non-technical
  team guide (built via headless Chrome → PDF).
- This context pack (`products/osint/ROBIN-OSINT-CONTEXT/`).

## E. "Top Stories For You" fixes (the big one)
User reported: blank summaries + the same stories repeating + no other AP news.
Investigated the live DB and proved **the data is fresh and varied** (newest
minutes old) — the problem was the ranking, not the data. Fixes shipped:

1. **Summary fallback** (`relevance.py`): card summary =
   `COALESCE(summary_executive, lead_text_translated, lead_text_original)` → no
   more blank cards (was ~40% blank).
2. **English summaries** (`top_articles.py`): run `i18n.attach_en` on the summary
   and surface the English text (stored "translated" lead is often still Telugu).
3. **Variety + Andhra-first** (`top_articles.py:_diversify`):
   - de-dup identical headlines (title signature),
   - **principal-protected person de-dup** (the principal may repeat, but a
     repeated OTHER person — e.g. a Karnataka minister written 3 ways — collapses
     to one),
   - cap any one matched entity to ~half the row,
   - **primary-state-first**: stories about the primary state (token, e.g.
     "andhra") or the principal are chosen before off-state stories,
   - faster freshness (`half_life_h=20`) + shorter window (default 72h).
4. **Made `half_life_h` a parameter** of `score_relevant`.

**Validated** for the AP user: 6/6 English summaries; all 6 Andhra; the Karnataka
"Ramalinga Reddy" triplet gone; varied (Chandrababu, monsoon, RS seats,
employment scheme).

## F. Incidents during the session (resolved)
- **Broke osint-backend DB auth** by recreating it with `--env-file .env.prod`
  (wrong password). `/ready` went 500 for a few minutes. **Fixed** by re-upping
  with the default `.env`. → This is THE landmine; see 09.
- A Python **closure bug** (`seen_person |= …` rebinds local) made the endpoint
  500 briefly; fixed with `.update()`. Always `py_compile` + run the validation
  script after editing `top_articles.py`.
