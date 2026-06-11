# Drain stall — 2026-05-20

## Severity: P0 — every downstream feature (brief, clustering, CM stance, entity FK linking) is starved of fresh data

## What's happening

- Scraping: **healthy**. ~5,500 articles/day, latest is 30 seconds old.
- v3 enrichment: **dead**. Zero v3 articles produced in the last 7+ days.
- Backlog: **28,365 articles** need v3 (~32% of corpus). 8,571 of those are from the last 7 days.

## Root cause (high confidence)

**Ollama on TRIJYA-7 is unreachable from Hetzner.**

```
$ docker exec rig-backend curl -sS -m 6 http://100.92.126.27:11434/api/tags
curl: (28) Connection timed out after 6002 milliseconds
```

The watchdog launches the drain with `LOCAL_LLM_BASE=http://100.92.126.27:11434`. Both modes (MIXED and LOCAL_ONLY) require Ollama. Without it the drain process crashes on first LLM call. Watchdog relaunches every 300s, drain dies again, infinite no-progress loop.

## Evidence

- `/tmp/drain_watchdog.sh` is running (PID 217349, uptime ~20.5 h).
- `pgrep -f semantic_repass` inside `rig-backend` → **zero processes**. The drain isn't actually running.
- Cerebras health: **OK** — 27 keys, "pong" response.
- Groq health: **timeout** (8s, possibly degraded — but not the blocker since Cerebras alone has 27M TPD).
- Tailscale-routed Ollama endpoint: **unreachable**.
- Hetzner-side `rig-backend` container: healthy (uvicorn, beat, 4 worker pools all up).
- Celery `inspect active` returns "no nodes replied" — likely just a heartbeat/broker quirk, workers are visibly running in `ps`.

## Why the watchdog can't self-heal

The watchdog assumes Ollama is reachable. It doesn't check Tailscale or Ollama health before relaunching the drain. So it loops without diagnosing.

Side effect: each invocation of `restart_worker_nlp` doesn't `pkill` the old worker first → duplicate worker processes accumulate (`ps -ef` shows root 9 + root 21 as duplicate `worker-collectors`; same shape for nlp).

## What I won't touch (per project rules)

- `/tmp/drain_watchdog.sh` — explicitly hands-off
- `backend/nlp/groq_client.py` — explicitly hands-off
- Ollama daemon on TRIJYA-7 (`OllamaServe` scheduled task) — cold-start kills in-flight calls

## What needs human action (you)

1. **Bring TRIJYA-7 back online** — check it's powered, Tailscale is up, `OllamaServe` scheduled task is running.
2. From any other Tailscale node: `curl http://100.92.126.27:11434/api/tags` should return a model list. If that works, the watchdog will auto-recover within 5 minutes.
3. After recovery: backlog of 28,365 articles will drain in ~24-48 hours at historical ~600 articles/hour rate.

## What I can do once Ollama is back (or in parallel)

1. Add a Tailscale + Ollama reachability check into the watchdog before each restart attempt — eliminates the silent loop. (Requires user OK to modify `/tmp/drain_watchdog.sh`.)
2. Add a Prometheus-style "drain heartbeat" so we can alert on stalls earlier than 7 days.
3. Proceed with story clustering using fallback fields (`title + lead_text_translated`) — doesn't require v3.

## Related operational debt observed

- Worker duplicates accumulating (root 9 + root 21 are both `worker-collectors --concurrency=1`).
- HTML scraper errors flooding logs: `parsed tree length: 1, wrong data type or not valid HTML` every ~5 sec. Likely one broken source poisoning the `collectors` queue.
- Groq health check timeout — pool may be misconfigured or all 24 keys exhausted.
