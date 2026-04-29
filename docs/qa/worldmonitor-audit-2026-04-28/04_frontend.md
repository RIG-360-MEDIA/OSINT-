# 04 — Frontend smoke (Step 4)

**Verdict: FAIL — BLOCKER (CSP frame-ancestors mismatch in dev).**
Plus several config/topology gaps.

## What I could verify

### Route gating ✓
- `GET http://rig-frontend:3000/worldmonitor` (anon) →
  `307 → /login?next=/worldmonitor`. Middleware redirect works.
- Middleware at `frontend/src/middleware.ts`:
  - First reads Supabase session via `@supabase/ssr` cookie.
  - Then calls `${NEXT_PUBLIC_API_URL}/api/me/access` to enforce
    page allowlist. Bounces non-allowed pages to `/brief?denied=…`.
- The `/worldmonitor` slug is in ROUTE_TO_SLUG map ✓.

### Page structure ✓ (code review)
- `frontend/src/app/worldmonitor/page.tsx:18` reads `?scope=`
  query param; defaults to `telangana`.
- Renders `<Navigation />` then either `<TelanganaBriefing>` or
  `<GlobalView>`.
- `useEffect` (line 24) keeps URL `?scope=` synced with state.
- TelanganaBriefing.tsx (713 LOC) — confirmed components: Dateline,
  StabilityNumber, DoorRow (Live/Map/Data), LiveChannelsDrawer,
  DataDrawer, DrawerShell.
- LiveChannelsDrawer (line 334) **does** have AbortController
  cleanup (`return () => ctrl.abort()`) — Phase-1 plan claim was
  wrong.

### Backend reachability from middleware (D-17)
- `rig-frontend` env: `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000`.
- `127.0.0.1:8000` from inside the rig-frontend container → no
  listener → connection refused.
- Middleware `try { fetch(...) } catch { return supabaseResponse }`
  swallows the error and **lets the request through**. So the page
  allowlist gate is effectively dead in dev:
  any signed-in user can reach `/worldmonitor` even if not in their
  `user_page_access`.
- Also affects the onboarding gate (same code path).
- **D-17 (HIGH)**: middleware API_URL must point to
  `http://rig-backend:8000` for SSR/middleware. The browser-side
  variable can stay `127.0.0.1:8000` because the host port-maps it.

### WorldMonitor iframe (Global view) — BLOCKER
- Iframe target: `rig-worldmonitor` container, port 8080 internal,
  mapped to host **3001**.
- Frontend served on host **4000** (per `docker ps`:
  `0.0.0.0:4000->3000/tcp`).
- Probe of `http://rig-worldmonitor:8080/`:
  ```
  Server: nginx/1.28.3
  Content-Security-Policy: frame-ancestors 'self' http://localhost:3000
  X-Frame-Options: <missing>
  ```
- **The CSP allows embedding from `localhost:3000` only**, but the
  user accesses the frontend at `http://localhost:4000`.
  Browsers will refuse to render the iframe → Global view shows a
  broken / blank embed.
- **D-18 (BLOCKER)**: nginx config in the rig-worldmonitor image
  must include `http://localhost:4000` in `frame-ancestors`, or be
  templated from `FRONTEND_ORIGIN` env. Production deploys will
  also need their actual origin added.

### WorldMonitor sidecar health (rig-worldmonitor)
`GET http://rig-worldmonitor:8080/api/health`:
```json
{
  "status": "UNHEALTHY",
  "summary": {"total": 138, "ok": 73, "warn": 25, "crit": 40}
}
```
- **40 EMPTY feeds** (no records ever): outages, sectors, etfFlows,
  climateAnomalies, climateAirQuality, …
- **14 STALE_SEED**: earthquakes (48 min old, max 30), positiveGeoEvents,
  riskScores, insights, cryptoQuotes
- **11 EMPTY_ON_DEMAND** (lazy — acceptable): serviceStatuses,
  chokepoints, minerals, giving, usniFleetStale
- **72 OK**, 1 OK_CASCADE, 1 UNHEALTHY composite.

The user toggling to "Global" sees a dashboard with **70% of feeds
in some non-OK state**. Some categories are entirely blank.

**D-19 (BLOCKER)**: rig-wm-seeder is not refreshing 14 feeds
on schedule (STALE_SEED) and 40 feeds have never seeded (EMPTY).
Investigate seeder logs / source adapters.

### Browser-rendered checks I could not run
End-to-end click-through (open drawer, cycle channels, press Esc,
toggle scope) requires a real Supabase session. The dev container
has no `SUPABASE_JWT_SECRET`, but cookie-based middleware uses the
**Supabase project's** signing — not bypassable from the test
harness without a real signup. **D-20 (MEDIUM)**: add a test
fixture / Storybook page that renders the worldmonitor page with a
mocked Supabase session, so e2e tests can run in CI.

## Defects added
| ID | Sev | Title |
|---|---|---|
| D-17 | HIGH | Frontend middleware can't reach backend from container — API URL env wrong; access checks silently bypass |
| D-18 | **BLOCKER** | rig-worldmonitor CSP `frame-ancestors` only allows `localhost:3000`; frontend runs on `localhost:4000` → iframe blocked |
| D-19 | **BLOCKER** | WM dashboard health UNHEALTHY: 40 EMPTY feeds, 14 STALE_SEED — seeder failing |
| D-20 | MEDIUM | No way to e2e-test the worldmonitor page without a real Supabase login; missing test harness |
| D-21 | INFO | Phase-1 plan claim "no AbortController in LiveChannelsDrawer" — incorrect; cleanup is present at line 334 |
