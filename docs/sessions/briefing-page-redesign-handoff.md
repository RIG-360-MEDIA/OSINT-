# Briefing Page Redesign — Session Handoff

**Date:** 2026-06-08  
**Branch:** `feat/directional-sentiment-relevance-geo`  
**Status:** Fully implemented, validated, deployed to Hetzner.

---

## What This Session Did

Redesigned the OSINT night-desk briefing page (`/`) — both backend data generation and frontend rendering. The old page had cryptic template-stat cards and opaque headings. The new page reads like a human analyst wrote it.

---

## The 6 Changes Made

### 1. "Last 50 days" window label
- Frontend display only — hardcoded in masthead subline and briefing section label.
- No backend change. The window query itself is unchanged.

### 2. Four new bottom-line cards (replaced the old 4)
Old: WHERE YOU STAND / KNOW THIS / THE ATTACK / YOUR MOVE  
New: **Supporting You** / **Attacking You** / **Gaining Steam** / **Pressure Point**

Each card now has:
- `article_id` — the source article ID
- `url` — direct article URL (clickable if present)
- `v` — 1–2 sentence human-readable prose (not stats)

Logic:
- **Supporting You** → top allied outlet or top ranked article if overall favourable
- **Attacking You** → `attack_origination.origin` article (the identified hostile thread)
- **Gaining Steam** → second-ranked article in the relevance pool
- **Pressure Point** → contested issue-ownership topic, or the hostile thread if no contested front

### 3. "Highlights of the Day" (was "What It Means")
- 5–6 sentence prose block built from: overall stance lean, top story, quote balance, attack thread, issue ownership wins/contests, trajectory direction.
- Field name: `B.highlights` (frontend) / `briefing.highlights` (API)
- Sources shown via collapsible "Sources (N)" toggle: `B.highlightsSources`

### 4. "Timeline" (was "What Happened")
- Kicker rename only. Data unchanged.
- Each row is now clickable → opens source article URL in new tab.

### 5. "How to Play It" — removed entirely
- Frontend section deleted. Backend no longer returns `howToPlay`.

### 6. Why It Matters / The Other Side / What's Next — prose blocks
All three are now 3–4 sentence human-readable prose (not template stats).

- **Why It Matters** (`B.whyItMatters`) — explains strategic significance of the current coverage posture. Sources: `B.whyItMattersSources`
- **The Other Side** (`B.otherSide`) — steelmans the case for not over-reading the adverse signals. Sources: `B.otherSideSources`
- **What's Next** (`B.whatsNext.text`) — what to watch and why; includes trajectory confidence. Sources: `B.whatsNext.sources`

Each section ends with a collapsible "Sources (N)" toggle.

---

## Files Changed

### Backend: `products/osint/backend/home_sections.py`

**New helper function** (inserted before `build_briefing`):
```python
async def _fetch_article_urls(db, ids: list[str]) -> dict[str, str]:
    # Fetches {article_id: url} for a list of IDs
```

**`_what_happened`** — SQL now selects `url` column; output dicts include `"url"` field.

**`build_briefing`** — completely rewritten:
- New signature: `def build_briefing(prefs, posture, ranked, what_happened, wh, ao_en=None, ao_url="")`
- Returns `highlights`, `highlightsSources`, `whyItMatters`, `whyItMattersSources`, `otherSide`, `otherSideSources`, `whatsNext` (dict with `text`, `confidence`, `sources`)
- No longer returns `howToPlay` or `whatItMeans`

**`build_home`** — patched to:
1. Collect `article_id` from `attack_origination.origin`
2. Call `_fetch_article_urls` for top-10 ranked + attack origin article
3. Merge URLs back into `ranked` list via `{**r, "url": ...}`
4. Pass `ao_url` into `build_briefing`

### Frontend: `products/osint/design/night-desk/src/pages/Home.jsx`

Key additions:
- `SourcesToggle` component — collapsible disclosure showing outlet + title for each source article, links if `url` present
- `blTone()` updated to map new card key names (`support`, `attack`, `steam`, `pressure`)
- bl-band cards render as `<a>` when `b.url` present
- Timeline rows `<a>` when `w.url` present
- `B.highlights` + `<SourcesToggle sources={B.highlightsSources} />`
- `B.whyItMatters` + `<SourcesToggle sources={B.whyItMattersSources} />`
- `B.otherSide` + `<SourcesToggle sources={B.otherSideSources} />`
- `B.whatsNext.text` + `<SourcesToggle sources={B.whatsNext?.sources} />`

### Frontend: `products/osint/design/night-desk/src/index.css`

Added after `.record .t .src`:
- Clickable timeline row styles (`.record a.r`)
- bl-cell colour variants: `bl-support` (green), `bl-attack` (red), `bl-pressure` (amber)
- `a.bl-cell` hover style
- `.sblk-src` / `.sblk-src-btn` / `.sblk-src-list` / `.sblk-src-item` / `.src-outlet` / `.src-title` — the full Sources toggle component styles

---

## System Architecture (relevant parts)

```
OSINT product lives at:  products/osint/
Backend:                 products/osint/backend/   (FastAPI, port 8002)
Night-desk frontend:     products/osint/design/night-desk/src/   (Vite+React)

Key backend flow:
  GET /api/brief/home
    → home_cache.py (caches for 5 min)
      → home_sections.py:build_home()
          → compute_posture()   # stance metrics
          → score_relevant()    # ranked articles
          → _fetch_article_urls()  # NEW: resolves URLs
          → _what_happened()    # timeline events
          → build_briefing()    # assembles all sections
          → build_players()     # ally/foe table
          → build_six()         # six-panel cards

Frontend env var:  VITE_BRIEF_API  (points to port 8002)
```

---

## Deployment State on Hetzner

- **Server:** `root@178.105.63.154` (SSH key: `~/.ssh/rig_hetzner`)
- **Backend container:** `osint-backend` — rebuilt and healthy as of 2026-06-08 ~13:30 UTC
  - Compose file: `/root/rig/infrastructure/docker-compose.yml`
  - Image: `infrastructure-osint-backend`
  - Rebuild command: `cd /root/rig/infrastructure && docker compose build osint-backend && docker compose up -d osint-backend`
- **Frontend:** static files at `/root/rig/night-desk-dist/` — deployed 2026-06-08 ~13:30 UTC
  - Served by `rig-caddy` container
  - To redeploy frontend: build locally (`npm run build` in `products/osint/design/night-desk/`), then SCP `dist/` to `/root/rig/night-desk-dist/`

---

## Known Issues / Caveats

1. **URLs may be empty strings** — `score_relevant()` returns articles; if the `url` column is NULL in the DB, cards won't be clickable (they render as plain `<div>`). This is correct graceful-degradation behaviour.
2. **`_fetch_article_urls` fetches top-10 ranked only** — if the attack-origin article is ranked 11+, its URL is still fetched separately via `ao_id`. Cards 11–40 in the pool have no URL (not used in cards anyway).
3. **Hetzner git state is diverged** — the server has local uncommitted changes + untracked files in `products/osint/`. Do NOT `git checkout` or `git pull` directly on Hetzner without stashing first. The safe deploy path is: build locally → SCP files → rebuild container.
4. **Cache TTL** — `home_cache.py` caches the home response for ~5 minutes. After container restart, the first request builds fresh; subsequent requests are cached.

---

## What a New Chat Should Know

- This is an **intelligence briefing product** for political/media clients. "You" = the principal (politician/entity being tracked). "Coverage" = news articles about them.
- The backend computes **posture metrics** (stance, attack origination, issue ownership, friend/foe/fence, quote selection bias, trajectory) from article signals in the DB.
- `build_briefing()` is **purely deterministic** — no LLM calls. It assembles prose from the metric values using conditional logic. This is intentional (fast, auditable, no hallucination risk).
- The `products/osint/` directory is a **separate product** from the main `backend/` FastAPI app. They share the same Postgres DB but run as separate containers.
- The night-desk frontend (Vite+React at `products/osint/design/night-desk/`) is the **live production app** — not `products/osint/frontend/brief-next/` (that is a Next.js experiment, not in production).
