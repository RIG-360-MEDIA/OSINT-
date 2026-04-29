# 05 — Fallback + failure paths (Step 5)

**Verdict: PASS for graceful degradation; FAIL for one silent-bypass.**

| Path | Expected | Actual |
|---|---|---|
| No Bearer token | 401 with clear detail | ✓ `{"detail":"Authentication required"}` HTTP 401 |
| Invalid Bearer (malformed JWT) | 401 | ✓ (verified via `_decode_unverified` path) |
| ACLED token unset | 503 with explanatory message | ✓ `{"detail":"ACLED token not configured (ACLED_ACCESS_TOKEN env)"}` |
| Groq key invalid (LLM failure path) | Tasks no-op gracefully; endpoints don't 500 | ✓ stance_task records `unknown`; briefing summary has fallback (templated text) |
| `/api/cm/dashboard` with one section failing | `section_errors[name]` populated, other sections still served | ✓ `_safe()` wrapper isolates per-section |
| `cm_queries._safe_execute` against missing table | Empty result, not 500 | ✓ `ProgrammingError`/`InternalError` with "does not exist" caught |
| Frontend `/worldmonitor` unauth | Redirect to `/login?next=/worldmonitor` | ✓ 307 |
| Frontend page-allowlist denial | Redirect to `/brief?denied=worldmonitor` | ✗ **D-17**: dev container can't reach backend; middleware `try/catch` silently lets request through |
| Briefing endpoint with all upstream failed | Should still respond with sentinel data | Untested directly; given parallel `gather(return_exceptions=True)`, weather/air/news/events all default to empty containers ✓ |

## Defects added (already in Step 3/4)
D-17 (silent bypass) is the only failure-path defect not already
captured.
