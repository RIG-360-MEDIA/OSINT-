# Session Handoff — 2026-07-16 (Telangana/DIPR go-live · sandbox · summary defects)

> Paste the prompt at the bottom into a new chat. This is the single current source of truth for this workstream. **Verify live state before acting on any claim here.**

---

## 0. TL;DR — state right now

- **⏰ HARD DEADLINE: DIPR Telangana goes live Monday 2026-07-20.** VeriDeck's delivery lead flies to Hyderabad on the 19th. **Today + tomorrow are the window.** Robin is the press half of what DIPR receives.
- **✅ Ingestion incident RESOLVED** (see §3). Ingestion + extraction restored.
- **🎉 BIG FINDING (supersedes the old plan): Defect A needs NO GPU backfill.** English summaries **already exist** in `summary_executive` / `summary_preview`; the v1 API just serves the **wrong column**. Fix = a ~1-line projection change. See §4.
- **Client's #1 question (backfill) is ANSWERED and proven: history is automatic**, no job needed. See §5.
- **Two fixes still UNSHIPPED and both should land before Monday:** (1) the summary repoint, (2) the HTML strip (208,486 dirty rows). **Nothing is running; nothing is committed.**
- **Sandbox key issued + fully tested, still NOT delivered** to VeriDeck.

---

## 1. Access / environment

- **Repo:** `C:\Users\Dell\Desktop\rig-surveillance` (read its `CLAUDE.md`). **KB:** `C:\Users\Dell\Desktop\rig-knowledge-base\` (`01-rig-surveillance-backend/`, `02-osint-desk/`) — read-first per global CLAUDE.md.
- **Box:** `ssh -i ~/.ssh/rig_hetzner root@178.104.145.135` (Hetzner CPX42). Old `178.105.63.154` RETIRED.
- **DB:** `docker exec -i rig-postgres psql -U rig -d rig` (db `rig`; schemas `public`, `analytics`).
- **Containers:** `rig-postgres`; `rig-backend` (FastAPI + ALL celery workers + Beat; host code `/root/rig` → `/app/backend`); `osint-backend` (**the v1 partner API**, code `/app`, source `products/osint/`); `rig-frontend`; `rig-searxng`; `rig-freshrss`.
- **v1 API:** `https://api.rig360media.com/v1/*`. `/v1/admin/*` = super-admin JWT, 404-blocked publicly (mint keys from the box).
- **⚠️ SSH drops mid-script** — the box is draining a ~1M-row `topic_category` backlog. **Run ONE small query per SSH call**; heavy writes must be **batched + detached** (`nohup … &`), or they orphan (see §3 lesson).
- **Self-match gotcha:** a `pg_stat_activity` query whose own text contains e.g. `lead_text_original` will match itself → always add `pid<>pg_backend_pid()`.

---

## 2. Client: VeriDeck / DIPR Telangana

**VeriDeck** = integrator; **one org per end-client** (DIPR is the first, more coming). One key per org; each org has own scope/quota/rate-limit/metering/webhooks.

**LIVE org "Telangana CM & Government"** — `31ad3fa9-25eb-4b3c-8a56-360696fc680a`, key `rig_live_ddk_0c`.
- **Scope is CLIENT-self-managed** (`can_manage=true`; they PATCH it themselves — never say "we set your scope").
- Scope now: 6 entities (Bharat Rashtra Samithi, K. Chandrashekar Rao, K. T. Rama Rao, Harish Rao, Revanth Reddy, Bhatti Vikramarka); region Telangana; keywords `kaleshwaram`, `Telangana issues`.
- **Rate limit 240/min** (per-key override). Platform default + sandbox = **120/min**. Their monthly quota = 1,000,000 (platform default is *uncapped*).
- Their usage: bulk-mirrors cuttings/articles/stories; **daily 05:03 IST brief pull** = hard dependency.

**SANDBOX org "Telangana CM & Government — Sandbox"** — `9f2c6527-f2ca-4479-b792-7e625d21f107`.
- Key `rig_test_YWCRko1PwepaeJoT_WGmVuS6PeOJMYtUwe8GY8HwUSY` (id `a8f6102a-09f5-43b7-82c5-2819c7270163`); `is_sandbox`, 120/min, quota 100000, `can_manage=true`. Raw key also at box `/root/verideck_sandbox_key.txt` (chmod 600; `shred -u` after delivery).
- Scope = **snapshot copy** of live (does NOT auto-track). **Verified restored to mirror live** after testing (6 entities, 2 keywords). **Live was never touched by any test.**
- **Fully tested: every endpoint 200**; IDOR→404, no/bad key→401, PATCH non-destructive, webhook create/delete clean.
- **NOT yet delivered.** Client has asked twice. Box is healthy now; only the summary/HTML defects argue for waiting.
- **Quirks to tell them:** `/v1/analytics/outlets` needs an entity **UUID** (name → 400); `/v1/geo/district/{id}` takes a **slug** (`hyderabad`).
- Pre-existing `TELANGANA-SANDBOX` (`71589824…`) is **RIG's own QA**, not VeriDeck's. Three Telangana orgs — don't conflate.

**Their latest email (unanswered) — 3 asks:**
1. **Backfill** when they expand scope tonight — *answered in §5: none needed.*
2. **Confirm the PATCH landed cleanly** tonight — *we should do a per-term verification (§5).*
3. **Weekend watch** on their org — Pranav's staffing call; can be automated.
4. Standing: **the sandbox key**.

---

## 3. ✅ Incident (RESOLVED — historical, keep for lessons)

The 13h topic-relabel `UPDATE` (pid 2373332) was terminated; ingestion + extraction fully restored (swap 88%→25%, 0 blocked backends). KB: `01-rig-surveillance-backend/issues.md#I-20`.
- Ingestion had actually been stalled **~12h** (since 21:14 UTC), not ~3.3h — the "3h" was an artifact of one 06:00-UTC blip making `max(collected_at)` look fresh.
- **Root cause was NOT an external cron** but `topic_fill_task._rollup()`'s **unbatched whole-table UPDATE re-fired by Beat** (a `FINE_TO_COARSE` mapping change made ~96% of rows mismatch).
- **Fixed:** `_rollup()` rewritten batched + `FOR UPDATE SKIP LOCKED`; plus a PK-index fix in `enrich_journalist` (`id::text` → `CAST(:id AS uuid)`). Both **deployed live + mirrored to the repo (uncommitted)**. The batched rollup is draining the ~1M backlog non-blocking.
- **Mechanism worth remembering:** collectors upsert (`INSERT … ON CONFLICT (url_hash) DO UPDATE`); a long uncommitted UPDATE row-locks `articles` → upserts block → single-concurrency collector worker wedges → ingestion stops. **Never run an unbatched whole-table UPDATE on `articles`.**
- **Lesson:** a killed SSH leaves the server-side statement alive if it's blocked on a lock (zombie). Always `pid<>pg_backend_pid()` when hunting them, and run long writes detached.

---

## 4. The summary defects (v1 `summary` fields) — **plan CHANGED, read carefully**

v1 projections live in `products/osint/backend/v1/queries.py` (~lines **411, 464, 850**) — container path `/app/v1/queries.py`:
```
summary          = COALESCE(NULLIF(lead_text_translated,''), NULLIF(lead_text_original,''))   <-- WRONG COLUMN
summary_original = lead_text_original                                                          <-- raw HTML
full_text        = COALESCE(full_text_translated, full_text_scraped)                           <-- correct
full_text_original = full_text_scraped                                                         <-- correct
```

### Defect A — the "English" `summary` isn't English → **FIX IS TRIVIAL (no GPU!)**
**Discovery (2026-07-16, verified):** Mission Control shows an English "EXECUTIVE SUMMARY" for non-English articles because it reads **`summary_executive`** — a column the v1 API never touches. The English text **already exists**.

Non-EN articles, last 30d = **423,241**:
| column | populated | actually English (ascii) |
|---|---|---|
| `summary_preview` | 296,692 | **270,506 (64%)** |
| `summary_executive` | 296,739 | 218,961 (52%) |
| `lead_text_translated` (**served today**) | — | **~32%** |
| `full_text_translated` | 113,433 | — |

Spot-verified genuine English prose (te→"Minister targets Atmakur land mafia"; hi→"India's most beautiful rail routes"). `summary_preview` = short one-liner; `summary_executive` = full paragraph (better for the "EN ≤400" contract).

**→ THE FIX:** repoint the `summary` projection (3 spots) to prefer the English summary columns:
```
summary = COALESCE(English summary_executive, English summary_preview,
                   NULLIF(lead_text_translated,''), NULLIF(lead_text_original,''))
```
English coverage **~32% → ~65–70% instantly**. **No GPU, no translation backfill, no `lead_text_en` migration, no re-embed, no clustering risk.** Only needs an `osint-backend` restart; reversible.

**❌ SUPERSEDED — do NOT do these** (the old plan, now unnecessary): the `lead_text_en` column migration, and the Trijya GPU translation backfill of ~200k rows. Only the residual ~30% with *no* English summary at all would ever need translation — a tail, not a mountain.

**Still-true background:** two writers race on `lead_text_translated` — `backend/tasks/nlp_processor.py:269/360-384` writes real English, but `backend/tasks/substrate/run_corpus_pass.py:1069-1071` overwrites it with **native** trafilatura body (`LEFT(:body,2000)`). This session's PR `substrate-lead-fallback` (commit `7faf5cf`, pushed to `origin` `RIG-360-MEDIA/OSINT-`, **NOT merged**; `gh` not installed → open via compare URL) *widened* that by adding the `full_text_scraped` tier. **Optional cleanup:** reorder the COALESCE to prefer an existing `lead_text_translated` (fill only when empty). **Not urgent once the API is repointed**, and note `lead_text_translated` must keep receiving *some* text because it is the **LaBSE embed input** (`backend/nlp/embedding_recipe.py`, locked v4; `embed_fill_task.py`) — **never overwrite it with English or you force a full re-embed + re-cluster.**

### Defect B — `summary_original` is raw HTML → **backfill still TODO**
`lead_text_original` carries `<img>/<figure>/<a>`. **208,486 dirty rows** (`WHERE lead_text_original ~ '<[a-zA-Z/]'`). **STATUS: NOT run** (verified: `real_running_backfills=0`, backup table ABSENT, count unchanged). The earlier attempt was rolled back behind the incident.
- **Forward sites:** `backend/collectors/rss_collector.py:340/355/488` (dominant — raw RSS `<description>`), `direct_rss_collector.py:374`, `html_collector.py:297`. Add `backend/collectors/text_clean.py::strip_html_lead()` (html.unescape → strip comments/tags/script → drop WordPress "The post … appeared first on …" → collapse ws → None if empty) and call it **BEFORE** the `LEAD_TEXT_MAX_CHARS` slice (else truncation cuts a tag).
- **Naive `<[^>]+>` misses:** HTML entities (22.8k rows), tags truncated at the slice, comments containing `>`, WP boilerplate.
- **Backfill cleaner (previewed good on real rows):** strip comments → strip tags→space → decode `&nbsp; &#160; &amp; &quot; &#39; &#8230;` → catch-all `&#?[a-zA-Z0-9]+;`→space → drop WP footer → collapse `\s+` → `NULLIF(btrim(...),'')`. Then a 2nd pass: rows emptied (~1.6k; ~80% recoverable) ← `left(clean(full_text_scraped),300)`; ~312 stay NULL.
- **RUN IT BATCHED + DETACHED** with a backup table (`analytics.lead_orig_html_backup_20260716`). A single 208k-row UPDATE + full-scan backup is what stalled last time.

---

## 5. Scope & backfill mechanics (client's #1 — ANSWERED, proven)

**No backfill job is needed. History is automatic.** We collect + store the corpus **broadly** (articles + newspapers are store-everything); **scope is only a FILTER**, not a collection instruction.
- **Entities** are pre-tagged at ingest → filter is `EXISTS (SELECT 1 FROM article_entity_mentions aem … aem.entity_id = ANY(:eids))`.
- **Keywords** are matched **at query time** via `lower(coalesce(title,'')) LIKE ANY(:pats) OR lower(coalesce(lead_text_translated, lead_text_original,'')) LIKE ANY(:pats)`.

**Proven empirically 2026-07-16** (added a brand-new entity + keyword to the sandbox, then measured):
| newly added | Apr | May | Jun | Jul |
|---|---|---|---|---|
| entity "Asaduddin Owaisi" (mentions already tagged) | 5 | 31 | 104 | 63 |
| keyword "musi" (already in title/lead) | 220 | 1,709 | 9,178 | 4,813 |

**Caveats that matter for their expansion:**
1. **Unknown entity name → SILENT keyword fallback.** `PATCH /v1/scope` resolves names via `resolve_entity_by_name` (entity_dictionary canonical_name or `entity_lookup` alias); **unresolved names do NOT error — they're silently kept as keywords** (`name_fallback_keywords` in `/app/v1/endpoints/scope.py`). You still get text matches but **no entity-level sentiment/outlet analytics**. → This is exactly the "half-applies silently" risk; verify after they PATCH.
2. **Keywords match title + lead ONLY (not full body), and are SUBSTRING** ("musi" also matches "music"). Prefer distinctive terms.
3. **🔴 Language — biggest lever on DIPR looking full vs thin.** Much Telangana press is **Telugu**; for those rows the matched lead is **Telugu script**. An **English keyword will NOT match a Telugu article** ("irrigation" ≠ "నీటిపారుదల"). Names often appear in Latin script inside Telugu text (so those match) — ordinary words fail. **Ask for their term list and supply native-script variants.**
4. **PATCH semantics** are additive: `add_entities / remove_entities / add_keywords / remove_keywords / add_regions / add_topics / add_mute_terms` (`remove_entities` needs **UUIDs**; only `add_entities` resolves names). `languages` is replace-when-provided. Keywords are lowercased.

**Entity dictionary — "do we have a system if it's not in our dict?" → YES, but it's ours to run:**
- **No auto-discovery.** Only writers: `backend/routers/admin_router.py:45` (admin endpoint) + `scripts/seeds/seed_entity_dictionary.py` / `scripts/_seed_tridel_entities.sql`. Growth has flatlined: Apr 9,775 → May 7,257 → Jun 2,324 → **Jul 29**.
- **Retro-tagging demonstrably works:** entities added 2026-06-03 carry mentions on **older** articles (Fiji added 06-03 → oldest tagged 05-11; Maldives → 04-19; Malta → 04-22). So if VeriDeck names an entity we lack, **we add it + retro-tag → that IS the "controlled backfill" they asked about.**
- `article_entity_mentions` has **NO FK** to `entity_dictionary`.

---

## 6. Trijya GPUs (now only relevant for the residual translation tail)

- Configured Ollama pool is **DOWN**: `/root/rig/infrastructure/.env` `OLLAMA_ENDPOINTS` points at `172.30.0.1:11434/11435` fed by an autossh tunnel to **offline** nodes (`100.96.25.59`, `100.105.228.103`). `LMSTUDIO_BASE_URL` empty.
- **Live + translation-tested, reachable directly over Tailscale from the box:** `http://100.72.225.89:11434` (**qwen2.5:14b** + 7b, ~430ms warm) and `http://100.95.0.11:11434` (7b, ~540ms). To use: repoint `OLLAMA_ENDPOINTS` + restart, or call directly. No need to revive the dead Windows nodes.

---

## 7. Docs / memory already updated

- KB `02-osint-desk/subsystems/`: `v1-api-gateway.md`, `client-telangana-cm.md` (sandbox org/key, quirks).
- KB `01-rig-surveillance-backend/`: `issues.md` (**I-19** substrate lead defect, **I-20** the ingestion incident), `subsystems/nlp-substrate-pipeline.md`.
- Memory: `project_telangana_cm_api_client.md`, `MEMORY.md`.
- **Not yet documented:** the §4 discovery (English summaries exist in `summary_executive`/`summary_preview`) and the §5 scope/backfill proof. **Worth adding to the KB.**

---

## 8. Pending actions (priority order — Monday is the clock)

1. **Repoint the v1 `summary` projection** (§4) → English coverage 32%→~65–70%. Cheapest, biggest win. Verify live with the sandbox key; restart `osint-backend`.
2. **Run the HTML strip backfill** (§4 Defect B) — batched + detached + backup. Plus the `text_clean.py` forward fix in the 3 collectors.
3. **Reply to VeriDeck** (§2/§5): backfill not needed (proven); we'll add+retro-tag any entity we lack; warn about English-vs-Telugu keywords and offer to vet their list; confirm-the-PATCH offer; weekend watch (Pranav's call).
4. **Deliver the sandbox key** (`/root/verideck_sandbox_key.txt`, then `shred -u`).
5. **Tonight:** when they PATCH, verify **per term** — every intended entity resolved to an entity_id (not silently a keyword) **and** each term returns non-zero coverage.
6. Optional: substrate anti-clobber COALESCE; commit the live-but-uncommitted `_rollup()` + `enrich_journalist` fixes; open/merge PR `substrate-lead-fallback` (`https://github.com/RIG-360-MEDIA/OSINT-/compare/main...substrate-lead-fallback?expand=1`).

## 9. Guardrails
Live client-facing prod DB with a Monday go-live. Confirm before destructive/outward actions; don't kill jobs that aren't ours without asking; batch + detach heavy writes; keep raw keys out of chat; one small query per SSH call; **trust-but-verify every claim in this doc against live state.**
