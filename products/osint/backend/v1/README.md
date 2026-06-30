# /v1 — Client API Gateway

A sealed, key-authenticated, per-org-scoped **read** API for external clients.
Isolated from the JWT dashboard surface: it never touches Supabase JWTs or
impersonation, and every data path is forced through one scope gate so
leak-safety is enforced in a single auditable place.

## Request lifecycle
```
HTTP /v1/* 
  → MeteringMiddleware (pure-ASGI; times request, injects X-RateLimit-*,
                        fire-and-forget usage write — never blocks)
  → get_api_principal  (auth.py)   key → org; 401 on any failure
  → enforce_limits     (ratelimit.py) token bucket + monthly quota → 429
  → get_context        (scope.py)  loads the org's provisioned scope
  → endpoint           queries.py (scope-filtered SQL) → serializers.py (whitelist)
  → ok() envelope      (errors.py)
```

## Module map
| File | Role |
|---|---|
| `keys.py` | key generation + HMAC hashing (raw key never stored) |
| `settings.py` | gateway env config; fail-closed hash secret in prod |
| `auth.py` | `get_api_principal` — key → org; ignores X-Impersonate |
| `scope.py` | **the scope gate** — `effective_entity_ids`, `require_entity_in_scope` (IDOR) |
| `ratelimit.py` | in-process token bucket + quota; `enforce_limits` dependency |
| `metering.py` | pure-ASGI usage logger (SSE-safe) + rate headers + counter bump |
| `filters.py` | unified validated `CoverageFilters` (entity/topic/match/sentiment/window) |
| `pagination.py` | tamper-evident keyset cursors |
| `queries.py` | scope-filtered SQL — selects only client-safe columns |
| `serializers.py` | outward field whitelist (drops internal columns) |
| `errors.py` | `GatewayError` + `{data}/{error}` envelopes |
| `endpoints/` | entities, articles, analytics, usage, webhooks, meta |
| `admin.py` | staff-only (JWT) key issue/list/revoke + scope provisioning |
| `router.py` | assembles all routers |
| `__init__.py` | `install_v1(app)` — one call wires router + middleware + handler |

## Leak-safety invariants (do not break)
1. Every data query is constrained by `scope` — empty/absent scope yields **zero
   rows**, never the corpus (`effective_entity_ids` returns `[]` for an
   unprovisioned non-`all_entities` org, and endpoints early-return empty).
2. `all_entities=true` is the ONLY way an org reads beyond its `entity_ids`, and
   it's set only by staff via `/v1/admin/scope`.
3. Out-of-scope and not-found return an **identical 404** (no existence oracle).
4. SQL is parameterised; f-string fragments interpolate only fixed clause
   strings, never user input.
5. Auth fails closed; metering fails safe (never blocks); quota read fails open
   for availability (rate limiting still applies).

## Config
- `OSINT_APIKEY_HASH_SECRET` (required in prod — fail-closed)
- `OSINT_V1_RATE_LIMIT` (default per-key req/min; per-key override in DB)

## Tests
`python -m pytest v1/tests` — auth rejection, scope/IDOR, whitelist, cursor
tamper, filters, rate limit. DB-backed endpoint behaviour = integration (needs
a populated DB). Deploy steps: `docs/handoffs/api-gateway-deploy-runbook.md`.
