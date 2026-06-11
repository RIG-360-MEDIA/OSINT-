# 09 - Prioritised Backlog

> **TL;DR.** Concrete backlog in four priority bands. P0 = active now.
> P1 = this week. P2 = this month. P3 = someday-maybe.
>
> **Refresh policy.** Update this list when priorities change. Don't
> let it rot — see-also references the live `TaskList` in the active
> session for hour-by-hour status. This file captures the strategic
> backlog, not minute-by-minute progress.
>
> **Last refresh: 2026-05-28** — incorporates session D1-D26 outcomes
> and the 5 migrations shipped today.

---

## P0 — Active now

### P0.1 — D1 substrate v3 drain (in progress)

**Status.** ~52,500 articles `substrate_status='pending'` as of 03:30
UTC. Drain running on 4 parallel processes with atomic-claim
(`FOR UPDATE SKIP LOCKED`). Today's burst hit 64/min peak; current
steady-state ~30-50/min (Cerebras free-tier TPD exhausted, Ollama
binding the throughput). Resumes higher rate at 00:05 UTC daily reset.

**Driver.** `backend/tasks/substrate/run_corpus_pass.py`.

**Done-when.** `pending` count returns to ~0 (i.e. flush the 60K
backlog created when we reset extraction_version=0 on pre-D1
articles).

**Watch for.**
- Cerebras TPD exhaustion mid-day (see #5 in 11-session-2026-05-28).
  Drain rate drops from 60/min → 25/min.
- Drain process dies (no watchdog yet — manual `pkill -f
  run_corpus_pass` + relaunch needed).
- `parse_a2` count climbing in drain log = quality regression.

**ETA.** At sustained 30-50/min → ~17-29h from session start.
Realistic completion: late 2026-05-28 or early 2026-05-29.

### P0.2 — Resume ingest after drain (paused via SIGSTOP)

**Status.** Collectors workers SIGSTOPed during the drain to free
Ollama capacity. ~24-48h queue backlog of `collect_rss` tasks built
up in Redis.

**Action.** Per `docs/PAUSE_INGEST_RUNBOOK.md`:
```bash
ssh -i ~/.ssh/rig_hetzner root@178.105.63.154 'docker exec rig-backend bash -c "
PIDS=\$(ps -eo pid,cmd | grep \"queues=collectors\" | grep -v grep | awk \"{print \\\$1}\")
for p in \$PIDS; do kill -SIGCONT \$p && echo resumed \$p; done
"'
```

Plus purge stale queue if pause was >24h:
```bash
docker exec rig-backend celery -A backend.celery_app purge -f -Q collectors
```

**Done-when.** New articles appearing in DB within 15min cadence.

---

## P1 — This week

### P1.1 — D8: bake `article.published_at` into substrate prompt

**Why.** LLM defaults event years to its training-cutoff year (2024)
when articles don't state the year explicitly. Migration 072 fixes
this retroactively (4-tier `effective_event_date` rule); D8 fixes it
at the source.

**Action.** In `backend/tasks/substrate/run_corpus_pass.py`, prepend
to the substrate system prompt:
```
ARTICLE PUBLISHED: {article.published_at}. TODAY: {today}.
If an event date is mentioned without a year, assume the year matches
the article's publish year. Never emit event_date earlier than 2023
unless the article explicitly states a pre-2023 year.
```

Deploy after current D1 drain completes (so all newly-extracted articles
benefit). Backfill won't be needed — `effective_event_date` already
populated by migration 072.

**Effort.** 1h code + image rebuild.

### P1.2 — D13: permanent fix for D1 reset cron + auto-corpus-pass

**Why.** D1 cron at `5 0 * * *` invokes
`/app/scripts/d1_force_reextract.py` inside rig-backend container but
that script only exists at `/tmp/d1_force_reextract.py` on the host.
Cron has been failing silently. AND even when run, the script only
RESETS flags — doesn't enqueue the corpus pass.

**Action.**
1. `COPY scripts/d1_force_reextract.py /app/scripts/` in
   `infrastructure/Dockerfile.backend`.
2. Modify cron command to chain: `python /app/scripts/d1_force_reextract.py
   && python -m backend.tasks.substrate.run_corpus_pass --limit 80000`.
3. Rebuild image + restart rig-backend.

**Effort.** 30min.

### P1.3 — Phase 1 source expansion (100 sources × 20 countries)

**Why.** Today's source pool is 81% India (659/793 sources). Zero US,
RU, JP, FR, DE, BR, MX, IR, SA, AE explicit national sources. Schema
ready (migration 075 added `sources.country`).

**Action.**
1. Write `scripts/migrations/076_phase1_sources_insert.sql` with 100
   curated rows (top 5 flagships per priority country, list in
   `docs/PHASE1_20_COUNTRIES.md`).
2. Test scrapability of each (HTML structure detection, RSS endpoint
   verification). Use `scripts/audit/probe_silent_sources.py` as a
   starting point.
3. Initial `health_score=0.3` (just above auto-disable threshold). Let
   them prove themselves over 7 days.
4. Monitor Day 1 article volume — expected +500-1000 articles/day.

**Effort.** 1 day (curation + scrapability check + monitoring).

### P1.4 — Re-enable LaBSE claim embeddings

**Why.** Only 0.96% of claims (225/23,391 sampled) have
`embedding IS NOT NULL`. Pipeline step has fallen out. Without claim
embeddings: semantic search broken, contradiction detection broken,
narrative clustering can't work.

**Action.**
- Find the embedding step in substrate (or as a celery task).
- Identify why it's been silent (likely missing model file or task
  unregistered).
- Backfill 23K recent claims via batched `tasks.embed_claims_batch`.

**Effort.** 2-4h diagnostic + 1h backfill.

### P1.5 — Promote `/tmp/*` scripts to repo

**Why.** Watchdog + probe scripts live in `/tmp/` on Hetzner. Not
committed. Lost on box rebuild. Same problem as D1 cron above.

**Action.** Move to `backend/ops/` (with proper Python module
structure or simple `scripts/`):
- `drain_watchdog.sh`
- `probe_cerebras_keys.py` (already partially in repo — verify
  matches what's running on Hetzner)
- `probe_groq_keys.py`
- `d1_force_reextract.py`

Add to Dockerfile so they ship with the image.

**Effort.** Half a day.

---

## P2 — This month

### P2.1 — Narrative pipeline Stage 0-6 wiring

**Why.** Migrations 070-075 done, narrative tables exist, but the
narrative pipeline (`backend/tasks/narrative/`) is scaffolded with no
runner. `narrative_frame` field is 0% populated. `event_cluster_id`
is 0.2% populated.

**Plan.**
1. Stage 0 (cluster assembly) — beat-scheduled nightly. Groups
   recent articles by embedding similarity + temporal proximity into
   `narrative_clusters` rows.
2. Stage 2A (triangulation) — runs after Stage 0. Validates clusters
   have 3+ independent sources.
3. Stage 2B → 6 (interrogation, lede, body, critic, revision) — for
   each cluster, generates `narrative_drafts` row.
4. Frontend brief page reads `narrative_drafts` for daily digest.

**Effort.** 2 weeks for first end-to-end run.

### P2.2 — TPD-aware drain back-pressure

**Why.** Today's drain blew Cerebras free-tier daily budget in ~5h.
Pool keeps trying exhausted keys = wasted round-trips. Watchdog
auto-flips to LOCAL_ONLY only AFTER ~95% burn — too late.

**Plan.** Track rolling 24h token consumption per provider per key.
Throttle the drain so consumption tracks the daily-budget pace (50%
through day → ~50% through budget, not 99%). Pre-emptive flip to
LOCAL_ONLY at 70% burn instead of 95%.

**Effort.** 1-2 days.

### P2.3 — Monitoring + alerting layer

**Status.** Nothing today.

**Plan.**
- Metrics endpoint: queue depths, source health rollup, drain
  process alive + v3 delta, FreshRSS auth healthy, Cerebras /
  Groq quota.
- Email alert routing to `heretech.shodh1@gmail.com`.
- Auto-restart for Celery workers on crash.
- Boot-time integrity checks (FreshRSS admin user, Tailscale).

**Effort.** 3-5 days.

### P2.4 — Relevance v3 implementation

**Status.** Designed in `03-relevance-system.md`. Not implemented.

**Plan.**
1. Add `articles.summary_embedding vector(768)` migration.
2. Nightly job to embed new article summaries via LaBSE.
3. Per-user interest centroid computation.
4. Layer-2-only A/B vs Layer-1.
5. Frontend engagement logging.
6. Per-user reranker (Layer 3).

**Effort.** 1-2 weeks for layers 1+2; another week for layer 3.

### P2.5 — Documentation consolidation

**Status.** 127 active docs in `docs/` — too many. Many are dated
snapshots of repeated audits. Plan in `docs/DOCS_CONSOLIDATION_PLAN.md`.

**Action.** Reduce to ~30 canonical docs.
- Merge dated `DATA_QUALITY_AUDIT_2026-05-XX.md` files into ONE
  `DATA_QUALITY.md` updated in place.
- Move completed sprint plans to `docs/archive/sprints/`.
- Merge 5 runbook fragments into ONE `RUNBOOK.md`.

**Effort.** 1 day.

### P2.6 — Phase 2 source expansion (~500 total)

After Phase 1 lands and we observe actual ingest rates, add tier-2
outlets per country. Target ~500 sources covering ~30 countries with
healthy diversity.

---

## P3 — Someday

### P3.1 — Watchlist-priority re-pass scheduling

Articles matching watched entities get priority queueing for
substrate extraction. Today it's first-come-first-served by article
ID.

### P3.2 — Source-tier auto-classification

Today `source_tier` is hand-set. A classifier trained on signal
quality (substrate success rate, byline presence, geo specificity,
claim density) could auto-tier.

### P3.3 — Entity dictionary alias generation

Phase A of the entity-resolution roadmap. Bulk job to generate 3-5
aliases per canonical (~30K-50K alias rows target, current ~15K).

Phase B: LaBSE embeddings on canonical names for semantic match.

Phase C: bulk resolution pass over existing actor strings.

Phase D: candidate auto-promotion table.

### P3.4 — v4 prompt iteration

Defer until v3 drain is complete and stats are stable. Current v3
quality (last 6h, 8,156 articles):
- 100% summary preview/snippet/executive
- 100% article_type / register_style / register_emotion
- 99% SPO triple completeness on claims
- 99% locations, 96% events, 84% claims, 74% numbers, 59% quotes

If v4 is needed, focus on stronger entity linking (currently ~35%
linked across child tables).

### P3.5 — Phase 3 source expansion (full xlsx 3,263 sources)

Only with cloud as overflow. Pure local LLM can't sustain 28K
calls/day for full source set. Need Groq paid tier or 2nd GPU.

### P3.6 — Dossier endpoint

`DOSSIER_ENABLED=false` in compose. Experimental per-entity dossier
endpoint with GDELT integration. Not surfaced in UI.

### P3.7 — Whisper / audio transcription

The `whisper` queue exists but no consumer. Reserved for podcast /
video transcription if a use case emerges.

### P3.8 — vLLM via WSL2 on Trijya

Only practical Windows option. Complex setup. Probably never worth
it unless we need genuine 100+ calls/min sustained.

### P3.9 — Resurrect remaining disabled sources

~150 dead RSS paths. Probe with URL mutations (`/feed`, `/rss.xml`,
scheme/www swap). Some are recoverable, most are genuinely dead.

---

## See also

- `08-future-plans.md` — strategic context for the major items.
- `07-known-issues.md` — root causes for the work in P1/P2.
- `11-session-2026-05-28-learnings.md` — full lessons from today
  feeding this backlog.
- `docs/PHASE1_20_COUNTRIES.md` — Phase 1 source list candidates.
- `docs/DOCS_CONSOLIDATION_PLAN.md` — P2.5 plan details.
