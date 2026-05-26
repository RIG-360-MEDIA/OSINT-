# 10 - Context From the May 2026 Session

> **TL;DR.** Six critical findings from the multi-day debugging
> session of **2026-05-13 to 2026-05-16** that future sessions need
> to know about. Each one cost hours to discover; documenting here
> so the next session doesn't re-discover them.

## 1. Old Ollama install was 553MB and silently CPU-only

**Discovery date.** 2026-05-13.

**Symptom.** Ollama "loaded" `qwen3:30b-a3b` and responded to
inference requests, but each call took ~60-90 seconds (vs. the
expected ~10-30s on an RTX 4090). GPU utilisation on TRIJYA-7 was
~0% during inference.

**Root cause.** The old Ollama installer for Windows shipped at
**553MB and was missing CUDA DLLs**. With no CUDA, Ollama silently
fell back to CPU inference — no error, no warning, just slow. The
diagnostic command was `ollama serve` from the daemon's working
dir, which showed CUDA initialisation messages absent.

**Fix.** Re-installed Ollama from the official Windows installer,
which is now **2GB and includes CUDA support**. After reinstall,
inference latency dropped to the expected range and GPU
utilisation climbed to 80-95% during calls.

**Watch for.** If you see "Ollama loaded but slow" in a future
session, *first* check the installer size and CUDA presence
before debugging anything else. This burned half a day before
the size discrepancy was noticed.

## 2. FreshRSS admin user wiped on 2026-05-15

**Discovery date.** 2026-05-15.

**Symptom.** All 574 RSS sources stopped returning new articles.
`tasks.collect_rss` reported `sources_checked=0`. DB still had
574 active `source_type='rss'` rows.

**Root cause.** The directory
`/config/www/freshrss/data/users/admin/` was missing entirely
from the FreshRSS container. Root cause of the deletion never
identified — best guess is a stray `rm` against the wrong path
during an unrelated debug session, or a volume-mount mishap on
container restart. There is no integrity check at FreshRSS boot,
so a missing admin user looks identical to "no new RSS today."

**Recovery procedure.**
1. Recreate `admin` via the FreshRSS CLI inside the container.
2. `chown abc:users` on the user directory.
3. Restore `/config/www/freshrss/data/config.php` from the
   default template with `api_enabled => true`.
4. **Resubscribe all 574 feeds** via the GReader
   `subscription/quickadd` API. The subscription list was wiped
   along with the user.

**Watch for.** If RSS inflow ever drops to zero abruptly, FreshRSS
admin user is the first thing to check. The resubscription
procedure should be documented separately (P2 todo: write up the
resubscribe script and commit it).

## 3. FreshRSS subscription persistence is fragile

**Related to #2.** Once subscribed, feeds in FreshRSS live in the
mounted volume. But because the admin user can vanish (see #2),
and because the volume contents are ephemeral relative to the
DB-side `sources` table, the two can drift out of sync.

**Discovery.** During the 2026-05-15 recovery, we found that the
DB had 574 `source_type='rss'` rows but FreshRSS itself only had
~250 subscriptions before the wipe. Some had been added to the
DB but never subscribed in FreshRSS; others had been subscribed
historically but lost during earlier volume drift.

**Implication.** Treat the DB as the source of truth. The
resubscribe procedure should reconcile FreshRSS subscriptions
against the DB row set, not the other way around.

## 4. The 7-variant prompt eval — Prompt G is the winner

**Discovery date.** 2026-05-15/16.

**Method.** 100 sampled article IDs at
`/tmp/eval_v2_sample_ids.txt`, frozen across all variants for
fair comparison. Each variant run through Ollama qwen3:30b-a3b
at `http://100.92.126.27:11434/api/chat` with semaphore=2
matching `OLLAMA_NUM_PARALLEL=2`. 300 calls per variant set.

**Variants tested.** A through G:
- A — baseline (the v2 prompt).
- B-D — incremental tweaks to location rules.
- E — added India anchor city list.
- F — added state-vs-city decision tree.
- G — F + EVENT DATE RULE addendum.

**Winner.** **G** — the only variant that simultaneously hit:
- 0% null-subject claims
- ~80% factual claim rate
- Aggressive India city extraction (no empty city on stories
  that named a specific town)
- Correct state-vs-city behaviour (cabinet meetings = state
  story, not Hyderabad story)
- All events carry a `date` field (real date or explicit `null`)

**Headline metrics for v3 / Prompt G post-drain.**

| Metric                     | v2 baseline | Prompt G   |
|-----------------------------|-------------|------------|
| Quotes / article (median)  | 0.9         | 1.4        |
| Claims / article (median)  | 2.1         | 3.2        |
| Factual rate (claims)       | 60%         | 80%        |
| Null-subject claims         | 28%         | 0%         |
| Byline coverage             | 12%         | 37%        |

The eval harness is in
`backend/tasks/substrate/eval_prompts.py` plus a `eval_prompt_G`
module. Historical record kept; do not overwrite.

## 5. The 32-line drain watchdog auto-recovers MIXED ↔ LOCAL_ONLY

**Built during.** 2026-05-16, in response to the Cerebras TPD
blow-out (see `07-known-issues.md` #4).

**Location.** `/tmp/drain_watchdog.sh` on Hetzner. Currently PID
**2136723** as of the May 2026 session. Log at
`/tmp/drain_watchdog.log`.

**Behaviour.**
- Every minute, calls `/tmp/probe_cerebras.py` to check aggregate
  remaining TPD across all 27 Cerebras keys.
- If aggregate falls below ~5% remaining: `export
  LLM_LOCAL_ONLY=1` and signal the drain to reload env.
- When Cerebras resets at 00:00 UTC: unset `LLM_LOCAL_ONLY`,
  drain returns to MIXED.
- Polls the drain PID; if dead, relaunches with current mode.

**Watch for.** This script is **not in git**. It will be lost on
box rebuild. P1 todo to promote it to `backend/ops/`.

**Lesson.** When orchestrating long-running container work,
don't have the agent be the synchronous owner — let the work
file its own progress (in a known table or file) and let any
observer read it asynchronously. This pattern was forced by
agent-watchdog-killed-orchestrators-while-work-continued
incidents during the eval runs.

## 6. Re-enabled 174 of 406 bulk-disabled sources

**Discovery.** 2026-05-15/16, during the source recovery sweep.

**Procedure.** Ran `probe_all_disabled.py` (committed at repo
root) which:
1. Selects all `sources` where `is_active=false`.
2. For each, attempts the source's primary URL (RSS feed or HTML
   landing).
3. Records HTTP status, response size, parseable content
   detection.
4. For sources returning HTTP 200 with parseable content (i.e.
   they're actually alive), prints a SQL line to flip
   `is_active=true`.
5. Operator reviews + applies (NOT auto-applied — the 2026-04-25
   incident was an auto-applied bulk SQL, so we don't repeat
   that mistake).

**Result.** 174 sources re-enabled. ~232 remain disabled:
- Some genuinely dead (404, dead domain).
- A meaningful fraction need URL-path fixes (RSS moved from
  `/rss` to `/feed`, scheme switched from `http` to `https`,
  www-vs-no-www).

**Open work.** P1 todo to do a second sweep with URL-mutation
extensions. See `09-todos-prioritized.md` P1.1.

## Auxiliary findings from the same session

These didn't get their own numbered section but are worth
recording:

- **Qwen3 reasoning mode silent token burn.** First Ollama
  integration used `/v1/chat/completions` (OpenAI-compat). Calls
  returned HTTP 200 but `content=""`. Cause: reasoning tokens
  routed to a hidden `reasoning` field the OpenAI spec doesn't
  expose. Fix: switch to native `/api/chat` and pass
  `think: false` in the body. See `02-substrate-pipeline.md`
  Known bugs #2.

- **Groq Cloudflare WAF rejection.** Default httpx UA triggered
  `error code: 1010` (403). Fix: real browser UA override in
  `groq_client.py`. Without it every Groq call 403s and the
  pool logs phantom rate-limit errors.

- **Cerebras failover for Groq rate-limits.** Commit `a819fa7`
  added formal cross-provider fallback. Before this, an
  exhausted Groq pool wouldn't reach for Cerebras automatically.

- **Newspaper queue migration.** Newspaper collection used to
  live on `collectors` (concurrency=1, regularly blocked by RSS
  scrapes). Moved to `documents` queue in the 2026-04-28 audit.
  Newspaper-task code lives in `backend/tasks/newspaper_task.py`.

- **Newsroom cold-start deadlock.** `process_broadcast` hangs
  reliably as first task after a worker restart. Workaround:
  warm worker with ping tasks. Root cause: suspected
  module-level asyncio Lock in `groq_manager` interacting badly
  with Celery prefork. Open investigation.

- **Branch divergence Hetzner ↔ origin.** Branch
  `fix/brief-prod-readiness` diverged at commit `3a9441a`
  (2026-05-09). Reconcile before Phase 7. Origin is canonical
  for CM editorial UI. Newsroom migrations start at 051.

## See also

- `docs/mistakes.md` — the canonical incident log. Many of the
  above are also recorded there with more detail.
- `02-substrate-pipeline.md` — for Prompt G details.
- `05-llm-infrastructure.md` — for the watchdog architecture.
- `07-known-issues.md` — for current open issues that originate
  in this session.
