# 06 - Operations Runbook

> **TL;DR.** Recipes for the common ops tasks. Everything assumes
> you're SSH'd into Hetzner: `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154`.

## How to check drain progress

The drain rewrites every article from v1/v2 to v3. To see how far
along it is:

```bash
docker exec rig-postgres psql -U rig -d rig -c \
  "SELECT extraction_version, COUNT(*) FROM articles
   GROUP BY 1 ORDER BY 1;"
```

Expected output shape (numbers change daily):

```
 extraction_version | count
--------------------+--------
 v1                 |  22897
 v3                 |  84031
```

Watch the v3 count rise — should climb at ~100-300/hour in
LOCAL_ONLY mode, ~500-1500/hour in MIXED mode with full Cerebras
quota.

## How to restart the drain — MIXED mode

MIXED uses Cerebras + Groq + Ollama with the watchdog managing
auto-flips.

```bash
# Inside rig-backend container
docker exec rig-backend bash -c '
  export LOCAL_LLM_ENABLED=1
  export LOCAL_LLM_PRIMARY=1
  unset LLM_LOCAL_ONLY
  nohup python3 -m backend.tasks.substrate.semantic_repass \
    > /tmp/drain.log 2>&1 &
  echo "drain PID=$!"
'
```

Then ensure the watchdog is running (see "How to read watchdog log"
below).

## How to restart the drain — Ollama-only mode

LOCAL_ONLY ignores cloud quota entirely. Use when Cerebras TPD is
exhausted OR when you want to verify Ollama is healthy in isolation.

```bash
docker exec rig-backend bash -c '
  export LOCAL_LLM_ENABLED=1
  export LLM_LOCAL_ONLY=1
  nohup python3 -m backend.tasks.substrate.semantic_repass \
    > /tmp/drain.log 2>&1 &
  echo "drain PID=$!"
'
```

## How to check FreshRSS health

```bash
# Inside the container — confirm admin user directory exists
docker exec rig-freshrss ls /config/www/freshrss/data/users/admin/

# Authenticate against the GReader API
docker exec rig-backend bash -c '
  curl -s -X POST http://rig-freshrss:80/api/greader.php/accounts/ClientLogin \
    -d "Email=admin" -d "Passwd=$FRESHRSS_PASSWORD"
'
```

A healthy response is a 3-line body ending with `Auth=...`. A 403
or empty body means the admin user is broken — see
`07-known-issues.md` #1 for recovery.

Count of subscribed feeds (sanity-check after a recreation):

```bash
docker exec rig-backend bash -c '
  curl -s "http://rig-freshrss:80/api/greader.php/reader/api/0/subscription/list?output=json" \
    -H "Authorization: GoogleLogin auth=$AUTH" | jq ".subscriptions | length"
'
```

Should be 574 in steady state.

## How to test scraping end-to-end

Pick a single source URL and run it through the cascade:

```bash
docker exec rig-backend python3 -c '
from backend.collectors.tiered_fetcher import fetch_article
import asyncio
url = "https://www.thehindu.com/news/national/some-article/article123.ece"
r = asyncio.run(fetch_article(url))
print("tier_used:", r.tier_used, "body_len:", len(r.body or ""))
'
```

Should print `tier_used=2` or `3` and `body_len` > 500. If it
crashes or returns `body_len=0`, the source adapter is broken or
the URL is dead.

## How to check Cerebras quota

```bash
# probe_cerebras.py lives at /tmp on Hetzner; it iterates all 27 keys
ssh -i ~/.ssh/rig_hetzner root@178.105.63.154 \
  "python3 /tmp/probe_cerebras.py"
```

Returns a table of (key_index, used_today, remaining, %_remaining).
Aggregate across all keys = total daily budget remaining.

If aggregate < 5% remaining, the watchdog *should* have already
flipped to LOCAL_ONLY — verify by checking `/tmp/drain_watchdog.log`
for a recent "flipping to LOCAL_ONLY" line.

## How to check Groq quota

Groq resets per-minute so the snapshot is less useful, but:

```bash
ssh -i ~/.ssh/rig_hetzner root@178.105.63.154 \
  "python3 /tmp/probe_groq.py"
```

Returns per-key remaining TPM. If many keys are at 0, the pool is
in mass cooldown — typically self-recovers within 60 seconds.

## How to read the watchdog log

```bash
ssh -i ~/.ssh/rig_hetzner root@178.105.63.154 \
  "tail -100 /tmp/drain_watchdog.log"
```

What to look for:

- `mode=MIXED` / `mode=LOCAL_ONLY` lines, with timestamps. A flip
  every ~24 hours (around 00:00 UTC) is normal.
- `restarted drain PID=NNNN` lines. More than 2-3 per day suggests
  the drain script itself is unstable — investigate.
- `cerebras_remaining_pct=X` lines — should reach 100% briefly
  after 00:00 UTC and decline through the day.

## How to spot a stalled drain

Three telltale signals:

1. **PID alive but v3 count flat.** The drain process exists but
   isn't actually processing rows. Most common cause: Ollama
   daemon on TRIJYA-7 died and `LLM_LOCAL_ONLY=1` is set, so
   there's no failover.
2. **`/tmp/drain.log` last write timestamp is old.** Check with
   `ls -l /tmp/drain.log`. If the mtime is >5 minutes old, the
   drain is wedged.
3. **Watchdog log silence.** The watchdog logs at least once per
   minute. If `tail` shows the most recent line is old, the
   watchdog itself died.

Recovery sequence:

```bash
# 1. Kill the wedged drain
ssh ... "pkill -f semantic_repass"

# 2. Verify Ollama is up
curl -s http://100.92.126.27:11434/api/tags | jq

# 3. If Ollama is down, RDP to TRIJYA-7 and restart the OllamaServe
#    scheduled task. Or trigger it remotely if Tailscale allows.

# 4. Restart the drain (see above)
# 5. Verify the watchdog is running:
ps -ef | grep drain_watchdog
```

## How to flush a stale collectors queue

The `collectors` queue is concurrency=1 and a 30-60 minute RSS
scrape can back up Beat-scheduled jobs. If the queue depth is
hundreds of stale tasks, flush selectively:

```bash
docker exec rig-backend celery -A backend.celery_app \
  purge -Q collectors -f
```

Then re-fire the canonical beat tasks manually:

```bash
docker exec rig-backend celery -A backend.celery_app call \
  tasks.collect_rss
docker exec rig-backend celery -A backend.celery_app call \
  tasks.collect_html
```

> **Don't** purge other queues without thinking. Purging `nlp`
> means losing all queued substrate work since the last successful
> drain commit. Purging `relevance` means re-scoring entire
> backlogs.

## How to inspect Celery worker state

```bash
docker exec rig-backend celery -A backend.celery_app inspect \
  registered 2>&1 | head -50

docker exec rig-backend celery -A backend.celery_app inspect \
  active 2>&1 | head -50

docker exec rig-backend celery -A backend.celery_app inspect \
  reserved 2>&1 | head -50
```

`registered` lists every task name known to each worker.
`active` shows what's currently running. `reserved` is queued.

## How to query the DB ad-hoc

```bash
docker exec rig-postgres psql -U rig -d rig -c "<your SQL here>"
```

Or interactive:

```bash
docker exec -it rig-postgres psql -U rig -d rig
```

## How to follow logs

```bash
# All container logs
docker logs -f rig-backend
docker logs -f rig-freshrss
docker logs -f rig-postgres

# Just the FastAPI side (inside container)
docker exec rig-backend tail -f /tmp/uvicorn.log

# Just a specific Celery worker
docker exec rig-backend tail -f /tmp/celery_nlp.log
```

(Filenames may vary by deploy state — check `/start.sh` for the
actual paths.)

## How to restart a container without rebuilding

```bash
docker restart rig-backend
docker restart rig-frontend
docker restart rig-freshrss
```

> **Reminder.** `rig-backend` and `rig-frontend` do **not**
> bind-mount `site-packages` / `node_modules`. Editing a
> `requirements.txt` / `package.json` on the host and restarting
> the container will not pick up new deps. You must
> `docker compose build` (or `docker compose up -d --build <svc>`)
> for dep changes to land.

## How to deploy a backend code change

```bash
# On laptop
git push origin <branch>

# On Hetzner
ssh ...
cd /root/rig
git fetch origin
git checkout <branch>
git pull
docker compose -f infrastructure/docker-compose.yml \
  up -d --build rig-backend
```

Then verify:

```bash
docker logs --tail 50 rig-backend
```

## How to reset super-admin bootstrap

Super-admins are seeded from `SUPER_ADMIN_EMAILS` env var (CSV) on
every backend boot. To add an email:

```bash
# Edit infrastructure/.env on Hetzner
ssh ... "nano /root/rig/infrastructure/.env"
# Add to SUPER_ADMIN_EMAILS
docker restart rig-backend
```

See `docs/RUNBOOK_SUPER_ADMIN_BOOTSTRAP.md` for the full procedure.

## See also

- `05-llm-infrastructure.md` — the LLM pool internals.
- `07-known-issues.md` — symptoms + recovery for the most common
  failures.
- `docs/RUNBOOK_DEPLOY.md` — the full deploy runbook (more
  detailed than this section).
- `docs/RUNBOOK_SUPER_ADMIN_BOOTSTRAP.md` — RBAC bootstrap.
