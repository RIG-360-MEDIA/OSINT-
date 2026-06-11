# Boss's Brief — Build Plan

**Goal:** ship a working version of the boss's Morning Brief frontend, locally viewable, with a clear feature-by-feature build sequence, fully isolated from the existing rig-surveillance production app.

## Architecture (chosen)

```
┌─────────────────────────────────┐         ┌──────────────────────────────────────┐
│  YOUR LAPTOP — local browser    │         │  HETZNER — production backend        │
│  http://localhost:5173          │  HTTPS  │  https://robin-osi.rig360media.com   │
│                                 │ ───────►│                                       │
│  brief-app/ (boss's frontend    │         │  /api/brief/*  (NEW namespace,        │
│  with React+Babel via CDN +     │         │   completely separate from            │
│  Vite dev server)               │         │   /api/observe/*)                     │
└─────────────────────────────────┘         └──────────────────────────────────────┘
```

**Why this layout:**
- **Local frontend = instant feedback**, no SSH, no deploy lag — refresh browser, see change
- **Backend on Hetzner = real data**, no need to copy 100K-article corpus to laptop
- **`/api/brief/*` namespace = full isolation** from production /observe and other pillars
- **CORS on Hetzner = single-line add** to allow localhost:5173

## What we put where

| Component | Location | Notes |
|---|---|---|
| New folder `brief-app/` | `C:\Users\Dell\Desktop\rig-surveillance\brief-app\` | Copy boss's files exactly, untouched at first |
| New backend router | `backend/routers/brief_router.py` | New API namespace; doesn't touch existing routers |
| New backend helpers | `backend/observability/brief_helpers.py` | All the brief-specific SQL queries |
| Frontend dev server | Vite (faster than CRA, instant HMR) | `npm install vite -D` in brief-app/ |
| Production link | NOT TOUCHED initially | Only after the boss approves the local version |

## Day 0 — Setup (~30 min)

1. Create `brief-app/` folder
2. Copy all boss's files (`app.jsx`, `data.js`, `primitives.jsx`, `styles.css`, `Morning Brief.html`, `image-slot.js`)
3. Add `package.json` with Vite as dev dependency
4. Run `npm run dev` → opens `http://localhost:5173`
5. **Verify**: boss's design loads, all 47 components render with MOCK data
6. **Gate**: visual match with boss's screenshot

## Day 1 — Backend bridge (~2 hr)

1. Create `backend/routers/brief_router.py` with one stub endpoint:
   ```
   GET /api/brief/dashboard
   ```
   Returns the EXACT shape of boss's `RIG_DATA` object (initially with hardcoded mock data identical to `data.js`)
2. Add CORS for `http://localhost:5173` to backend
3. In `brief-app/data.js`: change `RIG_DATA = {...mock...}` → `RIG_DATA = await fetch('/api/brief/dashboard')`
4. **Verify**: frontend now pulls mock data from backend instead of static file
5. **Gate**: same UI, but data flows through the API — proven E2E plumbing works

## Day 2 onwards — Feature-by-feature swap

**One feature at a time**, in order from cheapest to richest:

| Order | Feature | What changes |
|---|---|---|
| 1 | KPI tiles (articles/outlets/languages/sentiment) | Stub returns real counts from `/api/observe/corpus-overview` |
| 2 | Watched Entities (8 Telangana politicians) | Read `entity_mention_daily` for the 8 hardcoded entities |
| 3 | Climbing Stories | Same table, surge_ratio filter |
| 4 | Defining Stories (top 5) | `event_clusters` by `importance_score` |
| 5 | Per-story sparkline (24h velocity) | New aggregation endpoint |
| 6 | Voices Overnight | `article_quotes` last 12h |
| 7 | Horizon 7-day calendar | `article_events` future |
| 8 | Coverage Matrix | source × cluster join |
| 9 | Recommended Reading | filter analysis articles |
| 10 | Mini India map | `article_locations` by state |
| ... | (38 more) | each is a separate PR-sized change |

**For EACH feature:**
1. I write the backend query + endpoint
2. I update one section of `brief-app/data.js` to fetch from that endpoint
3. **You refresh `http://localhost:5173`** and verify the panel now shows real data
4. We sign off → move to next feature

This gives you a **visible green tick per feature**, and you can stop at any time / re-order priority.

## Strict isolation rules

- ❌ **DO NOT** touch any file in `frontend/src/app/observe/*`
- ❌ **DO NOT** modify any existing `/api/observe/*` endpoint
- ❌ **DO NOT** touch production deployment files
- ✅ **ONLY** new files in `brief-app/` and `backend/routers/brief_router.py` + `backend/observability/brief_helpers.py`
- ✅ Single CORS line addition in `backend/main.py` to allow localhost (no other changes)

## When you say "ship"

After all features green locally:
1. Deploy `brief-app/` to its own subdomain (`brief.rig360media.com`) — separate from production
2. Or merge into the main rig-surveillance frontend as a route `/brief` (your call)
3. Either way, **no impact on existing `/observe`**

## What this approach gives you

- ⏱️ **Feature visible in minutes, not days** (Vite HMR + browser refresh)
- 👀 **You can check after every change** at `http://localhost:5173`
- 🛡️ **Zero risk to production** — entirely separate namespace + folder
- 📝 **Clear per-feature gate** — sign off one at a time
- 🔁 **Easy rollback** — just stop the dev server, nothing else affected
- 🎨 **Boss's design stays EXACTLY** as he made it (his files copied unchanged at first)
