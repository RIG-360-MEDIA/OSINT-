# 07 - Known Issues

> **TL;DR.** Seven recurring frustrations, each documented with
> symptom / root cause / current workaround / proper fix. Sourced
> from `docs/mistakes.md` (~25 incidents, 911 lines) condensed
> to the ones that are actively painful. Read this BEFORE re-debugging
> a problem.

## 1. Scrapers silently fail (FreshRSS auth, bulk-disable cascade)

**Symptom.** The DB has 574 active RSS sources, but new-article
inflow drops to zero. No errors in logs. `tasks.collect_rss`
reports `sources_checked=0`.

**Root cause (variant A — FreshRSS).** The FreshRSS admin user's
data directory under `/config/www/freshrss/data/users/admin/` was
wiped on **2026-05-15**. Root cause of the wipe never identified —
suspected stray `rm` during an unrelated debug, or a volume mount
mishap during container restart. With the admin user missing, the
GReader API returns 403 on every request, so no feeds are
reachable. The 574 subscription list was also wiped and had to be
resubscribed.

**Root cause (variant B — bulk-disable).** On **2026-04-25**,
uncommitted manual SQL flipped `is_active=false` on ~406 sources.
174 have been re-enabled after live probe; ~232 remain pending
investigation. Some of those are genuinely dead, but a significant
fraction are alive and just need URL fixes.

**Current workaround.**
- Variant A: Recreate the admin user via FreshRSS CLI; `chown
  abc:users` on the user dir; restore `/config/www/freshrss/data/
  config.php` with `api_enabled=true`; resubscribe all 574 feeds
  via GReader `subscription/quickadd`.
- Variant B: Run `probe_all_disabled.py` (in repo root) to live-test
  every disabled source URL and flip the alive ones back to
  `is_active=true`.

**Proper fix.** Boot-time integrity check for FreshRSS admin user
that fails loudly if missing. Monitoring + alerting on RSS inflow
(see #3). Commit the source-state changes as SQL migrations so
they're recoverable from git.

## 2. Drain stalls when Ollama daemon dies on TRIJYA-7

**Symptom.** The drain process is alive, but the `v3` count isn't
climbing. `/tmp/drain.log` shows repeated `OllamaCallFailed` or
its mtime is stale.

**Root cause.** Two variants:
- Ollama daemon on TRIJYA-7 crashed (rare but happens — old
  install was 553MB and CUDA-broken; new install is 2GB and
  stable).
- Tailscale connection between Hetzner and TRIJYA-7 dropped.

When `LLM_LOCAL_ONLY=1` is set (which the watchdog flips during
high Cerebras consumption), there's no cloud failover, so the
drain just retries Ollama forever.

**Current workaround.** Operator notices and either restarts
Ollama on TRIJYA-7 (Windows scheduled task `OllamaServe`) or
manually clears `LLM_LOCAL_ONLY` to let the pool fall back to
cloud.

**Proper fix.**
- Watchdog should detect "drain alive but v3 not climbing for
  10+ minutes" and try Ollama health-check; flip to cloud
  fallback if Ollama is unreachable.
- Add a Tailscale-up healthcheck to the backend startup.
- Promote watchdog + probe scripts from `/tmp/` to
  `backend/ops/` so they're version-controlled.

## 3. No monitoring / alerting

**Symptom.** Every other known issue in this list is "invisible
until manually checked." Failures cascade silently. The first
indicator is usually a user complaint or a manual SQL spot-check
days later.

**Root cause.** No monitoring layer was ever built. There is no
Prometheus, no Grafana, no alert routing. Container logs are the
only signal, and they're not aggregated.

**Current workaround.** Manual `docker logs -f` and SQL probes
during active sessions. The drain watchdog is the one piece of
automation, and it only covers the drain.

**Proper fix (P2 future-plan).**
- Lightweight metrics layer: queue depth, source health,
  drain-process-alive, FreshRSS-auth-healthy, Cerebras quota,
  Groq quota.
- Alert routing — at minimum to email (the user's `heretech.shodh1@gmail.com`),
  ideally to a phone notification.
- Auto-restart for the 6 Celery workers if they crash.
- Boot-time integrity checks: FreshRSS admin user, Tailscale to
  TRIJYA-7, watchdog running.

## 4. Cerebras TPD burn during long drains

**Symptom.** A drain that starts at 09:00 UTC consumes 99.5% of
the 27M-token daily Cerebras budget by 17:00 UTC. The remaining
16 hours of pipeline work stall on 429 refusals from every
Cerebras key.

**Root cause.** The drain's throughput controller knows about
per-minute rate limits (RPM / TPM) but has no concept of the
per-day token budget. It runs at maximum sustainable RPM, which
blows through the daily cap roughly a third of the way through
the day.

**Current workaround.** The drain watchdog flips to `LOCAL_ONLY`
when Cerebras aggregate falls below ~5% remaining. The drain
continues on Ollama (slower but unlimited) until 00:00 UTC reset.

**Proper fix.** TPD-aware back-pressure controller. Track a
rolling 24h token consumption per provider; throttle the drain
when consumption exceeds daily-budget pace (if you're 50%
through the day, you should be ~50% through the daily budget,
not 99%). Open todo, P2.

**Lesson.** Rate limits and quota limits are different signals.
RPM/TPM protects the *provider* from instantaneous spikes;
TPD/MTD protects *you* from premature exhaustion. A controller
that respects only the first blows the second.

## 5. Groq organisation restrictions (uncommon but happens)

**Symptom.** A handful of Groq keys return HTTP 403 with
`error code: 1010` *despite* the pool's browser-UA override.

**Root cause.** Groq applies organisation-level rate limits and
abuse heuristics on top of per-key quotas. A noisy key from an
org under scrutiny gets WAF'd even when individual quota is OK.

**Current workaround.** The cooldown logic treats 403s the same
as 429s — that key gets parked for a cooldown window. The pool
rotates around it. If multiple keys WAF simultaneously, the pool
falls over to Cerebras.

**Proper fix.** Distribute keys across more Groq organisations
where possible. Track WAF rate per-org and rebalance.

## 6. `semantic_repass.py` ignores `LOCAL_LLM_PRIMARY`

**Symptom.** Setting `LOCAL_LLM_PRIMARY=1` and starting the drain.
Monitoring shows traffic going to Cerebras/Groq, not Ollama —
exactly the opposite of intent.

**Root cause.** `LOCAL_LLM_PRIMARY` is wired only at the
unified-pool entry point. `semantic_repass.py` constructs its
own provider list manually and never consults the local-primary
flag. The flag "works" in the sense that it's set and read, but
the code path the drain exercises bypasses it.

**Current workaround.** Use `LLM_LOCAL_ONLY=1` instead, which is
gated at the unified-pool layer that all paths eventually reach.

**Proper fix.** Audit every LLM-call site in the codebase; route
through the unified pool OR explicitly consult the local-primary
flag in any manual provider-list construction. P1 todo.

**Lesson.** Env-flag plumbing is not consistent across substrate
code paths. There are at least two LLM-routing layers (unified
pool + per-task manual lists), and a flag set at one layer
doesn't propagate.

## 7. Worker-collectors backed-up queue accumulates stale tasks

**Symptom.** Queue depth on `collectors` climbs to 800+ stale
messages. New Beat fires queue up behind them. Real-time scrapes
get delayed by hours.

**Root cause.** `worker-collectors` is `concurrency=1`
intentionally — RSS scrapes are I/O-heavy and overlapping them
causes timeout cascades. But that means one 60-minute scrape
blocks everything else queued behind it. If multiple Beat fires
happen during that 60 minutes, they queue up; the queue never
catches up.

**Current workaround.** Flush selectively with `celery purge -Q
collectors -f` then re-fire canonical tasks manually. See
`06-operations-runbook.md`.

**Proper fix.**
- Move slow scrapes off `collectors` to a separate queue (the
  `documents` queue absorbed newspaper collection for this
  reason).
- Per-source timeout caps to prevent any single scrape from
  running 60+ minutes.
- Beat deduplication: don't enqueue a new `collect_rss` if the
  previous one is still running.

## 8. (Operational, not on the canonical list) — YouTube IP-reputation gating

**Symptom.** YouTube transcript fetches start returning 429 / blocked.

**Root cause.** A debug session called `yt-dlp` or
`youtube-transcript-api` raw from the Hetzner shell (bypassing
`_youtube_throttle`). This burst burnt the IP reputation.
Recovery is 24-72 hours.

**Current workaround.** Wait. There is no manual recovery.

**Proper fix.** Already documented in memory: NEVER call yt-dlp /
transcript-api raw from a debug shell on Hetzner. Always go
through `_youtube_throttle`. Consider rotating egress IPs for
YouTube traffic in the longer term.

## See also

- `docs/mistakes.md` — the full incident log. ~25 entries, 911
  lines. Chronological.
- `docs/qa/` — the defect registers per pillar. Most actionable
  bugs are tracked there.
- `08-future-plans.md` — proper fixes for several of the issues
  above show up here as planned work.
- `09-todos-prioritized.md` — concrete priority order.
