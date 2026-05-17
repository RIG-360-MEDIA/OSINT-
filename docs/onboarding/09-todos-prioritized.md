# 09 - Prioritised Backlog

> **TL;DR.** Concrete backlog in four priority bands. P0 = active
> now. P1 = this week. P2 = this month. P3 = someday-maybe. Refresh
> this list when priorities change rather than letting it rot.

## P0 — Active now

### P0.1 — Complete v3 substrate drain

**Status.** In progress. ~23K v1 articles remaining as of
2026-05-16.

**Driver.** `backend/tasks/substrate/semantic_repass.py`. Watchdog
at `/tmp/drain_watchdog.sh` on Hetzner manages MIXED ↔ LOCAL_ONLY
flips.

**Done-when.** `SELECT COUNT(*) FROM articles WHERE
extraction_version='v1'` is 0.

**Watch for.** Drain stalls (PID alive but v3 count flat) —
usually Ollama daemon issue on TRIJYA-7. Cerebras TPD blow-out —
should be handled by watchdog auto-flip.

### P0.2 — Flush stale collectors queue

**Status.** ~800 stale messages reported backing up beat-scheduled
tasks.

**Action.**
```bash
docker exec rig-backend celery -A backend.celery_app \
  purge -Q collectors -f
docker exec rig-backend celery -A backend.celery_app call \
  tasks.collect_rss
docker exec rig-backend celery -A backend.celery_app call \
  tasks.collect_html
```

**Done-when.** Queue depth back to 0-5 messages; new RSS articles
appearing in DB within 15-min cadence.

## P1 — This week

### P1.1 — Resurrect remaining ~100 disabled sources (selective)

**Status.** 174 of 406 bulk-disabled sources re-enabled. ~232
remain; of those an estimated ~100-150 are recoverable.

**Action.**
- Run `probe_all_disabled.py` (repo root) with extended URL
  mutations (`/feed`, `/rss.xml`, scheme/www swap).
- For each alive, commit a per-source SQL migration (NOT manual
  SQL) flipping `is_active=true` with the corrected URL.
- For each dead, mark with a `deprecation_reason` in a notes
  column (or doc file) so future probes don't waste cycles.

**Effort.** 1-2 days, mostly manual.

**See.** `04-scrapers.md` for the bulk-disable history,
`08-future-plans.md` #4 for the strategic context.

### P1.2 — Byline extractor patch

**Status.** Coverage at ~14%. Target 80%.

**Action.**
- Enumerate meta-tag and JSON-LD byline forms on top 100
  sources.
- Add site-specific selectors as fallback.
- Extend the generic-string blacklist (PTI, ANI, Staff Reporter,
  News Desk, Web Desk, etc.) so they go to `byline_role` not
  `byline_name`.
- Backfill existing v3 articles with improved extractor.

**Effort.** 2-3 days.

**Lives in.** `backend/tasks/substrate/byline_periodic_task.py`,
`backfill_bylines.py`.

### P1.3 — `semantic_repass.py` LOCAL_LLM_PRIMARY support

**Status.** Open. Today `LLM_LOCAL_ONLY=1` is the only flag that
forces Ollama from semantic_repass. The proper fix is to route the
drain's LLM calls through the unified pool entry-point that honours
`LOCAL_LLM_PRIMARY`, or to teach the manual provider-list
construction to consult the flag.

**Action.**
- Audit every LLM-call site in the codebase (grep for direct
  calls to `groq_sdk` / `cerebras_sdk` / Ollama HTTP).
- Route through the unified pool OR add explicit flag checks.
- Add a test that asserts setting `LOCAL_LLM_PRIMARY=1` actually
  routes drain traffic to Ollama.

**Effort.** 1 day.

**See.** `07-known-issues.md` #6, `02-substrate-pipeline.md`
"Known bugs".

### P1.4 — Promote watchdog scripts from /tmp to repo

**Status.** Watchdog + probe scripts live in `/tmp/` on Hetzner.
Not committed. Will be lost if the box is rebuilt.

**Action.** Move to `backend/ops/`:
- `drain_watchdog.sh`
- `probe_cerebras.py`
- `probe_groq.py`

Add a systemd-style unit (or just a docker-compose entry) so the
watchdog is launched as part of the deploy, not manually.

**Effort.** Half a day.

## P2 — This month

### P2.1 — Relevance v3 implementation

**Status.** Designed in `03-relevance-system.md`. Not implemented.

**Plan.**
1. Add `articles.summary_embedding vector(768)` migration.
2. Nightly job to embed new articles via LaBSE (model is
   already cached in the image).
3. Per-user interest centroid computation.
4. Layer-2-only A/B vs Layer-1.
5. Frontend engagement logging.
6. Per-user reranker (Layer 3).

**Effort.** 1-2 weeks for layers 1+2; another week for layer 3.

### P2.2 — Monitoring + alerting layer

**Status.** Nothing today.

**Plan.**
- Metrics endpoint: queue depths, source health rollup, drain
  process alive + v3 delta, FreshRSS auth healthy, Cerebras /
  Groq quota.
- Email alert routing to `heretech.shodh1@gmail.com`.
- Auto-restart for Celery workers on crash.
- Boot-time integrity checks (FreshRSS admin user, Tailscale).

**Effort.** 3-5 days.

**See.** `07-known-issues.md` #3, `08-future-plans.md` #5.

### P2.3 — Frontend redesign discovery

**Status.** Mockup work done (`demo-no-lines-v3.html`); palette and
register locked. Not yet ported to React.

**Plan.**
- Decide on component library (continue with current Tailwind
  + shadcn-ish or move to something publication-y).
- Build the "Edition" data model — backend endpoints, scheduling.
- Component-by-component port of HOME zones.
- Mobile responsive pass.

**Effort.** 2-3 days component build + 1-2 days mobile.

**See.** `08-future-plans.md` #2.

### P2.4 — TPD-aware drain back-pressure

**Status.** Workaround via watchdog. Proper fix pending.

**Plan.** Track rolling 24h token consumption per provider.
Throttle the drain so consumption tracks the daily-budget pace
(50% through day → ~50% through budget, not 99%). Live signal:
the watchdog log showing flips well before quota exhaustion.

**Effort.** 1-2 days.

**See.** `07-known-issues.md` #4.

## P3 — Someday

### P3.1 — Watchlist-priority re-pass scheduling

Articles matching watched entities get priority queueing for
substrate extraction. Today it's first-come-first-served by
article ID, so a fresh PIB story might wait behind a 6-month-old
random article.

### P3.2 — Source-tier auto-classification

Today `source_tier` is hand-set. A classifier trained on signal
quality (substrate success rate, byline presence, geo
specificity, claim density) could auto-tier.

### P3.3 — Entity dictionary alias generation

Phase A of the entity-resolution roadmap. Bulk Groq job to
generate 3-5 aliases per canonical (~30K-50K alias rows target,
from current 14). Cost ~15% of one day's Groq quota.

Phase B: LaBSE embeddings on canonical names for semantic match.

Phase C: bulk resolution pass over existing actor strings.

Phase D: candidate auto-promotion table.

**See.** `docs/future-todo.md` entry #3 for full design.

### P3.4 — v4 prompt iteration

Defer until v3 drain is complete and stats are stable. Current
v3 stats: 1.4 quotes / article, 3.2 claims / article, 80%
factual, 0% null subject, 37% byline coverage. If v4 is needed,
focus on stronger claim anchoring (80% → 90% factual).

### P3.5 — Dossier endpoint

`DOSSIER_ENABLED=false` in compose. Experimental per-entity
dossier endpoint with GDELT integration. Not surfaced in UI.

### P3.6 — Whisper / audio transcription

The `whisper` queue exists but no consumer. Reserved for podcast
/ video transcription if a use case emerges.

## See also

- `08-future-plans.md` — strategic context for the major items.
- `07-known-issues.md` — root causes for the work in P1/P2.
- `docs/future-todo.md` — the canonical roadmap doc (this file
  is a re-prioritised view of the same).
