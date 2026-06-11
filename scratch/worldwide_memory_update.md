# Memory / compute update — re: your H5 red flag (from the database/pipeline chat)

Closing the loop on H5 ("4 cores / 15 GiB RAM / ~123 MiB free / no GPU → hourly
Leiden on 140–280K nodes + embed job not feasible on-box"). We triaged the box.
Bottom line: **the acute OOM crisis is fixed, but the compute ceiling you flagged
is unchanged — plan the clustering engine around it.**

## What was wrong
- The host was **actively OOM-killing processes** (kernel log showed real
  `Out of memory: Killed process … global_oom` events). RAM was full **and swap
  was 100% full** (8/8 GiB). ~123 MiB available.
- Cause: a **leaked Chromium (Playwright) footprint** — **9.1 GiB across ~141
  chrome processes** inside `rig-backend` (which was eating 87% of host RAM).
- Root cause was NOT buggy code (the Playwright launchers already use proper
  `try/finally` + `--disable-dev-shm-usage`). It's **orphaned Chrome from *killed*
  tasks** — when a scrape task is SIGKILLed (OOM, time-limit, recycle), Python
  cleanup never runs and the Chrome tree is orphaned. A classic cascade.

## What we did (all live now)
1. **Reclaimed 9 GiB** (killed the orphaned Chrome). available RAM 129 MiB → ~8.9 GiB;
   swap 100% → 52%.
2. **Reaper cron (every 10 min):** caps Chrome RSS at 4 GiB (emergency-reaps if
   host available < 600 MiB) and re-asserts the OOM shield.
3. **OOM shield:** `oom_score_adj` = **−900 on Postgres (un-killable)**, −500 on
   the backend init → the OOM victim can only ever be a recyclable Chrome/worker,
   **never the database**.
4. **`rig-backend` `mem_limit` = 12 GiB (cgroup cap):** the backend can no longer
   starve the host; if it climbs, the cgroup OOM-kills Chrome *inside* its own
   limit, leaving ≥3 GiB for Postgres + everything else.
5. **Celery `--max-memory-per-child = 2.44 GB`** on all 7 workers → any bloated
   worker recycles *gracefully* (after its task, so it doesn't orphan Chrome).

Verified: host available **4.5 GiB**, cgroup OOM kills **0**, DB protected, no
errors. The memory crisis is closed.

## ⭐ What this means for the clustering engine (unchanged ceiling)
The box is still **4 cores · 15 GiB RAM · no GPU**, and `rig-backend` is now
**hard-capped at 12 GiB**. So:

- **Do NOT plan an in-RAM 280K-node community-detection (Leiden/CC) pass on this
  box.** Loading that graph into memory — especially inside the rig-backend
  process — would blow the ~3 GiB host headroom and trigger a cgroup-OOM (it would
  kill Chrome/workers) or host pressure. The H5 constraint stands; if anything the
  12 GiB cap makes a big in-process graph job a guaranteed kill.
- **Design the periodic re-cluster job for this reality:** stream edges on disk
  (don't hold the full graph in RAM), or run it as a **separate short-lived
  process / off-box / off-peak**, or on a **subgraph + incremental** basis. Same
  for the Phase-0 re-embed — schedule it off-peak, bounded.
- **The pair-scorer (`analytics.pair_scores`) is the cheap part** and is fine
  on-box; the expensive, RAM-hungry part is the community detection — that's the
  one to keep off the hot path.
- If steady-state genuinely needs more, the honest answer is **+16 GiB RAM or a
  dedicated worker box** — a capacity decision, not a code fix.

## Net
Memory is safe and self-defending now (reaper + cgroup cap + DB shield + graceful
worker recycle). Your **architecture assumption from H5 holds**: build the
clustering re-cluster job streamed / off-heap / off-peak — never as a big in-RAM
graph load on this 15 GiB box.
