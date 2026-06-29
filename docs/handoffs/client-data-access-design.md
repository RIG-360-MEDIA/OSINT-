# Client Data Access — Isolation, API Gateway & Telemetry (Design)

How to give a client **only their relevance-filtered slice**, make cross-tenant access **impossible by construction**, instrument **usage**, and decide **frontend-only vs API**. Internal design doc.

---

## 1. Tenant isolation — "only their data", no hardcoding, no bypass

**Principle: scope is derived from the authenticated identity, never from anything the client sends.** This is already how the platform works and must be enforced for *every* data path.

### 1.1 The isolation chain (data-driven, zero per-client code)
```
API key / JWT  →  principal (analytics.users row)  →  org_id  →  user_brief_prefs (watchlist/geo/topics)  →  relevance-scoped query
```
Adding a client = create their **org** + **watchlist** + issue a **key**. No code change, no hardcoding. The relevance engine already filters every pillar to the org's entities/geo/topics.

### 1.2 The non-negotiable rules (audit every endpoint against these)
1. **Never accept `org_id` / `user_id` as a request parameter for scoping.** Always resolve it from the token's principal. (A client passing `?org_id=other` must be impossible — the param must not exist.)
2. **Object-level authorization (IDOR defense).** Any endpoint taking an `entity_id` / `article_id` / `district_id` / `story_id` must verify that object is *within the caller's allowed scope* before returning it — else `404`. Today some drill-downs (`/dossier/entity/{eid}`, `/district/{did}`) trust the id; a client key must gate these to the org's watchlist/geo set.
3. **Reject `X-Impersonate` for non-super principals.** (Already enforced in `_effective_user` / `get_current_principal` — keep it; client keys are never super_user.)
4. **Field whitelisting.** Serializers return only client-facing fields — never internal columns (`labse_embedding`, `substrate_status`, raw provenance, `clip_source`, scoring internals).
5. **Pagination + result caps.** Hard max page size; cursor-based; no "give me everything".
6. **Read-only DB role.** The API already runs as `analytics_user` (no writes to `public.*`) — keep it.
7. **Scope the RAG.** Ask-RIG currently retrieves over the **whole corpus**. For a client, either (a) constrain retrieval to their org's relevant set, or (b) make a deliberate decision that RAG is corpus-wide. Default: **scope it**, so answers can't surface another tenant's narrative.
8. **No raw query passthrough.** Only curated endpoints; never expose SQL or arbitrary filters.

### 1.3 Defense in depth
- **Rate limits + anomaly detection** per key — a client paginating the entire corpus is a flagged event.
- **Watermarking / canary rows** — seed unique benign records per org to detect redistribution.
- **Contractual** — ToS forbidding bulk extraction / resale, with the telemetry to prove violations.

> With rules 1–8, a client **cannot** reach another tenant's data *regardless of what tricks they try*, because the server never lets the request widen its own scope. Isolation is structural, not based on the client "behaving".

---

## 2. "Force them to use our frontend only" — analysis

The ask: can we make them use our **webapp** to get data (so they can't pull raw data programmatically)?

**Honest technical reality:** a white-label frontend calls the *same* backend API, and the client's browser holds a valid token. A technical client can open DevTools, see the network calls, and replay/script them. "Frontend-only" is **friction, not a security boundary** — you cannot fully stop a determined client from scripting the endpoints their own browser uses. Anti-automation (short-lived signed tokens, bot detection, obfuscation) raises the cost but is an arms race.

**What actually protects you is §1 (server-side scoping):** no matter how they call, they only ever get *their* data. So don't rely on "frontend-only" for security — rely on it for **telemetry and product lock-in**.

**Is it a good strategy?**
| | Frontend-only (no API) | API access |
|---|---|---|
| Telemetry on their *analysis* | ★★★ full (every click/filter/drill-down) | ★ pulls only |
| Integration appeal to tech clients | ✗ low (they want an API) | ★★★ |
| Bulk-extraction friction | ✓ higher | needs rate limits |
| Bypass-able | yes (replay browser calls) | n/a |
| Product lock-in | ★★★ | ★ |

**Recommendation:** **Don't make it a hard either/or.** Make the **white-label frontend the default surface** (maximizes telemetry + lock-in), and offer a **metered, strictly-scoped API as a paid add-on** for integration. Security comes from §1 in both cases; the frontend just happens to give you far richer behavioral data (see §4).

---

## 3. API gateway + usage telemetry (the build)

A small layer in front of the existing routers — no rewrite.

**3.1 API keys.** New table `analytics.api_keys (id, org_id, key_hash, label, scopes, rate_limit, created_at, revoked_at)`. A FastAPI dependency validates the key (hash compare) → loads the org principal → feeds the *same* org-scoping used by the JWT path. Keys are org-scoped and revocable.

**3.2 Usage log.** New table `analytics.usage_events (id, org_id, key_id, ts, method, endpoint, params_json, result_count, latency_ms, ip, user_agent)`. Middleware writes one row per request (async, fire-and-forget). Params_json captures the *intent* — which entities, filters, time-ranges, pillars.

**3.3 Quotas + rate limiting** per key/org (token bucket), returning `429` past quota; metered for billing.

**3.4 Analytics views** over `usage_events` → top entities/topics pulled, feature mix, frequency, peak times, growth. This is the "what do they value → what to build next" signal, per org.

---

## 4. Tracking *how* they use the extracted data (not just what they pull)

The deeper ask: can we see their **analysis, their feature logic**, not just their queries?

**The hard truth:** once raw/extracted data leaves via API into *their* system, **their downstream analysis is invisible to us.** We see the *pull*, never the *use*. No amount of API logging reveals the dashboards/models/features they build on top.

**The only way to see their analysis behavior is to keep the analysis on *our* surface.** Three levers, strongest first:

1. **Frontend behavioral telemetry (richest).** If they use our white-label desk, instrument it: clicks, dwell time, filters applied, drill-downs opened, entities focused, charts viewed, exports. *Every analytical action becomes a logged event.* This is the only place we observe their actual "feature logic".
2. **Analysis-as-endpoints, not raw data.** Instead of shipping raw rows for them to compute on, expose the *computations* as endpoints (e.g. `stance-over-time?entity=X`, `outlet-lean?subject=Y`, `emerging?geo=Z`). Then **their feature = our endpoint call**, and their call patterns *reveal their logic*. The more the product is "ask us the analysis" vs "here's the raw data", the more we learn.
3. **Canary/watermark + ToS** to detect re-use/redistribution outside agreed bounds.

**The governing law:**
> **Telemetry richness is inversely proportional to how raw the data you hand over.**
> Raw bulk export → ~zero usage insight. Curated analysis endpoints → call patterns reveal logic. Frontend/hosted → full behavioral capture.

So design the offering so the client consumes **analysis** (our endpoints / our UI), not raw data they process privately. That single choice is what makes Q3 ("learn from how they use it") actually possible.

---

## 5. Recommendation (ties to master-doc §8)

1. **Default to white-label frontend** (max telemetry + lock-in) + **metered scoped API** add-on for integration.
2. **Isolation by construction** (§1 rules 1–8) — the real security boundary; audit every endpoint, especially the `/{id}` drill-downs and the RAG scope.
3. **Build the gateway** (§3): `api_keys` + `usage_events` + rate limits. Small lift, big strategic payoff.
4. **Sell analysis, not raw data** (§4): expose computations as endpoints so their usage is observable; reserve raw full-text (copyright risk) for snippets+links only.
5. **Avoid self-host** — it gives the client everything and gives us *zero* telemetry (the opposite of the goal).

---

## 6. Concrete next steps (engineering)

- [ ] Audit all `/api/brief/*` `/{id}` endpoints for object-level scope checks (IDOR) under a client key.
- [ ] Add `analytics.api_keys` + `analytics.usage_events` (migration).
- [ ] API-key dependency + request-logging middleware in `osint-backend`.
- [ ] Per-key rate limiter + quota.
- [ ] Scope Ask-RIG retrieval to the caller's org set (or ratify corpus-wide).
- [ ] Field-whitelist the client serializers (strip internal columns).
- [ ] Frontend behavioral telemetry events (if white-label path).
