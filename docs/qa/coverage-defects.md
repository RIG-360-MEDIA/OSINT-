# Coverage — Defect Register (2026-04-28)

Defect IDs `C-N`. Severity: **P0** = blocks production · **P1** = data integrity / security / UX-visible · **P2** = degraded but functional · **P3** = polish / follow-up.
Status: **CLOSED** with commit / **OPEN** with reason.

Remediation pass landed 2026-04-28 (this commit). Verification: `pytest test_coverage_router.py` **32/32 green** (was 1/22). Live probes against the running stack confirm `/article/<bad-uuid>` → 422, `/feed?cursor=garbage` → 400, `/feed?sentiment=BANANA` → 422, `X-Request-Id` echoed on all responses, FTS handles Devanagari queries.

| ID | Sev | Area | Title | Status | Evidence |
|---|---|---|---|---|---|
| C-1 | P0 | tests/backend | pytest harness does not stub `require_page("coverage")` | **CLOSED** | `test_coverage_router.py::make_app` overrides router deps; 32/32 green |
| C-17 | P0 | router | `/article/<bad-uuid>` returned 500 | **CLOSED** | `article_id: UUID` on `/article` and `/summary` (FastAPI now 422s); live probe confirms |
| C-7 | P1 | collectors | `html_collector` flooded 4 137 errors / 24 h | **CLOSED** | `htmldate / trafilatura / courlan / readability` loggers pinned to WARNING at module load |
| C-11 | P1 | relevance | `score_unscored_articles` was one-shot backfill | **CLOSED** | Added Sweep 2: tier 1+2 UAR rows older than 7 d are re-dispatched to `score_relevance_batch` (cap 200) |
| C-15 | P1 | router | `/feed?cursor=garbage` silently returned first page | **CLOSED** | Parse error → 400; cursor_id forced through `UUID(...)` to block injection |
| C-19 | P1 | security | `/summary/{id}` had no rate limit | **CLOSED** | In-process sliding-window: 15 calls / 60 s / user → 429 with `Retry-After`. Pytest `test_summary_rate_limit_returns_429` |
| C-3 | P2 | db | Unused indexes `idx_articles_topic`, `idx_articles_updated_at` | **CLOSED** | `032_drop_unused_coverage_indexes.sql` written + applied; 1.6 MB reclaimed |
| C-4 | P2 | nlp | 18 articles `nlp_processed=true` with NULL `topic_category` | **CLOSED** | NLP error UPDATE now sets `topic_category = COALESCE(topic_category,'OTHER')`; existing 18 backfilled |
| C-6 | P2 | relevance | 69 % of tier-1 UAR rows older than 7 d | **CLOSED via C-11** | Stale rows now re-scored every 30 min (capped) |
| C-9 | P2 | collectors | YouTube errors | **OPEN** | Out of coverage scope — file under YouTube/Clips audit |
| C-12 | P2 | nlp/groq | No alert on full Groq pool exhaustion | **CLOSED** | `mark_exhausted_for` emits `logger.critical("GROQ_POOL_EXHAUSTED ...")` when `remaining == 0` |
| C-13 | P2 | tests | No cross-user RBAC test | **CLOSED** | `test_feed_uses_jwt_user_id_in_query` + `test_article_endpoint_uses_jwt_user_id_in_query` |
| C-16 | P2 | router | `/feed?sentiment=BANANA` accepted | **CLOSED** | `Literal["all","FOR_USER","AGAINST_USER","NEUTRAL"]` enum + `Literal` on `sort` too. Live → 422 |
| C-18 | P2 | observability | No request-id / structured logging | **CLOSED** | `RequestIdMiddleware` (`backend/middleware/request_id.py`); `X-Request-Id` echoed on every response; coverage error logs include `rid=` |
| C-21 | P2 | security | CORS allow-list hardcoded localhost | **CLOSED** | Reads `CORS_ALLOWED_ORIGINS` env var; default keeps dev origins; `expose_headers=['X-Request-Id']` added |
| C-23 | P2 | observability | No Sentry / no backlog alert | **OPEN** | Tracked separately — needs Sentry SDK + Prometheus exporter; out of one-PR scope |
| C-2 | P3 | frontend | `coverage/page.tsx` 1 188 LOC | **OPEN** | Tracked as refactor follow-up; not a defect |
| C-5 | P3 | relevance | NULL `relevance_explanation` on tier-0/3 — by design | **CLOSED** | Stage-2 docstring now documents the gate (`stage1_score >= 0.25 and tier > 0`) and tier mapping |
| C-8 | P3 | collectors | Communications Today scrape repeatedly fails | **CLOSED** | In-process per-domain back-off: 5 consecutive failures → 1 h skip; falls back to RSS summary |
| C-10 | P3 | nlp | Translation truncated at 2 000 chars | **CLOSED** | `TRANSLATION_MAX_CHARS = 4500` constant; all 9 call sites use it |
| C-14 | P3 | router | One 89 s cold-call observed | **OPEN** | Single observation, not reproducible in warm probes; LaBSE warm-up at startup already mitigates. Monitor |
| C-20 | P3 | security | gitleaks / secret-scan not run | **OPEN** | Tracked separately — operational task, not code change |
| C-22 | P3 | privacy | User UUID logged plain | **CLOSED** | `_hash_uid()` helper used in router error paths |
| C-24 | P3 | observability | `logger.error` instead of `logger.exception` | **CLOSED** | Switched in `/summary` error handler |
| C-25 | P3 | router | FTS used `'english'` regclass | **CLOSED** | Switched to `'simple'` — Devanagari probe live → 200 |
| C-26 | P3 | router | `cached: false` always | **CLOSED** | In-process LRU (cap 1024) keyed by `article_id`; pytest `test_summary_caches_on_second_call` |

## Closed: 21 · Open: 5 (out-of-scope follow-ups)

The five remaining items are explicitly out of single-PR scope:
- **C-2** — frontend `coverage/page.tsx` refactor (1 188 LOC → split). Not a defect.
- **C-9** — YouTube transcript errors. Belongs to the YouTube/Clips pillar audit.
- **C-14** — single 89 s cold call, not reproducible. LaBSE warm-up already in place; monitor.
- **C-20** — gitleaks / secret scan. Operational task, run before prod cut-over.
- **C-23** — Sentry + Prometheus + alert pipeline. Multi-PR ops project.

None block production.

## Recommended remediation order

1. **C-1** — fix the test harness so the suite passes; we cannot certify any other change without working tests.
2. **C-17** — change `article_id: str` to `article_id: UUID` on the FastAPI Path param (works for `/article/{id}` and `/summary/{id}`); also add UUID validation for `:cursor_id` parsing.
3. **C-15** — replace the silent `except: pass` in `coverage_router.py:114` with a `raise HTTPException(400, "malformed cursor")`. The frontend already validates the cursor regex, so legitimate clients will not hit this.
4. **C-19** — add a per-user rate limit (e.g. `slowapi` 10 req / min on `/summary/{id}`). The unbounded Groq spend is a real risk.
5. **C-11** — promote `score_unscored_articles` from one-shot backfill to a re-scorer of UAR rows older than N days *or* invalidate UAR on `user_entities` mutations via a DB trigger / app hook.
6. **C-7** — add a per-source `consecutive_failures` increment on `parsed tree length: 1` results, plus a domain-level back-off; otherwise the log noise hides real failures.

P2/P3 can ship behind the P0/P1 wave or be filed as `fix/coverage-phase-N` branches.
