# RIG — Master session handoff (OSINT + Rig Wire + Database)

_Paste the companion `new-chat-starter-prompt.md` into a fresh chat, then keep this doc open. It gives a
new session everything needed to work exactly like the current one._

---

## 0. Working style (how to behave)
- You are a hands-on staff engineer for RIG. **Act, then verify** — never claim something works without
  proving it (query the DB, curl the live URL, read the rendered page). Report failures honestly.
- The user moves fast and wants things **done**, not just planned. Prefer doing + showing proof.
- For news-AI architecture calls, the `aryan-mehta-news-ai` skill persona is the house style.
- **Verify pattern:** box changes → SQL query to confirm; frontend → `curl --resolve` the live site or
  run the dev server via `preview_start` and read the page.

## 1. The two products
**A) OSINT — "RIG Intelligence API"** (the client-facing product)
- Live: `https://api.rig360media.com/v1` (health 200). Served by container **`osint-backend`**.
- Code: `products/osint/backend/v1/`. Auth: `Authorization: Bearer <key>` or `X-API-Key`
  (`rig_live_*` / `rig_test_*`, HMAC-hashed). Per-org scope, rate-limit + monthly quota, sandbox flag,
  tenant isolation, signed webhooks (`whsec_`).
- ~28 endpoints: entities, articles, cuttings, clips, **stories** (v9 clusters+timeline+outlets),
  **brief** (today/situation/daily), **geo** (districts), **analytics** (topics/outlets/sentiment/
  coverage/keyword-sentiment), scope (GET/PATCH/purge), usage, webhooks.
- Handover package: `docs/handoffs/client-api/` (openapi.json, Postman, PDF, HTML). Build docs:
  `docs/handoffs/client-api-build-{plan,spec}.md`, `client-api-data-quality.md`.
- **Clients (analytics.orgs / api_keys / org_api_scope / api_usage_events):** 4 orgs.
  - `31ad3fa9` = **Telangana CM & Government** (LIVE, healthy, active daily from GCP python-httpx;
    100% success; leans on cuttings+articles+stories; only pain = `/v1/stories` ~5.9s slow).
  - `71589824` = **TELANGANA-SANDBOX** (your own QA org — keys `qa-*`; its 429/404/injection-probe
    "errors" are intentional local tests from 127.0.0.1; NOT a real client, NOT a breach).
  - `f0dddedb` = Karnataka; `f49ee4fa` = all-entities/internal.
- Known API to-dos: cache slow `/v1/stories` & `/v1/analytics/keyword-sentiment` (~32s);
  `api_ready_at` + bump-on-change sync cursor; credibility flag (absent); sentiment is entity-gated
  (~28% global / ~50% regional — frame honestly).

**B) Rig Wire — DNL (Democracy News Live)** + the **CMS**
- Reader site: Vercel app, live at **`https://global.democracynewslive.com`** (repo
  `Desktop/rig-news`, project `democracy-news-live`). `/long-read` is the home (served at `/` via a
  rewrite). Pipeline: RSS/HTML → articles → LaBSE cluster (`story_clusters_v8`) → LLM generate
  (`story_generated_v8`, Cerebras gpt-oss-120b) → front page (`src/lib/worldwide/ranking.ts`).
- **CMS = `Desktop/rig-cms`** (separate standalone Next.js app, own login argon2+jose vs shared
  `auth.users`, product switcher, port 3400) AND the embedded `/studio` in rig-news. Both read the
  canonical **`editorial.decisions`** table (migration `rig-news/migrations/005`). Editorial changes are
  audited + reversible (`editorial.audit`). DNL still writes `rigwire.editorial_overrides`; a DB trigger
  mirrors into `editorial.decisions(product='dnl')`.

## 2. Infrastructure & access
- **The box** (does everything): `178.104.145.135` (NEW prod box; `.154` is OLD/stale — ignore).
  SSH: `ssh -i ~/.ssh/rig_hetzner -o StrictHostKeyChecking=no root@178.104.145.135`.
- **Containers:** `rig-postgres` (Postgres+pgvector, all box data), `rig-backend` (FastAPI + Celery
  workers + Beat + the LLM pool for DNL gen), `osint-backend` (the client API), `mc-backend`,
  plus searxng/freshrss/frontend. Query DB: `docker exec rig-postgres psql -U rig -d rig -c "<sql>"`.
- **Databases:**
  - **Box `rig` db = source of truth.** Schemas: `public` (articles, sources, article_*), `analytics`
    (story_clusters_v8, story_generated_v8, story_dedup, merge_verdicts, orgs, api_keys, org_api_scope,
    api_usage_events), `rigwire` (editorial_overrides, image_checks, domain_reputation), `editorial`
    (decisions, audit — the canonical CMS table), `auth` (users: id,email,password_hash,role).
  - **Neon = DNL read-mirror** (serverless, 512MB, bounded). Host
    `ep-nameless-unit-asq9rdsa...neon.tech/neondb`. The deployed DNL reader reads Neon; **editorial +
    OSINT API read the BOX.** Sync: box cron `dnl_neon_sync.sh` (:*/20) + `dnl_neon_imagechecks.sh`.
- **Local run of DNL/CMS against the box** (for verifying UI): additive box role **`cms_dev`**;
  creds in `rig-news/.env.local` and `rig-cms/.env.local` (gitignored). Launch configs in
  `rig-surveillance/.claude/launch.json`: `dnl-dev` (port 3300), `rig-cms` (3400). Auth bypass for local
  only: env `CMS_DEV_EDITOR=1` (INERT in production — guarded by `NODE_ENV!=='production'`).
- **Secrets live in files the new session can read on this machine:** SSH key `~/.ssh/rig_hetzner`;
  box DB roles in `/root/rig/infrastructure/.env`; app DB URLs in `rig-news/.env.local` &
  `rig-cms/.env.local`; Neon string appears in box `/root/rig/scripts/dnl_neon_*.sh`. Never commit these.

## 3. What was built/fixed this session (recent state)
- **DNL images:** watermark leak root-caused (scanner had no ORDER BY → 68% unscanned; classifier
  false-negatives). Fix: prioritized scan (`dnl_image_scan.py` ORDER BY rep+recency) + curated domain
  denylist (`dnl_neon_imagechecks.sh`, flag_rate≥0.9 overrides "clean") + code in ranking.ts/detail.ts.
- **DNL sections:** "1 story / looks empty" = front-end de-dup starvation + placeholder heroes, NOT
  supply. Fixed: `TOPIC_SECTION_MAX=24` buffer + band leads with an image-bearing card. Section-backfill
  (`worldwide_backfill.py`, cron :12/:42) fills thin topics from small clusters.
- **Front-page health guardrail:** box cron `dnl_frontpage_health.sh` (:10/:40) checks live page
  (placeholders/watermarks/empty sections) + self-heals.
- **CMS:** migration 005 canonical `editorial.decisions`; standalone `rig-cms` app built + verified;
  views `/lens/[id]` (timeline/bias/perspectives), `/merges`, `/sources`. Only remaining: deploy rig-cms
  to a domain (needs user Vercel/DNS).
- **Iran attack story** under-surfaced (fragmentation + flagship HELD on one fact) → pinned "A Summer of
  Fire" via the editorial override (reversible) to demo the CMS.
- Added 30+ biz/tech/finance RSS sources (`public.sources`, collect_rss_direct every 30 min).

## 4. Gotchas / rules
- **Newest box, not .154.** **Editorial + API read box, DNL reader reads Neon** — mind which DB.
- Neon sync TRUNCATE+copies — never write app data straight to Neon; write box, let sync propagate.
- `public.sources` has UNIQUE(domain); collector auto-deactivates dead feeds.
- moneycontrol/financialexpress/zeebiz/gadgets360 hard-403 the datacenter IP (verify feeds FROM box).
- Full memory index: `~/.claude/projects/C--Users-Dell-Desktop-rig-surveillance/memory/MEMORY.md`
  (per-topic files there have deep detail). Project rules: `rig-surveillance/CLAUDE.md`.
