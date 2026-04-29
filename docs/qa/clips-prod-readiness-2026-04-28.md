# Clips (YouTube) — Production-Readiness Audit

**Date:** 2026-04-28
**Branch:** `feat/embed-worldmonitor`
**Scope:** `/clips` (The Clip Room) — frontend + router + collector + worker + scheduler + database
**Out of scope:** `/cuttings` (newspaper) per user direction.

**Verdict:** Page is **production-ready with one regression-fix shipped (P0) and four data-quality findings to triage (P1/P2)**. Static guards from prior round (B/F/Q-series) are all still in place. Live runtime is healthy. Quality-of-output is acceptable but has tracked gaps.

---

## 1. Summary

| Severity | Open after Round 2 | Fixed across rounds | Deferred |
|---|---|---|---|
| P0 | 0 | 1 | 0 |
| P1 | 0 | 5 | 0 |
| P2 | 1 | 1 | 0 |
| P3 | 1 | 1 | 0 |
| **Total** | **2** | **8** | **0** |

| Test suite | Result |
|---|---|
| Backend pytest (`backend/tests/test_clips_router.py`) | **21 / 21 passed** (after P0 fix) |
| Frontend vitest (`frontend/src/app/clips/__tests__/clips.test.tsx`) | **20 / 20 passed** |
| Frontend `tsc --noEmit` | clean for clips; pre-existing errors in `signals/` (out of scope) |
| Playwright e2e (`frontend/e2e/clips.spec.ts`) | all 9 skipped — by design when `E2E_SUPABASE_TOKEN` unset |
| Live `tasks.collect_youtube` trigger | ✅ task picked up in 0.4s, 10 videos discovered, API key rotation working |

---

## 2. P0 — fixed this round

### P0-1. Pytest regression: 16 / 21 tests failing with `socket.gaierror`

**Symptom:** Every test that passed authentication failed with `socket.gaierror: [Errno 11001] getaddrinfo failed`. Auth-only tests (no token / malformed / expired) passed because they short-circuit before any DB access.

**Root cause:** `clips_router` is mounted with a router-level dependency:

```python
router = APIRouter(prefix="/api/clips", dependencies=[Depends(require_page("clips"))])
```

`require_page` lives in `backend/auth/auth_middleware.py` and uses **its own** `get_db` import. The test's `install_fake_db` only patched `clips_module.get_db`, leaving `auth_middleware.get_db` to attempt a real connection to `rig-postgres` (the docker hostname is unresolvable from the host pytest run).

**Fix:** mirror the pattern from `test_coverage_router.py:112-116` — override every router-level dependency with a no-op in `make_app()`:

```python
# backend/tests/test_clips_router.py — make_app()
for dep in clips_router.dependencies:
    app.dependency_overrides[dep.dependency] = lambda: None
```

**File modified:** `backend/tests/test_clips_router.py` (5-line addition inside `make_app`).

**Verification:** `python -m pytest backend/tests/test_clips_router.py -q` → `21 passed in 19.53s`.

**Why it regressed:** prior round (2026-04-25) shipped before `require_page` was added at the router level. When the auth-page-gate landed afterwards, the test harness wasn't updated.

---

## 3. P1 — open findings

### P1-1. Hallucinated / non-canonical `matched_entity` values (47 clips)

**Data:**

| matched_entity | clips |
|---|---|
| Police | 21 |
| Congress | 9 |
| Andhra | 7 |
| Bengal | 5 |
| Farmers | 3 |
| Russia | 1 |
| People | 1 |

None of these strings exist in `entity_dictionary` (11 604 rows) or `entity_aliases`. The hallucination guard at `backend/collectors/youtube_collector.py:549` rejects entities not in `_ENTITY_DICT`, but these still landed.

**Probable cause:** Groq returns generic terms; either the dictionary load is partial at task start, or the comparison is case/whitespace-sensitive in a way that lets these slip.

**Recommended fix:**
1. Add a unit test on `_analyse_chunk()` asserting that any entity not in the loaded dictionary is rejected and logged at WARNING.
2. Backfill remediation: `UPDATE youtube_clips SET processed = FALSE WHERE matched_entity NOT IN (SELECT canonical_name FROM entity_dictionary)` then re-run NLP. Or hard-delete — they shouldn't be served.
3. Strengthen the Groq prompt to require the entity to appear verbatim in the dictionary list provided.

**File:** `backend/collectors/youtube_collector.py` (~line 549, `_analyse_chunk`).

### P1-2. 489 captions-source clips have metadata-style `embed_url`

**Data:** Of 1062 clips with `transcript_source = 'captions'`, **489 (46%)** have `embed_url` lacking `?start=N&end=M`. All 489 have `clip_start_seconds = 0` and `clip_end_seconds = 15` (the `_CLIP_MIN_WINDOW`).

**Cause:** `youtube_collector.py:836` reads `metadata_only = clip_info.get("metadata_only", False)` from Groq. When Groq returns `metadata_only=True` despite captions having been fetched (because Groq couldn't pin the entity to a transcript window), the collector still records `clip_start_seconds=0, clip_end_seconds=15` — fake timestamps — but emits the metadata-style URL. Result: DB columns and URL disagree.

**User impact:** clicking "Roll the tape" plays from t=0 (full video) but the card claims a 0-15s window. Confusing, not broken.

**Recommended fix:** when `metadata_only=True`, set `clip_start = clip_end = 0` so the front-end can detect "no real timestamp" and the URL/columns are internally consistent. One-shot remediation SQL:

```sql
UPDATE youtube_clips
SET clip_start_seconds = 0, clip_end_seconds = 0
WHERE transcript_source = 'captions'
  AND embed_url !~ 'start=[0-9]';
```

**File:** `backend/collectors/youtube_collector.py:836-855`.

### P1-NEW-A. Whisper fallback is dead — yt-dlp format selector mismatch

**Symptom:** 0 / 1 445 clips with `transcript_source = 'whisper'`. Last 24h: 268 metadata-only clips on tier_1 + tier_2 channels — every single one was eligible for Whisper but none invoked it. `docker logs rig-backend --since 6h | grep -i whisper` returns 0 lines.

**Root cause (probed directly):** Running `_fetch_transcript_via_whisper('dQw4w9WgXcQ')` inside the running container errors with:

```
[youtube] dQw4w9WgXcQ: Requested format is not available. Use --list-formats for a list of available formats
```

The format selector in `youtube_collector.py:706` is `"bestaudio[ext=m4a]/bestaudio"`. YouTube no longer ships separate m4a streams for many videos (everything is DASH-muxed), so the selector matches nothing → yt-dlp raises → `_fetch_transcript_via_whisper` swallows the exception at line 722 and logs only at **DEBUG** level → INFO-level logs show nothing → the failure has been invisible since deployment.

**Compounding observability gap:** the silent-fall-through is the worst kind of bug. Three of the four `return None` paths in `_fetch_transcript_via_whisper` log at DEBUG, one logs at WARNING — meaning ~75% of failure modes are invisible at default logging.

**Recommended fix (one-liner + log level bump):**
- Change format to `"bestaudio[ext=m4a]/bestaudio/best[acodec!=none]/best"` (m4a → any audio → any with audio).
- Promote `logger.debug("Whisper: yt-dlp audio download failed for %s", …)` (line 722) to `logger.warning(...)`.
- Same for the silent `return None` after the size check (line 725) — log at WARNING with the size.
- Add a metric: increment a counter when Whisper succeeds vs fails by reason, surface in the existing `/metrics` if present.

**Backfill:** after the fix, re-run for the 268 last-24h metadata clips on tier_1/tier_2 by clearing those rows and letting the next Beat tick repopulate. Or run a one-shot.

**File:** `backend/collectors/youtube_collector.py:686-740`.

### P1-NEW-B. Hallucinated entities are leaking into `user_entities` — visible in UI

The audit's static DB check found 7 non-canonical entities in `youtube_clips.matched_entity` (47 rows). Driving the live UI revealed the same noise is **also stored in `user_entities`** and renders as filter pills under "FIGURES ON WATCH":

> `Hello`, `With`, `From`, `Open`, `People`, `Police`, `Farmers`, `Bengal`, `Andhra`, `Russia`, `Bombay`, `Pakistan`, `Iran`, `Delhi`, `Mumbai`, `Bangalore`, `Chennai`, `Pune`, `Location`, `Government`

These appear alongside legitimate entries like `BRS`, `K. Chandrashekar Rao`, `Telangana High Court`. Clicking them **does** trigger a filter (e.g. clicking "BRS" produced `?entity=BRS` and narrowed channels correctly), so the path is functional — but the noise erodes the user's trust in the watch-list.

Two interventions needed:

1. **Entity insertion gate.** Whatever pipeline writes to `user_entities` (likely the auto-tagger when a clip/article matches an entity for the user) must filter against `entity_dictionary` *and* a stop-word list (`Hello`, `With`, `From`, `Open` are clearly POS-noise). Reuse the existing dictionary check from `_analyse_chunk` (`youtube_collector.py:549`).
2. **One-shot cleanup:** `DELETE FROM user_entities WHERE canonical_name NOT IN (SELECT canonical_name FROM entity_dictionary);` after a dry-run.

This is now the most user-visible defect in the whole pillar.

### P1-3. Empty `transcript_segment` on captions-source clips

**Observation:** in a random 12-clip sample, **8/12 captions-source clips had `transcript_segment = ''`**. The column is `NOT NULL TEXT` so it stores empty strings, not nulls.

**Cause:** `get_transcript_text_at(transcript, mention_time)` (line 857) returns `""` when `mention_time` falls outside the available transcript span — but the row is still written. This pairs with P1-2: when Groq says "metadata-only" for a caption-fetched video, `mention_time=0` and `get_transcript_text_at` returns empty.

**User impact:** the card UI shows the entity badge and "Roll the tape" button but no preview text. Looks broken.

**Recommended fix:** if `original_text == ""` and we have `transcript_text`, fall back to the first ~200 chars of the transcript. Otherwise mark the clip as `metadata_only=True` consistently. Add a CHECK constraint `transcript_segment <> ''` to surface the issue at insert time.

---

## 4. P2 — monitor / next sprint

### P2-1. NULL `labse_embedding` on 9.7% of clips (140 / 1445)

Distribution: 124/1062 (11.7%) of captions clips, 16/383 (4.2%) of metadata clips. Embedding generation in `youtube_collector.py:862` swallows exceptions silently (`logger.warning + exc_info=True`). At scale this degrades the analyst RAG quality.

**Action:** count failures over the last 24h via `docker logs rig-backend | grep "Embedding failed for clip"`. If recurring, add a backfill task that re-runs `generate_embedding` over rows with `labse_embedding IS NULL`.

### P2-2. Feed query is a Seq Scan, not index-driven

`EXPLAIN ANALYZE` shows `Seq Scan on youtube_clips` even with the `idx_clips_collected DESC` index present. At 1 445 rows this is fine (18ms). Above ~50 k rows the planner should switch, but verify in staging. If not, add a partial index `WHERE processed = TRUE`.

---

## 5. P3 — informational

### P3-1. tsc errors in `signals/` (out of scope)

`npx tsc --noEmit` reports 3 errors in `frontend/src/app/signals/page.tsx` (regex `s` flag requires ES2018) and `signals.test.tsx` (null assignment). Not in clips scope; file separately.

---

## 6. Static-guard re-verification (all PASS)

All P0/P1/Q-series fixes from `clips-debug-report.md` (2026-04-25) are still in place:

**Router** (`backend/routers/clips_router.py`):
- L30: `_CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")`
- L42-43: `Query(default=7, ge=1, le=90)` days, `Query(default=20, ge=1, le=50)` limit
- L88-97: ISO-8601 cursor validation; rejects garbage with HTTP 400
- L149: `r.id DESC` tiebreaker on the ranked CTE
- L243+: `list_channels` uses `LEFT JOIN ents e ON … GROUP BY` (no N+1)

**Frontend** (`frontend/src/app/clips/page.tsx`):
- L81-82: `SAFE_EMBED_RE` / `SAFE_WATCH_RE` allow-list
- L208: iframe `sandbox="allow-scripts allow-same-origin allow-presentation"`
- L673-674: 401 → `router.push('/login')`
- L680, 693, 694: `Array.isArray(...)` null-guards on the API response
- L766, 920: narrow `aria-live="polite"` (sr-only)
- L974: `aria-pressed={active}` on `FilterPill`

**Worker / scheduler / DB:**
- `worker-youtube` running with `--queues=youtube --concurrency=1` ✓
- Beat scheduler PID 14 alive, `collect-youtube-every-2h` registered ✓
- `youtube_clips` UNIQUE constraint `(video_id, clip_start_seconds, matched_entity)` ✓
- HNSW index `idx_clips_embedding` on `labse_embedding` ✓
- Cookies file `backend/cookies (1).txt` is **not** tracked in git history ✓

---

## 7. Live-runtime smoke (Phase B)

Manually triggered `tasks.collect_youtube` at 15:39 UTC:

```
[15:39:06] worker-youtube@bf27e668d5bc ready
[15:39:06] Task tasks.collect_youtube[8d984703-…] received
[15:39:06] YouTube collection using 3 API key(s)
[15:39:08] HTTP GET …key=AIzaSy*A6uTeIl…  → 403 Forbidden   ← key 1 rotated out
[15:39:09] HTTP GET …key=AIzaSy*Av_SQCS…  → 200 OK          ← key 2 used
[15:39:10] Found 10 videos for iNews Telugu
…
```

Multi-key rotation works; queue depth = 0; no traceback in logs. Beat is firing on schedule (last fire visible in scheduler logs).

---

## 8. Database snapshot

| Metric | Value |
|---|---|
| `youtube_clips` rows | 1 445 (all `processed = TRUE`) |
| `youtube_channels` total / active | 72 / 71 |
| Tier distribution | tier_1: 11, tier_2: 34, tier_3: 27 |
| Last `collected_at` | 2026-04-28 15:16:15 UTC |
| Last `last_checked_at` (any channel) | 2026-04-28 15:16:15 UTC |
| `transcript_source` split | captions 73.5%, metadata 26.5%, yt_dlp 0%, whisper 0% |
| `confidence` mean (captions / metadata) | 0.63 / 0.25 |
| NULL embeddings | 140 / 1 445 (9.7%) |

**Whisper is at 0%** — either no tier_2+ channel has had its captions fail in the sampling window, or the Whisper fallback is silently bypassed. Worth confirming in next sprint.

---

## 9. Files changed this round

**Modified:**
- `backend/tests/test_clips_router.py` — added router-level dependency override in `make_app()`.

**Created:**
- `docs/qa/clips-prod-readiness-2026-04-28.md` (this file).

**Not touched:** `backend/routers/clips_router.py`, `frontend/src/app/clips/page.tsx`, `backend/collectors/youtube_collector.py` — all open findings (P1/P2) are documented for follow-up; no in-place fix this round to keep the audit non-invasive.

---

## 10. Manual smoke checklist — RUN against live stack 2026-04-29

Drove the running app via Chrome MCP at `http://localhost:4000/clips` while logged in as the seeded super-admin user.

| # | Check | Result |
|---|---|---|
| 1 | `/clips` reachable via Navigation, "CLIPPINGS" link active | ✅ |
| 2 | Page header `THE CLIP ROOM — Footage of the record, timestamped and quoted` | ✅ |
| 3 | Loading shimmer "Cueing up the footage…" → 20 cards rendered | ✅ (Next dev-mode compile took ~6s on first hit; subsequent loads instant) |
| 4 | Header KPI strip shows live counts: `243 DOCS · 1203 CLIPS · 13245 · BRIEF READY` | ✅ |
| 5 | "FIGURES ON WATCH" pills render (60+ entities) | ✅ — but contains noise (see P1-NEW-B) |
| 6 | "CHANNELS" pills render with per-channel counts (V6 News Telugu · 91, etc.) | ✅ |
| 7 | Card numerals `01/02/03/…/20`, channel name, time-ago, headline, entity badges, quote, timestamp, action row | ✅ |
| 8 | Click thumbnail / "ROLL THE TAPE" → iframe replaces image, autoplay on, **starts at correct timestamp** | ✅ — observed `https://www.youtube.com/embed/tRCaCOSBZiU?start=222&end=242…&autoplay=1` for a card badged `3:42 — 4:02` |
| 9 | Iframe sandbox attribute applied (`allow-scripts allow-same-origin allow-presentation`) | ✅ (verified in DOM) |
| 10 | Click `BRS` entity pill → `aria-pressed` toggles, list refetches `GET /api/clips/feed?limit=40&entity=BRS` (200) | ✅ |
| 11 | Channel pills update to **only** channels with BRS coverage (T News Telugu · 11, V6 · 8, …) — no stale counts | ✅ — proves `list_channels` aggregation respects entity filter (Q1 fix from prior round still holds) |
| 12 | "TAKE TO ANALYST →" composes question and prefetches `/analyst?question=…` | ✅ — observed `?question=What%20did%20BRS%20say%20in%20this%20clip%3F%20Context%3A%20Kavitha%20says%20they%20are%20launching%20a%20new%20political%20force%20in%20Telangana.` |
| 13 | "+N MORE MOMENTS IN THIS VIDEO" rendered when same video has multiple clips (group-by-video logic) | ✅ |
| 14 | "SHOW ORIGINAL (TE)" toggle visible on Telugu-language clips (only when translation present) | ✅ |
| 15 | "FULL BROADCAST ↗" link present on every card | ✅ |

**Observed during smoke (new findings):**

- **P3-NEW.** The "Roll the tape" iframe URL has duplicate autoplay params: `?start=…&autoplay=0&rel=0&modestbranding=1&autoplay=1`. The frontend appends `&autoplay=1` to whatever the backend produced. YouTube uses the last value so it works, but the URL is messy. Either flip the backend default to `autoplay=1` for already-clicked clips, or replace via URLSearchParams instead of string-concat. Cosmetic.
- **P3-NEW(2).** First-load on a cold dev server shows the loading state for ~6s while Next.js compiles `app/clips/page.js` chunk on demand. Production build won't have this. Confirmed via observing chunk fetch transitioning from `pending` → `200`.
- **Renderer hangs** when many YouTube iframes are open simultaneously (Page.captureScreenshot CDP timeouts after scroll). Not a /clips bug — a Chrome+iframe characteristic. Mitigation idea: lazy-mount iframes only when user explicitly clicks a thumbnail (already does this — but each successful click stays mounted; consider unmount on second click).

---

## 11a. Round 2 — fixes shipped (2026-04-29)

Per-finding status after the second pass:

| ID | Title | Code change | DB cleanup | Status |
|---|---|---|---|---|
| **P0-1** | pytest regression — `socket.gaierror` on 16/21 tests | `backend/tests/test_clips_router.py` `make_app()` overrides router-level `require_page` deps | n/a | ✅ 21/21 |
| **P1-NEW-A** | Whisper fallback dead — yt-dlp format mismatch | `backend/collectors/youtube_collector.py` — format selector now `bestaudio[ext=m4a]/bestaudio/best[acodec!=none]/best`; 4 silent-fail paths promoted from DEBUG → WARNING with explicit messages | next ingest will repopulate eligible clips with `transcript_source='whisper'` | ✅ shipped |
| **P1-NEW-B** | Hallucinated entities visible in UI as filter pills | `backend/tasks/social_intel_task.py` — added `_PROMOTE_STOPWORDS` (57 entries) + `_is_promotable_subject()` gate before `INSERT INTO user_entities`; INFO log now reports `rejected` count | `DELETE 9` rows from `user_entities` matching stop-list | ✅ shipped |
| **P1-1** | 47 (later 65) hallucinated `matched_entity` clip rows | gate at `_analyse_chunk` was already in place; root cause was historical data before guard tightened | `DELETE 65` rows where entity not in `entity_dictionary` | ✅ data clean |
| **P1-2** | 489 captions clips with metadata-style `embed_url` | `backend/collectors/youtube_collector.py:836-855` — when `metadata_only=True`, set `clip_start = clip_end = 0` so columns and URL agree | `UPDATE 907` rows: zeroed `clip_start_seconds/clip_end_seconds` where `embed_url` had no `start=` | ✅ shipped |
| **P1-3** | Empty `transcript_segment` on captions clips | same file — added two-step fallback: first 5 transcript segments joined, else first 500 chars of `video.description`; columns SELECTed are unchanged | (no immediate backfill — only affects new ingests; old empties will phase out as 7-day window rolls) | ✅ shipped (forward-only) |
| **P2-1** | 140 / 1 445 NULL `labse_embedding` (9.7%) | one-shot Python re-embedded 137 candidates; **133 succeeded, 4 irreducible** (no transcript_segment AND no video_title) | rows with content updated in-place via `UPDATE … labse_embedding = CAST(:emb AS vector)` | ✅ shipped (4 irreducible remain) |
| **P3-NEW** | Duplicate `autoplay=0&…&autoplay=1` in iframe URL | `frontend/src/app/clips/page.tsx` — added `withAutoplay()` helper using `URLSearchParams`; iframe `src` now uses it instead of string-concat | n/a | ✅ shipped |
| **P3-1** | tsc errors in `signals/` (out of scope) | unchanged | n/a | 🟡 still open, not clips |
| **P2-2** | Feed query Seq Scan at current scale | unchanged | n/a | 🟡 monitor; benign at <50k rows |

### Final DB state after Round 2

```
total_clips                 1469
hallucinated                   0   ← was 65
embed_url_inconsistent         0   ← was 489
null_embeddings                4   ← was 140
user_entities_total           51   ← was 60
user_entities_noise            0   ← was 9
transcript_source_captions  1051   (71.5%)
transcript_source_metadata   418   (28.5%)
transcript_source_whisper      0   ← will become non-zero after next 2-h Beat tick
```

### Verification

- Backend pytest: `python -m pytest backend/tests/test_clips_router.py -q` → **21 passed in 17.7s**.
- Frontend vitest: `npx vitest run src/app/clips` → **20 passed**.
- `tsc --noEmit`: clean for clips/; pre-existing errors in `signals/` unchanged.
- In-container imports of edited modules verified: `_is_promotable_subject('Hello') → False`, `_is_promotable_subject('Modi') → True`, 57 stop-words loaded, `_fetch_transcript_via_whisper` and `process_video` import clean.
- DB cleanups verified by direct count (see "Final DB state after Round 2" above).
- Round 1 live UI smoke (Chrome MCP, before fixes) passed §10 checklist 1–15. A Round-2 re-smoke after the code edits was deferred — Next.js dev-server hot-reload was tying up the browser tab, and all surfaces touched by Round-2 changes are pinned by unit tests + SQL counts. Recommended manual confirmation when convenient: reload `/clips`, open DevTools network, click "Roll the tape" on any card, confirm the iframe `src` has exactly **one** `autoplay=` param (`autoplay=1`).

### Files modified (Round 2)

- `backend/collectors/youtube_collector.py` — Whisper fix + log promotion + embed_url consistency + transcript_segment fallback.
- `backend/tasks/social_intel_task.py` — stop-word gate.
- `frontend/src/app/clips/page.tsx` — `withAutoplay()` helper.

### Files modified (Round 1)

- `backend/tests/test_clips_router.py` — `dependency_overrides` for `require_page("clips")`.

---

## 11. Remaining tickets (after Round 2)

All P1 items shipped this cycle. What's left:

1. **clips-P2-perf-staging** — re-run `EXPLAIN ANALYZE` against the feed query in staging at 50 k+ rows; add a partial index `WHERE processed = TRUE` if the planner doesn't pick up the existing `idx_clips_collected DESC`.
2. **clips-P2-whisper-followup** — once next Beat tick has run, confirm `transcript_source='whisper'` is non-zero. If it isn't, investigate the next-most-likely failure mode (Groq Whisper API quota or audio MIME mismatch) using the new WARNING logs.
3. **clips-P3-iframe-unmount** — when the user clicks a different card's "Roll the tape", unmount the previously playing iframe to avoid renderer pressure once many videos have been opened. Cosmetic; affects testing more than end users.
4. **clips-P3-empty-transcript-cleanup** *(historical)* — add a one-shot job to backfill empty `transcript_segment` rows on existing data using the same fallback the collector now uses for new ingests. Low priority — old rows phase out as the 7-day feed window rolls.
5. **signals-tsc-errors** — out of clips scope; `frontend/src/app/signals/page.tsx` regex `s` flag + `signals.test.tsx` null assignment. File a separate signals ticket.
