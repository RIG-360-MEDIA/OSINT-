# Live QA Session — `/documents`

This document records the **executable** parts of the QA pass — what was actually run, what passed, what failed, and how to reproduce.

## Session 1 — 2026-04-25 (static analysis + frontend unit tests)

### Frontend unit tests — `documents.test.tsx`

```
cd frontend
npx vitest run src/app/documents/__tests__/documents.test.tsx --reporter=basic
```

**Result:** 8 passed, 1 skipped, 0 failed (12.75s).

```
✓ DocumentsPage — happy path > redirects to /login when there is no session
✓ DocumentsPage — happy path > fetches feed and renders rows
✓ DocumentsPage — happy path > sends Authorization header with bearer token
✓ DocumentsPage — happy path > refetches when geography filter changes
○ DocumentsPage — happy path > debounces search input  [skipped: covered by e2e]
✓ DocumentsPage — error handling > shows a user-visible error when /feed returns 500 (D-4)  [it.fails — confirmed: NO error UI]
✓ DocumentsPage — pagination > appends rows when "Pull more papers" is clicked
✓ DocumentsPage — accessibility > modal opens with role="dialog" and aria-modal  [it.fails — confirmed: D-10]
✓ DocumentsPage — accessibility > filter pill exposes aria-pressed when active  [it.fails — confirmed: D-12]
```

The three `it.fails` tests are intentional defect-confirmations. Once the corresponding fixes ship, remove the `.fails` modifier and they should turn into normal green tests.

### Backend registry contract — `test_source_adapters.py`

```
python -m pytest backend/tests/test_source_adapters.py::test_registry_has_no_collisions \
                  backend/tests/test_source_adapters.py::test_registry_count_matches_inventory_doc -q
```

**Result:** 2 passed (2.13s).

Confirms:
- 47 adapters, 0 URL-key collisions.
- `docs/qa/govt-sources-inventory.md` is in sync with the live registry.

### Source inventory

```
PYTHONIOENCODING=utf-8 python -m backend.scripts.list_govt_sources --markdown \
    > docs/qa/govt-sources-inventory.md
```

**Result:** 47 adapters across 7 families. See [govt-sources-inventory.md](govt-sources-inventory.md).

---

## Pending — Session 2 (requires live dev stack)

The following must run with the dev DB + FastAPI server up. They are **scripted** below; just execute them when the stack is running.

### 1. Backend router tests (need test DB)

```bash
# Set DATABASE_URL to a disposable test database
export DATABASE_URL=postgresql+asyncpg://...

python -m pytest backend/tests/test_documents_router.py -v
```

Expected: 11 passed, 3 xfailed (D-1, D-2, D-3).

### 2. Adapter smoke test (mocked HTTP — should pass without network)

```bash
python -m pytest backend/tests/test_source_adapters.py -q
```

If many tests `skip` with "requires live HTTP / Playwright", that's expected — those adapters have HTML parsers that need realistic markup. Set `SOURCE_ADAPTER_LIVE=1` to hit real portals (not for CI).

### 3. Source-health cross-reference

```bash
python -m backend.scripts.list_govt_sources --with-db --markdown \
    > docs/qa/govt-sources-inventory.md
```

This populates the `Rows (30d)` and `Last success` columns with real data. The "no DB row (orphan adapter)" labels in the current snapshot are because no DB was attached.

### 4. Pagination repro (proves D-1)

```bash
TOKEN=$(...)  # any valid Supabase access token
URL=http://localhost:8000/api/documents/feed
PAGES=()
CURSOR=
while :; do
  RESP=$(curl -sH "Authorization: Bearer $TOKEN" "$URL?limit=10&cursor=$CURSOR")
  PAGES+=("$RESP")
  HAS_MORE=$(jq -r '.has_more' <<< "$RESP")
  CURSOR=$(jq -r '.next_cursor // empty' <<< "$RESP")
  [ "$HAS_MORE" = "false" ] && break
done

# Expect: union of doc_ids across pages should equal a SELECT id FROM
# govt_documents WHERE nlp_processed AND collected_at > NOW()-30d
# Actual (D-1, D-2): union is smaller AND may contain duplicates.
echo "${PAGES[@]}" | jq -r '.documents[].doc_id' | sort | uniq -d
# ^ Any output here proves D-1 (duplicates).
```

### 5. Browser smoke (Playwright e2e)

```bash
cd frontend
E2E_BASE_URL=http://localhost:3000 \
E2E_SUPABASE_TOKEN=eyJ... \
  npx playwright test e2e/documents.spec.ts --reporter=html
```

Checklist — capture screenshots into `docs/qa/screenshots/`:
- `01-list.png` — initial render.
- `02-filtered-local.png` — Local desk active.
- `03-search-rbi.png` — search "RBI".
- `04-modal-open.png` — document dialog open.
- `05-mobile.png` — 375px viewport.
- `06-network.png` — DevTools network tab during `/feed`.
- `07-axe.json` — axe-playwright violations dump.

### 6. DB sanity panel

```sql
-- per-geography counts
SELECT source_geography, COUNT(*)
FROM govt_documents
WHERE nlp_processed
GROUP BY 1
ORDER BY 2 DESC;

-- adapters dead >7 days
SELECT portal_url, last_success_at, last_error
FROM govt_document_sources
WHERE last_success_at IS NULL
   OR last_success_at < NOW() - INTERVAL '7 days'
ORDER BY last_success_at NULLS FIRST;

-- unprocessed-doc backlog (D-8 visibility)
SELECT COUNT(*) AS pending
FROM govt_documents
WHERE NOT nlp_processed;

-- relevance coverage for the test user
SELECT relevance_tier, COUNT(*)
FROM user_govt_doc_relevance
WHERE user_id = '<TEST-USER-UUID>'
GROUP BY 1
ORDER BY 1;
```

Paste results back into `documents-quality-scorecard.md` to fill the **TBD** rows.

---

## Defects confirmed live this session

| ID | How confirmed |
|---|---|
| D-4 | `it.fails` "shows a user-visible error" passed → page does NOT render error UI on 500. |
| D-10 | `it.fails` modal `role=dialog` test passed → no role attr present. |
| D-12 | `it.fails` `aria-pressed` test passed → filter pills lack the attribute. |

The remaining defects (D-1 cursor mismatch, D-2 days/cursor collision, D-3 unfiltered total, D-5 race, D-6 chip coverage, D-7 missing date filter, D-8 silent NLP failure, D-9 GET enqueues Celery, D-11 locale hydration, D-13 token rotation, D-14–D-21) are **static-confirmed** in the audit docs and have tests written but not yet executed against the live DB.
