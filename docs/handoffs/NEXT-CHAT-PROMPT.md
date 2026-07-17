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

1. **Deploy the keyword filter — the UNION rewrite is WRITTEN and committed (`86ffa76`), but NOT deployed.** Do NOT rewrite it; it has been through adversarial review. What remains is the verification it explicitly could not do without the box:
   - **EXPLAIN ANALYZE at the MAX window.** The 151ms warm / 2,407ms cold numbers are **24h-window only**. There is deliberately no per-branch LIMIT, so the full match set is materialized and sorted on every page — cost scales with match count, and deep pagination is O(match set), not O(limit). Nobody has measured `MAX_WINDOW_DAYS`. If it's bad, the mitigation is a lower max window for keyword-scoped orgs — **NOT** a per-branch LIMIT (that re-arms the ORDER BY + LIMIT trap that caused the 118s scan, and is only sound if every post-union filter is duplicated into both branches).
   - **Live pagination test across a page boundary that straddles both branches** (page 1 all entity-matches, page 2 mixed). Silent row loss is the failure mode.
   - Then deploy to the container **and** `/root/rig/products/osint/backend/v1/`, run the v1 tests (baseline is **8F/136P** — match it exactly), restart `osint-backend`, verify live with the sandbox key.
   - It also fixes a **live latent 500**: `:eids` was referenced unconditionally while only bound inside `if entity_ids:`, so any keywords-only org (all_entities=false, entity_ids=[], keywords set) 500s today. Add a regression test.
   - Already verified on the box: both indexes exist and are `indisvalid`+`indisready`; neither org has a keyword under 3 chars (pg_trgm extracts no trigrams below 3 and would silently fall back to a scan); `article_entity_mentions` is a **MATVIEW** — a non-concurrent REFRESH takes an AccessExclusiveLock and would block the entity branch.
   - Paths A (all_entities) and B (entity-only) generate **byte-identical** SQL to the previous HEAD — only the keyword path is new.

2. Anything else in §11 of the handoff.

**ALSO DONE 2026-07-17 (don't redo):** title/suffix **aliases** added to `entity_lookup`, so VeriDeck can send names exactly as their analyst writes them — `Chief Minister A. Revanth Reddy`, `Deputy Chief Minister Mallu Bhatti Vikramarka`, and both `– Telangana` party units now resolve (verified live). `name_norm` is a global PK, so an alias maps to exactly one entity estate-wide; both dash shapes had to be added explicitly because the resolver is an exact string match. **Aliases are the supported way to absorb honorifics — never ask a client to reformat.**

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
