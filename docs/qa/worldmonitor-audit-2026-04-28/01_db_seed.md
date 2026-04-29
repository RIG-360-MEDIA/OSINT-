# 01 — DB schema + seed sanity (Step 1)

**Verdict: FAIL — multiple BLOCKER issues for content-correctness rule.**

## Row counts (current DB state)

| Table | Rows | Notes |
|---|---:|---|
| cm_coalitions | 9 | OK — small lookup table |
| cm_political_handles | **9** | **All 9 rows have NULL `verified_url` — see D-1** |
| cm_issues | 5 | Sparse (LaBSE clustering output) |
| cm_issue_evidence | 32 | Spread across 5 issues, all `source_kind='article'` |
| cm_stance_scores | **5582** | **Only 46 (0.8%) state-scoped — see D-2** |
| cm_spokesperson_quotes | **446** | **Only 10 state='TG'; 365 (82%) empty state — see D-2** |
| cm_promises | 12 | All have `source_url` ✓; `last_evidence_url` 100% null (status not yet scored) |
| cm_dissent_signals | **0** | **Empty — task `score_dissent` never ran or produced no output** |
| cm_counter_narratives | **0** | **Empty — task `generate_counter_narratives` never ran or all rejected** |
| cm_risk_calendar | 24 | Populated |

## CRITICAL findings (BLOCKER for ship)

### D-1 — `cm_political_handles.verified_url` is 100% NULL
```
total=9 | verified_url_null=9 | url_null=0
```
Per memory note `feedback_cm_content_correctness.md`: every seed row
**must** carry a verified source URL proving a human checked the
handle exists. Migration `029_seed_opposition_handles.sql` defines
`verified_url` as nullable, and the seed inserts left it NULL. **All
9 rows fail the rule.**

Impact: opposition collector (`backend/collectors/sources/opposition_pr.py`)
fans out to these handles to scrape press releases. If a handle is
spoofed or stale, we'd ingest garbage with no audit trail. The
`person_name` column is also blank for every row — only party-level
handles are seeded, no individual leaders.

**Fix (out of scope for audit):** Either (a) backfill `verified_url`
for every row by hand-verifying the canonical Twitter URL, or (b) add
`NOT NULL` constraint and re-seed. The schema should also be
strengthened to `NOT NULL` once cleaned.

### D-2 — Massive state-scope gap
- `cm_stance_scores.state` empty for 5536/5582 rows (99.2%)
- `cm_spokesperson_quotes.state` empty for 365/446 rows (81.8%)
- Quotes contain non-Telangana parties: TMC, Shiv Sena, AAP, BJD,
  SKM, AIADMK, Mizo National Front, "National Rally" (likely from
  an unrelated international corpus)

The state column is what `cm_queries._state_like_clause()` filters
on. With 99% empty, every CM endpoint with `?state=TG` will return
near-empty datasets, and unfiltered queries will mix Indian
political content with global noise. This is why
`test_cm_router_smoke.py` likely 500s — the queries assume non-empty
joins.

### D-3 — Empty narrative + dissent tables
`cm_counter_narratives` and `cm_dissent_signals` both have **zero
rows**. These are the outputs of `tasks.cm.generate_counter_narratives`
and `tasks.cm.score_dissent`. Either:
- the tasks were never enqueued (no Beat schedule entry for them — see
  Step 2)
- they ran but every output was rejected (counter_narratives has a
  `rejected` boolean — no rows = not even rejections)

Endpoints `/api/cm/counter-narratives` and `/api/cm/dissent` will
return empty arrays at best, 500 at worst depending on JOIN handling.

## HIGH findings

### D-4 — Quote party canonicalization
- `cm_spokesperson_quotes.party` mixes "BJP" (acronym) and
  "Bharatiya Janata Party" (full name) — 22 vs 2 rows.
- 5 rows have literal string `'null'` as party value.
- `speaker_canonical` column exists but is NULL for most rows.

Voice-share / silence / dissent endpoints aggregate by party — these
duplicates split the same coalition into multiple buckets.

### D-5 — Schema rule not enforced
`cm_promises.source_url` is the source-of-truth field per memory
note, but the column is `NULLABLE` in migration 025. The current
seed has 0 nulls (good), but the schema does not enforce the
invariant. Add `NOT NULL` once seed data is final.

## MEDIUM findings

### D-6 — `cm_political_handles.person_name` blank for all rows
Only party-level handles seeded (9 parties × 1 twitter handle each).
No leader-level handles (Revanth Reddy, KTR, KCR, Pawan Kalyan,
Chandrababu Naidu, Jagan Mohan Reddy, etc). The dissent / silence /
voice-share features assume per-person quote attribution to detect
"so-and-so going off-message".

### D-7 — Single platform coverage
All 9 rows are `platform='twitter'`. The check constraint allows
`twitter, youtube, press_rss, press_html, telegram, facebook` but
none of those other platforms have any seeded handle, despite
`opposition_pr.py` collector being designed for press_rss / press_html.

## Defects to enter in DEFECTS.md

| ID | Sev | Title |
|---|---|---|
| D-1 | **BLOCKER** | All 9 cm_political_handles rows lack verified_url |
| D-2 | **BLOCKER** | 99% of cm_stance_scores + 82% of cm_spokesperson_quotes have no state — CM state-scoped endpoints will return near-empty |
| D-3 | **BLOCKER** | cm_counter_narratives + cm_dissent_signals both empty |
| D-4 | HIGH | Quote party values not canonicalized (BJP vs Bharatiya Janata Party; 5 literal "null") |
| D-5 | MEDIUM | cm_promises.source_url should be NOT NULL once seed is finalized |
| D-6 | MEDIUM | No person-level handles (only party accounts) |
| D-7 | MEDIUM | Only twitter platform represented; press_rss/html/youtube/telegram unused |
