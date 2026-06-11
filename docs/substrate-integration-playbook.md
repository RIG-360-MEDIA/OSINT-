# Substrate-parity pillar integration — process & playbook

> Written after taking the **newspaper clippings** pillar to article-substrate
> parity (2026-06-10, branch `feat/newspaper-hybrid-extraction`, commit
> `b45ec0f`). This is the **reusable template** for the next pillar to migrate —
> **YouTube clips** is up next. Follow the phases in order; the "Learnings &
> gotchas" section is the part that will save you a day.

---

## 0. The mental model (why this works at all)

Every pillar has a **different front half** (how content is acquired) but should
share **one enrichment spine** (how content becomes structured intel). The whole
integration is the act of bolting a new front half onto that shared spine.

| Pillar | Front half (pillar-specific) | Body becomes… |
|---|---|---|
| Articles | RSS/HTML scrape → clean HTML | `full_text_scraped` |
| **Clippings** | Vision segment + OCR-grounded crop | OCR-in-box body |
| **YouTube (next)** | transcript fetch + time-anchored chunks | transcript span |

The spine is **identical** for all three:
> ONE structured-JSON LLM call (same output schema) → child tables
> (claims/quotes/stances/locations/events/numbers) → entity_lookup matview →
> topic_fine + LaBSE embedding → `content_items` union view.

**Core principle: adapt the prompt, keep the schema.** A pillar gets its OWN
system prompt (tuned to its input quirks) but emits the **byte-identical output
object** as the article substrate. That single discipline is what gives you
analytics parity, shared entity graph, shared embedding space, and one unified
read surface — for free.

---

## 1. The phases (in order)

This is the exact order that worked. Each phase has a hard gate before the next.

### Phase A — Recon (read before you write)
Map what already exists so you mirror, not reinvent:
- **The article substrate** (`backend/tasks/substrate/run_corpus_pass.py`):
  `GROQ_SYS` prompt, the `_persist_*` helpers, the output schema, the
  `FOR UPDATE SKIP LOCKED` drain, the 2-attempt retry + robust JSON parse.
- **The child-table column shapes** — DO NOT trust the migration files; the base
  `article_stances/locations/events/numbers` tables were created OUTSIDE the
  numbered migrations. **Query the live DB** for authoritative columns:
  ```sql
  SELECT table_name, string_agg(column_name||' '||data_type, ', ' ORDER BY ordinal_position)
  FROM information_schema.columns
  WHERE table_name IN ('article_stances','article_locations','article_events','article_numbers')
  GROUP BY table_name;
  ```
- **The entity matview** (`082_article_entity_mentions_view.sql`) — copy its
  shape exactly.
- **The LLM pool** (`backend/nlp/groq_client.py`): `call_groq`, `FAST_MODEL`,
  `TOKEN_LIMITS`, local-primary-when-up failover.
- **celery_app.py**: the `include` list, `task_routes`, `beat_schedule`, and any
  on-boot catch-up handlers.
- **The live table** vs ghosts — there were TWO clipping tables (`clippings` from
  105 = live, `newspaper_clippings` from 005 = old/empty). Confirm which one the
  ingest task actually writes to before extending anything.

### Phase B — The prompt (test it in isolation FIRST)
- Write the pillar prompt as a standalone module
  (`backend/nlp/newspaper_prompt.py` → for yt, `youtube_prompt.py`). Constants:
  `GROQ_SYS_<PILLAR>` + `_NON_ENGLISH`, `prompt_for_language()`, `body_cap()`,
  `sanitize_extraction()`, `TASK_TYPE`.
- **Add the task_type to `TOKEN_LIMITS`** in groq_client.py (clippings used
  `clipping_extraction: 3500`).
- Write a **field-by-field quality test** (`scripts/test_<pillar>_prompt.py`)
  with realistic fixtures per language (en + 2-3 Indic). Score every DB field
  group: schema keys, enum validity, length caps, location 5-field rule, ₹/number
  extraction, grounding, translation presence. Clippings hit **122/122** before
  any DB work began.
- **GATE: do not touch the DB until the prompt scores ~100%.** A bad prompt
  found here is a 2-minute fix; found after wiring, it's a day of confusion.

### Phase C — Migration (ADD-only, idempotent)
- New numbered migration (`107_clippings_substrate.sql`). Rules:
  - **ADD-only.** Never `ALTER` articles/article_* or any shared substrate table.
  - Extend the pillar table with extraction + provenance + enrichment columns +
    substrate lifecycle (`substrate_status`, `extraction_version`).
  - Create `<pillar>_claims/quotes/stances/locations/events/numbers` mirroring
    the live article column types (FK → pillar table, ON DELETE CASCADE).
  - Create `<pillar>_entity_mentions` matview — a SEPARATE matview, so the
    article matviews / CM metrics / district rollups stay article-only.
  - Extend (or create) the `content_items` union view with the new `src`.
  - HNSW index on the embedding column; a partial index on
    `substrate_status='pending'` for the drain.
- **Verify column existence before writing the union view.** `articles` has NO
  on-row `relevance_score` (it scores per-user) — the view used
  `NULL::double precision AS relevance_score` on the article side. Check every
  column you reference in a cross-table view or it fails at `CREATE VIEW`.

### Phase D — Enrichment drain (mirror the substrate, don't invent)
- `backend/tasks/<pillar>_enrich.py`. Copy the substrate pattern verbatim:
  - Atomic claim: `UPDATE … SET substrate_status='processing' WHERE id=(SELECT …
    FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING id`.
  - 2-attempt retry + robust JSON parse (strip fences, isolate outer `{}`).
  - `sanitize_extraction` → `_persist_*` child writers (copy the article ones,
    swap the FK column).
  - `classify_topic_fine` + `coarse_from_fine`; `generate_embedding` (LaBSE).
  - Lifecycle: `ok | extract_failed | junk`, `extraction_version=3`.
  - Two entry points: `enrich_<pillar>(id)` (enqueued per-row at insert) +
    `drain_pending_<pillar>(limit)` (periodic catch-up safety net).

### Phase E — Ingest wiring (fan-out + enqueue)
- Update the collection task: per-item fan-out (`<collect_one>.delay(id)`), swap
  to the new extractor, filter junk (notices/dupes), extend the INSERT with the
  new fields, set `substrate_status='pending'`, enqueue enrich per new row.

### Phase F — Celery registration
- Add the new modules to `include`.
- Add `task_routes` → the **documents** queue (NOT `nlp` — that's article NLP;
  sharing it steals article throughput). Clippings put BOTH collection and
  enrichment on `documents`.
- Add beat entries. Clippings: two idempotent passes (primary + fallback that
  only fires items missing today) + a periodic pending-drain. Reuse the existing
  beat dict — **never start a second Beat** (double-fire footgun per CLAUDE.md).
- Fix any stale on-boot catch-up handlers (ours queried the wrong/empty table).

### Phase G — Verify locally, then deploy durably
1. `python -m py_compile` every new/changed file.
2. Apply migration on Hetzner postgres; verify structure + the union view counts.
3. **Smoke test the full path** with synthetic rows (`scripts/smoke_*.py`):
   insert → enrich inline → assert child tables populated + matview resolves +
   `content_items` shows the rows → clean up.
4. Build durably (see Phase H).
5. Re-run the smoke test against the BAKED image (no docker cp) to prove
   durability.

### Phase H — The durable build (the dangerous part — read §3)
- `git archive HEAD <paths> | ssh … tar -x -C /root/rig` to land the *committed*
  files into the Hetzner build context (clean, no CRLF surprises).
- `docker compose build <service>` → recreate → verify.

---

## 2. The artifacts (what the clippings integration produced)

| File | Role |
|---|---|
| `backend/nlp/newspaper_prompt.py` | pillar prompt + sanitize + lang routing |
| `backend/tasks/clipping_enrich.py` | substrate drain + child-table writers |
| `backend/tasks/newspaper_task.py` | ingest fan-out + extended INSERT + enqueue |
| `scripts/migrations/107_clippings_substrate.sql` | ADD-only schema + matview + view |
| `backend/nlp/groq_client.py` | +`clipping_extraction` in `TOKEN_LIMITS` |
| `backend/celery_app.py` | include + routes + beat + catch-up fix |
| `infrastructure/Dockerfile.backend` | bakes tesseract + tessdata (pillar dep) |
| `scripts/test_newspaper_prompt.py` | field-by-field prompt quality harness |
| `scripts/smoke_clipping_enrich.py` | end-to-end enrich smoke test |
| `docs/newspaper-clippings-design.md` | the design doc |

---

## 3. Learnings & gotchas (the expensive lessons)

### 3.1 The Hetzner Dockerfile lag — the near-regression
**The repo on Hetzner `/root/rig` is on `main`, and its Dockerfile was STALE** —
the tesseract/tessdata baking from a prior local session had never been synced
there. A naive `docker compose build` would have built **without tesseract and
without the new code**, silently stripping OCR from production.
- **Lesson:** the live container often works only because of hand-installed
  state (`docker cp` + apt + pip inside the running container). That state is
  **ephemeral** — any container recreation wipes it. Before ANY rebuild, diff the
  Hetzner build context against what's actually running:
  ```bash
  ssh … "cd /root/rig && git branch --show-current && grep -c tesseract infrastructure/Dockerfile.backend"
  ```
- **Lesson:** sync the *committed* files into the build context first
  (`git archive | tar`), back up overwritten shared files
  (`/root/rig_backup_clipping/`), THEN build.

### 3.2 Code is baked, not bind-mounted
`rig-backend` COPYs `backend/` + `scripts/` at build time. Editing host files or
`docker cp`-ing into the container is a **temporary** patch for testing — it does
NOT survive recreation. Durability = Dockerfile + rebuild. (CLAUDE.md foot-gun #2.)

### 3.3 Don't trust migration files for base schema
The base `article_*` child tables were created outside the numbered migrations
(probably an early `init` or by an ORM). Grepping `scripts/migrations` for
`CREATE TABLE article_stances` returns nothing. **The live DB is the source of
truth** for column names/types — query `information_schema.columns`.

### 3.4 Two tables with confusingly-similar names
`clippings` (105, live) vs `newspaper_clippings` (005, old/empty). The on-boot
catch-up handler was even querying the WRONG one. Always confirm which table the
ingest path actually writes to.

### 3.5 Cross-table union views break on missing columns
`content_items` UNION-ALLs articles + clippings. `articles` has no
`relevance_score` column (scored per-user elsewhere) → the view had to emit
`NULL::double precision AS relevance_score` on that side. Verify every referenced
column exists, per side, before `CREATE VIEW`.

### 3.6 LLMs can't count characters
The prompt asks for `preview<=50ch / snippet<=200ch`, but the model overshoots by
2-10 chars ~half the time. **Don't fight it in the prompt** — truncate
server-side in `sanitize_extraction()` after the call. This single fix took the
prompt test from 96% → 100%.

### 3.7 Shared LLM quota is real
Both pillars draw from the same Groq/Cerebras key budget. During testing, Groq
TPD (tokens-per-day) was exhausted across all 21 keys; the pool sat in 900s
cooldowns. Two consequences:
- **Give test harness calls a hard `asyncio.wait_for` timeout** (we used 120s) so
  a saturated pool fails fast instead of hanging on cooldowns.
- **Route enrichment to its own queue at bounded concurrency** so the morning
  burst doesn't starve article NLP when the local GPU is down and everything
  falls back to cloud.

### 3.8 Local-primary "free" is conditional
Enrichment is GPU-bound and ~free **only while the 4090 (Ollama/Trijya via
Tailscale) is reachable**. When it's down, the pool fails over to Groq+Cerebras
and competes with article NLP for shared cloud quota. The bounded-concurrency
queue is the safeguard for that window — not redundant.

### 3.9 Vision is always cloud
Page segmentation (Groq Scout vision) has no local/Cerebras equivalent — it's
Groq-only, one call per page, a steady cloud load regardless of GPU state. Pace
it via the extractor's per-page concurrency cap. (yt has the analog: transcript
*fetch* must go through the relay/throttle, never raw — see the IP-reputation
memory.)

### 3.10 PowerShell vs bash quoting on Windows
The harness has both shells. `@'...'@` here-strings are PowerShell-only; running
them under the Bash tool breaks on apostrophes (e.g. "OCR'd"). For multi-line
commit messages, **write to a file and `git commit -F`**. Nested PowerShell
`ForEach-Object { $_ }` also gets mangled when wrapped through bash — use the
Grep/Read tools or a clean sandbox shell instead.

### 3.11 Verify against the baked image, not the patched container
The only honest proof of durability is re-running the smoke test after a clean
rebuild + recreate, with NO `docker cp` in between. If it passes there, it'll
survive the next restart.

---

## 4. YouTube clips — the next migration (concrete checklist)

The YouTube design already exists (`docs/sessions/youtube-clips-pipeline-design.md`)
and reaches the same conclusions. Apply this playbook:

- [ ] **Recon:** confirm the live table (`youtube_clips_v2`, migration 106) and
      its current columns; query live DB for the article child-table shapes.
- [ ] **Prompt:** `backend/nlp/youtube_prompt.py` — `GROQ_SYS_YOUTUBE` (+
      non-English). Transcript-tuned: read through ASR errors, no fetchable
      source, time-anchor phrases. **Reuse the existing `transcript_analysis`
      task_type** (already in `TOKEN_LIMITS` at 1500 — bump if the full substrate
      schema needs more). Add `start_phrase`/`end_phrase` for timestamp anchoring.
- [ ] **Prompt test:** `scripts/test_youtube_prompt.py`, fixtures per language,
      gate at ~100% before DB work.
- [ ] **Migration `108_youtube_substrate.sql`** (ADD-only): extend
      `youtube_clips_v2` + `youtube_clip_claims/quotes/stances/locations` +
      `youtube_clip_entity_mentions` matview + extend `content_items` with
      `src='clip'`. Keep `clip_start/end_seconds`, `embed_url`,
      `transcript_segment` on-row.
- [ ] **Enrich drain:** `backend/tasks/youtube_clip_enrich.py` — chunk transcript
      (≤150s/≤2200 chars), one call per chunk, anchor phrases → timestamps in
      Python, then the same persist + topic + LaBSE + lifecycle.
- [ ] **Ingest:** wire transcript drain → extraction drain (substrate lifecycle).
      Transcript fetch goes through `_youtube_throttle`/relay ONLY (IP reputation
      — never raw yt-dlp from a shell; see the memory).
- [ ] **Celery:** route to the **youtube** queue (its own worker, concurrency 1)
      — NOT nlp. Add the drain beat entries.
- [ ] **Verify:** py_compile → migration → smoke test (synthetic clip) → build →
      re-verify on baked image.
- [ ] **Watch the shared quota:** the clippings morning burst (02:00–03:00 UTC)
      and yt drains both hit the same cloud pool when the GPU is down. Stagger
      schedules / keep bounded concurrency.

**Reuse, don't re-derive:** `classify_topic_fine`, `coarse_from_fine`,
`generate_embedding`, the `_persist_*` shapes, the matview SQL, the
`content_items` view, and this playbook. The only genuinely new code is the
transcript-chunking + timestamp-anchoring front half.

---

## 5. One-paragraph summary

To migrate a pillar onto the substrate: read the article path, write a
pillar-tuned prompt that emits the identical schema, prove it field-by-field
before touching the DB, add an ADD-only migration with mirrored child tables + a
separate entity matview + the union view, copy the substrate drain verbatim
(swapping the FK), route everything to the pillar's own queue, then deploy by
syncing committed files into the Hetzner build context and rebuilding — never
trusting the live container's hand-installed state to survive. Verify on the
baked image. The schema converges; only the front half diverges.
