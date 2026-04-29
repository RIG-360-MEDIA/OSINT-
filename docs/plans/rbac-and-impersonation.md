# RBAC + Per-User Data Isolation + Super Admin Impersonation

**Status:** PLAN — awaiting confirmation before implementation
**Date:** 2026-04-28
**Branch target:** `feat/rbac-impersonation`

## Goals

1. Each user only sees pages they are explicitly granted (configurable per-user).
2. Each user only sees data filtered to their entity profile (shared content) and their own personal artifacts (briefs, dossiers, etc.).
3. A super admin (`pranavsinghpuri09@gmail.com`) has access to all pages, can grant/revoke page access for any user, and can impersonate any user with full read/write rights — every impersonated action is audited.

## Non-Goals

- Re-scraping content per user (rejected — model b).
- Granular row-level permissions beyond user-id and entity match.
- Multi-tenant org structure.

---

## Current State (verified)

### Frontend
- Supabase SSR client at `frontend/src/lib/supabase/client.ts`.
- `/login` and `/signup` pages exist.
- `Navigation` component reads `supabase.auth.getSession()` for sign-out.
- **No** `frontend/src/middleware.ts` — pages individually call `getSession()` and redirect. Inconsistent.

### Backend
- `backend/auth/auth_middleware.py` exposes `get_current_user(credentials)` — decodes Supabase JWT, returns `{id, email}`.
- **Security gap:** `_decode_jwt_payload` skips signature verification (TODO in code).
- Used by `analyst_router` and `brief_router`. **Other routers (clips, signals, cuttings, documents, coverage) do not gate by user.**

### DB (Postgres + pgvector)
- `users` table mirrors Supabase user IDs (UUID).
- Per-user tables already keyed by `user_id`: `user_profiles`, `user_entities`, `user_article_relevance`, `alerts`, `collections`, `briefs`, `analyst_sessions`, `analyst_turns`, `dossier`.
- `users` table has **no** `role` column.
- **No** `user_page_access` table.
- **No** `impersonation_sessions` audit table.

---

## Design

### Pages (slugs)

```
coverage    → /coverage     (Articles)
clips       → /clips        (YouTube clips)
cuttings    → /cuttings     (Newspaper editions)
threads     → /threads      (Social signals — hidden today, kept for future)
signals     → /signals      (Signal Room)
documents   → /documents    (Govt PDFs)
brief       → /brief        (Daily digest)
analyst     → /analyst      (RAG chat)
worldmonitor → /worldmonitor (Live world dashboard)
admin       → /admin        (Super admin only)
```

### Roles

```
'user'        — default. Sees pages in user_page_access; data filtered.
'super_admin' — full access; bypasses all gates; sees /admin; can impersonate.
```

### Migration `021_rbac_and_impersonation.sql`

```sql
-- 1. Add role to users
ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user'
    CHECK (role IN ('user', 'super_admin'));
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- 2. Page access
CREATE TABLE IF NOT EXISTS user_page_access (
    user_id   UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    page_slug TEXT NOT NULL,
    granted_by UUID REFERENCES users(id) ON DELETE SET NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, page_slug)
);
CREATE INDEX IF NOT EXISTS idx_user_page_access_user ON user_page_access(user_id);

-- 3. Impersonation audit
CREATE TABLE IF NOT EXISTS impersonation_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_user_id  UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at        TIMESTAMPTZ,
    reason          TEXT
);
CREATE INDEX IF NOT EXISTS idx_imp_sessions_admin ON impersonation_sessions(admin_id);
CREATE INDEX IF NOT EXISTS idx_imp_sessions_target ON impersonation_sessions(target_user_id);

-- 4. Per-impersonated-action audit (so we can replay what was done)
CREATE TABLE IF NOT EXISTS impersonation_actions (
    id          BIGSERIAL PRIMARY KEY,
    session_id  UUID NOT NULL REFERENCES impersonation_sessions(id) ON DELETE CASCADE,
    method      TEXT NOT NULL,
    path        TEXT NOT NULL,
    status_code INT,
    at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_imp_actions_session ON impersonation_actions(session_id);

-- 5. Seed super admin (idempotent — assumes the row exists from Supabase signup)
UPDATE users SET role = 'super_admin' WHERE email = 'pranavsinghpuri09@gmail.com';

-- 6. Default page grants for any existing user (everything except admin)
INSERT INTO user_page_access (user_id, page_slug)
SELECT u.id, p.slug
FROM users u
CROSS JOIN (VALUES
    ('coverage'), ('clips'), ('cuttings'), ('signals'),
    ('documents'), ('brief'), ('analyst'), ('worldmonitor')
) AS p(slug)
ON CONFLICT DO NOTHING;
```

### Backend changes

**`backend/auth/auth_middleware.py`** — harden:
- Verify JWT signature with `SUPABASE_JWT_SECRET` (HS256). Add to `config.py`.
- Resolve role and impersonation in one place. New return shape:
  ```python
  {"id": effective_user_id,        # impersonated when applicable
   "email": ...,
   "role": "user" | "super_admin",
   "is_impersonating": bool,
   "real_id": admin_id_when_impersonating,
   "impersonation_session_id": uuid_or_none}
  ```
- New deps:
  - `require_page("clips")` — checks `user_page_access` OR role=super_admin.
  - `require_super_admin` — 403 unless role=super_admin.
- Honor `X-Impersonate-User-Id` header **only** when caller is super_admin. Open or resume an `impersonation_sessions` row.

**Per-router gating** (apply `require_page(...)` at router level):
- `clips_router`         → `Depends(require_page("clips"))`
- `signals_router`       → `Depends(require_page("signals"))`
- `clippings_router`     → `Depends(require_page("cuttings"))`
- `brief_router`         → `Depends(require_page("brief"))` *(already user-aware)*
- `analyst_router`       → `Depends(require_page("analyst"))` *(already user-aware)*
- coverage / documents / worldmonitor / threads — same pattern.

**Per-user data filtering** (model a + c):
- **Shared content** (clips, cuttings, signals, documents, coverage): join against `user_entities` to filter rows that match user's tracked entities. Add `?include_unmatched=true` for super_admin convenience.
- **Personal artifacts** (briefs, alerts, collections, dossiers, analyst sessions): `WHERE user_id = :uid`.

**New router `backend/routers/admin_router_rbac.py`** (separate from existing dev `admin_router`):
- `GET /api/admin/users` — list all users + their page grants + role.
- `POST /api/admin/users/{id}/pages` — set page grants (replace).
- `POST /api/admin/users/{id}/role` — set role.
- `POST /api/admin/impersonate/{id}` — open session, return JWT-like token marker the frontend stores.
- `POST /api/admin/impersonate/end` — close session.
- All gated by `require_super_admin`.

**Middleware** — log `(method, path, status)` to `impersonation_actions` whenever `is_impersonating=true`.

### Frontend changes

**`frontend/src/middleware.ts`** (new):
- For any path under `/clips|/signals|/cuttings|/documents|/coverage|/brief|/analyst|/worldmonitor|/admin`, read Supabase session cookie.
- Unauthenticated → redirect `/login`.
- Authenticated → fetch `/api/me/access` once, cache in cookie. Redirect denied paths to `/` with toast.

**`frontend/src/lib/access.ts`** (new):
- `useAccess()` hook → `{role, allowedPages, isImpersonating, realEmail, targetEmail}`.
- `<RequirePage slug="clips">` wrapper for client components.
- `apiFetch()` helper that injects `X-Impersonate-User-Id` when impersonating.

**`frontend/src/components/Navigation.tsx`** — hide nav items the user can't access; show admin link only for super_admin; show impersonation banner ("Viewing as alice@example.com — Exit") at top of every page when impersonating.

**`frontend/src/app/admin/page.tsx`** (new):
- Table of users: email, role, granted pages (chips), "Edit" + "View as" buttons.
- Edit drawer: toggle role, toggle each page. Save → POST.
- "View as" → POST `/api/admin/impersonate/{id}` → cookie set → reload to `/`.

### Backend pageaccess endpoint

**`GET /api/me/access`** (new, in `backend/routers/me_router.py`):
- Returns `{role, allowed_pages, has_profile, has_entities, is_impersonating, target_email?}`.
- `has_profile` mirrors `/api/onboarding/status`. `has_entities` checks `EXISTS (SELECT 1 FROM user_entities WHERE user_id = :uid)`.
- Frontend middleware uses this to decide redirects (denied page → `/`; missing profile/entities → `/onboarding`).

---

## Rollout plan (PRs)

1. **PR 1 — DB + auth core** (no UI changes; cannot break existing flows)
   - Migration `021_rbac_and_impersonation.sql`.
   - Harden JWT verify (`SUPABASE_JWT_SECRET` env).
   - Auto-grant default pages on first `/api/onboarding/confirm` call (idempotent).
   - New deps: `require_page`, `require_super_admin`. `/api/me/access` endpoint.
   - Tests: `backend/tests/test_auth_middleware.py`.

2. **PR 2 — Frontend gating**
   - `middleware.ts` enforces: unauthenticated → `/login`; missing profile or entities → `/onboarding`; denied page → `/` with toast.
   - `useAccess()` hook + `Navigation` hides denied items.
   - Remove per-page `getSession()` checks (consolidated in middleware) — **except for `frontend/src/app/brief/page.tsx`** (do not touch, see guard rail).
   - E2E test: unauthenticated redirect, no-entities redirect, authenticated allowed/denied paths.

3. **PR 3 — Admin UI + impersonation**
   - `/admin` page, admin router, impersonation cookie + banner.
   - Audit logging middleware (logs to `impersonation_actions`).
   - Tests: super_admin can impersonate, audit row appears, non-admin gets 403 on `/api/admin/*`.

4. **PR 4 — Per-router page gates + data filters** (excludes brief router)
   - Apply `require_page(...)` to clips/signals/cuttings/documents/coverage/worldmonitor routers.
   - Add/strengthen entity-based filters on those routers (clips and signals already have them).
   - Tests: `user A` only sees rows matching their entities; `user B` sees a different set.

5. **PR 5 — Brief router gate** (after the parallel brief-page work merges)
   - 1-line change: add `Depends(require_page("brief"))` to `brief_router`.

---

## Locked-in decisions (2026-04-28)

- **Default page set for new signups** → **all non-admin pages auto-granted**. Super admin can revoke any page from the `/admin` UI later. Migration step 6 + a Supabase-trigger-style default in `/api/onboarding/confirm` ensure new users land with a full grant.
- **Empty entity profile** → **must be impossible**. No content page renders without at least one `user_entities` row. Frontend `middleware.ts` checks `has_profile` and `has_entities` (via `/api/me/access`) and force-redirects to `/onboarding` for any content path. Backend routers also fail closed (return 409 with `{ "error": "no_profile" }`) so direct API calls can't bypass.
- **Onboarding flow** → already exists. `/onboarding` runs a 5-question conversational flow that POSTs to `/api/onboarding/confirm` and writes both `user_profiles` + `user_entities`. `/api/onboarding/status` returns `{ has_profile: bool }`. **No changes to onboarding required** — it already does what we need. We only need to extend `/api/me/access` to expose `has_profile` so the middleware can read it cheaply.
- **Impersonation token** → **cookie-based session** (`rig_impersonate=<session_uuid>`, HttpOnly, Secure, SameSite=Lax). Reasoning: Supabase mints the JWTs and we don't want to crack open custom claims; the session row in `impersonation_sessions` is the source of truth and lets us cleanly close/audit. Backend reads cookie, looks up session row, validates the cookie's caller is the `admin_id`, then sets `effective_user_id = target_user_id`.

## Guard rail — concurrent brief-page work

A parallel session is heavily editing `backend/routers/brief_router.py`, `backend/nlp/brief_generator.py`, and `frontend/src/app/brief/page.tsx` (~964 line diff). To avoid merge conflicts:

- **Do NOT edit any of those three files** during this rollout.
- The brief router already uses `get_current_user` and filters by `user_id`, so data isolation is correct without our changes.
- Page gating for `/brief` happens **only at the frontend `middleware.ts`** in PR 2.
- A small follow-up PR after the brief rework merges will add `Depends(require_page("brief"))` to the brief router (1-line change).

---

## Estimated effort

- PR 1: ~3 hours (migration + auth + tests)
- PR 2: ~2 hours
- PR 3: ~4 hours
- PR 4: ~3 hours (most time on entity-join queries)
- PR 5: ~10 minutes (1-line change, post-brief-rework)

Total: ~12 hours focused work, spread over 2–3 sessions.
