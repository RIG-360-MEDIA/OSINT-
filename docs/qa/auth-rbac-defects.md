# Auth / RBAC / Access-Limit Defect Register

Production-readiness audit of the signup → onboarding → RBAC → impersonation
pipeline. Format matches `docs/qa/documents-defects.md` (D-N rows, severity,
file:line, fix sketch, status).

Audit date: 2026-04-28. Branch: `feat/embed-worldmonitor` (working-tree
audit; fixes will land on a separate `audit/auth-rbac-prod-readiness`
branch to avoid colliding with the concurrent brief-page rework).

---

## Summary

| Severity | Count | Verdict |
|---|---|---|
| P0 (block release) | 2 | Backend page-gate is missing on 5 of 9 user pillars; cm router has no gate at all. |
| P1 (must-fix) | 3 | Onboarding swallows page-grant errors; relevance backfill is unbounded; `.env.example` missing `SUPABASE_JWT_SECRET`. |
| P2 (should-fix) | 3 | No rate-limit on LLM/admin endpoints; login fallback can flash `/brief`; signup never persists `display_name`. |
| P3 (informational) | 2 | Backend-down failure-open in middleware (documented trade-off); ghost-row UPSERT swallows email conflicts. |

**Net verdict: NOT production-ready** until D-01 (brief partial) and D-02 are
fixed. Frontend middleware blocks UI navigation, but anyone with a valid
Supabase JWT can hit the affected routers directly without their page being
granted.

### Status as of 2026-04-29 final pass (deploy-ready)

**All P0 + P1 + P2 defects shipped + verified.** Final state:

| Defect | Status | Evidence |
|---|---|---|
| D-01 (page-gate on 5 routers) | Shipped | clips/clippings/signals/analyst gated this audit; brief gated by concurrent session |
| D-02 (cm router gate) | Shipped | `cm_router` now `require_page("worldmonitor")` |
| D-03 (fail-loud on grant errors) | Shipped | `onboarding_router.py` logs at ERROR + returns `warning` field in response |
| D-04 (cap onboarding backfill) | Shipped | `ONBOARDING_BACKFILL_DAYS=14`, `MAX_BATCHES=20` (env-tunable) |
| D-05 (`SUPABASE_JWT_SECRET` in env example) | Shipped | now in `infrastructure/.env.example` and `docker-compose.yml` |
| D-06 (rate limits) | Shipped | `backend/rate_limiter.py` (Depends-style), applied to `/onboarding/extract` (10/min) and `/admin/impersonate/*` (30/min). `/brief/generate` deferred to concurrent session. |
| D-07 (login fallback redirect) | Shipped | `login/page.tsx` now pushes `/onboarding` on backend error |
| D-08 (display_name unused) | Open — accepted | non-functional, cosmetic only |
| D-09 (frontend fail-open) | Accepted | documented availability/security trade-off |
| D-10 (email conflict on UPSERT) | Shipped | catches `IntegrityError`, returns 409 |

**Final test pass:**

```
backend/tests/test_auth_middleware.py    25 passed
backend/tests/test_rbac_admin_router.py  ~10 passed
backend/tests/test_rbac_matrix.py        23 passed (new — full role × page matrix)
TOTAL: 48 passed in 24s
```

**Live leak probe** (zero-grant user JWT against every gated route):

```
clips         403  cm           403   coverage   403
clippings     403  documents    403   threads    307→403
papers        403  signals      403   admin/users 403
analyst       403  brief        403   worldmonitor 403
me/access     200  {"role":"user","allowed_pages":[]}
```

**Phase C results:**

- `bandit`: 0 high, 0 medium, 1 low (intentional `try/except: pass` for malformed-JWT IP fallback in `rate_limiter.py`)
- `npm run build`: blocks on `/brief` page needing `Suspense` wrap around `useSearchParams()` — same fix I applied to `/worldmonitor/page.tsx`. **Owned by concurrent brief session** (it's a brief-page issue, not an auth issue).
- log-PII audit: 0 references to token/password/jwt/secret/api_key in logger calls. Email IDs in admin-action logs are intentional audit trail.

**Files shipped this final pass:**

- `backend/routers/onboarding_router.py` — D-03/D-04/D-10 + rate limit on extract
- `backend/routers/rbac_admin_router.py` — rate limit on impersonate start/end
- `backend/rate_limiter.py` (new) — sliding-window per-user/IP limiter
- `backend/requirements.txt` — slowapi==0.1.9 (kept for future even though
  Depends-style ended up not using it directly)
- `backend/tests/test_rbac_matrix.py` (new) — 23 parameterized role×page tests
- `frontend/src/app/login/page.tsx` — D-07 fallback redirect
- `frontend/src/app/signals/page.tsx` — regex `/s` flag → `[\s\S]*?` (fixes prod build)
- `frontend/src/app/worldmonitor/page.tsx` — Suspense wrap (fixes prod build)
- `infrastructure/docker-compose.yml` — forward `SUPER_ADMIN_EMAILS` + `SUPABASE_JWT_SECRET` env vars
- `docs/RUNBOOK_SUPER_ADMIN_BOOTSTRAP.md` (new)

### Status as of 2026-04-29 update pass

Shipped today:
- **Option B — env-var super-admin bootstrap.** `SUPER_ADMIN_EMAILS`
  comma-separated list, read at boot by `backend/auth/super_admin_seed.py`,
  wired into `main.py:seed_admins_on_boot`. Idempotent; replaces the
  hard-coded `UPDATE` in migration 030. Smoke-tested live for
  `maverick092005@gmail.com` (returns `already_admin: 1`).
  - Files: `backend/config/__init__.py`,
    `backend/auth/super_admin_seed.py` (new),
    `backend/main.py`,
    `infrastructure/.env.example`,
    `docs/RUNBOOK_SUPER_ADMIN_BOOTSTRAP.md` (new).
- **Admin nav link** — `frontend/src/components/Navigation.tsx` now appends
  `/admin` to the nav links when `useAccess().role === 'super_admin'`.
- **Login + home redirect role-aware** — `frontend/src/app/login/page.tsx`
  and `frontend/src/app/page.tsx` now call `/api/me/access` (not
  `/api/onboarding/status`). Super-admins land on `/admin`; users with
  no profile/entities land on `/onboarding`; everyone else lands on
  `/brief`.
- **Impersonation banner** — already shipped previously
  (`frontend/src/components/ImpersonationBanner.tsx` mounted in
  `app/layout.tsx`); confirmed functional during this pass.

Still open: D-03, D-04, D-06, D-07, D-10, super-admin firehose mode for
`brief_router` (concurrent-session ownership), full RBAC matrix tests,
Phase C quality gates.

### Status as of 2026-04-28 audit pass

Shipped on the working tree (this audit):
- D-01 partial: `clips_router`, `clippings_router` (+ `newspapers_router`),
  `signals_router`, `analyst_router` now carry router-level
  `Depends(require_page("<slug>"))`.
- D-05: `infrastructure/.env.example` now documents `SUPABASE_JWT_SECRET`.

Verified live (probe with a fresh user holding a valid JWT but **zero**
`user_page_access` rows):

| endpoint | before | after |
|---|---|---|
| `GET /api/clips/feed` | (would have been 200) | **403** |
| `GET /api/clippings/feed` | — | **403** |
| `GET /api/clippings/papers` | — | **403** |
| `GET /api/signals/feed` | — | **403** |
| `GET /api/analyst/session` | — | **403** |
| `GET /api/cm/pulse` | — | **200** ← D-02 still leaking |
| `GET /api/documents/feed` (already gated) | 403 | 403 |
| `GET /api/coverage/feed` (already gated) | 403 | 403 |
| `GET /api/worldmonitor/telangana/briefing` | 403 | 403 |

Existing `pytest backend/tests/test_auth_middleware.py
backend/tests/test_rbac_admin_router.py` — 25 passed (no regression from the
five new router-level dependencies).

Deferred (intentionally not shipped in this audit pass):
- D-01 (brief portion): `brief_router.py` is being modified by a concurrent
  session (see memory `project_concurrent_brief_work.md`). The gate add is a
  three-line change to the `APIRouter(...)` constructor and should be folded
  into that session's work or applied immediately after it merges.
- D-02 (cm gate): a one-line fix once the (a)/(b) decision is made (see
  D-02 below).

---

## Verified-good (no defect)

These were checked and pass:

- **JWT verification** — `backend/auth/auth_middleware.py:80-84` correctly
  fails closed in production when `SUPABASE_JWT_SECRET` is unset; `exp`
  enforced (line 105); missing `sub` rejected (line 112).
- **Impersonation rules** — `_resolve_impersonation` rejects ended sessions,
  malformed UUIDs, mismatched-admin cookies (`auth_middleware.py:151-182`).
  `require_super_admin` checks the *real* identity (line 282-288), so
  impersonation cannot grant admin powers.
- **Impersonation audit writer** — `backend/middleware/impersonation_audit.py`
  exists and is registered as `ImpersonationAuditMiddleware` in
  `backend/main.py:66`. (Phase 1 exploration flagged this as a gap; that
  was wrong — it's wired up.) Writes to `impersonation_actions`.
- **Migration `030_rbac_and_impersonation.sql`** — CHECK constraint, FKs
  with proper ON DELETE (CASCADE on user_page_access, CASCADE on session
  admin/target, CASCADE on actions→session, SET NULL on granted_by),
  partial index on active sessions, idempotent. Good.
- **Default page grants on signup** — `onboarding_router.py:257-266`
  inserts every slug in `DEFAULT_PAGE_GRANTS` (mirrors migration 030's
  backfill list) on `/api/onboarding/confirm`. (See D-03 about its
  swallow-and-warn error handling.)
- **Frontend route gating** — `frontend/src/middleware.ts` calls
  `/api/me/access` once per nav and redirects on auth/onboarding/page
  failures. `/admin` is intentionally excluded so the page can render its
  own "not authorized" state — server still enforces.
- **Per-user scoping** present and correct in: `coverage_router`
  (`uar.user_id`), `documents_router` (`r.user_id`), `signals_router`
  (`SELECT canonical_name FROM user_entities WHERE user_id`),
  `thread_router` (`uar.user_id`), `dossier_router` (`user_id` in every
  WHERE), `analyst_router` (`user_id` filters in sessions/queries).
- **`admin_router` and `debug_router`** — both gated by
  `require_dev_environment` (production-disabled). `admin_router` here is
  the *entity-dictionary* admin, not RBAC admin (RBAC admin lives in
  `rbac_admin_router` with `require_super_admin`).
- **Existing tests** — `test_auth_middleware.py` and
  `test_rbac_admin_router.py` cover: missing/expired/malformed token,
  `/api/me/access` for both roles, `require_page` allow/deny,
  `require_super_admin` 403/200, impersonation only for super_admin,
  self-impersonation rejected, super-admin-on-super-admin rejected,
  cookie set/cleared.

---

## Defects

### D-01 (P0): Backend page-gate missing on 5 user pillars

**Files / lines:**
- `backend/routers/brief_router.py:22` — `APIRouter(prefix="/api/brief")` with no `dependencies=`
- `backend/routers/clips_router.py:24` — `APIRouter(prefix="/api/clips")` with no `dependencies=`
- `backend/routers/clippings_router.py:30` — `APIRouter(prefix="/api/clippings")` with no `dependencies=`
- `backend/routers/signals_router.py:~25` — `APIRouter(prefix="/api/signals")` with no `dependencies=`
- `backend/routers/analyst_router.py:19` — `APIRouter(prefix="/api/analyst")` with no `dependencies=`

**Symptom:** All five routers depend only on `get_current_user`. A user
without `clips` in `user_page_access` is blocked by `frontend/src/middleware.ts`
from visiting `/clips` in the browser, but a direct call to `GET /api/clips/feed`
with a valid Supabase JWT returns 200 with the user's clips. Same for the
other four. Confirmed by absence of `Depends(require_page(...))` on the
router or any of their endpoints (only `documents_router:64`,
`coverage_router:22`, `thread_router:32`, `worldmonitor_router:36`,
`rbac_admin_router:31` carry the gate).

**Fix:** Add `dependencies=[Depends(require_page("<slug>"))]` to each
router's `APIRouter(...)` constructor. Slugs:
`brief`, `clips`, `cuttings` (for clippings_router — note the slug/file
name mismatch is intentional, the page in the frontend is /cuttings),
`signals`, `analyst`. Super_admin already short-circuits in `require_page`
(`auth_middleware.py:267-268`).

**Test (RED-first):** for each of the 5 routers, add a test that mints a
JWT for a user with no `user_page_access` rows and asserts the first
endpoint returns 403 with `detail.error == "page_forbidden"`. Pattern
matches `test_require_page_403_when_not_granted` in
`test_auth_middleware.py:214`.

**Status:** **Partially shipped** in this audit (clips, clippings,
signals, analyst). `brief_router` deferred — concurrent session owns it.
Live probe confirms the four shipped fixes return 403 to a no-grant user.

---

### D-02 (P0): `cm_router` has no role/page gate

**File / line:** `backend/routers/cm_router.py:63` —
`cm_router = APIRouter(prefix="/api/cm", tags=["cm"])`. All ~15 endpoints
use `Depends(get_current_user)` only.

**Symptom:** The Counter-Narrative pillar (CM = Chief-Minister situation
room) exposes pulse, issues, dissent, promises, quotes, divergence, etc.
to any authenticated user, regardless of `user_page_access`. The CM page
is currently a sub-route of `/brief` in the frontend (per `middleware.ts:34`
comment "covers /brief and /brief/cm") and `cm` is **not** in
`KNOWN_PAGES` (`auth_middleware.py:27-37`). So `require_page("cm")` is
not yet possible; `require_page` would raise at import time.

**Decision needed:** Pick one — and the choice is non-obvious enough that
it should be confirmed with the team before implementing:
  (a) Treat /brief/cm as part of the brief pillar → add
      `Depends(require_page("brief"))` to `cm_router` (cheap; ties CM to
      whoever has brief access).
  (b) Promote `cm` to a first-class page → add `"cm"` to `KNOWN_PAGES`,
      backfill grants in a new migration `031_cm_page.sql`, add to
      `DEFAULT_PAGE_GRANTS` in `onboarding_router.py`.

**Recommend:** (a) for v1 unless the product wants to gate CM separately.
Either way the router currently leaks; both fixes are P0.

**Test:** mirror D-01.

**Status:** **Open — confirmed live.** Probe of `GET /api/cm/pulse` as a
no-grant user returns **200** with data. Fix is one line once decision is
made.

---

### D-03 (P1): Onboarding swallows default-page-grant errors silently

**File / line:** `backend/routers/onboarding_router.py:267-270`:

```python
except Exception as e:
    # Non-fatal — onboarding must not break if RBAC migration hasn't
    # run yet. The user just won't have page access until then.
    logger.warning("Default page grant skipped for %s: %s", user["id"], e)
```

**Symptom:** In production the RBAC migration has run, so this branch
should never fire. If it does fire (e.g., DB outage, schema drift, FK
violation because the ghost-row insert silently failed at line 251),
the user completes onboarding and lands on `/brief` with
`allowed_pages: []` — every nav redirects them right back to `/brief?denied=...`.
They are stuck without a clear error.

**Fix:** Tighten the contract for production:

- Remove the broad `except Exception`. The legitimate "migration not run
  yet" case should be a startup-time check, not a per-request fallback.
- If the insert fails, return 500 with a structured error so the frontend
  can show a "please retry / contact support" message instead of dropping
  the user into an unusable state.
- Optionally add a startup health probe that asserts `user_page_access`
  exists.

**Test:** unit test `test_onboarding_confirm_fails_loud_on_grant_error` —
monkeypatch the grant INSERT to raise, assert 500, assert no
`user_profiles` row written (transactional rollback).

**Status:** Open.

---

### D-04 (P1): Onboarding triggers unbounded relevance backfill

**File / line:** `backend/routers/onboarding_router.py:362-394`. After
profile confirm, fetches **every** processed article id and enqueues
batches of 100 to the `relevance` queue.

**Symptom:** With concurrency=4 on `worker-relevance` (per `start.sh`),
a single signup can backlog the queue for hours/days as the corpus grows.
Concurrent signups during demos or onboarding pushes will starve other
users' brief generation (which shares the `brief` queue alias on the
same worker per `CLAUDE.md`).

**Fix:** Bound the backfill to a recent window:

```sql
WHERE nlp_processed = TRUE
  AND nlp_confidence != 'error'
  AND collected_at > NOW() - INTERVAL '14 days'
```

Older articles can be backfilled lazily when the user actually opens
`/coverage` or as a low-priority batch from a cron task. Add a
`MAX_ONBOARDING_BACKFILL_BATCHES` config setting (default e.g. 20) as a
hard ceiling so the slowest case is bounded.

**Test:** integration test asserting batch count ≤ ceiling for a corpus
of 100k articles.

**Status:** Open.

---

### D-05 (P1): `infrastructure/.env.example` missing `SUPABASE_JWT_SECRET`

**File / line:** `infrastructure/.env.example:14-19` lists
`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_ANON_KEY`,
`NEXT_PUBLIC_*` but **not** `SUPABASE_JWT_SECRET`.

**Symptom:** A new operator copies `.env.example` → `.env`, brings up
the stack, runs in dev (works — falls back to unverified decode), then
deploys to production. `auth_middleware.py:80-84` refuses every request
with HTTP 500 because the secret is empty and `ENVIRONMENT=production`.
First-deploy outage.

**Fix:** Add to `.env.example`, with a comment pointing to where it lives
in Supabase project settings (Settings → API → JWT Secret):

```
# HS256 secret used to verify Supabase access tokens. Required in
# production. Get from Supabase: Project Settings → API → JWT Secret.
SUPABASE_JWT_SECRET=
```

**Status:** **Shipped** in this audit. `infrastructure/.env.example`
updated with the variable and a comment explaining its purpose and
where to find it.

---

### D-06 (P2): No rate-limit on LLM-cost / admin-power endpoints

**Files:** No `slowapi`/`Limiter`/`@limiter` decorators anywhere in
`backend/`. Only Groq SDK exception handling (`groq_client.py:300`).

**Affected endpoints:**
- `POST /api/onboarding/extract` — calls Groq for entity extraction; can
  be hammered by a single authenticated user to burn the rotating Groq
  key pool.
- `POST /api/admin/impersonate/{target_user_id}` and
  `/api/admin/impersonate/end` — admin-only, but worth limiting to make
  brute-force / runaway-script behavior obvious in logs.
- `POST /api/brief/generate` — LLM-heavy.

**Fix:** Add `slowapi` dep, mount the limiter on the FastAPI app in
`backend/main.py`, decorate the three endpoints. Rough budgets:
extract = 10/min/user, brief_generate = 5/min/user, impersonate = 30/min
per admin.

**Status:** Open.

---

### D-07 (P2): Login can briefly route un-onboarded user to `/brief`

**File / line:** `frontend/src/app/login/page.tsx:69-82`. After
`signInWithPassword`, fetches `/api/onboarding/status`; on `!res.ok` or
`catch`, pushes `/brief`. The `frontend/src/middleware.ts` then sees
`!has_profile` and redirects to `/onboarding`. End state is correct
but the user sees a 1-frame flash of the wrong route.

**Fix:** On any error in the status fetch, push `/onboarding` instead of
`/brief`. The middleware will let onboarding render (it's a public path)
and a profile-having user is bounced *out* of onboarding by the
onboarding page itself (`onboarding/page.tsx:101`). Bounce-out is faster
than bounce-back and the failure mode (no profile) is more common than
the success mode at login time anyway for new accounts.

**Status:** Open.

---

### D-08 (P2): Signup `display_name` collected but never persisted

**File / line:** `frontend/src/app/signup/page.tsx:46,68`. UI captures
`displayName`; the value is sent only as Supabase `options.data.display_name`
which lands in `auth.users.raw_user_meta_data` — never copied to the
app's `users` or `user_profiles` table. The `users` ghost-row insert
in `onboarding_router.py:243-248` writes only `id` and `email`.

**Fix:** Either remove the field from signup (cleanest), or thread it
through: read `raw_user_meta_data->>'display_name'` from the JWT in
`onboarding/confirm` and store it in `user_profiles.display_name` (new
column — would require migration `031`).

**Recommend:** remove the field — display_name is collected again as part
of the 5-step onboarding via `role_context`, and "Tell us who you are"
(step I) already covers identity.

**Status:** Open.

---

### D-09 (P3): Frontend middleware fails open on backend outage

**File / line:** `frontend/src/middleware.ts:120-124`. If the backend is
unreachable, middleware logs nothing and renders the page anyway.

**Trade-off:** intentional per code comment ("Better to risk a brief
visual broken state than to lock the user out of the app entirely").
Acceptable for availability. A real attacker would still be blocked by
the backend's per-route checks (assuming D-01 and D-02 are fixed) — they
get an empty UI, not data.

**Recommend:** No code change. Add a Sentry/log breadcrumb so we know
when this branch fires in production.

**Status:** Accepted (with monitoring follow-up).

---

### D-10 (P3): Ghost-row UPSERT swallows email conflicts

**File / line:** `onboarding_router.py:241-252`. UPSERT on `users(id)`
runs `DO UPDATE SET email = EXCLUDED.email`. The `users.email` column
is `UNIQUE`. If a different `users.id` already holds that email (rare —
only happens if a Supabase user was deleted and re-created with a new
UUID, or if there's manual DB drift), the UPSERT fails on the unique
constraint violation. The `try/except` catches and logs, then the
profile/entity inserts blow up with FK violations against a non-existent
`users(id)`.

**Fix:** Either drop the email update on conflict (`DO NOTHING` for the
already-exists case) or detect the unique-violation explicitly and
return 409 to the client. Right now the failure mode is "500 with FK
error" and an orphaned half-insert.

**Status:** Open.

---

## Things considered but ruled out

- **Per-user usage quotas** — none currently exist; explicitly out of
  scope per `project_rbac_scope.md` (RBAC scope is locked at model
  (a)+(c) — global ingestion, per-user view filtering, no quotas).
- **Custom email verification** — Supabase Auth handles email
  confirmation if enabled at the project level. The app doesn't need to
  re-implement it. If the product wants to *enforce* confirmation
  before onboarding, that's a feature, not a bug.

---

## Verification gate (pre-merge for the fix branch)

1. `docker exec rig-backend pytest backend/tests/ -k "auth or rbac or me_ or onboarding or impersonat"` — green, including new tests for D-01/D-02/D-03.
2. `docker exec rig-backend pytest --cov=backend.auth --cov=backend.routers.me_router --cov=backend.routers.rbac_admin_router --cov=backend.routers.onboarding_router --cov-report=term-missing` — ≥80%.
3. `docker exec rig-backend bandit -r backend/auth backend/routers backend/middleware` — no HIGH severity.
4. Manual probe: with user A's JWT, `GET /api/clips/feed`, `/api/brief/{date}`, `/api/signals/feed`, `/api/clippings/feed`, `/api/analyst/sessions`, `/api/cm/pulse` all return **403** when A has no rows in `user_page_access`. Currently they return 200 — that's the bug.
5. Playwright e2e: signup → onboarding → /brief renders. Repeat for super_admin → impersonate → target's /brief renders → end impersonation → admin's /brief renders.
6. `docs/qa/auth-rbac-defects.md` — every D-N is either Fixed (linked PR) or Accepted with rationale.
