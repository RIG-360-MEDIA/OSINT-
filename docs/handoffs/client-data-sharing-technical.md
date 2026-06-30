# RIG Data Sharing — Technical Integration Brief (for the client's engineers)

## Access
- **Transport:** HTTPS REST, JSON request/response. Streaming assistant over **SSE** (`text/event-stream`).
- **Base:** a single API host per environment (sandbox + prod). Versioned paths.
- **Spec:** OpenAPI 3 document + a sandbox key for self-serve testing.

## Authentication & authorization
- **Per-org API key** (Bearer token); keys are hashed at rest, scoped to one org, individually revocable, rotatable.
- The dashboard path additionally uses **Supabase JWT** (HS256); both resolve to the same server-side **principal → org** identity.
- **Authorization is server-derived, never client-supplied:** the org/tenant is read from the key, not from any request parameter. There is no `org_id` query param to tamper with.

## Tenant isolation (by construction)
- **Row scoping:** every query is filtered to the caller's `org_id` + watchlist (entities/geo/topics).
- **Object-level checks:** any `/{id}` lookup verifies the object is within the caller's scope → otherwise `404`.
- **Read-only DB role:** the API connects as a read-only Postgres role; it physically cannot write or reach write-only tables.
- **No raw query passthrough / field-whitelisting:** only curated fields are returned (no internal columns like embeddings or pipeline status).

## Endpoints (functional groups)
- **Brief / situation** — daily brief, home, cross-pillar.
- **Analytics** — coverage volume, directed sentiment, outlet lean, topic battlefield.
- **Entities / dossier** — roster, per-entity profile + drill-down articles.
- **Map** — geo aggregates, country/district feeds (cursor-paginated).
- **Sources** — "show me the articles" receipts behind any figure.
- **Assistant** — `POST /chat` (SSE: status → tokens → sources → charts).

## Data model
- JSON objects; **cursor-based pagination** (`next_cursor`), hard page caps.
- Structured intelligence per item: entities, **directed stance** (supportive/critical + intensity), topic, geography, claims/quotes, language, timestamps, story-cluster id.
- Third-party article bodies are returned as **snippets + canonical source URLs**, not full reprints.

## Rate limiting, quotas, metering
- Per-key **token-bucket** rate limit; `429` + `Retry-After` past quota.
- Every request logged (org, endpoint, params, result count, latency) → usage analytics + billing.

## Delivery modes
1. **Pull REST API** (default).
2. **Webhooks / push** — alerts on new coverage matching a watchlist.
3. **White-label dashboard** — hosted or iframe-embedded, org-scoped.
4. **Warehouse feed** (optional) — scheduled export into the client's DB.

## Freshness
- Continuous ingestion; items are query-available shortly after publish. No nightly dump — every call returns the current state.

## Security
- TLS in transit; scoped + rotatable keys; full audit log; CORS allow-list for browser clients; no third-party PII beyond public reporting.

## Build status (be honest internally)
- **Live today:** FastAPI backend, `/api/brief/*` + Ask SSE, Supabase-JWT auth, per-org scoping, read-only DB role, the dashboard.
- **To build for a paying client:** API-key issuance, per-key rate limits + `usage_events` metering, the `/{id}` object-level checks (IDOR hardening), OpenAPI doc, optional webhooks/warehouse feed.
