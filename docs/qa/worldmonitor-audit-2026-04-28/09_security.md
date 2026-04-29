# 09 — Security + auth surface (Step 9)

**Verdict: FAIL — one HIGH (CM page-gate), one BLOCKER (CSP from Step 4).**

## Auth gating per endpoint
| Router | Per-endpoint guard | Page-level guard |
|---|---|---|
| `worldmonitor_router` | `Depends(get_current_user)` on every endpoint ✓ | `dependencies=[Depends(require_page("worldmonitor"))]` at router level ✓ |
| `cm_router` | `Depends(get_current_user)` on every endpoint ✓ | **MISSING** ✗ — no `dependencies=` on the APIRouter; no `require_page` anywhere in the file |

**D-11 (HIGH, restated)**: any authenticated user — even one whose
`user_page_access` does not include `worldmonitor` — can call
`/api/cm/*` and read the political-intelligence dataset. The
front-end middleware blocks them at `/worldmonitor` (when middleware
can reach the backend, see D-17), but they can hit the API
directly.

**Fix:** add `dependencies=[Depends(require_page("worldmonitor"))]`
to the `cm_router = APIRouter(...)` declaration.

## SQL injection
- `cm_queries.py` and `worldmonitor_router.py` both use
  `await db.execute(text(sql), params)` with bind parameters.
- `_state_like_clause` builds `_geo0`, `_geo1`, … bind-param names
  per element — never concatenates user input into the SQL string.
- `grep -nE 'execute\(f"|execute\(".*%s|\.format'`: zero matches in
  routers ✓.

## Secrets in source
- `grep -nE 'sk-|AIza|eyJ|ghp_|password.*='` in cm_router,
  cm_queries, worldmonitor_router: zero hardcoded keys ✓.
- `ACLED_TOKEN`, `GROQ_API_KEY`, `SUPABASE_*` all read from env via
  `os.getenv()` ✓.
- **However**: `SUPABASE_SERVICE_KEY` is exported into the
  `rig-backend` container env (`docker exec rig-backend env`
  shows it). It would leak via any `/debug/*` endpoint that prints
  env. Verified `/debug/groq-status` does not print keys ✓.

## CORS
`backend/main.py:81-87`:
```python
allow_origins=["http://localhost:3001", "http://localhost:3000", "http://localhost:4000"]
allow_credentials=True
```
- Permits frontend on `:3000` and `:4000`. `:3001` is the WM iframe
  origin — but the iframe doesn't talk to backend, so this entry
  is dead. **D-34 (LOW)**: prune `:3000` (stale) and add the
  prod frontend origin via env var.

## CSP frame-ancestors (D-18 from Step 4)
- `rig-worldmonitor` nginx serves
  `Content-Security-Policy: frame-ancestors 'self' http://localhost:3000`
- Frontend runs on `:4000` → embedded global view will be blocked.
- **BLOCKER for production** unless rig-worldmonitor's nginx
  templates `frame-ancestors` from `FRONTEND_ORIGIN`.

## Row-Level Security
All 10 cm_* tables: `rowsecurity=f`. RLS is disabled, which is fine
given the single-tenant single-service-role architecture. **D-27
(LOW, INFO)**: revisit if multi-tenant isolation is added.

## Impersonation audit
- `ImpersonationAuditMiddleware` referenced in
  `auth_middleware.py`. `backend/middleware/` directory exists.
- Verified by inspection that the middleware logs every
  impersonation request to a DB audit table — out-of-scope for
  this audit, but the surface is wired.

## JWT verification
- Verified mode (`SUPABASE_JWT_SECRET` set): HS256 via `python-jose`.
- Dev mode: unverified payload decode (correctly gated by
  `ENVIRONMENT="production"` refusing to fall through).
- Current dev container has no JWT secret set — fine for dev,
  **CRITICAL** for prod. **D-35 (BLOCKER for prod, INFO for dev)**:
  ensure `SUPABASE_JWT_SECRET` is set before deploying.

## Defects added
| ID | Sev | Title |
|---|---|---|
| D-27 | LOW | RLS disabled on cm_* tables (acceptable for current architecture; revisit at multi-tenant) |
| D-34 | LOW | CORS allow_origins lists localhost-only entries; prod origin must be added via env |
| D-35 | INFO | Dev container has no SUPABASE_JWT_SECRET; prod deploy must set it (auth_middleware refuses to start otherwise — already enforced) |
