# Pause / Resume RSS Ingest Runbook

> **Why this exists**
> When the D1 catch-up (or any other LLM-heavy backfill) is running, new RSS
> ingest competes for the same Ollama GPU. Pausing collectors frees 100% of
> the LLM capacity for the backfill. New articles arriving during the pause
> are NOT lost — they queue up at the RSS source side and get picked up when
> we resume.

---

## How RSS ingest is paused right now (2026-05-27 ~18:15 UTC)

We sent `SIGSTOP` to the 4 collectors worker processes inside `rig-backend`.
SIGSTOP **freezes** the process — it stays alive, just paused. Reverses cleanly with `SIGCONT`.

### Exact PIDs paused (as of pause time)

```
PID  10  →  parent collectors worker
PID  38  →  fork worker 1
PID  43  →  fork worker 2
PID  53  →  fork worker 3
```

These PIDs may change if rig-backend restarts. The COMMAND signature
(`celery worker --queues=collectors --concurrency=3`) is stable — use it to
find the live PIDs at resume time.

### Effect of the pause

| Component | State |
|---|---|
| RSS collectors (collect_rss, collect_rss_direct, collect_html) | ⛔ paused — fetching 0 new articles |
| Substrate workers (nlp queue, concurrency=4) | ✅ running normally |
| D1 catch-up | ✅ continues at full speed (no contention) |
| Beat scheduler | ✅ still firing collect_rss tasks every 15 min, but they just queue up — no worker to consume them |
| Journalist task | ✅ still running |
| Database | unchanged |

**Queue backlog risk:** beat keeps queuing collect_rss tasks. After ~24h paused,
~96 unprocessed tasks pile up in the `collectors` Redis queue. Harmless but
worth resume-purging if pause lasts > 1 day.

---

## ✅ How to RESUME ingest (when D1 is done OR you change your mind)

### Step 1 — find current collectors PIDs

```bash
ssh -i ~/.ssh/rig_hetzner root@178.105.63.154 \
  'docker exec rig-backend bash -c "ps -eo pid,cmd | grep \"queues=collectors\" | grep -v grep"'
```

This prints the live PIDs (typically 4 of them: 1 parent + 3 forks).

### Step 2 — SIGCONT them

```bash
ssh -i ~/.ssh/rig_hetzner root@178.105.63.154 'docker exec rig-backend bash -c "
PIDS=\$(ps -eo pid,cmd | grep \"queues=collectors\" | grep -v grep | awk \"{print \\\$1}\")
for p in \$PIDS; do kill -SIGCONT \$p && echo resumed \$p; done
"'
```

### Step 3 — verify ingest resumed

```bash
ssh -i ~/.ssh/rig_hetzner root@178.105.63.154 \
  'docker exec rig-postgres psql -U rig -d rig -tAc "SELECT count(*) FROM articles WHERE collected_at > NOW() - INTERVAL '"'"'2 minutes'"'"';"'
```

Should show non-zero new articles arriving within 2-5 min as the queue drains.

### Step 4 (optional) — purge stale queued tasks if pause lasted > 24h

```bash
ssh -i ~/.ssh/rig_hetzner root@178.105.63.154 \
  'docker exec rig-backend celery -A backend.celery_app purge -f -Q collectors'
```

This drops any old queued `collect_rss` tasks so we start fresh on the next
beat tick.

---

## ⚠️ What does NOT work to pause ingest

| Approach | Why we DIDN'T use it |
|---|---|
| Edit `celery_app.py` to comment out beat entries | Requires container restart, slower, more invasive |
| `docker stop rig-backend` | Kills D1 catch-up too — we want substrate to keep working |
| `docker exec rig-backend celery control cancel_consumer collectors` | Worked unreliably last time we tried — control plane sometimes timed out |
| `rate_limit 0/h` via celery control | Not persistent across restarts; same timeout issues |

`SIGSTOP` is the cleanest because:
- Instant (no waiting on signals to propagate)
- Reversible (SIGCONT brings it back exactly where it was)
- Doesn't lose worker state (the 100 in-flight tasks just freeze mid-step)
- Survives DB / Redis reconnections after resume

---

## ⚠️ Survives container restart? NO

If `rig-backend` restarts (manual, OOM, or docker compose), the SIGSTOP state
is lost. Workers come back running and ingest resumes automatically.

If you want pause to survive restart, edit `start.sh` to comment out the
collectors-worker block. We're NOT doing that now because we expect to
resume soon.

---

## When you decide to resume

Just tell me **"resume ingest"** and I'll run the 3 steps above + check
the article count climbs back up. Estimated time to verify resume: 5 min.

---

_Last paused: 2026-05-27 ~18:15 UTC by Claude via SIGSTOP._
_Resume command pattern documented above. PIDs may differ on resume — use the ps pattern to find live ones._
