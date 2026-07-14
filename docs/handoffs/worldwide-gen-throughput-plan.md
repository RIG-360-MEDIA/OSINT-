# worldwide_gen_v2 — throughput + HELD plan

## Current config (measured on the box)
- **Cron:** `*/30 * * * *` → `worldwide_gen_v2.py --write --limit 20`, `timeout 25m`, `flock` (no overlap).
- **Writer model:** `GEN_MODEL=qwen2.5:32b` on local Ollama `172.30.0.1:11434` → **DOWN (HTTP 000)** — the 32b box (`100.96.25.59`) is unreachable, so every writer call eats a connect-timeout before falling back to cloud.
- **Verifier:** `llama-3.3-70b-versatile` (Groq/Cerebras cloud).
- **Key pools:** **Cerebras 37 + Groq 20 = 57** — almost entirely idle.
- **Per-story cascade:** build_brief → writer → topic → verifier(70b) → repair (`repair_rounds` cap **1**) → re-verify.
- **Throughput:** 139 gen/24h (5.8/hr), 84 PUBLISHABLE (3.5/hr) = **~2.9 stories per 30-min run** — far under `--limit 20`, i.e. **runs hit the 25-min timeout with only a handful done.**
- **Processing is SEQUENTIAL** (per-story `await` chain, no `asyncio.gather`/Semaphore over the cluster batch) → this is the wall-clock killer.

## Bottleneck diagnosis
1. **PRIMARY — sequential processing.** One story at a time through a 3–4-call LLM cascade while **57 keys sit idle**. A 25-min run finishes ~3–6 stories. `--limit`/cadence are NOT the constraint (runs never reach 20).
2. **SECONDARY — dead 32b writer.** Every story pays a connect-timeout to the down endpoint before cloud fallback → fixed per-story latency tax.
3. **Wall-clock split:** writer(timeout+cloud) + **2× 70b verifier passes** (verify + re-verify after repair). The 70b verify/repair is the bulk.

## A) Throughput — exact knob changes
1. **Parallelize (the one change that matters):** wrap the cluster batch in `asyncio.gather` with `Semaphore(8)`. 57 keys support 8-concurrent trivially → **~6–8× wall-clock**. Confirm the main loop, then batch it.
2. **Fix the writer endpoint:** repoint `GEN_MODEL`/`OLLAMA_ENDPOINTS` off the dead 32b — either revive `100.96.25.59`, point at a live Ollama box, **or set the writer to Cerebras directly** (fast, 37 keys). Removes the timeout tax.
3. **Then** (only if needed): keep `*/30`; bump `--limit 40` for ~1 day to chew the 85-cluster backlog, then back to 20. Cadence↑ alone is pointless until #1 lands.

**Target:** **~7/hr PUBLISHABLE** clears the 85 backlog + holds 85/day within ~24h. Parallelism lifts generation capacity to ~15–20/hr; combined with the HELD fix below, publishable clears with margin.
**Cost delta: ≈ zero.** Parallelism reuses idle keys (same tokens, faster). Writer already falls to cloud today, so repointing just removes wasted timeouts. Verifier fix is free/near-free.

## B) HELD audit (measured, last 24h)
**100% of holds are `verify: N unresolved`** — the fact-verifier couldn't ground N claims after 1 repair round. No parse-fail / thin-facts / repair-crash in this window.

| Unresolved claims | Held | Share |
|---|---|---|
| **1** | **33** | **63%** |
| 2 | 11 | 21% |
| 3 | 4 | 8% |
| 4 | 3 | 6% |
| 7 | 1 | 2% |
| **Total** | **52** | |

**63% are held for a SINGLE unresolved claim** = the over-hold. Free throughput:
1. **`repair_rounds` 1 → 2** — a 2nd repair pass resolves most single-claim holds. Cost = 1 extra 70b call *only on held stories* (~50/day). Safest, keeps grounding.
2. **Allow ≤1 unresolved** (publish, omitting/footnoting the one claim) → reclassifies ~33 held→PUBLISHABLE with **zero** extra generation.
3. **Recalibrate both ways** — you've seen a parse-fail shipped PUBLISHABLE *and* a 1-unresolved held: tighten the parse-gate, loosen the single-unresolved hold.

**Net:** verifier tuning converts **~33 held → publishable/day (84 → ~117)** with no extra generation.

## Incremental engine (10× cost cut) — sequencing
It regenerates only changed clusters/parts (not full regen), cutting per-story cost ~10×, which lets you raise sustained cadence without a cost blowup. **But don't gate the fix on it.**
- **Now (free, ~1 day to drain):** parallelize (#A1) + fix writer endpoint (#A2) + verifier (`repair_rounds`→2 and/or allow ≤1 unresolved).
- **Then:** ship the incremental engine so a permanently higher cadence stays cheap.

## Do-now checklist
1. Repoint the writer off the dead 32b (revive box, or Cerebras). ← I can do this on the box now.
2. Parallelize the per-story loop (`gather` + `Semaphore(8)`). ← code change in `worldwide_gen_v2.py`.
3. `repair_rounds` 1→2 (or a `HOLD_UNRESOLVED_THRESHOLD=1` allow-through). ← code/env.
4. Backfill run at `--limit 40` for ~24h to drain the 85 backlog, then revert.
