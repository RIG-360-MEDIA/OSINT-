# Brief App — Production Deployment Plan

## TL;DR

**Three stages, one direction:**

```
NOW (Day 0)             →  DEV/STAGING                →  PRODUCTION
Python http.server         Vite + npm run dev            Vite build → Caddy on Hetzner
http://localhost:5173      http://localhost:5173          https://brief.rig360media.com
No build step              HMR + fast refresh             Minified, cached, CDN-able
Mock data                  Real API                       Real API + auth + monitoring
```

The recommended target is **Option A** below. Two other options are also valid; we pick based on your tolerance for boss-file modifications.

---

## Three production options ranked

### 🥇 Option A — Vite build, deployed to Caddy (RECOMMENDED)

**What changes for boss's code:**
- Replace 3 CDN script tags with `import` statements
- Add `package.json`, `vite.config.js` (~30 lines total)
- Folder structure stays the same; all component files barely touched

**Build pipeline:**
```
brief-app/                    [source]
   ├── index.html
   ├── app.jsx, primitives.jsx, data.js, styles.css
   ├── package.json           (new)
   └── vite.config.js         (new)
                  ↓ npm run build
dist/                         [output — what gets deployed]
   ├── index.html
   ├── assets/index-abc123.js (minified, bundled, hashed)
   └── assets/index-def456.css (minified, hashed)
```

**Deploy:**
- New domain: `brief.rig360media.com` (or `brief-staging.rig360media.com` first)
- Caddy on Hetzner already handles `robin-osi.rig360media.com`; add 5 lines to `Caddyfile`:
  ```
  brief.rig360media.com {
    encode gzip zstd
    root * /var/www/brief-app
    file_server
    header Cache-Control "public, max-age=3600"
  }
  ```
- Cloudflare DNS: A-record points `brief.rig360media.com` → 178.105.63.154
- Caddy auto-TLS handles HTTPS via Let's Encrypt

**CI/CD:**
- GitHub Actions: on push to main, build + rsync `dist/` to Hetzner `/var/www/brief-app/`
- ~3 minutes per deploy, zero downtime

**Pros:**
- ~50× faster first load than CDN+Babel (10KB vs 500KB, no in-browser compile)
- Standard production-grade pipeline
- Caching, gzip, HTTP/2 all handled by Caddy
- Easy to add monitoring (Sentry frontend SDK)

**Cons:**
- Need to convert 3 `<script>` CDN tags to ES module imports (~10 min work)
- Need to add `package.json` (small mental shift from "just HTML files")

**Total effort to ship: 1 day** (after all features built locally)

---

### 🥈 Option B — Integrate as `/brief` route in main rig-surveillance Next.js app

**What changes:**
- Boss's components become Next.js pages under `frontend/src/app/brief/*`
- Reuses existing Supabase auth (super_admin gate or new persona gate)
- Same domain: `https://robin-osi.rig360media.com/brief`

**Pros:**
- One codebase, one deploy pipeline (the rig-surveillance one already in place)
- Auth comes for free
- Server-side rendering (faster initial paint, SEO)
- Shares the `useObservePoll` hook, theme system, etc.

**Cons:**
- Significantly more code rewrite — boss's CDN-style React must become Next.js components
- Couples brief to main app — can't deploy brief without redeploying everything
- Slower dev iteration (Next.js dev server vs Vite)

**Total effort to ship: 3-4 days**

---

### 🥉 Option C — Deploy CDN-style as-is (no build)

**What changes:** nothing in the code.

**Deploy:** Caddy serves the `brief-app/` folder directly. Browser downloads React + Babel from unpkg, compiles JSX in-browser.

**Pros:**
- Zero rewrite — boss's files deploy untouched
- Simplest possible pipeline

**Cons:**
- ~3-5 second first page load (Babel compile in browser is slow)
- Vulnerable if unpkg.com goes down
- No tree-shaking, no minification
- Hard to add monitoring or modern features

**Total effort to ship: 2 hours**
**Not recommended for production**, only for emergency demos.

---

## My recommendation: **Option A**

Reasons:
1. **Fast to ship** (1 day post-feature-complete) and **clean separation** (own domain, own pipeline)
2. **Production-grade performance** out of the box
3. Boss's code structure stays intact — just swap how scripts load
4. Doesn't entangle with existing `/observe` or `rig-surveillance` deploy
5. Easy migration path to Option B later if you decide to consolidate

## Full production checklist for Option A

| Step | Effort | When |
|---|---|---|
| **1. Local dev with mock data** | Already done ✅ | Day 0 |
| **2. Local dev with real API** | 2 hr | Day 1 |
| **3. Build all 47 features locally** | 2 weeks | Day 2-14 |
| **4. Switch from CDN → npm dependencies** (Vite migration) | 30 min | Day 14 |
| **5. Add Sentry frontend error tracking** | 1 hr | Day 14 |
| **6. Add page-level auth gate** (super_admin only) | 2 hr | Day 14 |
| **7. Deploy GitHub Action: build + rsync to Hetzner** | 3 hr | Day 14 |
| **8. Add Caddy block for new subdomain** | 15 min | Day 14 |
| **9. DNS A-record at Cloudflare** | 5 min | Day 14 |
| **10. Smoke test on production URL** | 30 min | Day 14 |
| **11. Set up uptime monitoring** (UptimeRobot/Pingdom) | 15 min | Day 14 |
| **12. Add Cloudflare in front (DDOS / CDN cache)** | 30 min | Optional |

**Total to ship: 1 day of pure deploy work after features are done.**

## Architecture diagram (end state)

```
                    ┌────────────────────────────────┐
                    │  Cloudflare (DNS + CDN cache)  │
                    └──────────────┬─────────────────┘
                                   │
                                   ▼
                    ┌────────────────────────────────┐
                    │  Caddy on Hetzner (HTTPS)      │
                    │   brief.rig360media.com        │
                    │     ↓ serves static /dist/     │
                    │   robin-osi.rig360media.com    │
                    │     ↓ proxies /api/* to        │
                    │       rig-backend container    │
                    └──────────────┬─────────────────┘
                                   │
                                   ▼
                    ┌────────────────────────────────┐
                    │  rig-backend (FastAPI + Celery)│
                    │  /api/brief/* (new namespace)  │
                    │  /api/observe/* (existing)     │
                    └──────────────┬─────────────────┘
                                   │
                                   ▼
                    ┌────────────────────────────────┐
                    │  rig-postgres (the clean data) │
                    └────────────────────────────────┘
```

## What we DON'T do (anti-patterns to avoid)

- ❌ Don't deploy with Babel-in-browser to production (slow, fragile)
- ❌ Don't deploy without HTTPS (Caddy handles it automatically)
- ❌ Don't deploy without auth (anyone could read the principal's brief)
- ❌ Don't embed API keys in the frontend bundle (use httpOnly cookies)
- ❌ Don't deploy without error monitoring (you won't know when it breaks)
- ❌ Don't couple deploy to backend deploy (we want independent rollouts)

## Migration moment: when do we go from local → production?

**Trigger: after all 47 features are built and validated locally.** Not before. The Vite migration + deploy is a single uninterrupted day — don't fragment it.

Until then, **stay on `start.bat` + Python server**. It's the fastest possible iteration loop.
