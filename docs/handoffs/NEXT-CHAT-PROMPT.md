# Paste this into a new chat

---

Continuing a RIG Surveillance session — pick up as if we never switched chats.

**FIRST read, in order:**
1. `C:\Users\Dell\Desktop\rig-surveillance\docs\handoffs\session-handoff-2026-07-17-FINAL.md` ← full state, read it all
2. The repo `CLAUDE.md` + your `memory/MEMORY.md` (per your global CLAUDE.md)
3. KB: `rig-knowledge-base/02-osint-desk/subsystems/{client-telangana-cm,keyword-tracking,v1-api-gateway}.md` and `01-rig-surveillance-backend/issues.md#I-21`

**CONTEXT:** DIPR Telangana (client VeriDeck, integrator) goes LIVE **Monday 2026-07-20**. Their delivery lead flies to Hyderabad on the 19th. The ingestion incident from 07-16 is RESOLVED — don't re-litigate it. A previous session (07-17) shipped a lot; that handoff lists exactly what, and also lists where it was wrong.

**ALREADY SHIPPED + VERIFIED LIVE — don't redo:**
- v1 `summary` now serves English (36.6%→72.7% corpus, 45.6%→74.8% Telugu). `_SUMMARY_MAX` 400→2000.
- `keyword-sentiment`: 561x faster (Telugu 118s→211ms via an `AS MATERIALIZED` CTE) and now scores the **English** summary, so Telugu returns real stance (0→41 scored).
- `days` accepted as an alias for `window`.
- `random_page_cost` 4→1.1 + `effective_io_concurrency` 1→200 (disk is SSD; 4 was making the planner avoid indexes estate-wide). Proven 11x. Client endpoints 2-4x faster.
- The v1 API is finally in git (it existed only inside the `osint-backend` container).

**RUNNING UNATTENDED:** the HTML strip backfill (209,166 rows, batch=200, detached, resumable, ETA Sat ~07:00). Check it's alive and that blocked backends stay 0.

**THE HEADLINE FINDING — most of the scope API is inert, on the LIVE key too.**
For `/v1/articles` only `entity_ids` and `mute_terms` do anything. `keywords`, `languages` and `topics` are stored, echoed back by `GET /v1/scope`, and **never** select articles; `regions` works for brief/cuttings/geo but not articles. It's the code, not a per-org setting. The live client's `kaleshwaram` keyword has done nothing since 2026-07-09 — 95 of 321 kaleshwaram articles never reach them.
**⚠️ Do NOT "fix" languages/topics/regions** — they're *narrowing* filters; wiring them up REMOVES articles (their sandbox has `languages=Telugu` but the DB stores `te` → feed would return zero). Inert is protecting them. Keywords are the only safe one (it widens).

**WHAT I WANT NEXT (in priority order):**
1. **The keyword filter.** Code is committed (`9105ff6`) but NOT deployed because the committed version uses `OR` (5.5–8.4s). Finish it with the **UNION rewrite** — §4 of the handoff has the exact SQL shape, the measurements (151ms warm vs their current 1,526ms), and the gotchas (`LIKE ANY(array)` is never trigram-indexable; the WHERE expression must byte-match `idx_articles_titlelead_trgm`; the keyset cursor must apply inside both branches). Test pagination hard, verify live with the sandbox key, don't ship a slow query onto their feed.
2. Anything else in §11 of the handoff.

**WORKING RULES:**
- Live client-facing prod DB with a Monday go-live. **Confirm before destructive/outward actions.**
- Box drops SSH mid-script → **run ONE small query per SSH call**.
- **Never** run an unbatched whole-table UPDATE on `articles` — and "batched" is not sufficient; size batches by **lock-hold time**. `SKIP LOCKED` never stops collectors waiting on *us*.
- Always check `pg_blocking_pids()` before blaming your own job.
- **The LIVE key is in active production use — never test with it.** Use the sandbox key at `/root/verideck_sandbox_key.txt`. Keep raw keys out of chat.
- A `rig-backend` restart re-arms Beat and re-fires the broken `topic_fill` rollup → it will stall ingestion. Its schedule is disabled **on the box only**; don't copy the repo's `celery_app.py` over it.
- **Verify every claim — including the handoff — against live state before acting.** Both handoffs so far have been confidently wrong in load-bearing ways, and §9 lists the previous session's own wrong turns. Measure before concluding.

**STILL OPEN / NOT DONE (someone must do these, possibly you):**
- **Nothing is pushed.** 13+ commits on `dipr-golive-20260717` exist only on this laptop, including the only git copy of the v1 API.
- The VeriDeck reply (draft at `docs/handoffs/client-api/verideck-reply-draft-20260717.md`) and the sandbox key were **not sent** as of the last session — check with me before assuming either way.
- 5 entities need adding + retro-tagging: Telangana Council of Ministers; Department of Information and Public Relations (Telangana); Telangana Jagruthi; Telangana Rajyadhikara Party; Teenmaar Mallanna.
- The sandbox scope does NOT mirror live (52 keywords, prose region) — restore before/after delivering the key.
- `shared_buffers` is 160MB on a 15.6GB box (cache hit 55.9%) — needs a restart window, not near 05:03 IST.
- `topic_fill` rollup root cause (KB I-21).
- DNL's `dnl_image_scan.py` spikes 1.4GB every 20 min on this box via root cron — different product, on Neon. Escalate.

Start by verifying current state (is the backfill still running and clean? is ingestion healthy? are blocked backends 0? did the branch get pushed?), tell me what you find, then tell me what you'd do first.
