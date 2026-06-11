# Brief Page Frontend — New-Chat Kickoff Prompt

> Copy this entire file into the new chat as your first message. It carries every memory from the 2026-05-27/28 session needed to start building the brief page frontend correctly.

---

## What we're doing

Building (or finishing) the **`/brief` page** of the RIG Surveillance frontend. This is the daily intelligence digest each user gets — curated articles from their watchlist with summaries, quotes, locations, events. Inspired by "Particle" but oriented around multi-edition publishing (5 editions per day: 06:00, 10:00, 13:00, 17:00, 21:00 UTC). For govt / PR / MNC analysts in India.

Build needs to be designed so that **when scrapers resume, the page automatically shows fresh data without refactoring**. Live-update architecture baked in from day one.

---

## Step 0: READ ONBOARDING FIRST

Before touching any code, read in order:
- `CLAUDE.md` (repo root) — project-wide rules
- `docs/onboarding/00-README.md` → walk through 01-10 in order
- `docs/onboarding/11-session-2026-05-28-learnings.md` — most recent session's full lessons

That gives you architecture, DB schema, LLM infrastructure, current state, known issues, and the strategic roadmap (brief redesign is roadmap item #5).

---

## Critical project state (as of 2026-05-28 session end)

### What's running

- **Hetzner production** at `178.105.63.154` (SSH key `~/.ssh/rig_hetzner`)
- **TRIJYA-7** at Tailscale `100.92.126.27` — **Windows 11** + RTX 4090. Owner `tdsworks@gmail.com`. We can SSH as `Admin@100.92.126.27` per `Connection_Guide.pdf` BUT the AI is forbidden from using passwords directly — hand the user a PowerShell script to paste in their already-open admin terminal
- **Substrate v3 drain** in progress (~52K articles `substrate_status='pending'`); 30K processed today
- **Collectors workers SIGSTOPed** (paused) — see `docs/PAUSE_INGEST_RUNBOOK.md` for resume procedure

### DB state for brief page work

- **~119K articles** in DB, ~30K with full substrate v3 today
- **100% of v3 articles have** summary_preview / summary_snippet / summary_executive / primary_subject / article_type / register_style / register_emotion / author_name populated
- **99% of claims have SPO triples** (subject_text + predicate + object_text) — post-D1 fix
- **`articles.source_country`** added via migration 075 (ISO 3166 alpha-2) — usable for country filtering
- **`article_events.effective_event_date`** added via migration 072 — usable for timeline grouping
- **`article_locations.location_scope`** derived via migration 074 — city/state/country/continent
- **Country distribution:** 83% IN, 7% XX (global wires), 12% rest of world (UK 19, China 9, others small)

### Tech stack

- Frontend: Next.js 15 (app router), Tailwind, ~shadcn-ish components
- Tests: Vitest unit + Playwright e2e
- Backend: FastAPI + 6 Celery workers in single `rig-backend` container
- DB: Postgres 16 + pgvector (`rig-postgres`, port 5433 on host)

---

## Step 1: VERIFY what currently exists (do not assume)

Before writing anything new, audit the current state:

### File audit

```bash
# Frontend
ls frontend/src/app/brief/
ls frontend/src/components/brief/
ls frontend/e2e/ | grep -i brief

# Backend
ls backend/routers/ | grep -i brief
ls backend/tasks/ | grep -i brief
```

For each file found, READ it (don't analyze — actually open and understand). Document:
- What component / endpoint / task it is
- What it claims to do
- Whether the implementation looks complete or stubbed
- Any TODO / FIXME / "not implemented" markers

### DB schema check

```sql
-- What brief-related tables exist?
\dt+ *brief*
\dt+ *narrative*

-- Are they populated?
SELECT 'briefs' AS tbl, COUNT(*) FROM briefs
UNION ALL SELECT 'narrative_drafts', COUNT(*) FROM narrative_drafts;
```

Cross-check schema against what the frontend pages expect to fetch.

### API contract check

```bash
# What brief endpoints does FastAPI expose?
curl -s http://localhost:8000/openapi.json | jq '.paths | keys[] | select(contains("brief"))'
```

For each endpoint, capture request/response shape. Document discrepancies between what frontend pages call and what backend serves.

### Render the page and screenshot

```bash
# Start frontend if not running
docker compose -f infrastructure/docker-compose.yml up -d rig-frontend

# Hit /brief — capture console errors
# (use Playwright trace mode or browser devtools)
```

Document what renders, what's broken, what's stubbed.

### Run existing Playwright tests

```bash
docker exec rig-frontend npx playwright test e2e/brief.spec.ts
```

Document pass/fail per test. If tests are missing, note that.

### Manual brief generation against existing data

```bash
# Trigger brief for a super-admin user (no new articles needed — uses existing)
docker exec rig-backend celery -A backend.celery_app call \
  tasks.generate_brief_for_user \
  --kwargs='{"user_id": "<super-admin-uuid>"}'
```

Check the generated brief row in DB — what shape does it have?

### REPORT BACK BEFORE WRITING CODE

After the verification pass, write a short status file to `docs/BRIEF_PAGE_VERIFICATION_2026-05-28.md` that captures:

1. What exists and works
2. What exists but is broken/stubbed
3. What's missing entirely
4. The current API contract (request/response shapes)
5. Recommended build plan based on findings

Then wait for user approval before scaffolding new code.

---

## Step 2: Build with live-update architecture in mind

When you start implementing, bake in these patterns so scrapers resuming = automatic freshness:

### Data fetching

- Use **TanStack Query** (preferred) or **SWR** for all data calls
- Configure `staleTime: 60_000` (60s) and `refetchInterval: 120_000` (2 min) for the main brief list
- Pass-through cursor for pagination

### Pagination

- **Cursor-based**: `?cursor={articles.collected_at}__{articles.id}&limit=20`
- NEVER offset-based — articles flow continuously when scrapers run; offset pagination would shift under user's feet
- Backend route should accept cursor + return `next_cursor` for the next page

### Live-update indicator

- "**Last updated X min ago**" badge top-right of the page
- Optional "**New articles available — click to refresh**" banner when poll detects newer data than what's currently rendered (use last `collected_at` as marker)

### Freshness filters

Chip group at top of page:
- "Last 6 hours"
- "Last 24 hours" (default for brief)
- "Last 7 days"
- "All time"

Each maps to a `min_collected_at` query param.

### Country / topic filters

- Country chip group using `articles.source_country` — IN / GB / CN / XX (global) / etc.
- Topic chip group using `articles.topic_category` (already populated)
- Multi-select, AND between filter groups

### Multi-edition support

Brief page renders ONE edition at a time. URL = `/brief?edition=morning|midmorning|lunch|afternoon|evening`. Each edition has its own curated set. Default = closest-recent edition based on current time.

### Empty / loading / error states

- **Skeleton cards** while data fetches (3-5 placeholder cards)
- **Empty state** with copy: "Brief is being generated — check back in a few minutes" + retry button
- **Error state** with copy: "Couldn't load your brief. Try again?" + retry button + link to support

### Optimistic UI

- "Save" / "Dismiss" / "Share" actions should update local state immediately, then sync to backend asynchronously
- Show toast on success/failure

### Article card design

Per `08-future-plans.md` mockup spec:
- Summary preview (50 chars) as headline
- Summary snippet (200 chars) as 2-line subhead
- Tag chips: article_type · register_style · register_emotion · source_country · register_is_breaking
- Quote pull-out (if `article_quotes` exists, show 1 best quote with speaker)
- Location map dot (if `article_locations` city/region/country present)
- "Read full" expands to summary_executive + claims + events list
- Source attribution: source name + country flag + "X hours ago" via `collected_at`

---

## Step 3: Don't break

- **Drain is running.** Don't kill the drain process. Don't restart `rig-backend` without checking — would kill 4 parallel drain processes and lose in-flight work
- **Scrapers are SIGSTOPed.** Don't resume them until told. The drain needs LLM capacity; resuming scrapers competes for Ollama
- **Playwright is DISABLED** (`PLAYWRIGHT_ENABLED=false`) — Chromium memory leak. Don't re-enable without OOM fix
- **Don't run yt-dlp / transcript-api raw from shell** — burns YouTube IP reputation 24-72h
- **Don't SSH to Trijya with the password from Connection_Guide.pdf** — security policy. Use the PowerShell script handoff pattern
- **Don't use dated Cerebras model tags** (e.g. `qwen-3-235b-a22b-instruct-2507`) — they get retired without notice. Probe `/v1/models` for current names

---

## Step 4: Quality checklist before declaring "done"

- [ ] All verification findings documented in `docs/BRIEF_PAGE_VERIFICATION_2026-05-28.md`
- [ ] Frontend renders without console errors on cold load
- [ ] TanStack Query / SWR configured for stale-while-revalidate
- [ ] Cursor pagination working (not offset)
- [ ] Country filter using `source_country` works
- [ ] Freshness filter chips work
- [ ] At least 1 Playwright e2e test passing
- [ ] At least 1 unit test (Vitest) per non-trivial component
- [ ] Loading / empty / error states implemented
- [ ] Optimistic UI for save/dismiss
- [ ] "Last updated" indicator on page
- [ ] Polling logic confirmed: new article in DB → visible on page within 2 min without refresh
- [ ] Multi-edition routing (`?edition=...`) implemented
- [ ] Mobile responsive at sm / md / lg breakpoints
- [ ] No regressions to existing pages (run full Playwright suite)

---

## Step 5: Hand-off back to main session

When done OR blocked, update:

- `docs/BRIEF_PAGE_VERIFICATION_2026-05-28.md` — what you found pre-build
- `docs/onboarding/12-session-2026-05-29-brief-page.md` (NEW) — your session's lessons (anything that should persist as project memory)
- `docs/onboarding/09-todos-prioritized.md` — mark brief-page work complete OR note remaining items
- Active TaskList — close brief-page tasks; flag blockers

---

## Quick-reference: useful repo paths

| What | Path |
|---|---|
| Project entry | `CLAUDE.md` |
| Onboarding pack | `docs/onboarding/00-README.md` → 11 numbered files |
| Today's session learnings | `docs/onboarding/11-session-2026-05-28-learnings.md` |
| DB migrations | `scripts/migrations/*.sql` (latest 075) |
| Backend tasks | `backend/tasks/*.py` |
| Substrate driver | `backend/tasks/substrate/run_corpus_pass.py` |
| LLM pool | `backend/nlp/groq_client.py` |
| Frontend pages | `frontend/src/app/<pillar>/page.tsx` |
| Pause/resume runbook | `docs/PAUSE_INGEST_RUNBOOK.md` |
| Trijya admin script | `scripts/deploy/trijya_ollama_tune.ps1` |
| Phase 1 source list | `docs/PHASE1_20_COUNTRIES.md` |

---

## One last thing

Today's drain is consuming Ollama capacity. **Don't trigger anything heavy on the `nlp` queue during your session** — it'll slow the drain. Frontend dev does NOT touch nlp; you should be fine. If you need LLM access for something experimental, use the cloud lane (Groq + Cerebras) directly via `groq_manager`.

Now: start with **Step 0 (read onboarding) → Step 1 (verify) → Report back before writing code.**
