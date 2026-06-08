# Night Desk — Home Page (OSINT) Session Handoff

> Paste the **Jump-in prompt** at the bottom into a new chat, and attach/point to
> this file. It captures everything needed to continue seamlessly.

Last updated: 2026-06-09 · Product: `products/osint/` (RIG OSINT "Night Desk")

---

## 1. What this product is

The **OSINT Night Desk** — a personalized political-intelligence dashboard.
Each user has a **principal** (the politician the whole dashboard is *about*) plus
a **watchlist** of other people. The Home page has these sections:

1. **Masthead** — principal name, net favourability, confidence.
2. **Coverage Sentiment** — a 3-day sentiment waveform; click the number to expand
   drivers (lazy-loaded).
3. **Top Stories for You** — relevance-ranked article feed.
4. **People to Watch** — manually-curated list of watched individuals (cards with a
   per-person coverage read).
5. **THE LATEST** (was "THE SIX") — six live evidence feeds (see §4).

**Test user this session:** `maverick092005+telangana@gmail.com`
- Principal = **Revanth Reddy** (Telangana CM, INC), id `9a70e644-5a04-456e-a569-1a9e68aae1ed`.
- Watchlist has ~70 entities (onboarding picks + manual adds).

---

## 2. Deployment topology & how to deploy (CRITICAL)

Everything runs on **Hetzner**: `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154`

### Backend — `osint-backend` container
- **Source is BAKED into the image** (no bind mount). Editing host files or `scp`
  to the host does **NOT** affect the running container.
- **Deploy a backend file:**
  ```bash
  scp -i ~/.ssh/rig_hetzner <localfile> root@178.105.63.154:/tmp/<f>.py
  # compile-check WITHOUT a running container (avoids crash-loop):
  ssh ... "docker run --rm -v /tmp/<f>.py:/c.py infrastructure-osint-backend python3 -m py_compile /c.py"
  ssh ... "docker cp /tmp/<f>.py osint-backend:/app/<path>/<f>.py && docker restart osint-backend"
  ```
- Health check: `docker exec osint-backend curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/api/brief/home` (401 = up + auth-gated; 200 = up).
- Logs: `docker logs osint-backend --tail 20` (look for `error|traceback`).

### Frontend — `products/osint/design/night-desk/` (Vite + React)
- Live = **static files** at `/root/rig/night-desk-dist/`, served by `rig-caddy`.
- **Deploy the frontend:**
  ```bash
  cd products/osint/design/night-desk && npm run build
  ssh ... "rm -rf /root/rig/night-desk-dist/assets"
  scp -i ~/.ssh/rig_hetzner -r dist/* root@178.105.63.154:/root/rig/night-desk-dist/
  ```
- Users must hard-refresh (Ctrl+Shift+R) — hashed bundle name changes each build.

### Database — `rig-postgres` container
- `docker exec rig-postgres psql -U rig -d rig -c "<sql>"`
- **Home is cached** in `analytics.home_cache` (≈30-min precompute). After ANY
  change to a user's data or backend logic, **bust it**:
  `DELETE FROM analytics.home_cache;` (or `WHERE user_id = ...`).

---

## 3. Hard-won gotchas (read before editing)

1. **Curly-quote contamination.** The Edit tool can inject U+201C/U+201D as string
   delimiters → Python 3.12 SyntaxError. In `home_sections.py` use the constants
   `_LQ`/`_RQ` for decorative curly quotes inside f-strings, never literal “ ”.
2. **Always compile-check before restart** (`py_compile` via `docker run`), the
   container crash-loops on a syntax error and you lose `docker exec`.
3. **PowerShell writes UTF-8 BOM** by default → `U+FEFF` SyntaxError. Use
   `New-Object System.Text.UTF8Encoding($false)` if writing files via PS.
4. **Directed sentiment.** For any "is this for/against the principal" measure, use
   `article_stances` filtered by **`actor_entity_id = :pid`** (the stance TARGET).
   Summing all stances in an article mislabels (e.g. "Congress criticised" reading
   as *support* for a Congress CM).
5. **`_BODY_PRESENT` guard (posture.py).** Anti-hallucination: only counts an
   article if the entity's name/surface-form/alias literally appears in the text.
   This is why raw `article_entity_mentions` counts can be wildly inflated.
6. **Junk aliases in `entity_dictionary`.** Single-token aliases like `"Ali"`
   false-match huge numbers of articles → fake coverage. The `_BODY_PRESENT` guard
   hides it on the page, but recommendations off raw counts will be wrong. Verify a
   candidate's `name_in_text` count before trusting its volume. Duplicate person
   records also exist (e.g. two "K T Rama Rao").
7. **`now_sim()`** = `analytics.now_sim()`, the simulated "now" used by all windows.
   Currently equals real `NOW()`.

---

## 4. THE LATEST — the six evidence feeds (this session's main build)

Replaced the old analytical "THE SIX" (Hard Truth / Real-or-Noise / etc.) with six
plain, sourced, newest-first feeds. Built in
`products/osint/backend/home_sections.py` → **`build_six_feeds(db, prefs, pid, pname, wh)`**
(returns `{"six": [...]}`), wired into `build_home` (replaced `build_six(...)`).
Old `build_six` left in place but unused (marked legacy).

| key | Title | Source |
|---|---|---|
| `quotes` | Latest quotes about you | `article_quotes` (is_direct) in principal's articles |
| `articles` | Latest articles about you | `article_entity_mentions` + `articles`, newest |
| `criticism` | Latest criticism of you | articles with **directed** pol < 0 |
| `support` | Latest support for you | articles with **directed** pol > 0 |
| `watchlist` | Latest from people you watch | articles mentioning watchlist person ids |
| `tied` | What you're being tied to | co-occurring entities + story counts |

- Tone dot uses **directed** stance (`actor_entity_id = pid`).
- Non-English headlines/quotes translated in ONE batched `_i18n.ensure_en` pass
  (the `quote_text_en` column is empty, so translation is on-the-fly).
- Item shapes: `{kind:'quote'|'link'|'tag', text, en?, sub, when, tone, url}`.
- Frontend render: `Home.jsx` (search "THE LATEST"); CSS in `index.css` (search
  `.six.feed`, `.feed-row`, `.feed-dot`, `.feed-tag`).
- **Validated live** by running `build_six_feeds` / `build_home` inside the
  container against the test user — all 6 feeds returned real items.

---

## 5. People to Watch — current design & fixes shipped

- It is a **manually-curated list, capped at 8 — `8` is a ceiling, not a target.**
  It shows ONLY entities the user explicitly added (`pinned: true`), newest first.
  **No auto-backfill** — removing someone leaves the panel smaller.
- Backend: `build_players` in `home_sections.py`. Pinned-only selection; each card
  still renders a real coverage read (pressure / entangled / thin / "just added").
- Endpoints: `routers/home.py`
  - `POST /api/brief/watchlist/add` — adds OR re-pins an existing member, stores the
    **real** entity type, **rejects** non-persons (400) and the **principal** (400),
    moves the entity to newest so it surfaces at top.
  - `DELETE /api/brief/watchlist/{entity_id}` — removes (frontend does optimistic UI).
- `_is_person(m)` accepts `type`/`kind` in (`person`,`politician`), case-insensitive,
  excludes party/org-shaped names via `_PARTY_RE`.
- Watchlist stored in `analytics.user_brief_prefs.watchlist` JSONB:
  `entity_ids[]` + `entity_meta[]` (each meta: `{id,name,type,party,state,pinned?,kind?}`).
  Onboarding entries have `kind`; modal-added have `type`.

### Other fixes this session
- **Coverage Sentiment drivers** were 404ّing → added the missing route
  `GET /api/brief/home/sentiment-explain` in `routers/home.py` (calls
  `sentiment_explain`). Glosses now use a clean **title** translation (not the
  breadcrumb/HTML-polluted lead text), only for non-English headlines.
- **Report** (`report_render.py`) restructured to exactly 5 sections: Geography
  Intelligence → Top Stories → Heat Risk → Sentiment Analysis → Key Developments.
- War-room italics removed (`index.css` `.cabledesk` overrides).

---

## 6. Files touched (all under `products/osint/`)

- `backend/home_sections.py` — `build_six_feeds` (new), `build_players` (pinned-only),
  `_is_person`, `sentiment_explain`, helpers `_ago/_pol_tone/_trim/_clean_head`.
- `backend/routers/home.py` — watchlist add/remove, sentiment-explain route, cache bust.
- `backend/routers/onboarding.py` — entity search (excludes party/junk, coverage rank).
- `backend/report_render.py` — 5-section report.
- `design/night-desk/src/pages/Home.jsx` — THE LATEST render, People-to-Watch cards,
  add/remove modal, optimistic remove.
- `design/night-desk/src/index.css` — `.feed-*` styles, war-room italic overrides.
- `design/night-desk/src/components/ReportDispatch.jsx` — report description.

---

## 7. Known open items / possible next steps

- Feeds 2 & 4 (articles/support) can briefly overlap when the newest article is also
  the most positive — could de-dupe across feeds if desired.
- `tied` feed surfaces obvious tokens (e.g. "Telangana", "BRS"); could filter the
  principal's own home state/party.
- **Systemic data cleanup (not yet done):** merge duplicate person records and strip
  single-token junk aliases (e.g. `"Ali"`) in `entity_dictionary` — the root cause
  behind inflated counts and the Mir Zulfeqar Ali fiasco.
- People to Watch shows only modal-added (pinned) people; onboarding-selected persons
  no longer auto-populate it (intentional, per user).

---

## 8. Jump-in prompt (paste this in the new chat)

> I'm continuing work on the **RIG OSINT Night Desk** home page
> (`products/osint/`). Read `docs/sessions/night-desk-home-handoff.md` first — it
> has the full context: deployment topology (baked `osint-backend` container — use
> `docker cp`, not host scp; static frontend at `/root/rig/night-desk-dist` via
> rig-caddy), the SSH/deploy/compile-check procedures, the gotchas (curly quotes,
> directed sentiment via `actor_entity_id=pid`, the `_BODY_PRESENT` guard, junk
> aliases), and what we just built: **"THE LATEST"** — six live evidence feeds
> (`build_six_feeds` in `home_sections.py`) — plus the manually-curated
> **People to Watch** (pinned-only, cap 8) and the watchlist add/remove endpoints.
> Test user: `maverick092005+telangana@gmail.com`, principal **Revanth Reddy**.
> Always compile-check before restart, and bust `analytics.home_cache` after data/
> logic changes. Here's what I want to do next: <DESCRIBE YOUR NEXT TASK>.
