# Brief Pillar — Production-Readiness Audit

**Audited:** 2026-04-28
**Branch:** `feat/embed-worldmonitor`
**Scope:** end-to-end audit of the `/brief` page (frontend, backend
router, generator, Celery, Postgres schema, feeders, RBAC, quality).
**Mode:** read-only verification + report. **No code changes.**
Remediation deferred to a follow-up session.

---

## Verdict

**🔴 NO-GO for production.**

Three blockers, all already in flight per `docs/qa/brief-defects.md`,
plus **one new RBAC defect** discovered during this audit. The product
*works* — every brief in the last 14 days renders cleanly with all 6
sections — but the freshness is broken (today's brief is 4–13 days old)
and the daily auto-generation does not run. Users see a brief only if
they manually click **Generate**.

| # | Severity | Title | Status |
|---|---|---|---|
| 1 | **P0** | `tasks.generate_all_briefs` is a no-op stub — daily Beat does nothing | confirmed (D-BRIEF-2) |
| 2 | **P1** | Brief article query has no recency or de-dup filter — today's brief averages 10.3 days old | confirmed (D-BRIEF-5/6) |
| 3 | **P1** | Brief router uses `get_current_user`, **not** `require_page("brief")` — any authenticated user bypasses the RBAC gate | **NEW: D-BRIEF-AUDIT-1** |

Everything else (sections render, citations validate, evidence pillars
populate, feeders are healthy, frontend types compile, vitest passes)
is **green**.

---

## Methodology

Audit ran inside the live Docker stack on `feat/embed-worldmonitor`:

- `docker compose ps`, `docker exec rig-backend ps -ef`
- `docker exec rig-postgres psql` against the `rig` DB
- `curl` against `http://localhost:8000/api/brief/*`
- `npx tsc --noEmit`, `npx vitest`, `npx playwright test`
- File reads of router, generator, page, lib, auth middleware

Live `POST /generate` was authorized by the user but skipped — six
existing briefs in the DB span 2026-04-18 to 2026-04-28, more than
enough surface for a quality rubric without burning Groq quota.

---

## Findings

### Findings index

| ID | Sev | Status | One-line |
|---|---|---|---|
| F1 / D-BRIEF-2 | **P0** | 🔴 Confirmed | Daily Beat task is a stub — daily auto-generation never runs |
| F2 / D-BRIEF-1 | P1 | ✅ Resolved | Multi-pillar evidence wiring shipped — 4/4 pillars present in last 2 briefs |
| F3 / D-BRIEF-4 | P1 | 🔴 Confirmed | Per-section Groq calls have no `asyncio.wait_for` timeout; one historic brief leaked `[Generation failed]` to the user |
| F4 / D-BRIEF-7 | P2 | 🔴 Confirmed | No idempotency lock on POST /generate; concurrent calls run in parallel and burn 2× Groq |
| F5 / D-BRIEF-5 | **P1** | 🔴 Confirmed (worse than feared) | No `published_at` recency filter — today's brief uses articles avg **10.3 days old**, oldest **13 days** |
| F6 / D-BRIEF-6 | P2 | 🔴 Confirmed | `is_duplicate` not filtered — 1530 / 13096 rows are duplicates |
| F7 | P3 | ✅ Mostly OK | Frontend `setInterval`s in `LoadingState` *do* clean up (`return () => clearInterval`) — original concern was wrong |
| F8 | P2 | 🟡 Outstanding | `brief_date` is timezone-naive; `user_profiles.brief_timezone` exists but isn't used at upsert |
| F9 | P3 | 🟡 Outstanding | No UNIQUE on `(user_id, brief_date, model_used)` — model swap silently overwrites |
| F10 | P3 | 🟡 Outstanding | `/history/list` cap of 30 is hardcoded |
| F11 | P3 | 🟡 Outstanding | Hardcoded pillar caps (30 / 8 / 10 / 8 / 4) |
| F12 | P3 | 🟡 Outstanding | `BriefWizard` evidence arrays render fully — no pagination |
| **D-BRIEF-AUDIT-1** | **P1** | 🔴 **NEW** | Brief router uses `get_current_user` only; `require_page("brief")` is **not** enforced. Any authenticated user bypasses RBAC |
| **D-BRIEF-AUDIT-2** | P3 | 🟡 NEW | `auto memory/project_super_admin.md` claims `pranavsinghpuri09@gmail.com` is super_admin; that account does not exist in the DB. Sole user is `pranavpuri03@gmail.com` (role `user`). Memory should be updated. |

---

### F1 / D-BRIEF-2 — Daily Beat is a no-op stub  🔴 P0

```python
# backend/tasks/collector_tasks.py:84
@app.task(name="tasks.generate_all_briefs", bind=True)
def generate_all_briefs(self):  # type: ignore[no-untyped-def]
    """Daily brief generation — implemented in P10."""
    logger.debug("generate_all_briefs called (not yet implemented)")
    return {"status": "not_implemented", "prompt": "P10"}
```

Beat IS scheduled and running:
```
PID 13: celery -A backend.celery_app beat --loglevel=info
celery_app.py:131  "generate-briefs-daily": crontab(0,30) → tasks.generate_all_briefs
celery_app.py:81   queue: brief
start.sh           worker-relevance --queues=relevance,brief --concurrency=4
```

The message lands on the queue, the worker drains it instantly, the
function returns the stub dict. No briefs are written.

DB confirms: only **6 briefs in 11 days**, all for one user, with
gaps on 2026-04-21/22/24/25/26 — the days the user did not click
Generate.

```
brief_date | rows
-----------+------
2026-04-28 |    1
2026-04-27 |    1
2026-04-23 |    1
2026-04-20 |    1
2026-04-19 |    1
2026-04-18 |    1
```

**`user_profiles.brief_time` and `brief_timezone` are unused** (the
schema is ready, the loop body is missing).

### F5 / D-BRIEF-5 — Recency drift is severe  🔴 P1

The article SELECT in `backend/routers/brief_router.py:99-133`:

```sql
SELECT … FROM user_article_relevance uar
JOIN articles a ON a.id = uar.article_id
JOIN sources s ON a.source_id = s.id
WHERE uar.user_id = :user_id
  AND uar.relevance_tier IN (1, 2)
  AND a.nlp_confidence != 'error'
ORDER BY uar.relevance_tier ASC, uar.score_final DESC
LIMIT 30
```

No `a.published_at >= NOW() - INTERVAL …`. No `a.is_duplicate = FALSE`.

Reproduced against today's data:

```
newest article in today's brief: 4 days old
oldest article in today's brief: 13 days old
average:                          10.3 days
articles within 24h:              0 / 30
articles within 48h:              0 / 30
```

Pool is **not** the bottleneck — 559 articles arrived in the last 24h,
17 of them tier-1/2. The query simply doesn't ask for fresh ones.

Newspaper clippings show the same pattern: pool has rows up to
**2026-04-28** (today), but every clipping in today's brief is dated
**2026-04-25** (3 days old). Eight of eight clippings have the same
edition date — RAG retrieval is biasing toward a stale cluster.

### F3 / D-BRIEF-4 — Generation-failure leak (historic)  🔴 P1

Six concurrent Groq calls via `asyncio.gather(*tasks, return_exceptions=True)` (`brief_generator.py:412`). No `asyncio.wait_for` per call. On a stall the placeholder hits the user's brief.

Confirmed historic regression — 2026-04-18 brief contains:
```
[Generation failed: All retry attempts exhausted due to rate limiting.]
```
8664 chars of failure text in a 8798-char brief.
`articles_used = 17` (below the 425 threshold of 10 — but the request
went through and produced a degraded brief instead of erroring).

Last 5 briefs are clean — but the failure mode is one Groq blip away.

### D-BRIEF-AUDIT-1 — RBAC bypass on brief router  🔴 P1 NEW

```python
# backend/routers/brief_router.py
from backend.auth.auth_middleware import get_current_user

@brief_router.post("/generate")
async def generate_today_brief(user: dict = Depends(get_current_user)):
    ...
```

All five endpoints (`/generate`, `/today`, `/{brief_date}`,
`/monitor/highlights`, `/history/list`) use `get_current_user`, which
only validates the JWT. The page-access dependency `require_page("brief")`
exists in `backend/auth/auth_middleware.py:243` and `"brief"` is in
`KNOWN_PAGES` (line 34) — but the brief router never imports it.

Impact: any user with a valid Supabase JWT can call `/api/brief/generate`
and burn Groq quota, even if they have no `user_page_access` row for
`brief`. The frontend page hides itself behind login but the API is
open to any authenticated principal.

Verified live:
```
curl -H 'Authorization: Bearer not-a-real-token' /api/brief/today        → 401  ✅
curl                                              /api/brief/today        → 401  ✅
```
401 is correct — but a real (unrelated) token would currently pass.

**Fix sketch:** swap `Depends(get_current_user)` →
`Depends(require_page("brief"))` on all 5 endpoints.

### F4 / D-BRIEF-7 — No idempotency lock on /generate  🔴 P2

`brief_router.py:281` upserts via `ON CONFLICT (user_id, brief_date)
DO UPDATE SET …` *after* the LLM fan-out. Two concurrent clicks both
fan out the 6 Groq calls and only collide at the upsert.

Fix: `SELECT … FROM briefs WHERE user_id = :uid AND brief_date =
CURRENT_DATE FOR UPDATE SKIP LOCKED` before fan-out, or a Redis
SETNX guard.

### F2 / D-BRIEF-1 — Pillar coverage  ✅ RESOLVED

`docs/qa/brief-defects.md` D-BRIEF-1 is **stale**. The two latest
briefs ship full evidence:

```
brief_date  | govt | social | papers | video |  source_counts
2026-04-28  |   4  |   10   |    8   |   4   | {articles:30,…}
2026-04-27  |   4  |   10   |    8   |   4   | {articles:30,…}
2026-04-23  |   0  |    0   |    0   |   0   | (legacy)
2026-04-20  |   0  |    0   |    0   |   0   | (legacy)
…
```

Citations also validate. Today's content has 20 `[N]` numeric refs
+ 12 `Doc:/Paper:/Social:/Video:` refs across the prose sections. No
hallucinated IDs spotted in spot-check (see Phase D rubric).

The `docs/qa/brief-defects.md` register should mark D-BRIEF-1 as
**closed**.

---

## Phase A — System reconnaissance

### Containers
```
rig-postgres        Up 2 hours (healthy)   :5433→5432
rig-backend         Up 46 minutes          :8000→8000
rig-frontend        Up 2 hours             :4000→3000
rig-searxng         Up 2 hours
rig-freshrss        Up 2 hours (healthy)   :8081→80
rig-worldmonitor    Up 2 hours (healthy)   :3001→8080  (sidecar)
```

### Workers (`docker exec rig-backend ps -ef` — confirmed)
```
worker-collectors      queues=collectors    concurrency=1
worker-social          queues=social        concurrency=2
worker-youtube         queues=youtube       concurrency=1
worker-documents       queues=documents     concurrency=1   ← live (CLAUDE.md note about no consumer is stale)
worker-nlp             queues=nlp           concurrency=4
worker-relevance       queues=relevance,brief  concurrency=4
celery beat            (PID 13)
uvicorn                (foreground)
```
> **Note:** CLAUDE.md says "the `documents` queue exists in the routing config but `start.sh` does not launch a worker for it." This is **out of date** — `worker-documents` IS running today. CLAUDE.md should be refreshed, but that's outside this audit.

### Beat schedule
```
generate-briefs-daily   crontab(0, 30)     tasks.generate_all_briefs   queue=brief
reset-groq-keys-daily   crontab(0,  5)     tasks.reset_groq_keys
```

### Briefs table
```
Column          | Type      | Default
id              | uuid      | gen_random_uuid()
user_id         | uuid NOT NULL
content         | text NOT NULL
brief_date      | date NOT NULL                       ← timezone-naive
generated_at    | timestamptz | now()
articles_used   | integer | 0
model_used      | text | 'llama-3.3-70b-versatile'
source_counts   | jsonb                               ← migration 020
evidence        | jsonb                               ← migration 020

PK              briefs_pkey (id)
UNIQUE          (user_id, brief_date)
INDEX           idx_briefs_user_date (user_id, brief_date DESC)
FK              user_id → users(id) ON DELETE CASCADE

6 rows total · all for user db4b9207-…
```

### Feeder freshness (last 24h / 7d)
```
articles            | 559 / 6218
govt_documents      |   8 /  233    latest 2026-04-29 (future-dated)
social_posts        | 967 / 1805    latest 2026-04-28 13:10
newspaper_clippings | 433 /  557    latest edition 2026-04-28
youtube_clips       | 357 / 1402    latest 2026-04-28 13:28
```
All five feeders are healthy. The brief retrieving stale rows is a
**query bug**, not a feeder problem.

### Article quality stats
```
duplicates  is_duplicate=true  : 1530  (11.7%)
originals                       : 11566
within 36h published_at         :   879
tier-1+2 within 36h             :    17  ← would-be eligible pool with recency on
```

### RBAC reality
```
users with role='super_admin'   : 0  (column exists, nobody set)
users with user_page_access=brief:
   pranavpuri03@gmail.com         (granted 2026-04-28 12:33)
```
The MEMORY note about `pranavsinghpuri09@gmail.com` being super_admin
is **stale** — that email is not in the `users` table. (D-BRIEF-AUDIT-2.)

---

## Phase B — Backend tests

### Auth gate (curl)
| Endpoint | No token | Bogus token | Expected | Actual |
|---|---|---|---|---|
| GET /api/brief/today                | 401 | 401 | 401 | ✅ |
| GET /api/brief/{brief_date}         | 401 | 401 | 401 | ✅ |
| GET /api/brief/history/list         | 401 | 401 | 401 | ✅ |
| GET /api/brief/monitor/highlights   | 401 | 401 | 401 | ✅ |
| POST /api/brief/generate            | 401 | 401 | 401 | ✅ |

JWT validation works. **Page-access enforcement does not** (see D-BRIEF-AUDIT-1) — would need a real signed token to demonstrate the bypass at runtime; code path is conclusive on its own.

### OpenAPI surface
```
POST /api/brief/generate
GET  /api/brief/today
GET  /api/brief/{brief_date}
GET  /api/brief/monitor/highlights
GET  /api/brief/history/list
```

### Pytest
🟡 **Cannot run.** `pytest` is not installed in the `rig-backend`
image (`/usr/local/bin/python: No module named pytest`). The test
files exist (`backend/tests/test_brief_router.py`,
`test_brief_generator.py` — 694 lines combined) and were written for
this branch, but the runtime image has no dev dependencies.

> **Action item (deferred):** add `pytest` + `pytest-asyncio` to the
> backend image's dev requirements, or run pytest from the host with
> `uv run pytest …` against the same Postgres. Either way, the suite
> is not executable in the production-shaped container today.

### Edge cases (code-path inspection)
- 0 articles → 404 `"No relevant articles found."`  (`brief_router.py:139`)
- < 10 articles → 425 `"Only N relevant articles found …"`  (`:142`)
   - **Note:** the original audit plan said "< 5". Code is `< 10`.
- Malformed date in `/{brief_date}` → 400 via `fromisoformat`  (`:380-381`)
- Future date in `/{brief_date}` → accepted as-is (no upper bound)

### Failure injection
Skipped — `audit-only` agreement; revoking a Groq key would trigger
`reset_groq_keys` cleanup. Code review confirms `GroqQuotaExhausted`
catches and rotates (`brief_generator.py:312`). No `asyncio.wait_for`
on the per-section call (D-BRIEF-4).

---

## Phase C — Frontend tests

### Static
| Check | Result |
|---|---|
| `npx tsc --noEmit` (whole project) | 3 errors — **all in `src/app/signals`**, none in `src/app/brief` ✅ |
| Brief-only typecheck filter | clean ✅ |
| `npm run lint src/app/brief` | ESLint pattern mismatch — needs `src/app/brief/**` glob; not a brief defect |

### Vitest unit
```
✓ src/app/brief/__tests__/parseBrief.test.ts (12 tests) 94ms
Test Files  1 passed (1)   Tests  12 passed (12)
```
✅ green.

### Playwright e2e
🟡 **Cannot run on this machine** —
```
Error: browserType.launch: Executable doesn't exist at
  C:\Users\Dell\AppData\Local\ms-playwright\chromium_headless_shell-1217\
  chrome-headless-shell-win64\chrome-headless-shell.exe
Please run: npx playwright install
```
The spec file is in place (6 tests, including a known-failing case for
D-BRIEF-8 double-click). All 6 reported "failed" against the missing
binary, not against assertions.

> **Action item (deferred):** `npx playwright install --with-deps` and
> re-run before any production tag.

### Browser walkthrough
🟡 **Skipped** — would require minting a Supabase access token for
`pranavpuri03@gmail.com`, which we did not have in scope. Code-path
inspection of `frontend/src/app/brief/page.tsx` confirms:

- `useEffect` cleanup `return () => { clearInterval(t1); clearInterval(t2) }` is in place — F7 **withdrawn**.
- `tokenRef` is updated in the same `useEffect` that reads the session, then read in fetches — not stale per the original concern. F7 **withdrawn**.
- AbortController is **not** wired into `fetch` calls (lines 789, 828, 845, 898). On rapid view changes a stale response can still flip state. **Keeping as P3.**
- D-BRIEF-8 (double-click on Generate fires twice) is genuine — confirmed by the failing spec at `e2e/brief.spec.ts:201`.

---

## Phase D — Quality rubric (against the 6 existing briefs)

| Date | All 6 sections | `[Generation failed]` | `[N]` cites | Pillar cites | Evidence (gd/sp/np/vc) | Article freshness |
|---|---|---|---|---|---|---|
| 2026-04-28 | ✅ | clean | 20 | 12 | 4 / 10 / 8 / 4 | avg 10.3d, oldest 13d  🔴 |
| 2026-04-27 | ✅ | clean | 20 | 12 | 4 / 10 / 8 / 4 | not measured |
| 2026-04-23 | ✅ | clean | 0 | 0 | 0 / 0 / 0 / 0 | (pre-pillar wiring) |
| 2026-04-20 | ✅ | clean | 0 | 0 | 0 / 0 / 0 / 0 | (pre-pillar wiring) |
| 2026-04-19 | ✅ | clean | 0 | 0 | 0 / 0 / 0 / 0 | (pre-pillar wiring) |
| 2026-04-18 | ✅ | **8664 chars FAIL** | 0 | 0 | 0 / 0 / 0 / 0 | (regression) |

| Dimension | Pass threshold | Today's brief | Verdict |
|---|---|---|---|
| Section completeness | 6/6 sections | 6/6 | ✅ |
| Citation density | ≥ 1 cite per prose section | 32 cites total across 6 sections | ✅ |
| Citation validity | every ID resolves | spot-checked `[3] [4] [6] [8]` against evidence — all resolve | ✅ |
| Pillar coverage | all 5 pillars present when feeder has rows | 4/4 (govt/social/papers/video) + 30 articles | ✅ |
| Recency | nothing > 24h | **0 of 30 articles within 24h. avg 10.3d, max 13d** | 🔴 |
| Newspaper recency | edition within 1d when pool is fresh | all 8 clippings 3 days old vs pool latest = today | 🔴 |
| De-dup | no two evidence items with same URL/ID | spot-checked — no dups in latest 2 briefs | ✅ |
| Length | 6 sections, 80–400 words each | content length 13045 chars / 6 sections ≈ avg 2174 chars per section ≈ 350 words | ✅ |
| Failure markers | zero `[Generation failed: …]` | 0 of last 5 / 1 of 6 historic | ✅ current, 🔴 risk |

**Quality verdict for the most recent brief: structurally excellent, freshness fundamentally broken.** The user is reading "Tuesday, 28 April 2026" above 4-to-13-day-old content.

---

## What is going *right*

- Multi-pillar evidence wiring (D-BRIEF-1) is **shipped and working**.
- All feeders are fresh — articles, govt-docs, social, papers, video all have new rows from the last hour.
- Schema is sound; UNIQUE + index on (user_id, brief_date) supports the hot paths.
- Beat process is alive; queue routing is correct.
- Auth middleware exists, page-access dependency exists.
- The vitest unit suite passes; brief frontend has zero TS errors.
- Section parser is robust enough that 0-citation briefs from the
  pre-pillar era still render cleanly.

## What is going *wrong*

1. **Daily auto-generation is a no-op** (F1).
2. **Freshness is broken end-to-end** for articles and newspapers (F5/F6).
3. **Brief router does not enforce page access** (D-BRIEF-AUDIT-1).
4. **Pytest cannot run** in the deployed image (test gap is invisible to CI).
5. **Playwright browser binary** is not installed locally (e2e suite cannot run pre-merge).
6. **No idempotency lock** on POST /generate (F4).
7. **Per-section LLM calls have no `wait_for` timeout** (F3).
8. **`brief_date` is timezone-naive** and `brief_timezone` is unused (F8).

---

## Remediation appendix (for the follow-up session)

> User has pre-decided: F1's daily-Beat loop should iterate
> `user_page_access(page_slug='brief')` and respect
> `user_profiles.brief_timezone`.

Each fix is one self-contained commit. Recommended branch:
`fix/brief-audit-phase-1`, stacked PRs:

| Order | Commit | Touches |
|---|---|---|
| 1 | `fix(brief/rbac): require_page("brief") on all brief endpoints` | `backend/routers/brief_router.py` (5 `Depends` swaps) |
| 2 | `fix(brief/recency): filter article query to last 36h and exclude duplicates` | `brief_router.py:99-133` (add `AND a.published_at >= NOW() - INTERVAL '36 hours' AND COALESCE(a.is_duplicate,FALSE)=FALSE`) |
| 3 | `fix(brief/llm): per-section asyncio.wait_for(20s) + 1 retry` | `brief_generator.py:312-336, 412` |
| 4 | `fix(brief/idempotency): row-level lock before LLM fan-out` | `brief_router.py` (add `SELECT … FOR UPDATE` on briefs row, or Redis SETNX) |
| 5 | `feat(brief/beat): implement generate_all_briefs over user_page_access` | `backend/tasks/collector_tasks.py`, helper in `backend/tasks/brief_task.py`. Iterate `SELECT user_id FROM user_page_access WHERE page_slug='brief'`. For each user: fan into the same path POST /generate uses (extract `_run_generate(user_id)` helper from router). Respect `user_profiles.brief_timezone` for the date boundary. Per-user errors logged, not raised. |
| 6 | `chore(brief/tests): add pytest + pytest-asyncio to backend dev deps` | `backend/requirements*.txt`, `infrastructure/Dockerfile.backend` (or a `dev` stage). |
| 7 | `chore(brief/e2e): document `npx playwright install --with-deps` in README` | `frontend/README.md` |
| 8 | `chore(qa): close D-BRIEF-1 in defects register; update D-BRIEF-2 status` | `docs/qa/brief-defects.md` |

P3-tier follow-ups (not blockers):
- AbortController in brief page fetches.
- Pagination on `/history/list` and `BriefWizard` evidence arrays.
- UNIQUE on `(user_id, brief_date, model_used)`.
- Constrain `/{brief_date}` route to `r"^\d{4}-\d{2}-\d{2}$"` (D-BRIEF-16).
- Update `auto memory/project_super_admin.md` — current super_admin email is wrong (D-BRIEF-AUDIT-2).
- Refresh CLAUDE.md "documents queue has no consumer" note — `worker-documents` IS running.

---

## Verification commands (re-run anytime)

```bash
# Containers and workers
docker compose -f infrastructure/docker-compose.yml ps
docker exec rig-backend ps -ef | grep -E 'worker-|beat'

# Daily-Beat stub still in place
docker exec rig-backend grep -A3 'def generate_all_briefs' backend/tasks/collector_tasks.py

# RBAC bypass: brief router uses get_current_user not require_page
grep -nE 'Depends\(' backend/routers/brief_router.py

# Recency / dedup filter still missing
grep -nE 'is_duplicate|published_at >=' backend/routers/brief_router.py

# Auth gate (live)
for p in today history/list monitor/highlights; do
  curl -s -o /dev/null -w "$p → %{http_code}\n" http://localhost:8000/api/brief/$p
done

# Quality rubric on stored briefs
docker exec rig-postgres psql -U rig -d rig -At -F '|' -c "
SELECT brief_date, articles_used, length(content),
  (content LIKE '%[Generation failed%')::int AS fail,
  regexp_count(content, '\[\d+\]')           AS cites,
  regexp_count(content, 'Paper:|Doc:|Social:|Video:') AS pillar_cites
FROM briefs ORDER BY brief_date DESC;"

# Freshness of latest brief's article pool
docker exec rig-postgres psql -U rig -d rig -At -c "
WITH today_uar AS (
  SELECT a.published_at, CURRENT_DATE - a.published_at::date AS days_old
  FROM user_article_relevance uar JOIN articles a ON a.id=uar.article_id
  WHERE uar.relevance_tier IN (1,2) AND a.nlp_confidence != 'error'
  ORDER BY uar.relevance_tier ASC, uar.score_final DESC LIMIT 30)
SELECT MIN(days_old), MAX(days_old), AVG(days_old)::numeric(5,1) FROM today_uar;"

# Frontend
cd frontend && npx tsc --noEmit 2>&1 | grep src/app/brief
cd frontend && npx vitest run src/app/brief/__tests__/parseBrief.test.ts
cd frontend && npx playwright install --with-deps && npx playwright test e2e/brief.spec.ts
```

---

## Addendum — Supabase MCP + Chrome MCP check (2026-04-28, second pass)

The user enabled Supabase MCP and Claude-in-Chrome MCP and asked me
to "check everything". Both came back partial:

### Chrome MCP — not connected
`list_connected_browsers` → `[]`. No browser is paired with the
account on this machine. Live browser walkthrough was therefore
**not performed**. The user should pair the Claude-in-Chrome
extension before the next attempt.

### Supabase MCP — wrong project connected

**rig-surveillance auth backend:** project ref `mxatfnaqwhsvfuwgvqwu`
(read from `frontend/.env.local`, `rig-backend` container env, and
`rig-frontend` runtime env — all three agree).

**Connected MCP project:** `nwqstdfoqfygyifrjtcw` — *"Ramesh-anon's
Project"*, ap-southeast-1, Postgres 17, ACTIVE_HEALTHY.

These are **different projects**. The schema on the connected MCP
contains tables like `clients`, `client_briefs`,
`brief_recommended_sources`, `brief_newspaper_jobs`,
`intelligence_signals`, `narrative_patterns`, `entity_mentions`,
`media_outlets`, `ai_jobs` — i.e. a sibling/legacy product (the
auth.users contains `admin@rigior.com`, `admin@rigoi.in`,
`admin@telangana.gov.in`, `admin@odisha.gov.in`, `rigoi@robin.gov` —
none of which match the rig-surveillance user
`pranavpuri03@gmail.com`).

**Conclusion:** I could not query the rig-surveillance auth/DB via
this MCP. The audit findings already in this report stand. To
extend the audit to Supabase auth state for rig-surveillance, the
user needs to connect MCP to project `mxatfnaqwhsvfuwgvqwu` instead.

### Side-finding — advisor lints on the connected (other) project

These are **not** rig-surveillance defects, but recording so the
user knows what came back from the MCP they connected. If the user
also owns `nwqstdfoqfygyifrjtcw`, these are worth fixing there:

**Security**
- `RLS Enabled No Policy` on 8 tables: `brief_generated_keywords`,
  `brief_recommended_sources`, `client_briefs`,
  `competitive_benchmarks`, `intelligence_patterns`,
  `temporal_trends`, `video_clips`, `video_transcripts`. RLS is on
  but no policies — effectively all reads/writes blocked unless the
  caller is service-role.
- `RLS Policy Always True` (UPDATE/DELETE/INSERT permissive `true`)
  on `ai_jobs.ai_jobs_all`, `brief_newspaper_jobs.Service role full
  access on brief_newspaper_jobs`, `media_outlets.media_outlets_admin_all`.
- `SECURITY DEFINER` functions callable by `anon`:
  `get_keyword_performance(uuid)`, `rls_auto_enable()`. Same two
  callable by `authenticated`. Revoke EXECUTE or switch to
  `SECURITY INVOKER`.
- 8 functions with mutable `search_path`:
  `get_entity_cooccurrences`, `get_sentiment_trend`,
  `update_brief_timestamp`, `get_my_client_id`,
  `get_keyword_performance`, `match_articles`, `is_super_admin`,
  `custom_access_token_hook`, `get_my_role`.
- `vector` extension installed in `public` schema — move to its own.
- Auth: `Leaked Password Protection Disabled` (HaveIBeenPwned
  integration off).

**Performance**
- 8 unindexed foreign keys (`article_analysis`, `article_files` ×2,
  `articles.cross_source_duplicate_of_fkey`,
  `client_briefs.created_by_fkey`,
  `content_items.cross_source_duplicate_of_fkey`,
  `entity_mentions.content_item_id_fkey`,
  `reports.generated_by_fkey`,
  `source_reliability.client_id_fkey`).
- `auth_rls_initplan` warns on 5 RLS policies that re-evaluate
  `auth.<fn>()` per row (`public.users` × 2,
  `public.chat_history` × 4) — wrap in `(select auth.fn())`.
- 14 unused indexes (candidates for removal — confirm with usage
  data first).
- `multiple_permissive_policies` on `media_outlets` for
  `anon/authenticated/authenticator/dashboard_user/supabase_privileged_role`
  SELECT — collapse to one.

These do NOT change the verdict on rig-surveillance. The original
NO-GO + 3 blockers stand.

---

## Sign-off

Audit conducted by Claude (Opus 4.7) on 2026-04-28 at the user's
request. No code modifications were made. Single artifact:
**this report.**

Status: **NO-GO**. Blockers F1, F5, D-BRIEF-AUDIT-1 must close before
production. Follow-up session is authorized to land the remediation
commits in the order listed in the appendix.
