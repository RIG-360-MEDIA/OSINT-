# Analyst Pillar — Frontend Findings (Phase D)

**Audit date:** 2026-04-28
**File reviewed:** [frontend/src/app/analyst/page.tsx](frontend/src/app/analyst/page.tsx) — 1,263 lines, single-file route.
**Method:** read-only review. No edits, no extracted components, no tests written this round.

---

## Findings

### F-01 [HIGH] Two silent `catch` blocks hide auth/network failures

[analyst/page.tsx:560](frontend/src/app/analyst/page.tsx:560), [:607](frontend/src/app/analyst/page.tsx:607), [:678](frontend/src/app/analyst/page.tsx:678)

```typescript
} catch { /* silent */ } finally {
  setLoadingSessions(false)
}
...
} catch { /* ignore */ }
...
} catch { /* ignore */ }
```

Three swallowed exception paths:
- `fetchAllSessions` (sidebar list) → user sees an empty list and can't tell if it's "no sessions yet" or "401, please re-login".
- Boot effect that calls `/api/analyst/session` and `/api/analyst/context` together → user lands on a blank workspace with no error.
- "New Investigation" handler at line 678 → click does nothing visible if the network is down.

**Fix.** Replace each with at least a `console.warn` plus a user-visible toast or a small banner. The submit handler already does this correctly at [analyst/page.tsx:649-651](frontend/src/app/analyst/page.tsx:649); copy the pattern.

---

### F-02 [HIGH] Frontend does not distinguish "rate-limited" from "server error"

The submit handler:

```typescript
if (!res.ok) {
  const err = await res.json().catch(() => ({}))
  setErrorMsg(err.detail ?? `Request failed (${res.status})`)
  return
}
```

If backend finding **B-05** is fixed and a 503 with `Retry-After` is returned, the user still just sees `"Request failed (503)"`. The retry header is ignored.

**Fix.** Branch on status:

```typescript
if (res.status === 503) {
  const retryAfter = res.headers.get('Retry-After') ?? '300'
  setErrorMsg(`Analyst is rate-limited. Try again in ~${Math.ceil(+retryAfter / 60)} minutes.`)
  return
}
if (res.status === 401) { /* redirect to login */ return }
```

---

### F-03 [HIGH] Massive a11y gap

A grep across the entire file for `aria-|role=|tabIndex|aria-label|aria-live` returns **one hit**:
```
700:      <div style={{ height: '56px', flexShrink: 0 }} aria-hidden />
```

That is the only accessibility attribute in the entire 1,263-line page. By comparison, [BriefWizard](frontend/src/app/brief) uses `role="banner"`, `aria-label`, and `aria-live="polite"` extensively.

Specific gaps:

| Element | Gap |
|---|---|
| LoadingState rotator | No `aria-live="polite"` — screen readers don't hear status updates. |
| Submit button (when `loading`) | No `aria-busy`, no `aria-disabled`. |
| Citation chips (`renderWithCitations`) | Inline buttons with no semantic markup; no `role="button"`, no keyboard activation hint. |
| Trail sidebar collapse/expand | Icon-only button, no `aria-label`, no `aria-expanded`. |
| Past-session list | No `role="list"` / `role="listitem"`; no keyboard focus trap. |
| Dossier panel | No `role="dialog"`, no `aria-modal="true"`, no focus trap, no Esc handler that returns focus. |
| Stagger reveal animation (400 ms × N) | No `prefers-reduced-motion` guard. Vestibular trigger. |

**Fix.** Add the attributes in-place. None of these require a refactor.

---

### F-04 [MEDIUM] 1,263-line monolith is the root of test inability and review pain

No extracted components, no hooks. 17 `useState` calls in the root, plus the hand-rolled `parseSections`, `renderWithCitations`, `EvidenceCard`, `AnswerDocument`, and `LoadingState` defined inline.

**Fix (deferred per scope).** Extract into `frontend/src/app/analyst/_components/`:
- `Trail.tsx` (sidebar)
- `EvidenceCard.tsx`
- `AnswerDocument.tsx`
- `LoadingState.tsx`
- `useAnalystSession.ts` (custom hook for the boot/session flow)
- `useAnalystSubmit.ts` (custom hook for the submit + abort flow)

This unblocks the Vitest unit tests in Phase C.

---

### F-05 [MEDIUM] No `AbortController` on in-flight queries

`handleSubmit` does not cancel a previous fetch when the user submits a new question, switches sessions, or clicks "New Investigation". The race condition is partially mitigated by `if (!q || loading) return`, but switching sessions ([analyst/page.tsx:675](frontend/src/app/analyst/page.tsx:675)) does **not** check `loading`, so a stale response can still arrive after a session switch and replace the new state.

**Fix.** Single `AbortController` ref, aborted on session change and on new submit:

```typescript
const abortRef = useRef<AbortController | null>(null)
// before fetch:
abortRef.current?.abort()
abortRef.current = new AbortController()
fetch(..., { signal: abortRef.current.signal })
```

---

### F-06 [LOW] Hardcoded 700 ms delay for URL-param query

[analyst/page.tsx:664 (approx)](frontend/src/app/analyst/page.tsx:664) — `setTimeout(..., 700)` to wait for boot before submitting a deep-linked question. Brittle: on cold-start or slow networks the delay is too short; on warm load it's an unnecessary wait.

**Fix.** Replace with `await Promise.all([sessionLoaded, suggestionsLoaded])` then submit.

---

### F-07 [LOW] Sessions list capped at 10 in the UI but backend returns 20

[analyst/page.tsx:889](frontend/src/app/analyst/page.tsx:889) slices to 10 in the render; [analyst_router.py:560](backend/routers/analyst_router.py:560) returns up to 20.

**Fix.** Either pass a `?limit=` query parameter, or paginate the trail. Currently a power user with > 10 sessions silently can't see older ones.

---

### F-08 [LOW] Boot effect uses `console.error` for past-session load but `console.error` only in one path

[analyst/page.tsx:591-592](frontend/src/app/analyst/page.tsx:591) is the single `console.error` in the file. Inconsistent with the silent catches at lines 560/607/678. Standardize on a thin `logFrontendError(area, exc)` helper so all errors are at least routable to a future Sentry hook.

---

### F-09 [LOW] No streaming / partial render

Confirmed — `await res.json()` blocks until the full Groq response is back. With `retrieval_ms` p95 around 7 s and Groq generation adding 2–8 s, the user can stare at a spinner for 10+ s. Out of scope per the plan; flagged for the streaming follow-up ticket.

---

## What is **not** a finding

- The submit handler **does** disable on `loading` ([analyst/page.tsx:625](frontend/src/app/analyst/page.tsx:625): `if (!q || loading) return`). The race-condition concern in the original audit doc was overstated for `handleSubmit` — it's only an issue for session switches and abort (covered in F-05).
- Auth flow (Supabase + redirect to `/login` on missing session) is correct.
- The page is feature-complete and visually polished.

---

## Summary

| Severity | Count |
|---|---:|
| CRITICAL | 0 |
| HIGH | 3 (F-01, F-02, F-03) |
| MEDIUM | 2 (F-04, F-05) |
| LOW | 4 (F-06, F-07, F-08, F-09) |

**Production verdict:** the page works for the happy path. The HIGH items are all fixable in a small PR (a few hours each). F-03 (a11y) is the largest in scope but does not require any architectural changes — additive attributes only.
