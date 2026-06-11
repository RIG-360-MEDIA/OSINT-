# New-Chat Kickoff — OSINT Brief Product (Cleanup + Build)

> Copy this entire file into the new chat as your first message. You will:
> (1) clean up the repo structure, (2) verify what's already built, (3) build the production brief-app frontend + backend wired to live data.

---

## TL;DR — what you're doing

There's a rig-surveillance data platform (~119K articles + 240K claims + every other intelligence extraction you'd want) sitting in PostgreSQL on a Hetzner server. You're building the **production OSINT brief product** on top of it — a multi-edition (5×/day) intelligence digest. There's already a partial static React design in `brief-app/`. Your job: clean up the repo + turn that static design into a live production frontend + backend wired to the database.

You have **READ-ONLY** DB access via a dedicated PostgreSQL role. **You cannot harm the data** — Postgres enforces it. You have **FULL** access to build whatever you need in `products/osint/`.

---

## Situation overview (read once, then refer back)

### The data platform (already built, don't touch)

- **Hetzner server** at `178.105.63.154`. SSH: `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154`
- **PostgreSQL 16 + pgvector** running in `rig-postgres` Docker container, host port `5433`
- **~119K articles** indexed, ~30K processed today through substrate v3 extraction
- **A drain process is currently running** in `rig-backend` container — processing ~52K pending articles. **DO NOT KILL IT** — it has nothing to do with your work but lives in the same container
- **Collectors are paused** via SIGSTOP — fine, you don't need fresh articles to build the UI
- **Data structure:** every processed article has `summary_preview` (50 chars), `summary_snippet` (200 chars), `summary_executive` (700 chars), `primary_subject`, `article_type`, `register_style`, `register_emotion`, `author_name`, plus child rows in `article_claims` (SPO triples), `article_quotes`, `article_locations`, `article_events`, `article_numbers`, `article_stances`. Migration 075 added `articles.source_country` (ISO 3166 alpha-2)

### What's been recently shipped (so you know context)

- **D1 fix (2026-05-27):** substrate now extracts proper subject-predicate-object triples (was 14% complete, now 99%)
- **Migration 072:** `effective_event_date` smart year-fix on `article_events`
- **Migration 073:** entity_type + unit deduplication
- **Migration 074:** location_scope derived column
- **Migration 075:** source_country on articles
- **Migration 076:** YOUR read-only DB role (`analytics_user`) + `analytics` sandbox schema

### What exists for brief-page work

| Location | What | Status |
|---|---|---|
| `brief-app/` (current) → `products/osint/frontend/brief-app/` (after step 1 below) | **Standalone React app — ~98 KB app.jsx + 282 KB CSS + image assets + rendered HTML mockups**. This is THE canonical design. | KEEP. Iterate on this. |
| `frontend/` | Old Next.js app with 3 incompatible designs (KPI dashboard, markdown-LLM brief, multi-edition). Not your concern. | ARCHIVE (step 1 below). |
| `backend/routers/brief_router.py` | Old backend KPI dashboard endpoints | IGNORE — too coupled to abandoned design |
| `docs/coverage/*.html` | Earlier design exploration mockups (palette, no-lines, etc.) | Read for context if useful |
| `docs/newsroom/wall-mode.html`, `docs/readout/morning.html` | More design exploration | Reference if useful |

---

## STEP 1 — Clean up the repo (do this FIRST, 5 minutes)

Run these on the user's laptop (the user will paste them). Tag first so it's reversible:

```bash
cd /c/Users/Dell/Desktop/rig-surveillance

# Safety tag
git tag pre-cleanup-2026-05-28

# Create the product home
mkdir -p products/osint/frontend products/osint/backend products/osint/queries

# Move brief-app to its proper location
git mv brief-app products/osint/frontend/brief-app

# Archive all the OLD stuff that confuses things
mkdir -p archive
git mv frontend archive/old-frontend-nextjs
git mv world-monitor archive/world-monitor
git mv blog-site archive/blog-site
git mv scratch archive/scratch
rm -rf .claude/worktrees

git add -A
git commit -m "cleanup: archive old frontends + scaffold products/osint/"
```

After this the repo has only 3 things that matter:
- `backend/` — data engine (the drain runs from here). **YOU DON'T TOUCH THIS.**
- `products/osint/` — your domain
- `archive/` — old stuff hidden away

---

## STEP 2 — Verify what's already there BEFORE writing code

Don't assume anything. Audit what exists:

```bash
# What's in your new product area?
ls -la products/osint/frontend/brief-app/
ls -la products/osint/backend/    # empty, you'll build
ls -la products/osint/queries/    # empty, you'll build

# Read the canonical design files (don't skim — actually understand)
# Open and read in this order:
# 1. products/osint/frontend/brief-app/README.md
# 2. products/osint/frontend/brief-app/Morning Brief.html  (rendered output target)
# 3. products/osint/frontend/brief-app/app.jsx             (main React component — ~98 KB)
# 4. products/osint/frontend/brief-app/primitives.jsx      (shared cards/components)
# 5. products/osint/frontend/brief-app/data.js             (mock dataset — tells you what fields the cards EXPECT)
# 6. products/osint/frontend/brief-app/styles.css          (full styling)
# 7. products/osint/frontend/brief-app/Top Bar Exploration.html  (top-bar design study)
# 8. products/osint/frontend/brief-app/images/             (story imagery + entity portraits)

# Browse additional design references
ls docs/coverage/   # demo-no-lines-v3.html, palette-options.html, etc.
ls docs/newsroom/
ls docs/readout/
```

**Output:** Write your findings to `docs/BRIEF_PRODUCT_BUILD_PLAN.md`:
- Tech stack of current brief-app (vanilla React? Vite? plain HTML?)
- Data shape expected by the cards (from `data.js`)
- Design intent (what the Morning Brief looks like rendered)
- Recommended migration: keep vanilla React + Vite, or migrate to Next.js?
- Backend API endpoints needed (list them)
- SQL views needed in `analytics` schema (list them)

Wait for user approval on the build plan before writing code.

---

## STEP 3 — Connect to the database

Connection details:

```
Username:  analytics_user
Password:  OCSjtTucdWQ83UOKHiMX6wsifVWxFH
Host:      178.105.63.154 (Hetzner) port 5433
Database:  rig
Schema:    public (read-only) + analytics (your sandbox, full RW)
```

Easiest way from your laptop — SSH tunnel:

```bash
# Terminal 1 — keep this open
ssh -i ~/.ssh/rig_hetzner -L 5433:rig-postgres:5432 root@178.105.63.154 -N

# Terminal 2 — connect
psql "postgresql://analytics_user:OCSjtTucdWQ83UOKHiMX6wsifVWxFH@localhost:5433/rig"
```

Verify access:

```sql
SELECT COUNT(*) FROM articles WHERE substrate_status='ok';  -- ~40,000+
SELECT current_user;                                         -- analytics_user
CREATE TABLE analytics.test_access (id int);                 -- should succeed
DROP TABLE analytics.test_access;                            -- should succeed
INSERT INTO articles (id) VALUES (gen_random_uuid());        -- should FAIL with "permission denied"
```

If the last one fails with permission denied → safety net working. You're good.

---

## STEP 4 — Build the production brief product

### Architecture you'll build inside `products/osint/`

```
products/osint/
├── frontend/
│   └── brief-app/                ← iterate on the standalone React app
│       ├── (existing files — refactor as needed)
│       ├── package.json          ← add proper build pipeline (Vite recommended)
│       ├── vite.config.js
│       ├── Dockerfile            ← for production deploy
│       └── src/
│           ├── api/              ← thin client for products/osint/backend
│           ├── components/       ← refactored card components
│           ├── hooks/            ← TanStack Query / SWR data fetching
│           └── App.jsx           ← new main shell
│
├── backend/                      ← brand new FastAPI service
│   ├── main.py                   ← FastAPI app
│   ├── db.py                     ← psycopg connection pool to analytics_user
│   ├── routers/
│   │   ├── articles.py           ← GET /v1/articles
│   │   ├── briefs.py             ← GET /v1/briefs/today
│   │   ├── entities.py
│   │   └── countries.py
│   ├── Dockerfile
│   └── requirements.txt
│
└── queries/
    ├── 001_brief_card_view.sql       ← materialized view for fast brief queries
    ├── 002_country_aggregates.sql
    └── README.md                     ← docs for analytics-schema artifacts
```

### Tech-stack decisions you make

- **Frontend framework:** the existing brief-app is vanilla React. Options: (a) keep it + add Vite for production build, (b) migrate to Next.js 15. Recommendation: (a) — less migration risk, faster to ship
- **Backend framework:** FastAPI (matches rig style; user is already familiar)
- **Data fetching:** TanStack Query (preferred) or SWR — for stale-while-revalidate
- **Pagination:** cursor-based (NOT offset — when scrapers resume, articles flow continuously)
- **Polling interval:** 60-120s for live updates

### Live-update architecture (bake in from day 1)

When scrapers resume and new articles flow into PostgreSQL, the brief page must show fresh content **without code changes**. Patterns:

- TanStack Query with `staleTime: 60_000`, `refetchInterval: 120_000`
- Cursor pagination: `?cursor={collected_at}__{id}&limit=20` (NOT offset)
- "Last updated X min ago" badge top-right
- Freshness filter chips: Last 6h / Last 24h / Last 7d / All time
- Country filter chips using `articles.source_country` (IN / GB / CN / XX / etc.)
- Multi-edition routing: `/brief?edition=morning|midmorning|lunch|afternoon|evening`
- Optimistic UI for save/dismiss/share actions

### Brief card design (from `data.js` + `Morning Brief.html`)

Match the EXISTING design. Don't redesign from scratch. The current static design is the canonical look — your job is to wire it to live data.

---

## STEP 5 — Production deployment

Add new Docker services to `infrastructure/docker-compose.yml` (alongside existing rig-postgres, rig-backend, rig-frontend). Don't modify existing services:

```yaml
osint-backend:
  build: ../products/osint/backend
  environment:
    - DATABASE_URL=postgresql://analytics_user:${ANALYTICS_DB_PASSWORD}@rig-postgres:5432/rig
  ports:
    - "8002:8000"
  depends_on:
    - rig-postgres

osint-frontend:
  build: ../products/osint/frontend/brief-app
  environment:
    - API_URL=http://osint-backend:8000
  ports:
    - "3001:3000"
  depends_on:
    - osint-backend
```

Deploy:
```bash
ssh -i ~/.ssh/rig_hetzner root@178.105.63.154
cd /root/rig
git pull
docker compose -f infrastructure/docker-compose.yml up -d osint-backend osint-frontend
docker logs --tail 50 osint-backend
```

---

## DO NOT touch

- **`backend/` folder** — that's the data engine. The drain process is currently running there. If you `import backend.X`, you've gone wrong.
- **`scripts/migrations/*` files for `public.*`** — schema changes need coordination with the user / platform team
- **`infrastructure/docker-compose.yml` rig-backend service** — don't modify; just add new services beside it
- **Trijya server** (`100.92.126.27`) — that's the GPU box hosting Ollama. Not your concern.
- **Cron jobs** — leave them
- **Anything in `archive/`** — old stuff, archived for safety, not for your use

## DO NOT do

- Use Cerebras / Groq / Ollama from your backend — those are the platform's LLM resources. Your product reads finished data from the DB; doesn't need to call LLMs itself
- Run any code that calls yt-dlp / transcript-api — burns YouTube IP reputation
- Re-enable Playwright (it's disabled due to memory leak)
- SSH to Trijya with the password from `Connection_Guide.pdf` — security policy. Hand the user a PowerShell script to paste if needed
- Restart `rig-backend` container — would kill the drain. Only restart the new `osint-backend` / `osint-frontend` services you create

## Useful starter queries (run via your psql connection)

```sql
-- 20 most recent fully-extracted English news articles
SELECT id, title, summary_snippet, source_country, published_at
  FROM articles
 WHERE substrate_status = 'ok' AND extraction_version = 3
   AND article_type = 'news' AND language_iso = 'en' AND NOT is_duplicate
 ORDER BY collected_at DESC
 LIMIT 20;

-- Article + its substrate output (single article shape)
SELECT
  a.title, a.summary_executive, a.primary_subject, a.register_style,
  (SELECT json_agg(json_build_object('s', subject_text, 'p', predicate, 'o', object_text))
     FROM article_claims WHERE article_id = a.id) AS claims,
  (SELECT json_agg(json_build_object('speaker', speaker_name, 'quote', quote_text))
     FROM article_quotes WHERE article_id = a.id) AS quotes,
  (SELECT json_agg(json_build_object('city', city, 'country', country))
     FROM article_locations WHERE article_id = a.id) AS locations
FROM articles a
WHERE a.id = '<some-uuid>';

-- Country breakdown of last 24h
SELECT source_country, COUNT(*) FROM articles
 WHERE collected_at > NOW() - INTERVAL '24 hours'
 GROUP BY 1 ORDER BY 2 DESC;
```

---

## Quality checklist before declaring "done"

- [ ] Step 1 cleanup committed
- [ ] Step 2 build plan written to `docs/BRIEF_PRODUCT_BUILD_PLAN.md` + approved by user
- [ ] Step 3 DB access verified (read works, write blocked)
- [ ] brief-app builds locally with `npm run build`
- [ ] FastAPI backend responds to `GET /health`
- [ ] At least one live brief renders end-to-end with real article data
- [ ] Cursor pagination working (verified with > 20 articles)
- [ ] Country filter works
- [ ] Freshness filter chips work
- [ ] "Last updated X min ago" badge updates
- [ ] Multi-edition routing implemented
- [ ] Loading / empty / error states implemented
- [ ] At least one Playwright e2e test passing
- [ ] Production Docker services deployed to Hetzner via compose
- [ ] No mutation of `public.*` tables (verify in DB write logs)
- [ ] No imports from `backend/` (verify with grep)

## When you finish or get blocked

1. Update `docs/BRIEF_PRODUCT_BUILD_PLAN.md` with what shipped
2. Write `docs/onboarding/12-session-2026-05-29-brief-product.md` with: tech-stack decisions, gotchas encountered, design choices made, anything that should persist
3. Tell the user what shipped + what's left

---

## Quick reference

| Thing | Value |
|---|---|
| Your DB role | `analytics_user` (READ-ONLY on public, RW on analytics schema) |
| Password | `OCSjtTucdWQ83UOKHiMX6wsifVWxFH` |
| DB host | `178.105.63.154:5433` (Hetzner Postgres) — or SSH tunnel to localhost |
| Your code lives in | `products/osint/` |
| Your design source | `products/osint/frontend/brief-app/` (after step 1 move) |
| Repo on Hetzner | `/root/rig/` (git pulled from same origin as laptop) |
| Existing backend | `backend/` — read only for context; **never modify** |
| Old code | `archive/` — safely tucked away |
| LLM platform | not your concern (data is already extracted) |
| Frontend port (when deployed) | 3001 (won't conflict with rig-frontend on 3000) |
| Backend port (when deployed) | 8002 (won't conflict with rig-backend on 8000) |

---

## Start now

1. **Step 1 (cleanup)** — paste the 5 git commands at the top
2. **Step 2 (verify)** — read the brief-app files + write `docs/BRIEF_PRODUCT_BUILD_PLAN.md`
3. **Wait for user approval on the build plan**
4. **Then Step 3-5 (build + deploy)**

Good luck. Build something the analysts will actually use.
