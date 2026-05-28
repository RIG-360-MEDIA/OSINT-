# OSINT Brief Product — End-to-End Roadmap (2026-05-28)

From "we have a static React mockup + a working data engine" to "public SaaS used by top politicians, PR teams, and analyst firms."

This doc is the **full arc**. Effort estimates are calendar weeks for a focused single builder, not engineer-weeks. They will be wrong; they're directional.

---

## Where we are right now

**Done today (Phase 0):**
- Repo cleaned up (commit `cc6be26`) — brief-app at `products/osint/frontend/brief-app/`, old frontends archived
- Build plan reviewed and Path A chosen (separate backend, read-only DB role)
- Hetzner SSH + `analytics_user` DB access verified end-to-end
- Live API response shapes captured at `docs/api-fixtures/`
- Decision: Next.js 15 frontend (pivoted from Vite — see "Why Next.js" below)

**Starting next:**
- Phase 1 (backend) + Phase 2 (Next.js scaffold) in parallel — both unblock Phase 3 (end-to-end proof)

---

## The arc — 17 phases

### **PHASE 1 — Backend foundation** (3–4 days)
Build a fresh FastAPI service at `products/osint/backend/`:
- `main.py`, `db.py` (async psycopg pool to `analytics_user`), `routers/{kpi,entities,emerging,stories}.py`
- Port the parallel session's SQL from `backend/observability/brief_*.py` (read-only port; don't modify the originals)
- `requirements.txt`, `Dockerfile`
- Match the JSON shapes already captured at `docs/api-fixtures/`
- Connect via SSH tunnel for local dev (`-L 5433:rig-postgres:5432`)

**Gate:** `curl localhost:8002/api/brief/kpi` returns same shape as Hetzner.

### **PHASE 2 — Next.js scaffold** (2–3 days)
New Next.js 15 app at `products/osint/frontend/brief-next/`:
- App router, JSX (not TypeScript yet — keep close to boss's `.jsx`)
- Boss's `app.jsx` becomes a single `"use client"` page component at `app/page.jsx`
- `primitives.jsx`, `data.js`, `styles.css`, `images/` imported into the project untouched
- Replace 3 unpkg `<script>` tags with ES imports
- Convert `window.RIG_DATA` + `window.RIG` globals to module exports
- Add TanStack Query provider
- Replace 4 `useLive*` hooks with `useQuery` (60s stale, 120s refetch)
- Add `"Last updated X min ago"` indicator using `dataUpdatedAt`

**Gate:** Next.js dev server shows pixel-identical visual to current `start.bat` baseline.

### **PHASE 3 — End-to-end local proof** (1 day)
- SSH tunnel + osint-backend local + Next.js local + browser
- All 4 sections (KPI, entities, emerging, stories) populated from live data
- Polling visibly updates the "last updated" badge

**Gate:** Demo-able locally to a stranger; "this works."

### **PHASE 4 — Fill the 20 aggregation endpoints** (2 weeks)
Per `docs/BOSS_BRIEF_GAP_ANALYSIS.md` — 20 sections in boss's design need new SQL aggregations. Sequence by impact:
1. Per-story sparkline (24h velocity per cluster)
2. Coverage breakdown (crit/neutral/supportive % per story)
3. Lens cards (1 quote per outlet × story with stance + language)
4. Cite blocks (3 outlets per story)
5. Story thumbnails
6. Voices Overnight (`article_quotes` last 12h)
7. Horizon 7-day calendar (`article_events` future)
8. Coverage matrix (source × cluster)
9. Recommended Reading (`article_type IN ('analysis','opinion')`)
10. Mini India map (`article_locations` by state)
11. Outlet Bias snapshot
12. Watched-entity sentiment per-entity
13. Watch Summary roll-up
14. Climbing Stories surge windows
15. Telugu vs English Blindspot Comparison
16. Narrative Diversity Score
17. Forecast Pulse aggregation tier
18. Network co-mention edges
19. Mood waveform (sentiment hourly)
20. Per-source integrity (matches `/api/observe/source-scorecard`)

Each endpoint = new SQL view in `analytics.*` + new FastAPI route + frontend `useQuery` swap. **Sign off one at a time.**

**Gate:** every section of boss's design shows real data; no more mock fallbacks except for the 9 LLM-driven sections.

### **PHASE 5 — LLM-driven sections** (1–1.5 weeks)
9 sections need narrative synthesis. New prompts + daily Celery tasks. These tasks live in `backend/` (the data engine) — the brief product reads the results. Sections:
- CM/Driving (which narrative CM is pushing)
- CM/Counter-Pressure (opposition counter strength)
- CM/Perspective (framing)
- Blindspot Key Insights
- Narrative Gap Overview
- Climbing Stories tactical advice ("BRACE FOR EVENING BULLETIN")
- Forecast Pulse
- Horizon Outlook
- Blindspot Insights summary

Estimated LLM spend: ~$5–15 per brief per user per day (Cerebras + Groq).

**Gate:** every section populated; no mock data anywhere.

### **PHASE 6 — Per-story permalinks + archive** (1 week)
Make the brief shareable:
- `/brief/2026-05-28` — full daily brief by date
- `/brief/2026-05-28/story/musi-rejuvenation` — individual story permalink
- `/archive` — browse past briefs
- Open Graph + Twitter Card metadata per page (so links unfurl in WhatsApp / LinkedIn / Slack / Twitter / iMessage with headline + image + summary)
- Server-side render the static parts so unfurl works without JS

**Gate:** paste a story URL into WhatsApp → see a proper card preview with title + image + summary.

### **PHASE 7 — Marketing surface** (1 week)
- `/` — landing page (what RIG OSINT is, who it's for, sample brief preview)
- `/pricing` — tiers
- `/about` — team / company
- `/contact` — lead capture
- All SSR'd, SEO-indexable
- Match the visual identity of the brief itself

**Gate:** a politician's PR head can land on `/` cold, understand the product in 30 seconds, and reach `/contact` or `/pricing`.

### **PHASE 8 — Auth + accounts** (1.5 weeks)
- Supabase auth (matches rig-surveillance ecosystem)
- `/login`, `/signup`, `/forgot-password`, `/account`
- Session middleware gates `/brief/*` routes
- Three tiers: anonymous (preview only), free (1 brief/day), paid (5 editions/day + archive + permalinks)
- Free-tier marker for stories: blur the bottom half, "subscribe to read full" CTA
- Role propagation: backend validates Supabase JWT, gates archive depth

**Gate:** a free visitor sees a partial preview; a paid user sees the full brief.

### **PHASE 9 — Production deploy** (3–4 days)
- New Docker services `osint-backend:8002` + `osint-next:3001` on Hetzner
- Caddy block for `brief.rig360media.com` + `rig360media.com` (marketing)
- Cloudflare DNS + DDoS shield
- HTTPS via Let's Encrypt (automatic with Caddy)
- GitHub Actions: build + rsync `dist/` + Docker push on merge to main
- Database connection pool sized for production traffic (10–25 connections)
- Health checks (`/health` endpoint, Docker `HEALTHCHECK`)

**Gate:** `https://brief.rig360media.com` resolves; a politician can reach it; HTTPS green lock.

### **PHASE 10 — Observability + reliability** (1 week)
- Sentry frontend SDK (client-side errors)
- Sentry backend SDK (FastAPI errors)
- Structured logs from osint-backend → centralised place (read-only DB so no audit overhead)
- Uptime monitoring (UptimeRobot, BetterUptime, or Cronitor)
- Alerts: 5xx rate > 1%, response time > 2s p95, health check fails
- Slack/email alert routing
- Dashboards: requests/sec, error rate, latency p50/p95/p99

**Gate:** when something breaks at 3am, oncall is paged within 5 min.

### **PHASE 11 — Billing + commercial** (2 weeks)
- Stripe Checkout + Customer Portal
- Subscription tiers map to auth tiers
- Webhook handling for subscription state changes
- Invoice + receipt emails
- 14-day trial logic
- Dunning / failed payment handling
- VAT/GST handling for international customers (India GST especially)
- Refund flow

**Gate:** a customer can sign up, pay, get an invoice, cancel, and re-subscribe — all self-serve.

### **PHASE 12 — Mobile responsiveness** (1 week)
Boss's design is desktop-first. Politicians read briefs on phones at 6am.
- Mobile breakpoints (tablet 768px, phone 480px)
- Touch interactions (tap to reveal Lens cards, swipe stories)
- Stack KPI tiles vertically on mobile
- Watched Entities → carousel on mobile
- Test on iPhone 15 + iPhone SE + Android mid-range + iPad
- Print stylesheet (so PR teams can print briefings for principals)

**Gate:** design works at 320px width without breaking.

### **PHASE 13 — Performance** (1 week)
- `next/image` for all images (auto WebP/AVIF, responsive)
- Code splitting per route (marketing pages don't load brief JS)
- CDN caching at Caddy / Cloudflare edge
- API response caching (Redis or just in-memory LRU per worker)
- Database query optimization (EXPLAIN ANALYZE every slow query)
- Lighthouse scores target: Performance 90+, Accessibility 95+, SEO 100
- TTI on 4G < 2 seconds, on broadband < 500ms

**Gate:** brief.rig360media.com page-loads in under 1 second on a 4G phone in Mumbai.

### **PHASE 14 — Security hardening** (1 week)
- Rate limiting on auth + brief endpoints (10 req/min anonymous, 100 paid)
- CORS strict allowlist (`brief.rig360media.com` only in production)
- Content-Security-Policy headers
- HTTPS-only cookies, SameSite=Lax
- CSRF tokens on state-changing endpoints
- Cloudflare DDoS protection enabled
- Dependency audit (`pip-audit`, `npm audit`)
- External security review (have someone outside the team look at it)
- Secrets management: Hetzner has env vars; rotate the analytics_user password before launch

**Gate:** passes a baseline OWASP Top 10 walkthrough.

### **PHASE 15 — Legal + compliance** (parallel, 1 week of focused effort)
This is the phase that DOESN'T live in code but blocks launch:
- Terms of Service (drafted by counsel; reviewed)
- Privacy Policy (GDPR for EU users, India's DPDP Act 2023 for domestic)
- Cookie consent banner (Cloudflare workers, Osano, or hand-rolled)
- Content licensing review — we display headlines + summaries scraped from news outlets. Fair use vs licensing requirements. Defamation risk on LLM-generated narrative synthesis. **Talk to a lawyer.**
- Data retention policy (how long do we keep article data? user activity logs?)
- Right to erasure flow (if a user requests data deletion under DPDP)
- DPO appointment if EU users present

**Gate:** launch counsel signs off in writing.

### **PHASE 16 — Customer onboarding** (1 week)
- Welcome email sequence (day 0, 1, 3, 7)
- Product tour on first login (overlay highlighting sections)
- Help docs / knowledge base (`/help` static pages)
- "Why this story matters" tooltips throughout the brief
- Customer support channel (Intercom embed, or just `support@rig360media.com`)

**Gate:** a new customer becomes active (reads a full brief) within 24h of signup.

### **PHASE 17 — Growth loops** (ongoing)
- Share buttons that drive signups
- Referral program ("invite a colleague → +1 month")
- Newsletter signup on marketing pages (capture leads who aren't ready to pay)
- SEO content (blog posts on political analysis methodology)
- Analytics: PostHog/Mixpanel for product funnel (signup → first brief → repeat read → upgrade → renewal)
- A/B testing pricing, CTAs, brief structure

**Gate:** organic signups growing month-over-month without paid ads.

---

## Timeline estimates

| Stage | Phases | Calendar weeks |
|---|---|---|
| **Foundation** (today's work) | 0–3 | **~1 week** |
| **Product complete** (all sections live with real data, archive, permalinks) | 4–7 | **+4–5 weeks** |
| **Pre-launch readiness** (auth, deploy, observability, security, compliance) | 8–10, 14–15 | **+4–5 weeks** |
| **Public launch + billing** | 11 | **+2 weeks** |
| **Polish + growth** | 12, 13, 16, 17 | **+3–4 weeks ongoing** |

**Realistic public-launch ETA: 12–15 weeks from today** (one focused builder, no surprises).

---

## Open decisions still needed

These don't block Phase 1–3 but should be settled before Phase 6+:

1. **Who picks the political slate?** Brief-app currently hard-codes 4 watched entities (Naidu / Rahul / Akhilesh / Owaisi). Per-customer customization (PR firm picks 8 entities to watch) → multi-tenant data model. Same slate for everyone → single-tenant content engine. **Big architectural fork.**

2. **Editorial control over LLM-generated narrative.** When Phase 5 ships a CM/Driving narrative claim like "The Chief Minister is pivoting to centrist messaging," who reviews that before it hits a politician's PR head's inbox? Defamation liability sits with whoever publishes it.

3. **Citation density.** Every claim in the brief needs to link back to source article(s). Affects both UI (cite-N popovers) and SQL (carrying citation IDs through every aggregation).

4. **Pricing model.** Per-seat, per-account, per-brief? Free preview with paid full? Tiered by entities watched? Affects auth + billing data model.

5. **Multi-edition cadence.** Future-plans §5 says 5 editions/day (06/10/13/17/21 UTC). Boss's design is one "Morning Brief." Do all 5 editions look the same, or does evening differ from morning? Affects Celery task design + UI variants.

6. **International expansion.** Telugu/Hindi/English content. PR firms in Singapore, London, DC. i18n needed at the UI level? Brief content language pinned to source language?

7. **Government / political client contracts.** B2G sales has different procurement cycles (RFPs, security clearances). Different motion than commercial PR firms.

---

## Risks worth thinking about NOW (not at Phase 9)

| Risk | What it could break | Mitigation |
|---|---|---|
| LLM hallucinates a quote and attributes it to a sitting politician | Defamation lawsuit | Cite-N guardrails on every LLM output. Editorial review queue. |
| Drain stops; brief shows stale data; subscribers churn | Reputation + retention | Health-check on data freshness; banner if data older than threshold. |
| Cerebras / Groq / Ollama outages | No new briefs generated | Multi-provider failover (already partially built); paid customers get cached prior-edition. |
| Cloudflare / Caddy / Hetzner outage | Site down | Status page (status.rig360media.com); Cloudflare worker for static fallback. |
| Scrape source goes paywalled or bans us | Source coverage drops | Source health monitoring; auto-fallback to alternative sources. |
| Sensitive PR firm data leak (which entities a customer watches reveals strategy) | Trust + GDPR | Encrypt customer watchlists at rest; audit log all access. |
| News-outlet content licensing dispute | Cease & desist | Pre-launch legal review of fair-use boundary; written outlet partnerships where possible. |
| Politician sues over how they're depicted | Existential | Editorial guidelines; cite-everything policy; PR-firm-only B2B model (vs B2C) limits exposure. |
| Indian DPDP Act enforcement | Fines + service freeze | Compliance review before launch; appointed DPO if scale warrants. |

---

## What I will NOT propose without explicit direction

Surfacing these so they don't quietly creep in:

- **Multi-tenancy** (per-customer entity selection, per-customer briefs) — significantly more complex DB model
- **Internationalization** (Spanish, Mandarin, Arabic markets)
- **Mobile apps** (iOS / Android native — web mobile responsive is the default unless asked)
- **Custom domains** (rig360.com/clientco/brief)
- **API access for customers** (give Reuters/Bloomberg programmatic access to our intelligence)
- **White-label / reseller program**
- **AI chatbot on top of the brief** ("ask anything about today's news") — different product

---

## Phase 1 starts next turn

Specifically:
1. Read parallel session's SQL queries from `backend/observability/brief_{entities,emerging,stories}.py`
2. Scaffold `products/osint/backend/` (main, db, 4 routers, requirements, Dockerfile)
3. Run against SSH tunnel
4. Verify JSON shapes match `docs/api-fixtures/`

Anything to redirect or add before I start?
