# Brief — Live UX Walkthrough Log

**Date:** 2026-04-26
**Tester:** RIG QA
**URL:** http://localhost:3000/brief
**Test user:** `db4b9207-51aa-4d39-a7bf-e6fab34c3465`
**Browser:** Chromium via Playwright + manual Chrome (recommended)

---

## Pre-flight (record before clicking anything)

| Check | Result |
|---|---|
| `docker ps` — all 5 containers Up | ✅ verified at audit start |
| `docker exec rig-backend curl -fs localhost:8000/healthz` | TBD (run during session) |
| Frontend reachable | TBD |
| User is signed in | TBD |
| `briefs` row count for user before session | 4 (pre-existing) |

---

## Golden path (must pass)

1. Navigate to `/brief` while signed in.
   - **Expected:** state machine resolves to `showing_brief` if today's brief exists, else `no_brief` or `too_early` (if <10 relevant articles).
   - **Observed:** ___
2. If `no_brief`: click "Generate brief". `LoadingState` shows phase animation.
   - **Expected:** ~15–30s. After: `showing_brief` with all six sections.
   - **Observed:** ___
3. Each section renders with its dedicated component:
   - SITUATION STATUS → `<blockquote className="rig-pullquote">`
   - KEY DEVELOPMENTS → numbered I–X items
   - ENTITIES TODAY → entity rows
   - SIGNALS TO WATCH → flag-prefixed items
   - FINANCIAL PULSE → prose paragraph (or "No significant financial developments...")
   - SOURCE COVERAGE → source list + quality sentence
4. History strip appears below brief; click yesterday → fetches `GET /api/brief/2026-04-25`.

## Edge / failure cases

| Case | How to trigger | Expected | Observed |
|---|---|---|---|
| Unauthenticated visit | Sign out, visit `/brief` | Redirect to login | ___ |
| Backend 500 on `/today` | Stop backend, reload | Error state with "Try again" | ___ |
| <10 relevant articles | Use a fresh test account | `too_early` state, "feed warming" copy | ___ |
| Double-click Generate | Rapid 2× click | **Currently fails — D-BRIEF-8.** Two POSTs fire. | ___ |
| Concurrent tabs Generate | Open in two tabs, click both | Both complete; later one wins upsert (D-BRIEF-7 — Groq spend doubled) | ___ |
| Section dropped from UI | Inject malformed `## Situation Status:` | Section silently disappears (D-BRIEF-13) | ___ |
| Groq section failure | Mock 1 of 6 calls to throw | `[Generation failed: ...]` literal in UI (D-BRIEF-14) | ___ |
| Stale article in "today" | Audit `published_at` of 30 articles | Some >24h old (D-BRIEF-5) | ___ |

## Network panel inventory

Record every request fired on first load. Flag duplicates, 4xx, ≥500ms.

| URL | Method | Status | Duration | Notes |
|---|---|---|---:|---|
| `/api/brief/today` | GET | | | |
| `/api/brief/history/list` | GET | | | |
| `/api/brief/generate` (only after click) | POST | | | |

## Console output

- Errors: ___
- Warnings: ___
- Hydration mismatches: ___

## Lighthouse scores

| Metric | Score |
|---|---:|
| Performance | |
| Accessibility | |
| Best Practices | |
| SEO | |

Specific a11y items to verify:
- All buttons have accessible names.
- Color contrast on `.rig-prose`, `.rig-pullquote`, `.rig-kicker`.
- Focus visible on every interactive element.
- Animation respects `prefers-reduced-motion`.

## Keyboard navigation

Tab through the page. Every interactive element reachable, focus indicator visible? ___

## Responsive

| Viewport | Outcome |
|---|---|
| 1440×900 | |
| 1024×768 | |
| 768×1024 (tablet) | |
| 375×667 (iPhone SE) | |

Watch for overflow in `HistoryStrip` and the numbered-roman `DevelopmentsSection`.

## Brief content sanity check

Pick 3 numbered KEY DEVELOPMENTS items at random. For each:
1. Find the corresponding article (cross-reference with `user_article_relevance`).
2. Confirm: claim is in the article, numbers match, no fabricated entity.

Notes: ___

## Exit summary

- Total defects observed during walkthrough: ___ (cross-link to [brief-defects.md](./brief-defects.md))
- New defects to add: ___
- Recommended P1 fix order: D-BRIEF-1, D-BRIEF-2, D-BRIEF-5.
