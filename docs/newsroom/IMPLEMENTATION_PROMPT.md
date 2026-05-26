# THE NEWSROOM — Implementation Prompt (zero-context briefing)

> Paste this entire document as the **first message** in a new chat. Do not
> abbreviate it. The receiving session must operate as if it has never seen
> this codebase before, and this brief is the only context it gets.

---

## 0. Who you are and what you're doing

You are a senior staff engineer + product designer joining the **RIG
Surveillance** project to build one feature end-to-end: a complete redesign of
the `/clips` page (currently a thin YouTube transcript browser) into a
cinematic multi-mode TV/YouTube intelligence interface called **THE NEWSROOM**.

You will design it, build the backend pipeline, ship the schema, and render
the frontend — solo, in phases, with verification at every gate.

This is not exploratory work. The product, the visual system, and the tech
stack are already decided. Your job is to **execute**, not redesign. Where
this brief is silent, you may make taste calls; where it is explicit, do not
deviate.

---

## 1. Project facts you must internalise before writing code

### Repository layout

- Backend: `backend/` — FastAPI app (`backend/main.py`), Celery workers,
  routers under `backend/routers/`, tasks under `backend/tasks/`, NLP under
  `backend/nlp/`, collectors under `backend/collectors/`.
- Frontend: `frontend/` — Next.js 15 app, pages under `frontend/src/app/`,
  components under `frontend/src/components/`.
- Migrations: `scripts/migrations/NNN_name.sql` — numbered, idempotent,
  applied in order at first DB boot.
- Infrastructure: `infrastructure/docker-compose.yml`,
  `infrastructure/Dockerfile.backend`, `start.sh`.
- Docs: `docs/` — `qa/`, `newsroom/` (you will write to this).

### Deployment topology — read carefully, this trips people up

Production runs in **5 containers**, not the multi-worker compose pattern most
projects use:

| Container | What runs |
|---|---|
| `rig-postgres`  | Postgres 16 + pgvector |
| `rig-backend`   | **FastAPI uvicorn + ALL Celery workers + Beat** (single image, all forked from `/start.sh`) |
| `rig-frontend`  | Next.js dev server |
| `rig-searxng`   | Web-search proxy |
| `rig-freshrss`  | RSS reader (data source) |

There is no separate `rig-celery-worker-*` service. Anyone reading the compose
file in isolation will conclude "no workers run" and be wrong. Workers live
inside `rig-backend` and are started by `/start.sh`.

**Existing queues** (do not duplicate, do not split): `collectors`, `social`,
`youtube`, `documents`, `nlp`, `relevance`, `brief`. You will add **one** new
queue: `whisper`.

### Source-of-truth files

When uncertain, these are authoritative:

- `infrastructure/Dockerfile.backend` + `/start.sh` (running inside container) — actual worker topology.
- `backend/celery_app.py` `task_routes` — task → queue mapping.
- `scripts/migrations/*.sql` — schema.
- `frontend/src/app/<page>/page.tsx` — frontend pages.
- `CLAUDE.md` at repo root — supplementary project notes.

### Stack you must respect

- Python 3.11, FastAPI, Celery (**Postgres broker** via `sqla+postgresql` — there is no Redis in this stack), SQLAlchemy 2.x async, asyncpg, Postgres 16 + pgvector.
- Next.js 15 (App Router), React 18, TypeScript strict, Vitest unit, Playwright e2e.
- Auth: Supabase (frontend) + JWT verification (backend).
- LLM: Groq (primary, rate-limited) + **Cerebras** (failover, separate quota) — both free-tier.
- Existing helpers: `backend/nlp/groq_client.py` already implements the
  Groq-then-Cerebras failover. Reuse it; do not reinvent.

### Design system — already shipped

The "Onyx" aesthetic is established. The palette is **strictly three colours**:
black, red (`--onyx-red: #FF2D2D`), white/bone. No cyan, no green, no blue
accents. CSS tokens live in `frontend/src/app/globals.css` (`--onyx-bg`,
`--onyx-bg-2`, `--onyx-bone`, `--onyx-bone-2`, `--onyx-dim`, `--onyx-red`,
`--onyx-red-soft`, `--onyx-red-hair`, `--onyx-display`, `--onyx-mono`,
`--onyx-italic`).

Reusable atmosphere primitives: `ParticleField`, `GrainOverlay`, keyframes
`onyx-scanline`, `onyx-marquee`, `onyx-pulse-cyan` (now red), `onyx-fade-up`,
`onyx-drift-glow`, `onyx-flicker-text`, `onyx-hud-pulse`. Reuse them.

A working visual reference of WALL mode exists at
`docs/newsroom/wall-mode.html` — open it in a browser **before writing any
frontend code**. The actual `/clips` redesign should match its rhythm,
typography, and motion vocabulary.

---

## 2. The product — THE NEWSROOM

### What it replaces

The current `/clips` page is a YouTube transcript browser with basic search.
It is functional but not sensory and surfaces ~10% of the data already in the
database. You are replacing it. The old route stays at `/clips`; do **not**
add a new top-level route.

### Five modes (a single page, switched via top tab strip)

1. **WALL** — landing mode. 3×3 grid of live channel tiles, each rendering
   a live caption ticker (transcript-as-it-speaks), HUD-corner brackets,
   `LIVE` chip, audio waveform. BREAKING tiles glow red. Top status bar
   shows live count, breaking count, your beat. Atmosphere: drift-glow,
   scanlines, grain, cursor red-dot trail.
2. **STREAM** — chronological transcript feed across all channels. Caption
   chunks land top-of-page newest-first, with channel + timestamp + entity
   chips. Pause/resume control. Filter by entity, beat, language.
3. **ECHO** — "What they're saying about you / your entities". Pulls every
   quote in the last N hours mentioning watched entities. Speaker
   attribution, channel tag, cross-channel carry-count, sentiment chip.
4. **DOSSIER** — entity-centric. Mention deltas (24h vs prior 24h),
   sentiment trend, top quotes, top channels carrying, related entities.
5. **BRIEF** — daily digest. Generated 06:00 IST. 5–7 anchored stories
   pulled from the day's broadcasts, each with: headline, 2-paragraph
   summary, 2–3 source clips, optional audio narration (TTS, deferred —
   ship text-only first).

### The 14 features (mapped to modes)

1. Live multi-channel wall — **WALL**
2. Real-time transcript ticker — **WALL** + **STREAM**
3. Cross-channel breaking detection — **WALL** flag + **STREAM** highlight
4. Quote extraction with speaker attribution — **ECHO**
5. Multi-language transcript (Telugu / Hindi / English) — pipeline-level
6. Speaker diarisation — pipeline-level
7. Phonetic entity snapping (Soundex/Metaphone) — pipeline-level
8. Live channel monitoring (`yt-dlp --live`) — pipeline-level
9. Sentiment + framing analysis per quote — **ECHO** + **DOSSIER**
10. "What they're saying about you" — **ECHO**
11. Daily Dossier — **DOSSIER**
12. Daily Brief — **BRIEF**
13. Cross-state coverage tracking (AP / KA / TS spillover) — **DOSSIER**
14. Editorial-framing flag (anchor opinion vs reported speech) — **ECHO**

There is **no feature 15**. Do not add. Do not propose. If the user asks for
more during the build, write it down and finish what's planned first.

---

## 3. The transcript pipeline — 3-Lens Consensus

This is the core technical innovation. **All three lenses are free.** No paid
services. Ever.

| Lens | Source | Cost | Quality |
|---|---|---|---|
| **L1** | YouTube auto-captions via `yt-dlp --write-auto-sub` | Free | Best for English, weak for Telugu |
| **L2** | Groq `distil-whisper-large-v3-en` for English; Groq `whisper-large-v3` for non-English | Free tier (rate-limited, use bucket from `groq_client.py`) | Strong all-round |
| **L3** | Self-hosted **AI4Bharat IndicConformer** on Hetzner CPU for Indic languages, **Faster-Whisper** small/medium for English | Free (CPU-bound) | Best Indic ASR available; slow |

**Reconciliation:** a Cerebras LLM call (free quota) takes the three lens
outputs as input and emits a single canonical transcript with confidence
scores per token. Prompt is structured: "Here are three transcripts of the
same audio. Output the most likely canonical version, preserving
proper-noun spelling. Mark low-confidence words with `~~`."

**Diarisation:** `pyannote.audio` (open-source, CPU-able) runs on the audio
to produce speaker-turn boundaries. Speaker labels are joined to transcript
tokens by timestamp.

**Phonetic snapping:** after reconciliation, run every token tagged as a
proper noun through Soundex + Metaphone against the watched-entities table.
If a phonetic match exists with edit distance ≤ 2, snap to canonical entity
name. ("Revant Reddi" → "Revanth Reddy").

### Where each lens runs

- L1: `whisper` queue, light task — just `yt-dlp` shellout.
- L2: `whisper` queue, calls Groq through `groq_client.py`.
- L3: `whisper` queue but **concurrency=1** (CPU-heavy) — runs Whisper /
  IndicConformer locally inside `rig-backend`.
- Reconciliation: `nlp` queue, calls Cerebras.

### Live monitoring

`yt-dlp --live-from-start --hls-prefer-native -o -` streams the live audio
chunk-by-chunk. A long-running task (run on `whisper` queue) consumes the
HLS feed in 30-second windows, writes each window to `/tmp`, fires L1+L2+L3
in parallel for that window, then reconciles and inserts a `segment` row.
For VOD (already-aired clips), same pipeline, just one-shot instead of
streaming.

---

## 4. Database — schema you will add

Do not invent extra tables. This is the complete set:

```sql
-- 051_newsroom_channels.sql
CREATE TABLE newsroom_channels (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name          text NOT NULL,                  -- "TV9 Telugu"
  yt_handle     text NOT NULL UNIQUE,           -- "@tv9telugulive"
  language      text NOT NULL,                  -- 'te','hi','en'
  beat          text NOT NULL,                  -- 'telangana_politics', etc.
  is_live_24x7  boolean NOT NULL DEFAULT false,
  active        boolean NOT NULL DEFAULT true,
  created_at    timestamptz NOT NULL DEFAULT now()
);

-- 052_newsroom_broadcasts.sql
CREATE TABLE newsroom_broadcasts (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  channel_id      uuid NOT NULL REFERENCES newsroom_channels(id) ON DELETE CASCADE,
  yt_video_id     text NOT NULL,
  title           text,
  title_en        text,                         -- inline translated
  started_at      timestamptz NOT NULL,
  ended_at        timestamptz,
  is_live         boolean NOT NULL DEFAULT false,
  duration_sec    integer,
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (channel_id, yt_video_id)
);

-- 053_newsroom_segments.sql
CREATE TABLE newsroom_segments (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  broadcast_id    uuid NOT NULL REFERENCES newsroom_broadcasts(id) ON DELETE CASCADE,
  start_sec       numeric(10,2) NOT NULL,
  end_sec         numeric(10,2) NOT NULL,
  speaker_label   text,                         -- 'SPEAKER_01' from pyannote, or canonical entity name after snapping
  speaker_entity_id uuid,                       -- FK once snapped
  text_native     text NOT NULL,                -- canonical transcript in source language
  text_en         text,                         -- English translation
  confidence      numeric(3,2),                 -- 0.00–1.00
  l1_text         text,                         -- raw L1 output for audit
  l2_text         text,
  l3_text         text,
  is_quote        boolean NOT NULL DEFAULT false,
  is_editorial    boolean NOT NULL DEFAULT false,  -- anchor opinion flag
  sentiment       numeric(3,2),                 -- -1..+1
  framing         text,                         -- 'adversarial','aligned','neutral'
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_segments_broadcast ON newsroom_segments(broadcast_id, start_sec);
CREATE INDEX idx_segments_entity ON newsroom_segments(speaker_entity_id);
CREATE INDEX idx_segments_recent ON newsroom_segments(created_at DESC);

-- 054_newsroom_entity_mentions.sql
CREATE TABLE newsroom_entity_mentions (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  segment_id      uuid NOT NULL REFERENCES newsroom_segments(id) ON DELETE CASCADE,
  entity_id       uuid NOT NULL,                -- references existing entities table
  span_start      integer,                      -- char offset in text_native
  span_end        integer,
  was_phonetic    boolean NOT NULL DEFAULT false,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_mentions_entity ON newsroom_entity_mentions(entity_id, created_at DESC);

-- 055_newsroom_breaking_clusters.sql
CREATE TABLE newsroom_breaking_clusters (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  headline        text NOT NULL,
  headline_en     text,
  first_seen_at   timestamptz NOT NULL,
  last_seen_at    timestamptz NOT NULL,
  channel_count   integer NOT NULL,
  segment_count   integer NOT NULL,
  is_real_event   boolean NOT NULL,
  severity        smallint NOT NULL,            -- 1..5
  created_at      timestamptz NOT NULL DEFAULT now()
);

-- 056_newsroom_breaking_segments.sql
CREATE TABLE newsroom_breaking_segments (
  cluster_id      uuid NOT NULL REFERENCES newsroom_breaking_clusters(id) ON DELETE CASCADE,
  segment_id      uuid NOT NULL REFERENCES newsroom_segments(id) ON DELETE CASCADE,
  PRIMARY KEY (cluster_id, segment_id)
);
```

Migrations are **numbered 051–056**, idempotent, applied automatically at
first boot. Do not write `DROP TABLE` in any migration. Do not modify any
migration once it has been applied to a real database — write a new one.

---

## 5. Phased build order — non-negotiable

You will ship in this order, verifying each phase to **the bible standard**
(see Section 6) before moving to the next.

### Phase 0 — `whisper` queue infrastructure

- Add `whisper` to `task_routes` in `backend/celery_app.py`.
- Add `worker-whisper` launch line to `/start.sh` (concurrency=1 for
  L3-heavy work; L1/L2 tasks share the queue but are cheap).
- `docker compose build rig-backend && docker compose up -d` and verify
  `docker exec rig-backend ps -ef | grep whisper`.

### Phase 1 — Schema migrations 051–056

- Write all six migrations.
- Apply by recreating Postgres or running `psql`.
- **Verify** with `\d newsroom_*` and a smoke `INSERT … RETURNING id`.

### Phase 2 — 3-Lens Consensus pipeline (VOD first)

Build VOD path before live. Pick one already-aired Telugu clip, hardcode
its yt video id, and produce a fully-reconciled `newsroom_segments` row
set end-to-end.

- `backend/tasks/newsroom/lens_l1_yt_captions.py`
- `backend/tasks/newsroom/lens_l2_groq_whisper.py`
- `backend/tasks/newsroom/lens_l3_local_asr.py` (IndicConformer + Faster-Whisper)
- `backend/tasks/newsroom/diarise.py` (pyannote)
- `backend/tasks/newsroom/reconcile.py` (Cerebras call)
- `backend/tasks/newsroom/phonetic_snap.py`
- `backend/tasks/newsroom/process_broadcast.py` — orchestrator
- `backend/nlp/cerebras_client.py` if not already present (reuse `groq_client.py`'s pattern)

### Phase 3 — Quote / sentiment / framing extraction

- `backend/tasks/newsroom/extract_quotes.py` — Cerebras call: "Given these
  segments and known speakers, return JSON of quotes with `is_quote`,
  `is_editorial`, `sentiment`, `framing` per segment."
- Update segments table accordingly.

### Phase 4 — Live channel monitor

- `backend/tasks/newsroom/live_monitor.py` — long-running task, one per
  active 24×7 channel, consumes HLS, fires Phase 2 pipeline per 30s window.
- Beat schedule: every 5 minutes, `enqueue_live_monitors` — checks which
  channels should be running and ensures one task per channel.
- **Channel dedup via Postgres advisory locks**, not Redis (there is no
  Redis in this stack). At task start: `SELECT pg_try_advisory_lock(hashtext('newsroom_live:' || channel_id))`.
  If it returns false, another worker already owns this channel — exit
  cleanly. Lock auto-releases when the worker's connection drops, so a
  killed worker frees its channels for the next beat tick. Hold the lock
  for the lifetime of the live-monitor task with a dedicated connection
  (do not return the conn to the pool while holding the lock).

### Phase 5 — Breaking detection

- `backend/tasks/newsroom/detect_breaking.py` — every 2 minutes, scan last
  20 minutes of segments, cluster by entity + topic similarity, flag
  clusters with ≥3 channels carrying as candidates, run quality gate
  (`is_real_event` boolean) via Cerebras.

### Phase 6 — Backend API

Routes in `backend/routers/newsroom_router.py`:

```
GET  /api/newsroom/channels                          — list active channels
GET  /api/newsroom/wall                              — current state of all live channels (latest 5 segments each)
GET  /api/newsroom/stream?cursor=&entity=&lang=      — paginated segment feed
GET  /api/newsroom/echo?entity_id=&hours=24          — quotes mentioning entity
GET  /api/newsroom/dossier?entity_id=&days=7         — entity dashboard
GET  /api/newsroom/brief?date=YYYY-MM-DD             — daily digest
GET  /api/newsroom/breaking                          — active breaking clusters
GET  /api/newsroom/segments/:id                      — one segment full detail (all 3 lenses for audit)
SSE  /api/newsroom/stream/live                       — server-sent stream of new segments (for tickers)
```

Auth: every route behind existing JWT middleware. No new auth surface.

### Phase 7 — Frontend `/clips` redesign

- New components under `frontend/src/components/newsroom/`:
  - `NewsroomLayout.tsx` (status bar + mode switcher + ticker)
  - `WallMode.tsx`
  - `StreamMode.tsx`
  - `EchoMode.tsx`
  - `DossierMode.tsx`
  - `BriefMode.tsx`
  - `LiveTile.tsx`, `CaptionTicker.tsx`, `QuoteCard.tsx`, `EntityChip.tsx`
- `frontend/src/app/clips/page.tsx` rewritten as the mode container.
- Match `docs/newsroom/wall-mode.html` for typography, rhythm, motion.
- Use SSE for live caption tickers (one EventSource for the page, fanned
  out client-side to tiles).
- Strict palette discipline. No new CSS variables.

### Phase 8 — Daily Brief

- `backend/tasks/newsroom/generate_daily_brief.py` — runs 06:00 IST,
  picks 5–7 anchored stories, writes a row to a new `newsroom_briefs`
  table (migration 057).
- Frontend renders. TTS audio narration is **deferred** — text only in v1.

---

## 6. THE BIBLE RULE — verification gates (read twice)

Verification is not optional. It is not a step at the end. It is a **gate
between every phase**. You may not start phase N+1 until phase N has passed
its gate. If you find yourself wanting to skip ahead "and verify it all at
the end" — stop. That impulse is the bug.

### What "verified" means at each phase

**Phase 0 — queue infrastructure**
- [ ] `docker exec rig-backend ps -ef | grep -E "celery.*whisper"` returns a process.
- [ ] `celery -A backend.celery_app inspect active_queues` lists `whisper`.
- [ ] A throwaway `add(2,3)` task routed to `whisper` returns 5.

**Phase 1 — schema**
- [ ] `\d newsroom_channels`, `\d newsroom_broadcasts`, etc. show every column with the right type.
- [ ] FK constraints exist (`\d+` shows them).
- [ ] One INSERT + one SELECT round-trips via asyncpg from inside `rig-backend`.
- [ ] No constraint or index name collides with existing tables.

**Phase 2 — 3-Lens pipeline (VOD)**
- [ ] Running `process_broadcast` on a known Telugu clip produces ≥10 segment rows.
- [ ] L1, L2, L3 raw text columns are all populated for ≥1 segment.
- [ ] `text_native` differs from each lens (i.e. reconciliation actually merged, not just copied L2).
- [ ] `text_en` is populated for non-English segments.
- [ ] Speaker labels exist. ≥1 segment has a non-null `speaker_entity_id` (phonetic snap fired).
- [ ] Confidence scores are in 0..1.
- [ ] **Manual content audit**: pick 3 random segments, listen to the actual audio at that timestamp, confirm the transcript is right. If wrong — fix before moving on. Do not paper over with a "good enough" claim.

**Phase 3 — quote extraction**
- [ ] At least one segment has `is_quote=true` and one has `is_editorial=true`.
- [ ] Sentiment values are in [-1, 1].
- [ ] Framing values come from the allowed enum.
- [ ] Re-run on the same broadcast is idempotent (no duplicate rows).

**Phase 4 — live monitor**
- [ ] Pick one channel known to be 24×7. Start a live monitor.
- [ ] Within 5 minutes, segments are landing in DB tagged `is_live=true`.
- [ ] No duplicate live monitors for the same channel — verify by enqueuing the task twice for the same channel and confirming the second one exits immediately (advisory lock works). Inspect with `SELECT * FROM pg_locks WHERE locktype='advisory'` to see the held lock.
- [ ] Killing the worker and restarting picks back up cleanly.

**Phase 5 — breaking detection**
- [ ] Manually inject 4 segments across 4 channels that all mention the same fictitious event in the last 20 min.
- [ ] Within 2 minutes a `newsroom_breaking_clusters` row appears with `is_real_event=true`.
- [ ] Inject 1 segment of generic chatter — no cluster appears (false-positive gate works).

**Phase 6 — API**
- [ ] Every route returns 200 for an authenticated request and 401/403 unauthenticated.
- [ ] Response shape matches a TypeScript interface defined in `frontend/src/types/newsroom.ts`.
- [ ] SSE stream emits a heartbeat every 15s and a real event when a new segment lands.
- [ ] Pagination works: cursor-based, no offset jumps, no row-skipping under live insert load.

**Phase 7 — frontend**
- [ ] Page builds with no TypeScript errors and no `any`.
- [ ] All 5 modes render with real data (not mock).
- [ ] Mode switch is keyboard-accessible (1–5 hotkeys).
- [ ] Live ticker updates within 2s of a new segment in DB.
- [ ] Computed CSS shows no cyan / green / blue colour anywhere on the page.
- [ ] Lighthouse perf ≥80 on a cold reload.
- [ ] Playwright e2e: launches /clips, asserts WALL renders, switches to ECHO, asserts a quote card.
- [ ] **Manual visual audit against `docs/newsroom/wall-mode.html`** — typography weights match, spacing rhythm matches, motion vocabulary matches.

**Phase 8 — daily brief**
- [ ] One brief row exists in DB after the scheduled run.
- [ ] Frontend renders the brief.
- [ ] Each brief story cites real source segment ids — clicking a citation opens that segment.

### Verification means *running the thing*

- "I wrote the code" is not verified.
- "Type-check passes" is not verified.
- "Tests pass" is not verified unless the tests cover the actual user flow.
- Verified means: you executed the feature against a real database with
  real data, observed the output, and checked it against the spec above.

If the user says "verify X" — you re-run that verification, you don't recall
that you verified it earlier.

---

## 7. Negative prompting — things you must not do

1. **Do not add a paid service.** No OpenAI, no Anthropic API, no Eleven
   Labs, no AssemblyAI, no Deepgram, no Azure speech. The brief lists every
   service you may use. If you find yourself wanting another, the answer is
   no.
2. **Do not add a new compose service.** Workers run inside `rig-backend`.
   Adding `rig-celery-worker-whisper` will create double consumers and
   double Beat scheduling. The fix is `/start.sh`, not compose.
3. **Do not introduce a new colour.** Three-colour palette is the point.
   Mode differentiation comes from typography, rule weight, and chip
   language — not hue.
4. **Do not break `/coverage/articles`, `/signals`, `/brief`, or any other
   existing pillar.** This work touches `/clips` only. Any backend route
   you add is namespaced under `/api/newsroom/`.
5. **Do not fabricate test data.** Use real channels, real videos, real
   captions. If a quality issue surfaces only against real data, that is
   the signal you are here to act on.
6. **Do not skip phases.** You may not build the frontend before the
   backend produces real data. You may not flip on live monitoring before
   VOD is verified. The order is the order.
7. **Do not write speculative columns.** The schema in Section 4 is final.
   If you discover a missing column mid-build, write a follow-up migration
   — do not pre-emptively over-spec.
8. **Do not commit secrets.** Cerebras / Groq / Supabase keys come from
   env vars exclusively. If a key appears in chat, treat it as compromised
   and tell the user to rotate.
9. **Do not silently degrade.** If L3 fails for a segment, the segment is
   still inserted with `confidence` lowered and the failure logged — but
   the failure is logged, not swallowed.
10. **Do not refactor unrelated code.** Touching `groq_client.py` is fine
    when adding the Cerebras helper if it's not there. Refactoring the
    article ingestion pipeline because you noticed something is not.
11. **Do not add chat / Q&A / "ask" surfaces** anywhere on /clips. The
    /coverage Ask Bar was removed for good reason. We do not put one back.
12. **Do not ship audio TTS in v1.** Daily Brief is text-only first. Audio
    is a follow-up branch.
13. **Do not use `console.log` in production code.** Pino-style logger or
    nothing.
14. **Do not produce mock data on the frontend.** If the API isn't ready,
    block on the API. No fake channels, no Lorem ipsum captions.
15. **Do not write multi-line code comments.** One-line max, only when the
    *why* is non-obvious. Do not narrate the code. Do not reference the
    task or PR.

---

## 8. Reusable assets you must read before starting

| File | What it gives you |
|---|---|
| `docs/newsroom/wall-mode.html` | The canonical visual reference. Open in browser before writing frontend. |
| `frontend/src/app/globals.css` | All `--onyx-*` tokens and keyframes. |
| `frontend/src/components/coverage/CardDetailView.tsx` | FLIP zoom pattern reused for tile→detail expansion. |
| `frontend/src/components/coverage/BreakingBand.tsx` | Cinematic alert vocabulary; reuse for breaking cluster banner. |
| `frontend/src/components/coverage/CustomCardsRow.tsx` | HUD-corner tile pattern. |
| `backend/nlp/groq_client.py` | Groq + Cerebras failover, token bucket, model mapping. |
| `backend/celery_app.py` | Where you add the `whisper` route. |
| `infrastructure/Dockerfile.backend` + `start.sh` | Where you add the worker launch line. |
| `scripts/migrations/049_*.sql`, `050_*.sql` | Reference style for migration formatting. |
| `CLAUDE.md` | Worker topology, foot-guns, source-of-truth pointers. |

You are encouraged to read these files first and copy their conventions
exactly. The codebase rewards stylistic consistency.

---

## 9. Working agreement

- **Plan, then build.** Before each phase, write a 6–10 line plan in the
  chat naming the files you will create/modify and the verification you
  will run. Then execute.
- **Communicate at decision points.** When a non-obvious taste call comes
  up (e.g. "should breaking clusters expire after 2 hours or 6?"), state
  the trade-off in one sentence and propose a default. Don't ask before
  you've thought.
- **Show your verification.** Paste actual `psql` output, actual
  `curl` responses, actual screenshots in the chat. The user is reading.
- **Confess failure.** If a verification fails, say so plainly. Don't
  reinterpret the failure as success. Don't move on hoping it'll resolve.
- **Match the codebase.** File-naming, import style, error-handling
  shape, logger usage — copy what's already there. Don't introduce a
  second style.

---

## 10. Definition of done

THE NEWSROOM is done when **all** of these are true:

- [ ] All 6 schema migrations applied on a fresh DB without error.
- [ ] `whisper` queue is running with the right concurrency.
- [ ] One known live channel produces fresh segments every 30s.
- [ ] One known VOD clip produces a complete reconciled segment set within 5 min of submission.
- [ ] WALL renders 9 live tiles with real captions ticking.
- [ ] STREAM updates within 2s of a new DB segment.
- [ ] ECHO returns ≥10 quotes for a watched entity in the last 24h.
- [ ] DOSSIER renders mention deltas, sentiment trend, top quotes for a watched entity.
- [ ] BRIEF generates at 06:00 IST and renders text-only.
- [ ] Breaking detection fires on a real cross-channel cluster within 2 min.
- [ ] Phonetic snap correctly normalises ≥80% of proper nouns in a manual sample of 50.
- [ ] No paid service is used.
- [ ] No new colour is introduced.
- [ ] Existing pillars (`/coverage`, `/signals`, `/brief`, `/documents`, `/threads`, `/cuttings`, `/analyst`) continue to work.
- [ ] `docs/newsroom/wall-mode.html` is referenced by the final UI; the live page matches it within taste tolerance.
- [ ] All Phase verification checklists pass.
- [ ] User opens `/clips` in a browser, looks at it, and says "ship".

---

## 11. First message you send back

When you start, your first reply must be:

1. A one-paragraph confirmation that you have read this brief.
2. The exact sequence of files you will read first (before writing
   anything) — at minimum `CLAUDE.md`, `docker-compose.yml`,
   `start.sh`, `celery_app.py`, `globals.css`, `wall-mode.html`,
   `groq_client.py`, the most recent 3 migrations.
3. A 6–10 line plan for **Phase 0** only.

Do not write any code in your first reply. Read first, plan first,
verify first, then build.

---

## 12. Final note from the project owner

This product is being built for users whose work depends on noticing
political and editorial signal moving across regional Telugu / Hindi /
English news in real time. They are not impressed by dashboards. They
are not impressed by features. They are impressed when something they
needed to know reached them ten minutes before anyone else. Build for
that user. Cut anything that doesn't serve that user. The cinematic
aesthetic is not vanity — it's signalling that the system takes their
attention seriously.

Verify everything. Ship in phases. Don't break what works.

— end of brief —
