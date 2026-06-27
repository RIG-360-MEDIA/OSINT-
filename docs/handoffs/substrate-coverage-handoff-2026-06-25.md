# Substrate Coverage Crisis — Handoff (2026-06-25)

> **Resume prompt** (paste into a new chat to continue seamlessly):
>
> "We're fixing a substrate-extraction coverage collapse on RIG Surveillance. As of 2026-06-23, article LLM-field coverage crashed because daily ingest ~4×'d (≈20k→90k/day) and overran LLM capacity, so the big 10-field extraction call (`groq_semantic` in `backend/tasks/substrate/run_corpus_pass.py`) started dropping fields. Coverage now (last 3d): summary ~27%, geo_primary ~40%, entities ~68% (was ~70/65/83% before 06-23). Root cause: the model omits fields from the crowded JSON (no error — silently `{}` at line ~762; the `claims_extracted`/`quotes_extracted` flags are set TRUE unconditionally so they MASK the real LLM success rate). geo_primary is DERIVED from `entities_extracted` via `backend/nlp/nlp_geo.py:tag_geography()` (it is NOT separately extracted). LLM pool is local-first on TabbyAPI/Qwen3-14B (TRIJYA-8 RTX4070, :5000); TRIJYA-7's 4090 is dead (Code 43 hardware). We SHIPPED a dedicated `summary` rescue call (`SPLIT_SUMMARY=1`, 100% compliance in dry-run) + a host-side backfill loop (`/root/_summary_backfill_loop.sh`) over ~148k `ok` articles. We were deciding between (A) per-field rescue calls vs (B) schema-forced single call vs (C) two balanced calls, and testing whether TabbyAPI's json_schema enforcement fixes field-dropping in one call. Read `docs/handoffs/substrate-coverage-handoff-2026-06-25.md` for full state. Continue from the schema-test result."

---

## The problem
Article enrichment fields collapsed. Coverage by **processing day** (the smoking gun):

| proc day | volume/day | geo% | entities% | summary% |
|---|---|---|---|---|
| 06-04 → 06-22 | ~10–20k | ~65 | ~83 | ~70 |
| **06-23** | **91,103** | 40 | 67 | 22 |
| **06-24** | **84,880** | 38 | 62 | 23 |

**Root cause:** on 06-23 daily ingest ~4×'d (≈20k→90k/day). The LLM pool has fixed capacity; under that load the big extraction call returns incomplete, so every LLM-derived field dropped at once — summary worst (no fallback), entities least (partial local-NER fallback), geo in between.

## How the extraction works (key mechanics)
- **One big call** `groq_semantic(title, body, sys, max_tok)` in `backend/tasks/substrate/run_corpus_pass.py` returns a ~10-field JSON: `article_type, primary_subject, summaries{preview,snippet,executive}, locations[{text,country,region,city,is_primary}], events[], quotes[], actor_stances[], claims[], numbers[], register{}, english_translation`.
- The model **omits the `summaries` block ~75% of the time** (and locations/others under load). No error is raised — line ~762 does `if not isinstance(parsed.get("summaries"),dict): parsed["summaries"]={}`. So it's silent.
- **`claims_extracted`/`quotes_extracted` are set `TRUE` unconditionally** on persist (lines ~1014–1015) — they are NOT evidence of content. They masked the real failure. **flag ≠ data.**
- **`geo_primary`/`geo_secondary` are DERIVED, not extracted** — `backend/nlp/nlp_geo.py:tag_geography(title, body, entities_extracted)` picks the first geo-type entity word-matching the title → first 300 chars → fallback. So **fix entities ⇒ geo re-derives for free.** (That's why geo% ≈ has-location-entity%.)
- `entities_extracted` shape (jsonb): `[{"name","type","label","confidence","prominence"}]`, type ∈ location/person/organization/…
- geo columns on `articles`: `geo_primary` (text), `geo_secondary` (array), `source_country` (char, =publisher country, always 100%, NOT article-derived).
- Data-quality note: geo_primary even when present has junk (`Para`, `Una`) and mixed granularity (cities like `Moscow` next to countries) — comes from junk location entities.

## Backlog
`summary_executive='' AND full_text_scraped<>''`: **all-time 246,822 / 30d 209,605 / 7d 144,195**. By status the real target is **`ok` = 147,651** (rest: fetch_failed 51k, junk 39k, processing/extract_failed — legitimately no summary). Backfill correctly filters `substrate_status='ok'`.
- Entities gap (3d): ~39,207 `ok` articles have NO entities. **⚠️ CORRECTION (later 2026-06-25): this was largely a STAGE-LAG MEASUREMENT ARTIFACT.** `entities_extracted` is written by `nlp_processor.py` via **local spaCy** (`en_core_web_sm`, `nlp_entities.extract_entities`), NOT the substrate LLM — a SEPARATE, later stage. Measuring entity coverage by `substrate_processed_at` undercounts (fresh substrate rows haven't hit nlp yet). Measured at the correct stage (`nlp_claimed_at`, last 3h): **english 79% / non_english 70% ≈ ~75% overall**, nlp stage 94% done & keeping up (~1764/hr). So **entities do NOT need an LLM rescue** — healthy local pipeline; geo derives from these. The real LLM-dependent gap was SUMMARY only (fixed). Long-tail ~25% (short/junk/no-translation) is a spaCy-quality matter, not an LLM one.
- 3d per-field geo: geo_primary 40.2% (ok 43.2%), geo_secondary 7.9% (≈dead), source_country 100%, entities 68.1%, has-location-entity 41.4%.

## Infrastructure
- **Hetzner** prod: `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154`. Backend is **bind-mounted** from `/root/rig` (edit host file + restart, no rebuild). `rig-backend` = FastAPI + all Celery workers + Beat. DB: `docker exec rig-postgres psql -U rig -d rig`.
- **TabbyAPI / local LLM**: TRIJYA-8 = `100.105.228.103` (sshuser / pw 1234 via Posh-SSH). Runs TabbyAPI + ExLlamaV3 + Qwen3-14B-exl3-4bpw on `127.0.0.1:5000`, ~2-3k full extractions/hr. Wired into pool as "lmstudio": autossh `172.30.0.1:5000→node 127.0.0.1:5000` (IPv4 target — `localhost`=::1 breaks it) + UFW `172.16.0.0/12→5000` + compose env block. **LOCAL-FIRST**: `LOCAL_LLM_PRIMARY=1` + `get_slot()` patched to prefer lmstudio even under `skip_local`.
- **TRIJYA-7 4090 = DEAD** (`100.96.25.59`): Code 43 hardware fault, survived 3 reboots + disable/enable + service restart + pnputil + clean 610.62 driver reinstall. Needs physical 12VHPWR reseat. Ollama auto-start disabled there.

## What's been SHIPPED
1. **Local-first TabbyAPI** (relieves cloud TPD starvation). Cloud 429 storm → 0.
2. **Dedicated summary rescue** — `GROQ_SYS_SUMMARY` + `_dedicated_summary()` in `run_corpus_pass.py`, fires when `summary_executive` empty, gated `SPLIT_SUMMARY=1` (.env + compose). Dry-run: **100% compliance (40/40)**, good cross-lingual quality. Backup `.bak-pre-splitsummary`.
3. **Backfill engine** `backend/tasks/substrate/summary_backfill.py` (filters `substrate_status='ok'`, newest-first, COALESCE-writes). Running via robust host loop `/root/_summary_backfill_loop.sh` (8k-article chunks, concurrency 8, survives container restarts; log `/root/summary_backfill_loop.log`). **NOTE: a `docker exec -d` backfill died in ~1 min earlier (fragile); the host loop is the fix.**

## OPEN DECISION (where we are)
The summary rescue works, but the big call is fundamentally **overcrowded**. Since ~75% of articles miss summary, we pay ~2 calls/article anyway — so the rescue's "only on miss" saving is small. Three options:
- **(A) per-field rescue calls** — but DON'T do separate geo (geo derives from entities). So really: rescue = **summary + entities** (one call), then re-run `tag_geography` for geo. Low-risk, incremental.
- **(B) schema-forced single call** — make the big call obey a strict json_schema (TabbyAPI supports it) so it CANNOT drop fields. One call, fixes everything. Risk: forced fields may be low quality; mixed pool (cloud vs local) support varies. **← being tested now** (`/tmp/_schema_test.py` on Hetzner, loose vs enforced on 4 real articles).
- **(C) two balanced calls** — split 10 fields into 2 focused calls (summary+entities | claims+quotes+etc.); each less crowded → better compliance. Always 2 calls.

**Decision rule:** if schema-enforcement (B) yields high compliance AND good quality → ship B (cleanest, one call). Else if entities rescue (A) hits ~90% → ship A. Else (C).

### ⚠️ RESOLVED 2026-06-25 — it's CAPACITY, not prompt looseness
Schema test (`/tmp/_schema_test.py`, 3 real articles, healthy/idle TabbyAPI): **LOOSE json_object = 3/3 summary+locations; ENFORCED json_schema = 3/3.** Both 100%. So on a healthy server even the loose 10-field call returns everything — **(B) schema enforcement is RULED OUT** (looseness was never the bottleneck). The production ~25% is driven by **saturation**: under the 4× load TabbyAPI **wedges/times out** and calls fall to truncating cloud models, dropping fields. The summary rescue (A) helps only marginally (small calls complete more often under load) — it's not a true fix either.
**The real levers are CAPACITY + RELIABILITY, not prompt structure:** (1) revive the 4090 / add local nodes; (2) stabilize TabbyAPI so it stops wedging under concurrency (cap concurrency, investigate its batching deadlock); (3) throttle the 4× ingest to match capacity. Per-field rescues are band-aids on a capacity wound.

**Corroboration (2nd session, REAL-prompt test — strengthens the above):** re-ran with the
byte-faithful production `GROQ_SYS` (5217 ch) + real `max_tokens` (3000/3500), not the lean
prompt — `docs/handoffs/_gensrc/schema_test_prod.py` (host `/tmp/_schema_test_prod.py`), 8 real
`ok` articles (en/fr/ja/te):
- **LOOSE = 8/8 summary + 8/8 locations.** Local 14B is fully compliant on the *real* crowded
  prompt → field-drop is NOT prompt looseness. **ENFORCED TIMED OUT at 2/8** (grammar-constrained
  decode ~5× slower at prod prompt size) → **B disqualified on throughput too.**
- **Live pipeline is self-healing at moderate volume.** Coverage by `substrate_processed_at` hour
  inversely tracks load — summary **4% @ 2197/hr (15:00) → 88% @ 732/hr (00:00)**; entities
  66–83%, geo (derived) tracks entities. The shipped local-first + summary rescue WORK; they're
  only swamped above ~1800/hr.
- **Routing is correct; "0 local" in the pool log is cosmetic** — it counts only Ollama
  `provider=="local"` slots, not the 8 registered `lmstudio` slots (total=76). With
  `LOCAL_LLM_PRIMARY=1`, `get_slot` returns lmstudio first even under `skip_local`
  (`backend/nlp/groq_client.py:805`). So overflow→cloud happens only when all 8 lmstudio slots
  are saturated/cooled (the wedge or a burst), exactly matching the field-drop hours.
- Narrow justified slice of (A): add an **entities** backfill (local, on-miss, batch like the
  summary backfill — NOT inline), then re-run `tag_geography` so geo re-derives for free.

## Next steps
1. ✅ DONE — schema test run (real prompt). B ruled out, root cause = capacity/wedge (see RESOLVED above).
2. **CAPACITY is the fix, not A/B/C.** Priority order: (a) revive the 4090 (TRIJYA-7) or add a local node — doubles ~2.5k→~5k/hr, above the ~3700/hr ingest; (b) keep TabbyAPI off the wedge (backfill concurrency 4, live ~4 — stay under the ~8 wedge threshold); (c) decide on the 06-23 4× surge (scale capacity if intentional, else throttle).
3. Add an **entities** on-miss backfill (mirror `summary_backfill.py`, local, batch), then re-run `tag_geography` so geo auto-recovers on backfilled rows.
4. Let the summary backfill finish (~1.5 days for 148k on the 4070; the 4090 would halve it).
5. Separately: investigate the **06-23 4× volume surge** (intentional source expansion? if so capacity must scale; if not, throttle) and the **fetch_failed 51k** ingestion gap.

## Gotchas
- **TabbyAPI WEDGES under high concurrency.** The backfill at concurrency 8–12 hung it: it kept *accepting* requests but stopped generating (GPU 0%, model still loaded 9.9GB, log shows "Received chat completion request" with no completions). This stalled BOTH backfill AND live ingestion (everything fell back to cloud). **Symptom:** even a tiny `max_tokens:8` call to `:5000` times out. **Fix:** on TRIJYA-8 `taskkill /F /IM python.exe /T` then `schtasks /run /tn TabbyServe`, wait ~50s, verify with a tiny curl (should be ~1.5s). **Mitigation:** backfill now runs at **concurrency 4** (loop script edited) since live drain already uses ~4 — total stays under the wedge threshold.
- Don't `docker compose restart/up rig-backend` casually — kills the backfill (host loop auto-resumes though) and the running detached jobs.
- TRIJYA boxes: slow reboot (~13-19 min), Tailscale doesn't reliably auto-reconnect.
- `flag ≠ data` — always measure actual column content, not `*_extracted` booleans.
- Quote-hell over ssh→docker→psql: write `.sql` to a file, `docker cp`, `psql -f`.

---

## Adjacent pillars — YouTube + Newspapers (2026-06-25, later session)

While the article-summary work above is capacity-bound, two **other** dashboard cards
were red. Triaged both; YouTube had a real stall, Newspapers was a false alarm.

### ✅ Newspapers (clippings) — NOT an issue, do not "fix"
`worker-documents` alive and draining (`tasks.enrich_clipping` succeeding ~40s each, ~180/hr
vs ~44/hr inflow → self-clears). Backlog 755 is just a cosmetic threshold flag. The **40s/item**
is the same **cloud-pool saturation** described above, NOT a newspaper bug:
- Clippings run in `rig-backend` where **`LOCAL_LLM_ENABLED=0`** → they use Groq/Cerebras cloud,
  not the 4070. (The 4070/TabbyAPI serves the host-side article substrate loop only.)
- Cloud pool was throttling **~2062 cooldown/429 events / 20 min**, all `429 on qwen/qwen3-32b`
  (articles pillar primary + all `classification`/`translation` calls share FAST_MODEL=qwen3-32b).
- Newspapers' OWN extraction is already off qwen (`_PILLAR_CHAINS["newspapers"]` =
  `llama-3.3-70b → llama-3.1-8b → gpt-oss-120b` in `backend/nlp/groq_client.py:73`). The 40s =
  big 70b call + the **topic sub-call** (`classify_topic_fine`→`classify`→FAST_MODEL=qwen3-32b)
  diving into the qwen 429 storm + general pool retries.
- **"Make it very fast" is capacity-bound** (same root as the article gap). Deferred options if
  revisited: (A) thread a `model` param through `classify`/`classify_topic_fine` so the clipping
  topic call uses a headroom model instead of qwen3-32b; (B) re-enable local headroom for the
  Celery pool (competes with article substrate on the 4070); (C) raise documents concurrency =
  won't help, pool-bound. None ship "very fast" without more LLM capacity.

### ✅ YouTube — real stall, FIXED + made political-only
**Symptom:** dashboard LATEST ~2240 min, 0 clips/24h, backlog climbing. Every downstream
timestamp (clips/transcribe/extract) frozen at **2026-06-23 17:52**.

**Root cause = beat throttle never restored.** `fetch-youtube-transcripts-every-3-min` in
`backend/celery_app.py` was left at **`timedelta(minutes=360)`** + `limit=1` (= ~4 fetches/**day**)
— an emergency throttle from a past IP-block. The relays were healthy the whole time
(`/health` on both `100.109.85.70:8888` + `100.96.25.59:8888` → `circuit:closed, authenticated:true,
cb_failures:0, engine yt-dlp`). The name lied; the schedule said 360 min.

**Fix 1 — restored rate:** schedule → `timedelta(minutes=3)` (~20/hr, kept at 3-min as a
**ban precaution**, NOT faster, per the ~20/hr-per-IP block threshold). Restarted `rig-backend`
to reload beat; verified a live fetch (`relay video=BdruwUZew3w, 32 segs, transcribed=1 failed=0`).

**Fix 2 — political-only focus** (user decision: the 2,186-row backlog was all FRESH — 1,953 <24h,
1,264 political — and refills ~5:1 because discovery ~2400/day ≫ safe fetch ~480/day, so a plain
"clear backlog" is cosmetic and refills in a day). Patched `backend/tasks/youtube_task.py`:
- **Fetch selection** (`_fetch_transcripts`) WHERE clause now has **`AND is_political`** → fetch
  capacity only ever goes to political videos.
- **Discovery insert** (`discover_youtube_channels`) routes non-political →
  `status` = `CASE WHEN :pol THEN 'pending' ELSE 'skipped'` → queue stays political-only at source.
- **One-time:** 922 non-political pending → `skipped`. Queue now **1,262 pending, 100% political**.

**Reversibility:**
- Code backup on Hetzner: `/root/rig/backend/tasks/youtube_task.py.bak.20260625`. Patcher (idempotent):
  `_patch_yt_political.py` (repo root). To revert: restore `.bak`, set schedule back, restart.
- DB skip is tagged: undo with
  `UPDATE pending_youtube_videos SET status='pending', last_error=NULL WHERE last_error='political_only_focus_20260625'`.

**⚠️ Do NOT undo these as "config drift":** the 360-min was the bug, 3-min is intended; the
`AND is_political` filter + insert routing are the political-only feature, not accidents.

**Open caveat:** even political-fresh (1,262) > ~480/day fetch ceiling, so the political queue
will still grow; it's processed **newest-first** (`is_political DESC, video_published_at DESC`).
Truly bounding it needs more fetch capacity (more residential relay IPs) or a freshness cap —
same capacity theme as everything else in this doc. The dead 4090 does NOT help YouTube (fetch is
relay/IP-bound, not GPU-bound).

### Also done this session
- **Killed the summary backfill** (host loop orchestrator `/root/_summary_backfill_loop.sh` fully
  stopped — not just workers — so it won't respawn and re-steal the 4070). `SPLIT_SUMMARY=1`
  go-forward rescue stays ON. Backfill should only resume in off-peak windows / after the 4090
  reseat, or it re-breaches the live-queue threshold. The live extraction queue (~17.7k, a
  separate metric from the 148k summary gap) drains once the 4070 isn't shared.
