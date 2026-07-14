# Client Partner API — Build-to-Complete Plan (0 → 100)

Goal: take the `/v1` OSINT intelligence API from "core built, hot-patched, live, and
**over-documented**" to the **full documented contract + the client's confirmed asks**,
durable, verified, and onboarded for a paying client.

Source of truth for current state: session audit 2026-07-07/08, re-verified live.
**The client is building their UI against our published API doc** (`rig-api-documentation.pdf`),
so every endpoint in that doc is now a contract — several don't exist yet.

---

## Phase 0 — AUDIT RESULTS (run live 2026-07-08)

**🔴 BLOCKER (Phase 1 first action):** the deployed `/v1` **cannot authenticate any client today.**
`OSINT_APIKEY_HASH_SECRET` is UNSET, no secret file at `/app/secrets/apikey_hash_secret`, and
`OSINT_ENVIRONMENT=production` → `hash_secret()` fail-closes (raises). A well-formed key → 500; there
are also **0 api_keys and 0 scope rows** — no client has ever been able to call the API. The code is
designed for the secret to be deployed as that **file + restart** (baked-safe, avoids a recreate that
would wipe the hot-patched `v1`). Fix = write the secret file + `docker restart osint-backend`, done
together with the durability fix.

**App health:** `/v1/health` → `{"data":{"status":"ok","api":"rig-intelligence","version":"v1"}}` ✅
(envelope correct). Reachable on the host at `127.0.0.1:8002` (not `localhost` — IPv6). Container port 8000.

**Live route inventory (13):** `GET /v1/{health,usage,articles,articles/{id},entities,entities/{id},
entities/{id}/coverage,analytics/sentiment,analytics/coverage,analytics/keyword-sentiment}`,
`POST/GET /v1/webhooks`, `DELETE /v1/webhooks/{id}`. **Documented-but-missing (~10):** `/brief/*` (3),
`/analytics/outlets`, `/analytics/topics`, `/stories` (2), `/geo/*` (2), `/ask`.

**Auth/scope schema:** `analytics.api_keys` (HMAC-SHA256 key_hash, `is_sandbox`, per-key rate/quota,
expiry, revoke) · `orgs` · `org_api_scope(all_entities, entity_ids uuid[], topics text[], regions text[],
languages text[])`. Supports sandbox keys + scope by entity/topic/region/language. **No `mute_terms`
column** (matches the gap). Key format `rig_live_…` / `rig_test_…`.

**Data-completeness snapshot (30-day usable = 533,749 articles):**
| field | % | field | % |
|---|---|---|---|
| language | 97.2 | full_text | 96.1 |
| translated | 93.3 | embeddings v4 | 83.3 |
| entities | 80.2 | topic | 73.9 |
| summary | 71.2 | per-article stance | 63.3 |
| **geo** | **54.4** ⚠ | claims/quotes flag ran | 100* |

Flags: **geo only 54%** → district breakdowns (client priority) cover ~half the corpus; `claims/quotes`
= "extraction ran," not "has content" (verify payloads in fast-follow). `full_text_scraped` +
`full_text_translated` exist → "Top news full text" is a serializer change, not a data gap.

**Deferred (blocked by the secret):** authenticated smoke of all 13 routes + scope-isolation (in-scope
Trump/USA vs out-of-scope Iran) + webhook POST/DELETE. Provisioning path is proven (mint in-container with
the app's own secret → org+scope+key rows); re-run immediately after the Phase 1 secret fix with a
7-day-expiry audit key. **No test rows were created** (mint fail-closed before any INSERT; orphan check = 0).

---

## Phase 1 — RESULTS (executed live 2026-07-08)

**Durability — DONE & proven.** Earlier "v1 is a hot-patch a recreate wipes" was **stale**: verified
`v1` is byte-identical across the **baked image, running container, and host build context** (25 files)
→ recreate-safe *and* rebuild-safe. osint-backend was recreated (no build) and `v1` stayed intact.

**Auth secret — CONFIGURED durably.** Root cause of "can't authenticate": `OSINT_APIKEY_HASH_SECRET`
unset + prod fail-close. Fix: generated a 32-byte secret into `/root/rig/infrastructure/.env` +
referenced `${OSINT_APIKEY_HASH_SECRET}` in the osint-backend compose env (same pattern as SUPABASE_*),
`docker compose up -d --no-build`. Backups: `docker-compose.yml.bak-apikey-*`, `.env.bak-apikey-*`.
Well-formed bad key now → 401 (was 500). Auth works end-to-end.

**Verification — ~37/38 checks green** (harness on host: `/root/phase1_verify1.sh`, `_verify2.sh`; audit
key persisted `/root/.phase1_audit.env`, org `PHASE1-AUDIT`, scope Trump+USA, 7-day expiry keys):
- Auth lifecycle ✅ live/sandbox 200; no-auth/malformed/bad/**revoked**/**expired** → 401.
- All 13 routes 200 (entity-UUID filtering works; articles/{id} 200).
- **Scope isolation airtight** ✅ out-of-scope Iran → sentiment 404, entity 404, articles 200 **empty (no leak)**, entities list == exactly 2.
- Validation ✅ limit 9999/0/−5 → 422; window 9999/0 → 422; missing args → 422; sentiment=purple → 422; bad-uuid → 404.
- Pagination ✅ cursor advances (distinct ids); bad cursor → 400.
- Envelope ✅ data+meta / error{code,status}.
- Rate limit ✅ 200,200,429,429… + `Retry-After: 30` + `X-RateLimit-*` headers.
- Metering ✅ increments. Webhooks ✅ POST→id+`whsec_` signing secret, list, DELETE 200. **SSRF `169.254.169.254` → 400 rejected**.

**Findings:**
- **F1 — unknown query param → 200 — RESOLVED (option A, chosen 2026-07-08):** keep standard REST
  behavior (ignore unknown params — robust; strict rejection can break clients using cache-bust/tracking
  params). No code change. Action item: **remove the "Unknown parameter → 400" promise from the client
  doc** in the Phase-7 OpenAPI reconciliation (the `{"code":"bad_request","message":"Unknown parameter
  'windwo'"}` example must go).
- **F2 — keyword-sentiment cold latency — PARTIALLY FIXED.** Verified live: dead keys were NOT the cause
  (69s with clean keys). Tuned `KW_SENT_CONC=32` + `KW_SENT_CAP=80` → **cold 69s→38s, cached ~50ms**
  (committed 3d6ea5f). 38s is still too slow for a sync client call; **real fix = precompute scoped
  keywords on a schedule (instant reads) + make the ad-hoc path async/202** — deferred to the endpoint-build phase.
- **F3 — Groq dead keys — FIXED.** Tested all 31 individually: 20 OK, 10 `organization_restricted`
  (account ban, unrecoverable), 1 invalid-401. Pruned the 11 dead from the shared pool `.env` → 20 working
  keys; osint-backend recreated, **0 restricted errors** (committed 3d6ea5f). NOTE: **rig-backend still
  runs the old 31-key env** until its next recreate — pruning benefits the whole ingest LLM pool
  (topic/sentiment) but restarts ingest, so left for a deliberate moment.

**Remaining Phase 1 polish (not yet done):** commit the compose env-ref line to git so a fresh deploy
keeps it (secret VALUE stays in `.env`, uncommitted); add `OSINT_APIKEY_HASH_SECRET` to `.env.example` +
deploy docs; CI/boot smoke that fails if `/v1` missing. Cleanup: `/root/.phase1_audit.env` (raw keys, 600)
+ `PHASE1-AUDIT` org expire in 7 days — remove earlier if desired.

---

## Locked decisions (2026-07-08)

1. **Sentiment = STANCE ONLY.** No "impact" field anywhere (incl. dropped from the live prompt).
2. **Labels: keep the client's vocabulary `supportive / neutral / critical`.** Engines may compute
   `positive/negative/neutral` internally; a **serializer-only mapping** (`positive→supportive,
   negative→critical, neutral→neutral`) presents the client's words. Zero internal churn, reversible.
3. **Per-article sentiment `{label, intensity}`** — `article_stances.intensity` is already **0–1**
   (0.1–1.0, avg 0.577). Surface directly for the precomputed path; add a `stance_confidence` to the
   live keyword prompt so live-scored items also carry intensity.
4. **One unified sentiment endpoint** `subject=` (name/alias/id, scoped) with invisible fast
   (precomputed) / live (keyword) routing; single response shape.
5. **Credibility flag = source-transparency signals, NOT a truth score, and NOT `source_tier`.**
   `source_tier` is a **reach/size** tier (tier 3 = small district press + a fact-checker like Boom
   Live) — using it as credibility would mislabel the exact district journalism the client values.
6. **Durability = bind-mount `/root/rig` + commit to `main`** (parity with rig-backend).

## Credibility flag — the honest design + client-facing wording

Ship a `source_flags` object on articles/stories, each field present only when defensible:
- `political_lean` — outlet's known editorial lean/affiliation (`state`, `lean-left/right`, …),
  shown only where classified (we have `sources.political_lean`, ~27% filled → "shown when known").
- `coordinated_coverage` — computed from **our cluster data**: same story text reprinted across many
  outlets with a low `independent_source_count` = syndicated/coordinated. No per-source rating needed.
- `low_credibility` — **curated** list of known propaganda/fake-news domains only; absence ≠ endorsement.

**Client doc wording (draft):** "Source & credibility signals — each article/story may carry a
`source_flags` object surfacing transparency signals about the outlet and the coverage pattern, **not a
verdict on the article's truth**: `political_lean` (the outlet's known editorial lean/affiliation, shown
where classified); `coordinated_coverage` (the same story reprinted across many outlets with few
independent originators — syndicated/coordinated distribution); `low_credibility` (true only for outlets
on our curated low-credibility list; its absence is not an endorsement). These aid analyst judgement; we
do not assert any individual article is true or false."

---

## Endpoint inventory — the full contract (✅ built · 🟡 partial · ❌ not built)

**Platform (built):** Bearer-key auth, per-org scope, token-bucket rate-limit + `X-RateLimit-*` headers,
`Retry-After` on 429, metering, `GET /usage`, `{data, meta}` envelope, error envelope, cursor pagination.

| # | Endpoint | Status | Work |
|---|---|---|---|
| 1 | `/brief/today`, `/brief/daily?date=`, `/brief/situation` | ❌ | scope-filtered digest + story summaries |
| 2 | `/analytics/sentiment` (unified `subject=`, split, net_lean, **daily[]**) | 🟡 | add daily trend, name-resolve, label-map |
| 3 | `/analytics/coverage?window` (mention trend, daily) | ✅ | add month window |
| 4 | `/analytics/outlets?entity&window` (source breakdown: vol + lean/outlet) | ❌ | build |
| 5 | `/analytics/topics?window&limit` (top topics) | ❌ | build (topic data exists) |
| 6 | `/entities` list + `?q=` typeahead search | 🟡 | add `?q=` search |
| 7 | `/entities/{id}` profile + `snapshot{coverage_7d, sentiment_7d, top_topics}` | 🟡 | build snapshot |
| 8 | `/entities/{id}/coverage` | ✅ | uniform filters |
| 9 | `/articles` feed (filters: entity/topic/match/sentiment/from-to/language/sort/limit/cursor) | 🟡 | see enrichment ↓ |
| 10 | `/articles/{id}` full item | 🟡 | full_text + quotes/facts/flags |
| 11 | `/stories` (article_count, last_updated, **outlet_count**, entities, sentiment) | ❌ | build (data exists: `independent_source_count`) |
| 12 | `/stories/{id}` (timeline/arc + members) | ❌ | build |
| 13 | `/geo/coverage?window` (state→district counts) | ❌ | build |
| 14 | `/geo/district/{id}?window` (district feed) | ❌ | build — **client's stated priority** |
| 15 | `/ask` (SSE: status/token/chart/sources/done) | 🟡 | wire Ask-RIG to documented SSE (fast-follow OK) |
| 16 | `/webhooks` CRUD + **delivery worker** (HMAC, retry, log; events: coverage.matched, sentiment.critical, spike, story.new) | 🟡 | build delivery + events |
| 17 | Related players / key quotes / key facts (detail fields) | ❌ | fast-follow |
| 18 | Scope/provisioning API (entities/topics/keywords, **mute terms**, **priority**, webhook sub, 30-day backfill, purge) | 🟡 | build; answer "API vs team-managed" |

**Article-object enrichment (feeds 9/10/11/12/14):** add `full_text`, per-article `sentiment{label,
intensity}`, `story_id`, `last_updated`, original + translated text + `language` tag, `source_flags`,
per-item signals (`relevance_score`, `source_authority`), `geo` (present). Cursor must order by
**ingestion/update time** so late-arriving/corrected items are caught. `api_ready_at` completeness marker
so clients never pull half-enriched rows.

---

## The build — phase by phase, 0 → 100

### Phase 0 — Audit & freeze the contract *(½–1 day)*
- Diff live routes vs the documented PDF → authoritative gap register (this table, formalized).
- Provision test org + scoped key **+ sandbox key**; smoke every route; prove scope isolation (out-of-scope → empty/404, never leak).
- Coverage snapshot per returned field (stance %, topic %, entities/article, embeddings %, geo/country %).
- Freeze the response shapes to match the doc the client is coding against.

### Phase 1 — Durability *(1 day, DO FIRST)*
- Bind-mount `/root/rig` into osint-backend; commit the whole `v1/` tree + hot-patches to `main`.
- Prove recreate-safety (`docker recreate` → `/v1/health` 200); CI/boot smoke that fails if `/v1` missing.

### Phase 2 — Data-layer enrichment — ✅ COMPLETE + BAKED (2026-07-08)
2a ✅ 2b ✅ 2c ✅ 2d ✅ deployed, verified live, and **baked into `infrastructure-osint-backend:latest`
via `docker commit`** (survives a recreate). Deploy loop = edit local → scp to context → `docker cp` into
container → py_compile gate → restart.
✅ **Context↔image reconcile — DONE 2026-07-08.** The "drift" (`642b…`≠`651c…`) was a **FALSE ALARM** —
an `xargs`/ordering artifact. Per-file md5 over all 80 non-v1 files: **identical** → context == running
container == baked image. **A `docker compose build` is SAFE** (reproduces the running state incl. Phase 2).
Real fragility was git: the entire `v1/` tree was **untracked** (working-tree/image only). Fixed —
committed `v1/` to git (`e0835c6`), so a clean checkout+build reproduces the API.
**Remaining (pre-existing, NOT introduced here):** the broader osint-backend working tree has ~17 untracked
+ 4 deleted + 18 modified non-v1 files never committed to `/root/rig` — a product-wide hygiene debt to
review/commit separately (involves code outside the API).
🔴 **INCIDENT (resolved):** attempting `ALTER TABLE articles ADD COLUMN api_ready_at` queued for ACCESS
EXCLUSIVE behind leaked idle-in-tx readers and **stalled ingest ~10 min** (INSERTs blocked behind the
ALTER). Fixed by terminating the stuck ALTERs + idle-in-tx holders; ingest recovered (30 art/10min).
**Lesson: NO DDL (ADD COLUMN / trigger / CREATE INDEX) on the hot `articles` table — it blocks ingest.**
Use computed columns or SKIP-LOCKED UPDATEs. (Also: `pg_terminate_backend` filters must include
`pid <> pg_backend_pid()` — a `query ILIKE '%ALTER…%'` match self-terminated my own session once.)
The `api_ready_at` column got added before I aborted → left **vestigial (all-NULL, harmless)**; drop in a
maintenance window or repurpose. `api_ready` is served as a **computed boolean** instead (zero DB load).
- **Article object:** ✅ `full_text` (translated|scraped), `story_id` (thread_id, nullable), `last_updated`
  (updated_at, ISO-UTC) exposed on list+detail. `geo`/`language` already present. Cursor already orders by
  `collected_at` (ingestion) → late items caught; `last_updated` lets clients detect corrections.
- **Per-article sentiment:** ✅ lateral join on `article_stances` (strongest stance toward the scoped entity),
  serialized `{label, intensity}` mapped supportive/critical/neutral (`positive→supportive, negative→critical`),
  `null` when absent. Filter-consistent (`?sentiment=critical` ⇒ all items critical). Intensity 0–1 verified.
- **2c `source_flags`:** ✅ `political_lean` (from `sources`, ~383 outlets) + `low_credibility` (bool, backed
  by curated `analytics.low_credibility_sources`, empty seed → honest "not listed"). `coordinated_coverage`
  DEFERRED (needs verified cluster-reprint computation — don't fake it).
- **2d `api_ready`:** ✅ computed boolean (substrate ok + not-dup + title + topic + embedding + entities).
- DEFERRED (small follow-ups): server-side `?ready=true` filter (bool is exposed; clients can filter now);
  original+translated *full-text* split if the client wants both; `coordinated_coverage`.
- **`api_ready_at`** marker (title+lead+topic+entities+embedding+sentiment present) + backfill; clients filter on it.
- **Cursor by ingestion/update time** (`collected_at`/`updated_at`); `last_updated` on articles + entities.
- **`source_flags`:** `political_lean` passthrough; build `coordinated_coverage` from cluster reprint density; seed curated `low_credibility` list.
- **Wire sentiment into live ingest** so new articles are scored on arrival (API must not lag ingest).

### Phase 3 — Core endpoints to the documented contract *(3–4 days)*
STATUS 2026-07-08: **`GET /v1/stories` ✅ DONE** (list) — deployed, verified, committed `ff587fe`, baked.
Reads `analytics.story_clusters_v8` (v9 keeper). Canonical surfaceable filter (verified against night-desk
`stories.py:543`): `status='active' AND is_template_family IS FALSE AND (independent_source_count>=3 OR
rescued_from_story_id IS NOT NULL)` — NOTE no `provisional` gate (all rows are provisional=true) and the
`IS FALSE` (not `IS NOT TRUE`) matters. Scope filter mirrors /articles: member mentions a scoped entity
(via `story_cluster_members_v8`→`article_entity_mentions`) OR `subject_region` ∈ org regions; `?entity=`
narrows to entity-only, default = full scope. Outlets = deduped `independent_source_count` (count) +
top-3 names from `members.source_id`→`sources` (NOT via `articles` — lossy on retention-purged old clusters).
Keyset pagination by `importance_score` (bind cursor importance as float, not str — asyncpg DataError otherwise).
Verified: fast (~0.8s), scope-isolated (out-of-scope Iran→0), pages distinct + ordered, bad cursor→400.
**ALL 6 REQUESTED ENDPOINTS SHIPPED + VERIFIED + BAKED (2026-07-08):**
1. `GET /v1/analytics/topics` ✅ — scoped topic_category counts (OTHER excluded).
2. `GET /v1/analytics/outlets?entity=` ✅ — per-outlet volume + net_lean toward a scoped entity; out-of-scope→404.
3. `GET /v1/geo/coverage` + `/v1/geo/district/{slug}` ✅ — district counts by state + district detail; region-scoped
   (region precedence; out-of-scope state→404). **⚠ DATA CAVEAT: the district-tagging pipeline
   (`tasks.cm.tag_article_districts`) has STALLED — `article_districts` has 49,654 rows but 0 in the last 7 days**
   (50,806 IN articles arrived untagged). So recent windows are empty; window=90 works (hyderabad=9,871 arts).
   Endpoints correct; the tagging job needs restarting for fresh geo. Gazetteer = TG+AP only (59 districts).
4. `GET /v1/analytics/sentiment` ✅ — now accepts entity **name or id** (scoped resolver, out-of-scope name→404) +
   **`daily[]` 7-day trend** + supportive/neutral/critical + net_lean.
5. `GET /v1/brief/today|situation|daily` ✅ — structured scope digest (top surfaceable stories grouped by topic);
   reuses list_scoped_stories. (Prose LLM narration = future; v1 is structured + a count summary.)
6. `GET /v1/stories/{id}` ✅ — surfaceable+scope-guarded detail: metadata + chronological member timeline (≤200)
   + full outlet breakdown; assembled from v8 keeper (avoids the 2-system chronicle split). out-of-scope→404.
All deployed via docker cp+restart, committed (eb3ebf5, 15105cd, 717b94d), and baked into the image.
Every one verified: 200s, scope isolation (out-of-scope→404/empty), pagination, and shape.
DEFERRED: per-story sentiment rollup on detail; historical `/brief/daily?date=`; restart the geo tagging job.
- **Sentiment** unified `subject=` + `daily[]` trend + label map + name resolution.
- **Entities** `?q=` search + `/{id}` snapshot.
- **Outlets** `/analytics/outlets`; **Topics** `/analytics/topics`.
- **Stories** `/stories` + `/stories/{id}` (outlet_count = independent_source_count, timeline).
- **Geography** `/geo/coverage` + `/geo/district/{id}`.
- **Brief** `/brief/today` + `/brief/daily` + `/brief/situation` (scope-filtered).
- **Consistency pass:** identical filter vocabulary, sort (`recent|relevant` + expose signals), pagination, envelope across all.

### Phase 4 — Delivery, alerts & scope management *(2–3 days)*
- ✅ **Webhook delivery worker — DONE 2026-07-08** (`v1/webhook_delivery.py`, commit 44d9b02, baked,
  migration 140, cron `/etc/cron.d/rig-webhook-delivery` every 2 min flock-guarded). Per active webhook:
  match new coverage (org scope + filter entity/topic/sentiment since `last_delivered_at`), HMAC-sign the
  JSON body (`X-RIG-Signature: sha256=…`, derived secret), POST with retry/backoff, log to
  `analytics.api_webhook_deliveries`, advance watermark (ordered at-least-once), disable after 15 fails.
  **SSRF-guarded** (https + host resolves to public IPs). **Verified e2e: 20/20 delivered, sig validates,
  logged, watermark advances.** Events: `coverage.matched` (sentiment.critical via filter). spike/story.new = future.
- ✅ **Rate-limit/quota + metering** — verified in Phase 1 (429 + Retry-After + X-RateLimit-*; /usage increments).
- ✅ **Scope self-management — DONE 2026-07-08** (commit 9a7974a, baked, migration 141). Client answer
  (their email §2/§5/§8) settled it: **API-managed**, mute terms + keyword priority yes, **explicit
  confirmed purge, no cascade**. Built: `GET /v1/scope` (any key), `PATCH /v1/scope` (management key
  `can_manage=true` — add/remove entities/topics/keywords/regions/languages/**mute_terms** + keyword
  priorities, plan-capped), `POST /v1/scope/purge` (`confirm=true` → clears scope + deactivates webhooks).
  **mute_terms wired into /articles + /stories + /brief.** Security note: corpus is shared → scope is a
  per-org filter, not a data boundary, so self-management is safe; caps are commercial guardrails.
  Verified: 403 without can_manage, PATCH persists, mute filters (0 "war" titles), confirmed purge.
  DEFERRED: **30-day backfill on a new keyword** (ties into the keyword_watch/dossier subsystem — separate);
  webhook subscription provisioning already exists (CRUD).

### Phase 5 — Fast-follow features *(2–3 days, may trail launch — client agreed)*
- **`/ask` SSE** to the documented contract (status/token/chart/sources/done).
- **Related players** (entity co-occurrence), **key quotes**, **key facts & figures** on detail endpoints.

### Phase 6 — Data readiness / quality *(parallel, gated by backfills)*
- Sentiment stance coverage ≥ target (3-GPU backfill improves it as it lands — non-blocking).
- Topic (fixed) / embeddings (draining) / entities / country all ≥ target.
- Fix future-`published_at` at source (5 TZ-misparsing collectors); retire the cron janitor.
- **UTC ISO-8601 sweep** — every timestamp stamped UTC (client renders IST).

### Phase 7 — Documentation *(1 day)*
- Reconcile the PDF into a **living OpenAPI** that matches the built contract exactly; curl per endpoint; error schema; versioning/breaking-change policy; Postman; sandbox vs prod note.

### Phase 8 — Validation & verification — mostly ✅ (2026-07-08) — see docs/handoffs/api-verification-report.md
- ✅ **Security review** (security-reviewer agent, full v1 read): "unusually well-built" — no SQLi, no IDOR,
  no priv-esc, no secret leak, no auth oracle. Findings: **M1** (WEBHOOK_ALLOW_INSECURE prod guard) + **M3**
  (SSRF check at webhook creation) FIXED (commit c05dbb3, verified 169.254/127.0.0.1→400, public→200).
  **M2** (SSRF DNS-rebind TOCTOU) = documented residual, mitigated. LOWs (per-process rate limiter, quota
  fail-open) accepted at current single-instance topology.
- ✅ **Live end-to-end acceptance: 42/42 PASS** (`/root/phase6_acceptance.sh`) — auth lifecycle, all 23
  routes, scope isolation, validation, rate-limit, metering, scope-mgmt, envelope. Signed report written.
- ✅ **Data-quality honesty pass** — per-field coverage recorded; sentiment labeled sample, source_flags =
  transparency-not-truth, credibility curated-only.
- ⏳ **pytest ≥80% on `v1`** — NOT done; live acceptance + security review are the evidence today; a formal
  coverage suite (needs test DB + fixtures) is the remaining quality bar.

### Phase 9 — Client onboarding *(½ day)* → **100%**
- Provision client org + scope + **prod key (shown once)** + sandbox key.
- Deliver docs + verification report + limits/SLA; monitoring/alerts (error rate, latency, quota, webhook failures).

---

## Timeline
```
P0 audit          ▓ ½–1d
P1 DURABILITY     ▓▓ 1d      ← first; nothing safe until this lands
P2 data layer     ▓▓▓ 2–3d   ← foundation the endpoints read
P3 core endpoints ▓▓▓▓ 3–4d  ← the documented contract
P4 delivery+scope ▓▓▓ 2–3d
P5 fast-follow    ▓▓▓ 2–3d   (may trail launch)
P6 data quality   ░░ parallel
P7 docs           ▓ 1d
P8 verification   ▓▓ 1–2d
P9 onboarding     ▓ ½d
```
**~2.5–3.5 weeks to fully-verified & client-ready** (scope ~doubled once the doc became the contract).
Critical path: **1 → 2 → 3 → 8**. Launch-blocking essentials live in P2+P3; fast-follow (P5) can trail.

## Open questions to answer back to the client
1. **Scope management:** API-managed vs team-configured? (They want to provision scope + webhooks programmatically on approval — we can expose a scoped provisioning API, or keep it team-side for v1.)
2. **Credibility framing:** confirm they accept source-transparency signals (lean + coordinated + curated low-cred) rather than a per-article truth verdict for launch.
3. **Fast-follow timing:** `/ask` SSE + related-players/quotes/facts confirmed as just-after-launch.
