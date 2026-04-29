# Coverage Pillar — Production-Readiness Audit (2026-04-28)

Branch: `feat/embed-worldmonitor` · Auditor: RIG Surveillance · Date: 2026-04-28

This document captures the full top-to-bottom audit of the **Articles / Coverage** pillar (page `/coverage`, router `/api/coverage/*`, RSS+HTML+newspaper collectors, NLP + relevance pipeline). It records evidence, flags defects (see `coverage-defects.md`), and lists the per-source health verdict (`coverage-source-health.md`).

**Top-line verdict:** The data plane is solid (zero DB integrity defects, NLP backlog = 0, 89 articles/hour ingesting). The control plane has **2 P0 issues that block production**: (a) the entire backend pytest suite for the coverage router is failing because `require_page("coverage")` is not stubbed in the test harness; (b) `/article/<bad-uuid>` returns HTTP 500 instead of 422. Plus 8 P1/P2 issues. Frontend Vitest 12/12 green. Live `/feed`, `/search`, `/article` happy paths are functional.

---

## Phase 0 — System snapshot

| Probe | Result |
|---|---|
| `docker ps` | rig-postgres, rig-backend, rig-frontend all healthy; worldmonitor stack also up |
| Backend processes (`ps -ef`) | uvicorn + 6 Celery workers (collectors=1, social=2, youtube=1, **documents=2**, nlp=4, relevance+brief=4) + 1 Beat. **The `documents` queue gap noted in CLAUDE.md is RESOLVED** — start.sh already launches `worker-documents`. |
| Beat | Single scheduler process (no double-fire) |
| Backend logs (24 h) | 4 137 `parsed tree length: 1, wrong data type or not valid HTML` errors (HTML scraper stub responses); 211 Groq 4xx; 16 govt-doc relevance errors; 27 `tasks.cm.tag_stance` errors. |

## Phase 1 — Database integrity ✅

| Check | Pass criterion | Result |
|---|---|---|
| Articles total | n/a | 13 096 (89 / 1 h, 674 / 24 h) |
| Orphan articles (no source) | 0 | **0** ✅ |
| Duplicate `url_hash` | 0 | **0** ✅ |
| `is_duplicate=true` without `duplicate_of` | 0 | **0** ✅ |
| `duplicate_of` pointing to nothing | 0 | **0** ✅ |
| Embeddings missing on processed rows | <1 % | 74 (0.56 %) ✅ |
| `inserted_at` null | 0 | **0** ✅ |
| `thread_id` invalid | 0 | **0** ✅ |
| HNSW index on `labse_embedding` | enabled or documented | **enabled** (`idx_articles_embedding`, 50 MB) ✅ |
| Migration 019 (`inserted_at`) populated | yes | yes ✅ |

Index health (`pg_stat_user_indexes`): 16/18 indexes used; **`idx_articles_topic`** and **`idx_articles_updated_at`** both at `idx_scan = 0` → see C-3.

Topic distribution: `OTHER` = 5 561 (43 %), `POLITICS` = 2 266, `SPORTS` = 811, etc. 18 rows with `topic_category IS NULL` despite `nlp_processed=true` — see C-4.

UAR snapshot for the only active user (`db4b9207-…3465`):
- tier 0 = 4 544, tier 1 = 135, tier 2 = 185, tier 3 = 8 214 (total 13 078)
- Stage 2 explanations populated for tier 1 (100 %), tier 2 (99 %); absent for ~95 % of tier 0/3 (probably by design — Stage 2 only runs on score ≥ 0.4). See C-5.
- `scored_at` minimum = 2026-04-20 — UAR rows older than 7 days: 93/135 tier-1 (69 %), 66/185 tier-2, 3 544/8 214 tier-3. See C-6.

## Phase 2 — Collectors

Source files reviewed: `direct_rss_collector.py` (442 LOC), `rss_collector.py` (457 LOC), `html_collector.py` (262 LOC), `newspaper_collector.py` (881 LOC).

Behaviours that pass:
- All inserts use `INSERT … ON CONFLICT (url_hash) DO NOTHING` — dedup is database-enforced.
- Health-score adjustments on success (+0.1) and failure (-0.2) plus `consecutive_failures` increment.
- HTTP timeouts present: 30 s on most fetches, 180 s on PDF streams.
- Newspaper collector correctly routed to `documents` queue via `task_routes`.

Issues:
- **C-7 (P1)** `html_collector` floods `parsed tree length: 1, wrong data type or not valid HTML` (4 137 / 24 h). Root cause: bot-block / 403 stub HTML responses. The error spams logs and does not bump `consecutive_failures` — affected sources stay green.
- **C-8 (P3)** Communications Today (`communicationstoday.co.in`) accounts for ~70 % of HTML-scrape failures but still ingests 35 articles/24 h via RSS. Scrape adapter needs a per-domain back-off.
- **C-9 (P2)** YouTube errors (`Requested format is not available`, `Failed to extract any player response`) — 60+ errors/24 h. Out of coverage scope but flagged for the YouTube/Clips audit.

Source health detail: see `coverage-source-health.md`. Top issue: 1 source with `health_score < 0.5` (The News International, 0.4).

## Phase 3 — NLP pipeline ✅ (with caveats)

`nlp/relevance_scorer.py` (337 LOC) — Stage-1 weights validated:
- Source-tier multipliers: 1→1.0, 2→0.7, 3→0.4 (line 147).
- Topic gate `INTERNATIONAL → 0.3` (line 74) reduces foreign-news noise.
- Geo multiplier 0.4 minimum (line 142).
- Final formula: `entity_component + non_entity_component × geo_multiplier + source_bonus`.
- Stage-2 (Groq) returns `score`, `explanation`, `sentiment_for_user ∈ {FOR_USER, AGAINST_USER, NEUTRAL}`.

Backlog: `articles WHERE nlp_processed = false` = **0** ✅.

Issues:
- **C-10 (P3)** `nlp_language.py` truncates to 2 000 chars before Google Translate fallback — long Indian-language articles get clipped translation.
- **C-11 (P2)** `score_unscored_articles` (Beat: every 30 min) is a one-shot **backfill**, not a re-scorer. After Stage 1 lands once, articles are never re-scored, so changes to `user_entities` / `user.geo_*` never propagate to old UAR rows. This is the structural cause of tier-1 staleness in C-6.
- **C-12 (P2)** Groq client uses multi-key rotation with 60 s cooldown on 429 (good); confirmed `reset_groq_keys` Beat at 00:05 UTC clears daily quota lock. No metric/alert if all keys exhaust simultaneously.

## Phase 4 — Relevance & RBAC

- Auth middleware enforces JWT signature when `SUPABASE_JWT_SECRET` is set; refuses to skip in production (line 81–83). In dev (no secret) it falls back to unverified decode.
- `require_page("coverage")` → DB lookup against `user_page_access` per request.
- Single user in DB: `pranavpuri03@gmail.com` (uuid `db4b9207-…3465`) — **memory was stale** (`pranavsinghpuri09@gmail.com`); corrected.
- That user has all 9 page slugs allow-listed → coverage access ✅.
- 11 604 `user_entities` seeded for this user. Spot-check confirmed `priority` column is dense at p=1 (21 rows) and p=5 (31 rows); other priorities at 1 row each.
- Cross-user RBAC could not be exercised (single-user dataset). Test gap: see C-13.

## Phase 5 — Backend router (`coverage_router.py`)

Live endpoint probes (with valid JWT):

| Probe | Expected | Got | Verdict |
|---|---|---|---|
| `GET /feed` no token | 401 | 401 | ✅ |
| `GET /feed` valid | 200 | 200, `{articles, pagination, totals}` | ✅ (warm 130–170 ms; one cold call took 89 s, see C-14) |
| `GET /feed?limit=999` | 422 | 422 | ✅ (Pydantic clamp at ≤50) |
| `GET /feed?cursor=garbage` | 400 or first page | **200 first page silently** | ⚠ C-15 |
| `GET /feed?sentiment=BANANA` | 422 | **200 (no rows)** | ⚠ C-16 |
| `GET /feed` page 1 → next_cursor → page 2 | 200 | 200 | ✅ |
| `GET /search?q=a` (1 char) | 422 | 422 | ✅ |
| `GET /search` SQL-i probe (`'; DROP TABLE…--`) | 200 (parameterised, 0 rows) | 200 | ✅ |
| `GET /article/<unknown_uuid>` | 404 | 404 | ✅ (RBAC enforced via `WHERE uar.user_id`) |
| `GET /article/<bad-uuid>` | 422 | **500** | 🚨 **C-17 P0** |
| `POST /summary/<id>` no token | 401 | 401 | ✅ |

Code review highlights:
- All SQL is parameterised (`text(…)` with `:bind` params or `ANY(:list)`). No string interpolation of user input.
- Tier and topic filters: `tier_list` + `topic_list` parsed and bound; topic up-cased to match DB enum.
- `LENGTH(lead_text_translated)` derives `has_full_text` flag.
- No request id / structured logging — see C-18.
- No rate limit on `/summary/{id}` despite each call being a Groq token spend — see C-19.

### Backend test suite — failing 22/23 🚨

`pytest backend/tests/test_coverage_router.py` produces 22 failures with the same error: `assert 403 == 200`. Root cause: the test harness overrides `get_current_user` (or implicitly via JWT decode) but **does not override `require_page("coverage")`**, which runs its own DB lookup against `user_page_access` and returns 403 because the test user `11111111-…` is not in the table. **Test infrastructure bug, not a product bug.** See C-1 (P0). Fix: add to `make_app()`:

```python
from backend.auth.auth_middleware import require_page
app.dependency_overrides[require_page("coverage")] = lambda: None
```

(or stub `cov_module.require_page` itself; the dependency is created once at router import time.)

## Phase 6 — Frontend

- `frontend/src/app/coverage/page.tsx` — 1 188 lines. Exceeds 800-line ceiling per `coding-style.md`; flagged for follow-up extraction (C-2 P3).
- Vitest unit (`coverage-logic.test.ts`): **12/12 green** in 14 s. Covers `buildFeedUrl` serialisation and cursor regex.
- `tsc --noEmit` clean for the coverage page.
- Playwright E2E (`coverage.spec.ts`, 93 lines) — not executed in this audit because it requires `E2E_SUPABASE_TOKEN`; user-driven smoke pass needed.

## Phase 7 — Workers / queues / Beat ✅

Live `app.conf.beat_schedule` matches design: RSS 15 min, RSS-direct 30 min, HTML 6 h, NLP 30 s, relevance backfill 30 min, briefs daily 00:30, govt docs 12 h, social hot/warm/cold 15 m / 1 h / 6 h, threads every 5 min, nightly recluster at 02:00.

`task_routes` correctly maps every Coverage-relevant task: `tasks.collect_rss/_direct/_html → collectors`, `tasks.process_nlp_batch → nlp`, `tasks.score_relevance_batch / score_unscored_articles → relevance`, `tasks.generate_all_briefs → brief`. Documents queue includes `tasks.collect_newspapers` and `tasks.collect_govt_documents` — both have a consumer.

## Phase 8 — Security & quality gates

| Gate | Verdict |
|---|---|
| Auth required on all 4 endpoints | ✅ (401 confirmed live) |
| RBAC scope (cross-user article fetch) | ✅ via `WHERE uar.user_id = :user_id` |
| SQL-i prevention | ✅ all params bound |
| XSS on rendered title | not directly tested; React renders text by default |
| Secrets in repo | not scanned in this audit (`gitleaks` not run) — flagged C-20 |
| Rate limit on `/summary/{id}` | ❌ none — C-19 |
| `SUPABASE_JWT_SECRET` enforcement in prod | ✅ middleware refuses unsigned in prod |
| CORS allow-list audit | not in scope of this audit — flagged C-21 |
| PII / user IDs in logs | uuid logged in error paths (`logger.error("DB insert failed for %s: %s")`) — minor (C-22) |

## Phase 9 — Observability

- Application logs go to stdout (`docker logs`). No request-id correlation, no structured (JSON) logger, no Sentry/equivalent. Defects: C-18, C-23, C-24.
- No Prometheus / metrics exporter visible.
- No alert on NLP backlog, relevance backlog, or "no articles in 30 min" — risk that ingestion silently stalls.

## Production cut-over checklist

| Item | Status |
|---|---|
| All P0 defects closed | ❌ 2 open (C-1, C-17) |
| All P1 defects scheduled | ⏳ pending owner assignment |
| Backend pytest green | ❌ 1/23 passing |
| Frontend Vitest green | ✅ 12/12 |
| Playwright e2e green | ⏳ user-driven smoke pending |
| Live `/feed`, `/search`, `/article` happy path | ✅ |
| Auth/RBAC manual probes | ✅ |
| Source health doc generated | ✅ `coverage-source-health.md` |
| Defect register | ✅ `coverage-defects.md` |
| Manual browser pass | ⏳ user-driven |
| Lighthouse a11y ≥ 90 | ⏳ user-driven |

**Recommendation:** **Do not ship until C-1 and C-17 are closed.** C-11 (relevance never re-scores after backfill) is a quality-of-output issue but not a hard blocker.
