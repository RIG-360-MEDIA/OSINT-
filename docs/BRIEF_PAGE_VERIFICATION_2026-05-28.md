# Brief Page — Verification Report (2026-05-28)

Pre-build audit per the kickoff prompt's Step 1. **No code written yet.** This
report exists to surface a design conflict that must be resolved before any
frontend work begins.

---

## TL;DR — what you need to decide before I write a line

Three different "brief page" designs exist in the repo right now, each with
*some* live code/tests behind it. They are mutually incompatible. Pick one
target (or define a fourth) before I scaffold:

| # | Source of truth | What it is | Status |
|---|---|---|---|
| A | `backend/routers/brief_router.py` + `backend/observability/brief_*.py` | "Boss's Morning Brief" dashboard — 4 watched political-entity cards (Naidu, Rahul, Akhilesh, Owaisi), KPI tiles, emerging signals, defining stories. SQL-driven, no LLM at query time. | Backend live. **No frontend exists.** |
| B | `frontend/e2e/brief.spec.ts` | OLD markdown LLM brief — `/api/brief/today`, `/history/list`, `/generate`, `/{date}`. Six narrative sections (SITUATION STATUS, KEY DEVELOPMENTS, ENTITIES TODAY, SIGNALS TO WATCH, FINANCIAL PULSE, SOURCE COVERAGE) rendered from server-generated markdown. | E2E test exists. **Frontend gone, backend endpoints gone, generator tasks deleted.** |
| C | Kickoff prompt + `docs/onboarding/08-future-plans.md` §5 | Multi-edition Particle-style article feed. 5 editions/day (06/10/13/17/21 UTC). Article cards w/ summary preview + chips + quote pull-out + location dot. Country + freshness filter chips. Cursor pagination. TanStack Query polling. Reads `narrative_drafts` (migration 070). | **Spec only.** Zero implementation. |

**Note:** the e2e test (B) does NOT match the live backend (A). If we kept B's
test as-is and ran it against A's router, it would 404 on every fixture.

---

## What exists / works

### Backend
- `backend/routers/brief_router.py` (89 lines) — `/api/brief/{entities,emerging,stories,kpi}` endpoints. **Design A.**
- `backend/observability/brief_entities.py` (237 lines) — hard-codes 4 political entities w/ UUIDs + ILIKE fallbacks; uses `entity_mention_daily` (T6), `article_stances`, `article_quotes`.
- `backend/observability/brief_emerging.py` (123 lines).
- `backend/observability/brief_stories.py` (198 lines) — reads `event_clusters` w/ T5 importance.
- Migration `070_narrative_clusters.sql` creates `narrative_clusters`, `narrative_cluster_members`, `narrative_drafts` (the **Design C** storage).
- Migration `036_brief_quality_scores.sql` and `020_briefs_evidence.sql` belong to **Design B** lineage (legacy markdown brief).

### Data substrate (per onboarding 11 + CLAUDE.md auto-memory)
- ~30K articles have full v3 substrate today.
- `articles.source_country` populated (migration 075).
- `article_events.effective_event_date` populated (migration 072).
- `article_locations.location_scope` derived (migration 074).
- 99% of `article_claims` have SPO triples.
- `article_quotes` with `speaker_name` + `speaker_entity_id`.
- `entity_mention_daily` (T6) for sparkline data.
- `event_clusters` with importance_score (T5).

All raw material for **Design C** is in place, *if* a router is written to
serve cursor-paginated article cards filtered by country/edition.

### Tests
- `frontend/e2e/brief.spec.ts` — 6 tests targeting **Design B** API. None will pass against the live backend or against any new implementation without rewriting fixtures + assertions.

---

## What is broken / stubbed / missing

### Frontend
- `frontend/src/app/brief/**` — **does not exist.** Deleted in commit `18f376a` ("frontend reset"). Comment in `frontend/src/app/page.tsx` confirms: `/admin, /onboarding, /brief, /coverage` removed. Surviving routes: `/`, `/landing`, `/login`, `/signup`, `/observe`.
- `frontend/src/components/brief/**` — **does not exist.**
- No TanStack Query or SWR setup visible in surviving frontend code (needs verification once we build).

### Backend (relative to Design B test contract)
- `backend/tasks/brief_task.py` — **deleted** (per git status).
- `backend/tasks/brief_quality_task.py` — **deleted**.
- `/api/brief/today`, `/api/brief/history/list`, `/api/brief/generate`, `/api/brief/{date}` — **not implemented** in current router.

### Backend (relative to Design C spec)
- No `/api/brief/editions` or `/api/brief/{edition}` endpoints.
- No edition cut-off logic (06/10/13/17/21 UTC scheduling).
- No cursor-paginated `/api/brief/articles?edition=…&cursor=…&country=…` endpoint.
- `narrative_drafts` table exists but no writer task (migration 070's reader path is unwired since `brief_task.py` was deleted).

### Operational
- **Docker daemon is not running locally.** `docker ps` failed with named-pipe error; `docker version` returns client only. Cannot render the page, hit the API, or query DB locally until Docker Desktop is started.
- Per CLAUDE.md auto-memory: drain is running on Hetzner; scrapers SIGSTOPed. Frontend dev should not touch nlp queue. ✅ no conflict.

---

## Current API contract (Design A — what's actually live)

```
GET /api/brief/entities
  → { entities: [{ rank, name, init, party, region, classification,
                   mentions_today, change_pct, sentiment, velocity,
                   velocityBars: number[15], latest_quote, ... }, ×4] }

GET /api/brief/emerging?limit=5
  → { signals: [{ entity_name, surge_pct, mentions_24h, ... }] }

GET /api/brief/stories?limit=5
  → { stories: [{ cluster_id, importance_score, headline,
                  article_count, ... }] }

GET /api/brief/kpi
  → { articlesParsed: int, outlets: int, languages: int,
      sentiment: float, lang_breakdown: [{ code, n }] }
```

Note: every endpoint is hard-coded to the last 24h. **No freshness param, no
country filter, no cursor pagination, no edition concept.** If we go with
Design C we need a new router; if we go with Design A we need to add filters.

---

## Recommended build plan

I see three credible paths. Ranked by what I *think* the user wants based on
the kickoff prompt's level of detail (which heavily emphasises multi-edition
+ cursor + country filters + TanStack Query — all Design C signals):

### Path 1 — **Build Design C from scratch** (my recommendation)
1. Write a new `brief_editions_router.py` (don't touch the existing
   `brief_router.py` — keep Design A for the "boss dashboard" use case).
   Endpoints:
   - `GET /api/brief/editions/current` — returns the active edition for now.
   - `GET /api/brief/editions/{slug}/articles?cursor=&limit=&country=&min_collected_at=` — cursor-paginated article cards.
   - `GET /api/brief/editions/list` — past editions.
2. Source: read directly from `articles` + child tables (no `narrative_drafts`
   dependency yet — wire that later via a Celery task).
3. Scaffold `frontend/src/app/brief/page.tsx` + components, with TanStack
   Query, cursor pagination, country/freshness chips, edition routing.
4. Rewrite `frontend/e2e/brief.spec.ts` against Design C fixtures (current
   test is for the dead Design B API).

### Path 2 — Wire frontend to Design A unchanged
- Faster (backend already done) but doesn't satisfy the kickoff prompt's
  multi-edition / country-filter / cursor requirements at all. We'd get a
  political-entity dashboard, not a daily multi-edition brief.

### Path 3 — Resurrect Design B
- Build a new markdown-generator task + restore `/today`, `/generate`, etc.
  Heaviest on LLM spend (writes a full brief per user per day). The kickoff
  prompt says scrapers are SIGSTOPed and not to load nlp queue — this path
  conflicts with that constraint.

---

## Blockers before I can start

1. **Design decision.** Path 1 / 2 / 3 / something-else?
2. **Docker daemon.** Need it up locally to run the dev server, hit the API,
   query DB. If you want me to dev against Hetzner instead, say so and I'll
   set up the SSH tunnel pattern.
3. **Auth.** The e2e test reads `E2E_SUPABASE_TOKEN`. Need to confirm the
   surviving `/login` route still issues Supabase tokens and what the brief
   page should do for unauthenticated users (redirect? read-only?).

---

## Files inspected for this report

- `frontend/src/app/page.tsx` (8 lines)
- `frontend/e2e/brief.spec.ts` (227 lines)
- `backend/routers/brief_router.py` (89 lines)
- `backend/observability/brief_entities.py` (first 100 of 237 lines — pattern config + entity loop)
- `docs/onboarding/00-README.md` (full, 173 lines)
- `docs/onboarding/08-future-plans.md` (headings + brief-relevant lines)
- `docs/onboarding/11-session-2026-05-28-learnings.md` (headings; no brief-specific learnings present)
- `scripts/migrations/*.sql` (filename + heading grep)

Glob inventory:
- 5 surviving app pages (landing/login/signup/observe + root)
- 3 brief observability modules backend-side
- 0 frontend brief components

---

## Awaiting your decision

Once you pick a path I'll proceed to Step 2 (build with live-update arch).
Until then, no code.
