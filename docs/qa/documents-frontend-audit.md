# Frontend Audit — `/documents` page

**File under review:** [frontend/src/app/documents/page.tsx](../../frontend/src/app/documents/page.tsx) (1043 lines, single file).
**Method:** static read of the source. No tests executed.

## 1. Component graph (verified)

7 inline components + 2 imports.

| Component | Lines (approx) | Role |
|---|---|---|
| `DocumentsPage` | 90+ | Top-level page; owns all state |
| `LoadingState` | ~582 | Skeleton placeholder |
| `DeskMemo` | ~597 | Empty-state / no-match banner |
| `DocumentDialog` | ~629 | Modal panel for the selected doc |
| `DocumentRow` | ~714 | Single feed row |
| `FilterPill` | ~852 | Toggle chip |
| `FilterRow` | ~876 | Filter group label + slot |
| `Navigation` | imported | `@/components/Navigation` |
| `Dateline` | imported | `@/components/Dateline` |

**Comment:** the file is 2× larger than the project's 800-line guideline. Extracting `DocumentDialog`, `DocumentRow`, `FilterRow`/`FilterPill` to sibling files (`./components/`) would be a P3 refactor — flagged in `documents-defects.md`, not done here.

## 2. State & effects

`useState` × 11 (lines 92–106): token, documents, total, geoCounts, hasMore, nextCursor, loading, appending, geoFilter, typeFilter, searchInput, search, openDoc.
`useRef` × 1: `searchTimer` (line 108).
`useCallback` × 1: `fetchFeed` (line 130).
`useEffect` × 3: auth (110), debounce (122), refetch-on-deps-change (165).

**Confirmed corrections to the exploration agent's report:**
- Search debounce is **350 ms**, not 300 ms (line 124).
- Search timer **IS** cleaned up on unmount (lines 125–127). The "leak" claim was wrong.

**Real issues found in this audit:**
- **No `AbortController`** on filter/search refetch (line 143). Rapid filter clicks can cause an older response to overwrite a newer one (stale-result race).
- `fetchFeed` resets `documents` to `[]` on `!res.ok` only when `!append` (line 148). If a `loadMore` fetch fails, the user sees the previous page silently with no error and no retry.
- `total` and `geoCounts` come from the backend response — but the backend computes them **without** applying the active filters (see backend audit §3). The UI label `"{documents.length} of {total.toLocaleString()}"` (line 309) therefore reads e.g. `"20 of 12,345"` even when the filter only matches 50 rows. **Misleading UX.**
- The auth effect (line 110) does not subscribe to `onAuthStateChange`. If the Supabase token rotates while the page is open, in-flight requests will start returning 401 and silently fall through `!res.ok`.

## 3. Network calls

Two `fetch(...)` sites:

| Method + URL | Where | Auth | Error UI | JSON parse |
|---|---|---|---|---|
| `GET /api/documents/feed?...` | line 143 | `Authorization: Bearer` | **none** — sets `[]` and returns silently | unwrapped, unguarded |
| `POST /api/documents/{id}/summary` | inside `DocumentDialog` (~660) | bearer | shows `"Summary generation failed."` text but no retry control | guarded |

**Defect:** the feed has no user-visible error path at all. A 500 / network outage / 401 produces an empty page with the same `DeskMemo "No papers match these terms."` as a legitimate empty filter result. The user cannot distinguish "no docs" from "API down".

## 4. Type drift vs backend response

Cross-checked `DocumentItem` (lines 11–30) against the backend's feed dict construction in [backend/routers/documents_router.py:179-205](../../backend/routers/documents_router.py). **All 18 fields align** — no drift in the feed payload. `entities_extracted` is selected by SQL but not exposed in the feed dict and not in the TS interface, which is consistent.

## 5. Accessibility (failed checks)

- No `role="dialog"`, `aria-modal`, or focus trap in `DocumentDialog`.
- Filter pills are `<button>`s but lack `aria-pressed` to convey active state.
- `Escape` key handler not wired — modal can only close via the `×` button.
- `formatShortDate` (line 79) uses `undefined` locale → SSR vs CSR may render different strings → React hydration warning likely under non-`en-US` locales. Server uses Node default; client uses browser locale.
- Sticky filter bar (line 204) has `z-index: 50` and overlays content — verify keyboard tab order isn't trapped behind it.
- The "search" icon `⌕` is decorative but lacks `aria-hidden="true"`.

## 6. Filter coverage gap (USER-FACING)

`DOC_TYPES` (lines 57–64) exposes only **5** of the document types the system collects:
- `government_order` (Telangana GO.Ms)
- `court_order` (HC orders)
- `audit_report` (CAG — but **no CAG adapter exists**, see source inventory)
- `press_release` (PIB)
- `ministry_order`

Adapters in `backend/collectors/sources/` produce many additional types (e.g. `regulator_circular`, `parliamentary_question`, `bill`, `committee_report`, `gazette_notification`, `tender`, `tariff_order`, `patent_grant`, `trademark`, `world_bank_doc`, etc.). Documents tagged with any of these are reachable only via the "All types" pill — there's no way to filter for them specifically.

## 7. Date-range gap

The backend `/feed` endpoint accepts `days` (1-365). The frontend never sends it (line 136-141), so the page is silently capped at the backend default (30 days). There is no UI for "all time" or "last year", even though the data is there.

## 8. Misc

- Inline `style={...}` everywhere — no CSS module or Tailwind. Acceptable for the project's hand-typeset style, but makes a11y / theming changes harder.
- `console.log` calls: **none found** ✓.
- `TODO` / `FIXME`: scan returned **0** in this file ✓.
- `void` keyword used to suppress promise warnings (lines 112, 167) — fine.

## 9. Summary

The page renders, but five user-impacting issues are present:

1. Stale-response race on rapid filter changes (no AbortController).
2. Silent failure mode — API error ↔ empty filter result indistinguishable.
3. Misleading `total` and geography counts (filtered query vs unfiltered total).
4. Filter chips expose only 5 of ~20 doc-types the data has.
5. No date-range control; window is silently capped at 30 days.

Plus accessibility debt and a 1043-line file that should be split.
