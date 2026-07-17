# Session Handoff — 2026-07-17 (DIPR go-live Monday 2026-07-20)

> Supersedes `session-handoff-2026-07-16.md`. **Verify live state before acting on any claim here** — the 07-16 doc was confidently wrong in several load-bearing places (listed in §6), and this one will rot too.

---

## 0. TL;DR

- **✅ Fix 1 (summary → English) is SHIPPED, LIVE, and VERIFIED.** English coverage **36.6% → 72.7%** corpus-wide, **45.6% → 74.8%** on Telugu. No GPU, no migration.
- **🔄 Fix 2 (HTML strip) is RUNNING** — detached, batch=200, ~200 rows/min, ETA ~07:00 Sat. Resumable.
- **🔴 NEW, UNRESOLVED: the `topic_fill` rollup still stalls ingestion.** Its beat schedule is **DISABLED** as a stopgap. Root cause open. See §3 — this is the most important thing in this doc.
- **✅ The v1 API is now in git** for the first time (it existed only inside a container).
- **⏳ Not done: reply to VeriDeck (draft ready), deliver sandbox key, tonight's PATCH verification.**

---

## 1. What shipped (all verified live, not inferred)

**Commits on branch `dipr-golive-20260717`** (repo `RIG-360-MEDIA/OSINT-`, **not pushed**):

| commit | what |
|---|---|
| `aa8758f` | import live v1 partner-API source from the container into git |
| `f211702` | v1 `summary` → English (+ `_SUMMARY_MAX` 400→2000) |
| `bb5387a` | collectors strip HTML from `lead_text_original` + the backfill |
| `5d39e20` | backfill batch 2000→200 |

**Fix 1 — `summary`.** `queries._SUMMARY_SQL` now prefers an English lead, then
`summary_executive`, then `summary_preview`, then the historic fallbacks. Live at
lines ~447/500/886 of `products/osint/backend/v1/queries.py`. Deployed to the
container **and** the build context. `_SUMMARY_MAX` 400→2000 in `serializers.py`.
Proof: `te` articles now return English at full length via the sandbox key;
`summary_original` still returns native script. Suite 8F/136P before and after
(the 8 are pre-existing).

**Fix 2 — HTML strip.** Forward fix live in the 3 collectors (needs the
`rig-backend` restart to take effect — done at 10:36). Backfill running:
`docker exec rig-backend tail -f /tmp/backfill_lead_html_20260717.log`.

---

## 2. Fix 2 — how to babysit it

```
# progress
docker exec -i rig-postgres psql -U rig -d rig -t -A -c \
 "SELECT count(*) FILTER (WHERE cleaned_at IS NOT NULL), count(*) FROM analytics.lead_orig_html_backup_20260717;"
# THE safety check -- must stay 0
docker exec -i rig-postgres psql -U rig -d rig -t -A -c \
 "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' AND pid<>pg_backend_pid();"
```

- **It dies if `rig-backend` restarts** (it runs via `docker exec -d`). That is safe — it is **resumable**: just re-launch, it resumes off the worklist.
  `docker exec -d rig-backend python /app/scripts/backfills/backfill_lead_html.py`
- **Rollback**: `analytics.lead_orig_html_backup_20260717` holds `id, old_lead` for every row.
  `UPDATE articles a SET lead_text_original = b.old_lead FROM <backup> b WHERE a.id=b.id AND b.cleaned_at IS NOT NULL;`
- A separate `..._test50` table holds the backup for the 50 rehearsal rows. **Don't drop either until verified.**
- Phase 2 recovers rows that cleaned to nothing (they were pure `<img>`/`<a>` markup) from `full_text_scraped`; the rest stay NULL, which is honest.

---

## 3. 🔴 THE OPEN ONE — `topic_fill` rollup stalls ingestion (KB I-21)

**Ingestion flatlined ~7 min today (10:41→10:48).** Not the backfill —
`pg_blocking_pids()` traced every blocked backend to one rollup pid; three
collector INSERTs were blocked 314s/253s/150s; its transaction hit 540s.

**I-20's fix was incomplete.** `_rollup()` *is* batched (`LIMIT 2000 FOR UPDATE
SKIP LOCKED`) — but batching bounds batch **SIZE, not DURATION**. The predicate
`topic_category IS DISTINCT FROM (CASE topic_fine ...)` has **no index** (`0`
indexes on `topic_fine`), so each batch **seq-scans 1.19M rows** to find its 2000
*while holding every lock it already took*. And `topic-fill-every-5-min` fires
faster than the task completes, so runs overlap — two were seen at once.

**Stopgap applied:** running backends terminated; the beat entry **commented out**
in `/root/rig/backend/celery_app.py` (backup `/root/celery_app.py.bak-20260717`).
Ingestion recovered in seconds (10:41:27 → 10:51:27, 765 articles/30min, 0
blocked). The ~1M `topic_category` backlog is left undrained — internal field, not
served by v1, cosmetic.

**⚠️ The box's `celery_app.py` DIFFERS from the repo's** (box line 417 vs repo 375)
— the disable was applied **on the box only**. Do not blanket-copy the repo over it.

**Re-enable ONLY after** (1) an index backs the predicate, or the rollup drives off
a bounded worklist (see `backfill_lead_html.py` for the pattern); **and** (2) the
interval exceeds worst-case runtime, or the task can't overlap itself.

**Also: a `rig-backend` restart re-arms Beat and re-fires this immediately.** That
is how it started today.

---

## 4. Environment finding — the box is memory-starved

`free -m`: **4,045 MB swap in use**, 180 MB free. **Postgres cache hit ratio 55.9%**
(want >95%). Random reads run ~300ms, which is why the backfill does 200 rows/min
rather than thousands. Not a code problem — worth its own look after Monday.

---

## 5. Still to do

1. **Reply to VeriDeck** — draft ready at `docs/handoffs/client-api/verideck-reply-draft-20260717.md`. **Not sent.** It deliberately says nothing about our internals; the one thing they MUST read is that `summary`/`summary_original` now return up to 2000 chars (was 400) — if they mirror into fixed-width columns, Monday breaks.
2. **Deliver the sandbox key** (`/root/verideck_sandbox_key.txt`, chmod 600 — `shred -u` after).
3. **Tonight: verify their PATCH per term** — an unknown entity name does NOT error, it silently degrades to a keyword (you keep text matches, you lose entity-level analytics). Confirm each name resolved to an entity_id AND returns non-zero coverage.
4. **Push the branch / open the PR.** Nothing is pushed.
5. Watch the backfill to completion, then verify `SELECT count(*) FROM articles WHERE lead_text_original ~ '<[a-zA-Z/]'` → 0.
6. Older: PR `substrate-lead-fallback` (`7faf5cf`), substrate anti-clobber COALESCE.

---

## 6. Where the 07-16 handoff was wrong (so you don't re-inherit it)

- **"`summary_executive` is better for the EN ≤400 contract"** — backwards. 84% of English executive summaries exceed 400; at 400 the API clipped 58% of all summaries (p50 513).
- **There is no "≤400 contract."** The client API PDF states no length limit anywhere — 400 was `_SUMMARY_MAX` in our own serializer. The ceiling is ours to choose.
- **Baseline "English ~32%"** — actually 41%; and the fix's real gain is 36.6%→72.7% corpus-wide.
- **Source path `products/osint/backend/v1/queries.py`** — did not exist locally; the whole v1 package was untracked. Real source was the container.
- **"Memory: updated"** — the memory directory was empty. (Now written.)
- **"The batched rollup is draining the backlog non-blocking"** — it is not. See §3.
- It was **right** about I-19/I-20 being in the KB (the file is newest-first, so `tail` misses them) and about the `queries.py` line numbers. Verify both directions.

---

## 7. Guardrails (unchanged, and they earned their keep today)

Live client-facing prod DB, Monday go-live. One small query per SSH call. Never
run an unbatched whole-table UPDATE on `articles` — **and note that "batched" is
not sufficient; size the batch by lock-hold time.** Always check
`pg_blocking_pids()` before blaming your own job. Confirm before destructive or
outward actions. Keep raw keys out of chat.

---

## 10. ADDENDUM (late 2026-07-17) — keyword work

**SHIPPED + VERIFIED LIVE:**
- `keyword-sentiment` discovery: **561x** (Telugu 30d 118,377ms → 211ms). The
  trigram index `idx_articles_titlelead_trgm` (3.1GB, migration 120) **already
  existed** and matched `_TITLELEAD` exactly — the planner just never chose it,
  because `ORDER BY collected_at DESC + LIMIT` made it walk `idx_articles_collected`
  with the ILIKE as a filter. `AS MATERIALIZED` forces the match set first.
- Telugu 500 → **200**. It was never Groq and never Telugu — just the slowest term.
  kaleshwaram only looked healthy because it was **cached**; Hindi because 15.9s
  squeaked under the timeout.
- Scoring now uses the **English** `summary_executive`/`summary_preview` as the
  body, not native text. Telugu `n_scored` **0 → 41** of 77.
- `days` accepted as an alias for `window` (400 if both given and disagree).

**WRITTEN, COMMITTED (`9105ff6`), DELIBERATELY NOT DEPLOYED — scope keyword filter.**
Scope keywords never filtered the article feed at all (see KB keyword-tracking.md).
The fix is correct and the semantics are right (entity OR keyword; no widening of
an explicit `?entity=` drill-down; searches the English summaries for the ~19x
gain on Telugu press). **It is gated on box health, not on code:**

| query | time |
|---|---|
| their feed today, 24h (entity only) | 1,526 ms |
| with keywords, 24h | 5,539 ms |
| with `AS MATERIALIZED` + OR'd single ILIKE | 8,127–8,406 ms |

The trigram index is **not** used at a 24h window — the planner correctly judges
`idx_articles_collected` cheaper for ~28k rows, then pays ~290µs/row on ILIKE over
large text. That per-row cost is the swapping box (§4), not the plan. On a healthy
box this is a few hundred ms. **Re-measure after the memory problem is addressed;
do not ship an 8s query onto the client's feed.**

Note `LIKE ANY(array)` is never trigram-indexable — only single-pattern
`ILIKE :pat` is. If this is retried, expand to OR'd single patterns.

**REFUSED, with reasons** (both were asked for; both are wrong to do now):
- *Substrate overwrite of `lead_text_translated`*: that column is the LaBSE embed
  input. It currently holds native text and the embeddings/clusters are built from
  it. "Stop overwriting" means it starts holding English → silently changes the
  embed input → forces a full re-embed + re-cluster. That is a migration, not a fix.
- *Entity auto-discovery*: NER + disambiguation + dedupe against the existing
  dictionary + a review step. Weeks, not a Friday.
