# Analyst Pillar — Test Gaps (Phase C)

**Audit date:** 2026-04-28
**Method:** enumerated `backend/tests/` and `frontend/e2e/`; no tests written in this task per scope decision.

---

## Current state

### Backend pytest files in [backend/tests/](backend/tests)
```
test_auth_middleware.py
test_brief_generator.py
test_brief_router.py
test_clippings_router.py
test_clips_router.py
test_cm_cache.py
test_cm_counter_narrative.py
test_cm_dissent.py
test_cm_router_smoke.py
test_cm_speakers.py
test_cm_stance.py
test_coverage_router.py
test_dateparse.py
test_documents_router.py
test_govt_collector.py
test_govt_intel.py
test_govt_intel_pipeline.py
test_govt_task.py
test_rbac_admin_router.py
test_signals_router.py
test_social_briefing.py
test_social_collector.py
test_social_intel.py
test_social_task.py
test_source_adapters.py
```

**No `test_analyst*` files. No `test_rag_engine*` files. No `test_groq_client*` files.**

### Frontend Playwright suites in [frontend/e2e/](frontend/e2e)
```
brief.spec.ts
clips.spec.ts
coverage.spec.ts
documents.spec.ts
fixtures/
signals.spec.ts
```

**No `analyst.spec.ts`.** Every other major pillar has e2e coverage; Analyst is the lone gap.

### Frontend Vitest unit tests
No `frontend/src/app/analyst/__tests__/` directory. The 1,263-line page is entirely untested at the unit level.

---

## Required tests (recommended for the next sprint, not this task)

### `backend/tests/test_analyst_router.py`

| Test | Scope | Why |
|---|---|---|
| `test_query_requires_auth` | 401 without bearer | Smoke. |
| `test_query_validates_input` | 422 on empty / oversize / bad-mode `question`, `mode`, `session_id` | Pins finding **B-01**. |
| `test_query_isolates_users` | seed two users, query with A's token, assert no B-data leaks in `articles`, `govt_docs`, `social_posts`, `newspaper_clippings` | Pins the user-isolation guarantee. **Cannot run on this DB** until a second user is seeded (Phase A finding **H-04**). |
| `test_session_lifecycle` | `POST /session/new` → `POST /query` → `GET /sessions/{id}` → assert turn count and ownership | Catches the `INSUFFICIENT COVERAGE` short-circuit not persisting (finding **B-03**). |
| `test_groq_quota_exhausted` | mock `GroqQuotaExhausted`; assert 503 with `Retry-After` | Pins finding **B-05**. |
| `test_session_ownership_enforced` | user A queries `GET /sessions/{B-owned}` → 404 | Already implemented in code at [analyst_router.py:590-596](backend/routers/analyst_router.py:590); needs regression test. |
| `test_prompt_injection_logged` | submit a probe; assert `analyst.query.injection_suspect` log line is emitted | Per the lenient bar, bypasses are logged — the test pins that the log line is real. |
| `test_per_pool_failure_degrades_gracefully` | mock `retrieve_relevant_govt_docs` to raise; assert response includes `degraded_pools=["govt_docs"]` (after finding **B-06** is fixed) | |
| `test_geo_filter_too_tight_returns_reason` | seed user with absurd geo; assert response `reason="geo_filter_too_tight"` (after **B-03** is fixed) | |

### `backend/tests/test_rag_engine.py`

| Test | Scope | Why |
|---|---|---|
| `test_embed_query_returns_768d` | `embed_query("hello world")` → list[float] of length 768 | Smoke on LaBSE singleton. |
| `test_embed_query_skips_short_text` | `embed_query("hi")` returns None or zero-vector per spec | Pin documented behavior. |
| `test_extract_query_keywords` | known questions → known keyword sets | Used by entity-presence check. |
| `test_check_entity_in_corpus` | pre-seed an entity; assert detected | |
| `test_recency_pool_returns_last_48h` | seed articles with varied `published_at`; assert window | |
| `test_dual_pool_dedup` | overlapping IDs in semantic + recency pools collapse to one | |
| `test_compute_confidence_band_boundaries` | feed canned scores; assert HIGH/MEDIUM/LOW transitions | |
| `test_detect_mode_classifier` | feed mode-tagged questions; assert correct mode | mocks Groq `classify`. |
| `test_build_context_includes_all_pillars` | feed mock evidence in each kind; assert all blocks present in context string | |
| `test_generate_followups_falls_back_on_groq_error` | mock Groq raise; assert empty list, not crash | |

### `backend/tests/test_groq_client.py`

| Test | Scope | Why |
|---|---|---|
| `test_call_groq_routes_to_fast_model_for_classification` | task_type="classification" → FAST_MODEL | |
| `test_call_groq_routes_to_quality_model_for_rag_response` | task_type="rag_response" → QUALITY_MODEL | |
| `test_quota_exhausted_after_3_429s` | mock 429 × 3; assert `GroqQuotaExhausted` raised | |
| `test_round_robin_key_rotation` | seed 3 keys; assert each is tried before quota_exhausted | |
| `test_daily_reset_at_0005_utc` | freeze time pre/post; assert exhausted keys come back | |

### `backend/tests/fixtures/analyst_eval.json` (Phase E artifact, not a unit test)

20 questions across 4 buckets — being generated in Phase E.

### `frontend/e2e/analyst.spec.ts`

Mirror [frontend/e2e/coverage.spec.ts](frontend/e2e/coverage.spec.ts) auth pattern (localStorage token injection via `E2E_SUPABASE_TOKEN`).

| Test | Scope |
|---|---|
| `analyst loads with no console errors` | navigate `/analyst`, assert page renders, no `console.error` |
| `submit a known retrieval-positive query renders citations` | type a fixture question, click submit, wait for response, assert ≥ 1 citation chip in `EvidenceCard` |
| `clicking a citation scrolls to evidence panel` | click chip, assert scroll target visible |
| `Trail (sidebar) opens past sessions` | open trail, click a past session, assert turns load |
| `Esc closes the dossier panel` | open dossier, press Esc, assert closed |
| `Groq quota error surfaces to user` | mock 503; assert visible banner, not blank screen (gates fix **B-05**) |
| `New Investigation clears state` | submit question, click "New", assert response/sections cleared |
| `Reduced motion respected` | set `prefers-reduced-motion: reduce`; assert stagger animation skipped (gates Phase D **F-04**) |

### `frontend/src/app/analyst/__tests__/` (Vitest)

| File | Scope |
|---|---|
| `parseSections.test.ts` | feed canned LLM markdown; assert section split matches snapshot |
| `renderWithCitations.test.tsx` | render with circled-number tokens ①…⑩; assert clickable spans |
| `EvidenceCard.test.tsx` | given evidence array, render asserts `.length` chips, accessible role |

These would require Phase D's component extraction first (also report-only this round).

---

## Coverage estimate

| Area | Current | Target |
|---|---:|---:|
| `backend/routers/analyst_router.py` | **0%** | 80% |
| `backend/nlp/rag_engine.py` | **0%** | 70% (size + Groq mocks make 80% expensive) |
| `backend/nlp/groq_client.py` | **0%** | 80% |
| `frontend/src/app/analyst/page.tsx` | **0%** | 60% (post-extraction) |

The whole pillar is currently a **"works on my machine" deploy**. None of the regression invariants (auth, isolation, validation, quota handling, citation rendering) are pinned by automation.

---

## Priority order for the next test sprint

1. `test_query_isolates_users` — RBAC regression. Highest value per minute of effort.
2. `test_query_validates_input` — pairs with finding B-01 fix.
3. `test_groq_quota_exhausted` — pairs with B-05 fix.
4. `analyst.spec.ts: groq quota error surfaces to user` — closes loop with B-05.
5. The rest of `test_rag_engine.py` — large but mockable.
