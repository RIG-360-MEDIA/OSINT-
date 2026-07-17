# RIG Surveillance — Session Handoff, 2026-07-17 (FINAL)

> **DIPR Telangana goes live Monday 2026-07-20.** VeriDeck's delivery lead flies to
> Hyderabad on the 19th. This doc is the single current source of truth.
> **Verify live state before acting on any claim here.** The 07-16 handoff was
> confidently wrong in several load-bearing ways (§8) — this one will rot too.

---

## 0. TL;DR — where things stand

| | status |
|---|---|
| **Summary → English** | ✅ SHIPPED, LIVE, VERIFIED |
| **keyword-sentiment (561x + Telugu scoring)** | ✅ SHIPPED, LIVE, VERIFIED |
| **`days` alias** | ✅ SHIPPED, LIVE, VERIFIED |
| **`random_page_cost` 4 → 1.1** | ✅ SHIPPED, LIVE, VERIFIED (11x) |
| **HTML strip backfill** | 🔄 RUNNING, unattended, ETA Sat ~07:00 |
| **v1 API imported into git** | ✅ (it existed only in a container) |
| **Scope keyword filter** | ⚠️ WRITTEN, COMMITTED, **NOT DEPLOYED** — see §4 |
| **topic_fill rollup** | 🔴 DISABLED as a stopgap, root cause OPEN (§5) |
| **VeriDeck reply** | ⏳ DRAFT READY, **NOT SENT** — time-critical (§3) |
| **Sandbox key** | ⏳ tested + safe, **NOT DELIVERED**; restore its scope first (§3) |
| **Branch pushed?** | ❌ **NO. 13+ commits local only.** |

**Repo:** `C:\Users\Dell\Desktop\rig-surveillance` → `RIG-360-MEDIA/OSINT-`
**Branch:** `dipr-golive-20260717` (off `substrate-lead-fallback`, **unpushed**)
**KB:** `C:\Users\Dell\Desktop\rig-knowledge-base` (committed)

---

## 1. Access

- **Box:** `ssh -i ~/.ssh/rig_hetzner root@178.104.145.135` (Hetzner). Old `178.105.63.154` RETIRED.
- **DB:** `docker exec -i rig-postgres psql -U rig -d rig`
- **v1 API:** `https://api.rig360media.com/v1/*`
- **Sandbox key:** `/root/verideck_sandbox_key.txt` (chmod 600). Keep raw keys out of chat.
- ⚠️ **The LIVE key is in active production use** (`last_used_at` 12:45 UTC today). We only hold the `rig_live_ddk_0c` *prefix*, not the raw key. **Never test with live.**
- ⚠️ SSH drops mid-script → **one small query per SSH call**. Heavy writes must be batched + detached.
- ⚠️ Self-match gotcha: always add `pid <> pg_backend_pid()` to `pg_stat_activity` hunts.

---

## 2. 🔴 THE HEADLINE — most of the scope API is inert, on the LIVE key too

`PATCH /v1/scope` takes six fields. For **`/v1/articles`** only **two** do anything:

| field | effect on article feed |
|---|---|
| `entity_ids` | ✅ works |
| `mute_terms` | ✅ works |
| `keywords` | ❌ **INERT** — stored, echoed back, never selects articles |
| `languages` | ❌ **INERT everywhere** |
| `topics` | ❌ **INERT everywhere** |
| `regions` | ⚠️ brief/cuttings/geo only — **not** articles |

**It's the code, not a per-org setting.** Live's `kaleshwaram` + `Telangana issues`
have done nothing since go-live 2026-07-09. Measured on the **live** org: 321
articles mention kaleshwaram in 30d → they receive **226**, every one because the
article *also* names a scoped politician. **95 never reach them.** Verified three
ways: no keyword clause exists in v1; `articles.py` never passes `keywords`; live,
50/50 returned articles mention a scoped entity.

### ⚠️ DO NOT "fix" languages / topics / regions

They are **narrowing** filters — wiring them up **removes** articles. The sandbox
holds `languages = Telugu,English,Urdu,Hindi`; the DB stores `te/en/ur/hi`. Turn it
on and the feed returns **zero**. **Inert is currently protecting the client.**
Keywords are the only safe one (it widens: `entity OR keyword`).

---

## 3. ⏰ DO THIS FIRST — the client is pushing scope TONIGHT

**Draft:** `docs/handoffs/client-api/verideck-reply-draft-20260717.md` — **not sent.**

Their mail asked: *"when we add the new **keywords** tonight, does that history come
through automatically?"* Answers (verified, not inferred):

- **Entities: yes, automatic, no job.** Entities added 2026-06-03 carry tagged
  articles back to 2026-04-22 (Malta 223 mentions, Mauritius 125, Solomon Is. 108 —
  oldest tagged article predates the entity in every case).
- **Keywords: deliver nothing** (§2). Which is why the mail tells them to send the
  list as **entities**.

**Their name-format question — tested against their real 19:**
- **Titles break it**, exact match only: `Chief Minister A. Revanth Reddy` ✗ vs `Revanth Reddy` ✓
- **Initials are fine**: `T. Harish Rao` ✓ `N. Ramchander Rao` ✓ `G. Kishan Reddy` ✓
- **The dash is a red herring — the ` – Telangana` suffix is the problem.** Both
  en-dash and hyphen fail; plain `Indian National Congress` ✓ / `Bharatiya Janata Party` ✓
- **14 of 19 resolve tonight.** The **5 to add + retro-tag**: Telangana Council of
  Ministers; Department of Information and Public Relations (Telangana); Telangana
  Jagruthi; Telangana Rajyadhikara Party; Teenmaar Mallanna.

**Also tell them (verified):**
- `languages` is **replace-when-provided**, not additive → their language list
  *overwrites*. This is literally their "half-applies silently" fear.
- Caps: 500 entities, 200 keywords, 20 languages.
- `summary`/`summary_original` now return up to **2000** chars (was 400). They
  bulk-mirror → fixed-width columns break.

**Sandbox key:** tested + safe to deliver (§7), **but restore its scope first** —
it does NOT mirror live (52 keywords, 4 languages, a prose region). `shred -u` the
file after delivery.

---

## 4. The keyword fix — written, not deployed, and HOW to finish it

Committed at `9105ff6`. Semantics are right: `entity OR keyword`; keywords do **not**
widen an explicit `?entity=` drill-down; searches the English summaries (30d Telugu:
"irrigation" → 19 native vs **355** via `summary_executive`/`summary_preview`, ~19x).

**It is NOT deployed because the committed version uses `OR`, which is slow:**

| version | 24h window |
|---|---|
| their feed today (entity only) | 1,526 ms |
| committed `OR` version | 5,539–8,406 ms |
| **UNION rewrite** | **2,407 ms cold / 151 ms warm** |

**Finish it with the UNION rewrite.** `EXISTS(...) OR ILIKE(...)` **cannot be
bitmapped** — the planner evaluates both per row. UNION lets each branch use its own
index (`article_entity_mentions_entity_idx` + `idx_articles_titlelead_trgm`):

```sql
WITH ent AS MATERIALIZED (SELECT a.id, a.collected_at FROM articles a WHERE <base+cursor> AND EXISTS(...)),
     kw  AS MATERIALIZED (SELECT a.id, a.collected_at FROM articles a WHERE <base+cursor> AND (<_TITLELEAD> ILIKE :k1 OR <_TITLELEAD> ILIKE :k2 ...)),
     ids AS (SELECT * FROM ent UNION SELECT * FROM kw)
SELECT <projection> FROM articles a JOIN ids USING (id) JOIN sources s ... ORDER BY a.collected_at DESC, a.id DESC LIMIT :lim
```

**Gotchas, all learned the hard way:**
- `LIKE ANY(array)` is **never** trigram-indexable. Only single-pattern `ILIKE :pat`. Expand to OR'd single patterns.
- The WHERE expression must be **byte-identical** to `idx_articles_titlelead_trgm`'s indexed expression (see `_TITLELEAD` in `keyword_sentiment.py`) or the index silently stops matching.
- **Keyset cursor must apply inside BOTH branches** — this is the risky part; test pagination hard.
- `summary_executive`/`summary_preview` are **not** in any trigram index. Including them costs a scan. Either accept title+lead only for now (kaleshwaram is Latin script → matches), or add a trigram index on the summaries later for the 19x English gain.

---

## 5. 🔴 OPEN — topic_fill rollup stalls ingestion (KB I-21)

Ingestion flatlined ~7 min today (10:41→10:48). `pg_blocking_pids()` traced **every**
blocked backend to one rollup pid; three collector INSERTs blocked 314s/253s/150s;
its transaction hit 540s.

**I-20's "batched" fix was incomplete.** `LIMIT 2000 FOR UPDATE SKIP LOCKED` bounds
batch **SIZE, not DURATION**. The predicate `topic_category IS DISTINCT FROM (CASE
topic_fine ...)` has **no index** → each batch seq-scans 1.19M rows *while holding
every lock it already took*. And `topic-fill-every-5-min` fires faster than it
finishes → runs overlap (two seen at once).

**Stopgap:** backends terminated; beat entry **commented out** in
`/root/rig/backend/celery_app.py` (backup `/root/celery_app.py.bak-20260717`).
Ingestion recovered in seconds. The ~1M `topic_category` backlog is undrained —
internal field, not served by v1, cosmetic.

⚠️ **The box's `celery_app.py` DIFFERS from the repo's** (box line 417 vs repo 375).
The disable is **on the box only**. Do not blanket-copy the repo over it.
⚠️ **A `rig-backend` restart re-arms Beat and re-fires this immediately.**

**Re-enable only after** (1) an index backs the predicate or it drives off a bounded
worklist (see `scripts/backfills/backfill_lead_html.py` for the pattern), **and**
(2) the interval exceeds worst-case runtime.

---

## 6. The box — memory, and what's actually true

**`shared_buffers` is 160 MB on a 15.6 GB box** — the stock default, never tuned.
That is why `pg_stat_database` cache hit sits at **55.9%** (want >95%). Fixing it
needs a **Postgres restart** → brief client downtime. Do it outside DIPR's 05:03 IST
brief pull. **Likely a bigger win than the 11x already banked.**

Also still un-tuned: `effective_cache_size` 5GB → ~9GB (reloadable, safe),
`maintenance_work_mem` 64MB → 512MB–1GB.

**Already done (2026-07-17, `ALTER SYSTEM` + reload, no restart):**
`random_page_cost 4 → 1.1` (disk is SSD, `ROTA=0`; 4 is the *spinning-disk* default
and was making the planner avoid indexes estate-wide) and
`effective_io_concurrency 1 → 200`. Proven by session-level A/B, same query, same
warm cache: **1,624ms → 148ms (11x)**. Client endpoints: `stories` **7.95s → 2.14s**,
`articles` 1.52s → 0.77s, `brief/daily` 3.29s → 1.73s. All 200, no regressions.
**Rollback:** `ALTER SYSTEM RESET random_page_cost; ALTER SYSTEM RESET effective_io_concurrency; SELECT pg_reload_conf();` (both were `source=default`).

**Swap — do NOT read "10GB used" as disk thrash:**
```
/dev/zram0  8G / 8G   priority 100   <- compressed swap IN RAM, FULL
/swapfile   8G / 2.2G priority -2    <- actual disk, overflow only
zram: 8.00 GB stored -> 3.02 GB compressed (2.6x)
```
zram works, but it is **full**, so overflow now hits real disk, and its 3GB
compressed store is RAM apps can't use. 8GB zram on 15.6GB (51%) is aggressive.

**Biggest single consumer is NOT ours:** `dnl_image_scan.py` spikes **~1.4 GB every
20 min** via root cron (`dnl_neon_imagechecks.sh`). That is **DNL / Rig Wire**, which
runs on **Neon** — a different database — competing for RAM with the box DIPR goes
live on. Escalate; not this product's code.
Celery nlp workers: 611 + 526 + 476 MB; youtube 425 MB.

---

## 7. Fix 2 — the HTML backfill (running unattended)

```bash
# progress
docker exec -i rig-postgres psql -U rig -d rig -t -A -c \
 "SELECT count(*) FILTER (WHERE cleaned_at IS NOT NULL), count(*) FROM analytics.lead_orig_html_backup_20260717;"
# THE safety check -- must stay 0
docker exec -i rig-postgres psql -U rig -d rig -t -A -c \
 "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' AND pid<>pg_backend_pid();"
# when done, this must be 0
docker exec -i rig-postgres psql -U rig -d rig -t -A -c \
 "SELECT count(*) FROM articles WHERE lead_text_original ~ '<[a-zA-Z/]';"
```

- **Dies if `rig-backend` restarts** (runs via `docker exec -d`) — that's safe, it's
  **resumable**: `docker exec -d rig-backend python /app/scripts/backfills/backfill_lead_html.py`
- **Rollback:** `analytics.lead_orig_html_backup_20260717` holds `id, old_lead`.
  `UPDATE articles a SET lead_text_original=b.old_lead FROM <backup> b WHERE a.id=b.id AND b.cleaned_at IS NOT NULL;`
- `..._test50` holds the rehearsal rows' backup. **Don't drop either until verified.**
- It is clean: **9 MB RSS**, no leak. ~150–200 rows/min (box is slow, not the script).

### Sandbox key — re-verified today AFTER 4 API deploys, safe to deliver
no/garbage/empty key → **401** · `/v1/admin/*` → **404** · out-of-scope entity →
**404** (not 403 — correctly indistinguishable) · rate limit **120/min** with
`x-ratelimit-*` headers · quota 100k · `is_sandbox=true` · all 10 endpoints **200** ·
entity set **identical** to live.
**But its scope does NOT mirror live** — 52 keywords, 4 languages, a prose region
(`India (only where Telangana or the State Government is central)`). Restore first.

---

## 8. Where the 07-16 handoff was wrong (don't re-inherit it)

- **"`summary_executive` is better for the EN ≤400 contract"** — backwards. 84% exceed 400; at 400 the API clipped 58% of summaries (p50 513).
- **There is no "≤400 contract."** The client API PDF states **no length limit**. 400 was `_SUMMARY_MAX` in our own serializer. The ceiling is ours.
- **"English ~32%"** — actually 41%; real gain 36.6% → 72.7% corpus-wide.
- **Source path `products/osint/backend/v1/queries.py`** — didn't exist locally; the whole v1 package was untracked, living only in the container.
- **"Memory: updated"** — the memory dir was empty.
- **"The batched rollup drains the backlog non-blocking"** — it does not (§5).
- **"Keywords match at query time"** — they don't match at all (§2). Its "proof" was measured against the DB, not the API.
- **"Sandbox verified restored to mirror live"** — it isn't (§7).
- It WAS right about: I-19/I-20 being in the KB (file is newest-first, `tail` misses them), the `queries.py` line numbers, and entity retro-tagging. **Verify both directions.**

---

## 9. My own wrong turns today (so you don't repeat them)

- Blamed **Groq** for the Telugu 500. Wrong — `_score_bodies` has a 20s budget and degrades to partial; it cannot hang a request. It was the unindexed discovery scan.
- Then blamed **Telugu**. Wrong — kaleshwaram (33.7s) and Hindi (15.9s) were also broken; kaleshwaram only *looked* fine because it was **cached**, Hindi because 15.9s squeaked under the timeout.
- Said the keyword filter **needed a 2.2GB trigram index build**. Wrong — `idx_articles_titlelead_trgm` (3.1GB, migration 120) already existed; the planner just never chose it.
- Then said it was **gated on box health**. Wrong — it was gated on the query *shape* (`OR` vs `UNION`).
- Nearly accused the handoff of not writing I-19/I-20 to the KB. Wrong — the file is newest-first and my `tail` missed them.

**Pattern: measure before concluding, and measure again before contradicting.**

---

## 10. Commits on `dipr-golive-20260717` (UNPUSHED)

| commit | what |
|---|---|
| `aa8758f` | import live v1 partner-API source from the container into git |
| `f211702` | v1 `summary` → English (+ `_SUMMARY_MAX` 400→2000) |
| `bb5387a` | collectors strip HTML + the backfill |
| `5d39e20` | backfill batch 2000→200 |
| `72ed525` | handoff + VeriDeck draft |
| `7c95ec7` | correct the draft — unresolved names don't lose sentiment |
| `9105ff6` | **keyword filter (NOT DEPLOYED)** + `days` alias |
| `044bd84` | keyword-sentiment 561x + score English not Telugu |
| `a58ba1b` | addendum |
| `24903f3` | correct stale keyword claim |
| `793595e` | rewrite VeriDeck reply against their actual mail |

KB repo has its own commits (`f27295d`, `98ecf11`, `e5a6295`, …), also unpushed.

---

## 11. Priority order from here

1. **Send the VeriDeck reply + sandbox key — tonight, before their analysts push.** Restore the sandbox scope first.
2. **Push both branches.** 13+ commits exist only on one laptop — the exact failure mode we spent the morning fixing.
3. **Add + retro-tag the 5 entities** (§3) so they're live before Monday.
4. **Finish the keyword filter** with the UNION rewrite (§4). Fresh context; test pagination hard.
5. **`shared_buffers`** (§6) in a chosen window, not near 05:03 IST.
6. Watch the backfill to 0 dirty rows (§7).
7. **After Monday:** topic_fill root cause (§5); escalate DNL's 1.4GB cron (§6); normalise `languages` before ever wiring it (§2).

---

## 12. Guardrails (they earned their keep today)

Live client-facing prod DB, Monday go-live. **One small query per SSH call.** Never
run an unbatched whole-table UPDATE on `articles` — **and "batched" is not
sufficient; size the batch by lock-hold time.** `SKIP LOCKED` is one-directional: it
stops *us* waiting on collectors, never collectors waiting on *us*. Always check
`pg_blocking_pids()` before blaming your own job. Confirm before destructive or
outward actions. Keep raw keys out of chat. **Verify every claim — including this
doc — against live state.**
