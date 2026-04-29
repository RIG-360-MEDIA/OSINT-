# Backend Audit — `documents_router.py`

**File under review:** [backend/routers/documents_router.py](../../backend/routers/documents_router.py)
**Method:** static read of the source. No tests executed.

## Endpoints

| Verb | Path | Lines | Auth |
|---|---|---|---|
| GET | `/api/documents/feed` | 40–214 | `get_current_user` |
| GET | `/api/documents/{doc_id}` | 217–272 | `get_current_user` |
| POST | `/api/documents/{doc_id}/summary` | 275+ | `get_current_user` |

## 1. SQL injection surface — clean

Every dynamic predicate uses bound parameters via `text() + :param`:
`days`, `geography`, `doc_type`, `search`, `cursor`, `user_id`, `did`, `limit`. The dynamic `WHERE` is built from a **fixed allow-list** of clause strings (lines 52–81), not from raw user input, so the f-string concatenation at line 87 is safe.

`search` is wrapped in `%...%` for `ILIKE` (line 77). Special characters `%` and `_` will function as wildcards — that's behavioural, not unsafe. NUL byte handling is on the asyncpg driver (clean).

## 2. Cursor pagination — BROKEN (P0)

The query orders by:
```
ORDER BY
  (r.score_final IS NULL) ASC,
  r.score_final DESC NULLS LAST,
  d.intrinsic_importance DESC NULLS LAST,
  d.collected_at DESC
```
…but the cursor predicate (line 80) is:
```
d.collected_at < CAST(:cursor AS timestamptz)
```
…and `next_cursor` is the **last row's `collected_at`** (line 134).

This is a fundamental mismatch. Once you paginate:

- The cursor only filters by `collected_at`, but the result order is dominated by `score_final`. Page 2 will skip every document with a higher `collected_at` but lower score that didn't fit on page 1, **and** include every document with a lower `collected_at` that already appeared on page 1 if its score was higher. **Both duplicates and skips are possible** depending on the score distribution.
- Two rows sharing a millisecond `collected_at` (common after a batch insert) are also vulnerable to the classic tiebreaker-skip bug.

**Fix sketch:** either (a) make the cursor a composite key matching the full ORDER BY (score_final, intrinsic_importance, collected_at, doc_id), or (b) switch to keyset pagination on a stable sort, or (c) snapshot a result set into a server-side cache keyed by a request token.

## 3. `total` and `geography_counts` ignore filters (P1)

- `geography_counts` (lines 158–168) computes a **fixed** 30-day count grouped by geography — not by the active filter. This is OK if the chips are meant to advertise potential coverage, but:
- `total` (lines 171–175) is `SELECT COUNT(*) FROM govt_documents` with **zero predicates** — not even `nlp_processed`, not even the day window. The frontend label "X of {total}" therefore lies whenever any filter is active, and even when no filter is active it includes unprocessed rows the user can never see.

**Fix sketch:** compute `total` from the same `WHERE` as the feed, sans `LIMIT`. For very large tables, switch to `COUNT(*) OVER ()` window function on the main query, or accept an estimate via `pg_class.reltuples`.

## 4. `days` window collides with cursor (P0)

The `days=30` predicate is added unconditionally (line 60). When paging deep, every page re-applies the 30-day floor → once you reach the last 30-day-old row the feed says `has_more=false` even if the user has been told there are 12,000 total. **The user cannot reach older data**, ever.

**Fix sketch:** drop the `days` filter once a `cursor` is supplied, or expose the `days` knob in the UI so the user can widen the window.

## 5. Hardcoded `nlp_processed = TRUE` (P2)

Line 52: `conditions = ["d.nlp_processed = TRUE"]`. Documents that fail the NLP pipeline (Groq quota exhausted, language detection failure, OCR failure) become **invisible to the user forever**. There is no surfacing of "we have this PDF but couldn't extract intel" — silent data loss. Should at minimum be observable via metrics, ideally exposed with a degraded card in the UI.

## 6. Lazy-fanout side-effect in a GET (P2)

Lines 141–155: every feed hit enqueues `score_govt_doc_for_all_users` Celery tasks for any unscored doc on the page. Concerns:
- **Idempotency:** under user thrashing (filter clicks), the same doc is re-enqueued repeatedly. Celery dedup not enforced.
- **Bare `except Exception:` swallow** at line 152 hides queue outages.
- A GET endpoint mutating side-effects (queue fill) is awkward — surveys / health-checks / link-prefetchers will trigger it. Consider gating on `cursor is None and not append`.

## 7. Auth & error mapping

- `get_current_user` is the standard dependency — propagates 401 cleanly.
- `GET /{doc_id}` raises `HTTPException(404)` for missing rows. ✓
- `POST /{doc_id}/summary` (need to read continuation) — pre-checked: maps `GroqQuotaExhausted → 503`, `GroqCallFailed → 500`. ✓

## 8. Performance

The feed `SELECT` joins `govt_documents` to `user_govt_doc_relevance` and projects a wide row including `entities_extracted` (JSONB) and a 400-char substring of full text. Indexes required for the query plan to stay sub-100ms:

- `govt_documents (collected_at DESC)` — for the cursor & ORDER BY.
- `govt_documents (source_geography, collected_at DESC)` — for geo filter.
- `govt_documents (document_type, collected_at DESC)` — for type filter.
- `user_govt_doc_relevance (user_id, doc_id) UNIQUE` — for the LEFT JOIN.

Action: cross-check `scripts/migrations/006_govt_documents.sql` for these. (Not done in this audit — flagged for live session.)

## 9. Logging

`logger = logging.getLogger(__name__)` is correctly used. The only `logger.warning` (line 153) prints exception text only — no token, no doc_id, no user — clean for PII.

## 10. Summary of defects

| ID | Severity | Issue |
|---|---|---|
| BE-1 | **P0** | Cursor pagination ORDER-BY/cursor mismatch → dups + skips |
| BE-2 | **P0** | `days=30` clause prevents reaching older docs even when `has_more` |
| BE-3 | P1 | `total` ignores filters; `geo_counts` ignores filters |
| BE-4 | P2 | `nlp_processed=TRUE` silently hides failed-pipeline docs |
| BE-5 | P2 | GET endpoint enqueues Celery work on every read; no dedup |
| BE-6 | P3 | Bare `except Exception` masks queue failures |

Indexing claims to be verified in Phase D live session.
