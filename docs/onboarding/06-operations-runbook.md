# 06 - Operations Runbook

> **TL;DR.** Recipes for the common ops tasks. Everything assumes
> you're SSH'd into Hetzner:
> `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154`.
>
> **Note 2026-05-28.** Procedures updated for: integer
> `extraction_version`, `run_corpus_pass.py` drain (replaces legacy
> `semantic_repass.py`), atomic-claim recovery, pause/resume
> collectors via SIGSTOP. Trijya is Windows — admin scripts use
> PowerShell.

---

## How to check drain progress

The drain rewrites every article to `extraction_version=3`. To see
where it stands:

```bash
docker exec rig-postgres psql -U rig -d rig -c \
  "SELECT extraction_version, substrate_status, COUNT(*) FROM articles
    GROUP BY 1,2 ORDER BY 1 DESC, 2;"
```

Expected output shape:
```
 extraction_version | substrate_status | count
--------------------+------------------+--------
                  3 | ok               |  84031
                  3 | extract_failed   |    312
                  0 | pending          |  22897
                    | NULL             |   1503
```

Watch the `(3, ok)` count rise. In MIXED mode (Cerebras quota fresh):
500-1500/hr. In LOCAL_ONLY mode (Cerebras exhausted): 100-300/hr.

For real-time rate over last 5 min:
```bash
docker exec rig-postgres psql -U rig -d rig -c \
  "SELECT COUNT(*) AS last_5m FROM articles
    WHERE substrate_processed_at > NOW() - INTERVAL '5 min';"
```

---

## How to restart the drain (current method — D19, 4 parallel)

The drain uses `run_corpus_pass.py` (NOT the legacy
`semantic_repass.py`). Atomic-claim via `FOR UPDATE SKIP LOCKED` lets
multiple instances safely run in parallel.

### Single drain (simple case)

```bash
docker exec -d rig-backend bash -c '
  python -m backend.tasks.substrate.run_corpus_pass --limit 30000 \
    > /var/log/d1_drain.log 2>&1
'
```

### 4 parallel drains (production drain pattern)

```bash
for L in A B C D; do
  docker exec -d rig-backend bash -c \
    "python -m backend.tasks.substrate.run_corpus_pass --limit 30000 \
      > /var/log/d1_drain_$L.log 2>&1"
done
sleep 4
docker exec rig-backend ps -eo pid,etime,cmd | grep run_corpus_pass | grep -v grep
```

Should show 4 (PID, uptime, cmd) rows.

### Force LOCAL_ONLY (Cerebras exhausted)

```bash
docker exec -d -e LLM_LOCAL_ONLY=1 -e OLLAMA_MODEL=qwen3:14b \
  rig-backend bash -c '
    python -m backend.tasks.substrate.run_corpus_pass --limit 30000 \
      > /var/log/d1_drain_local.log 2>&1
  '
```

### Kill drains cleanly

```bash
docker exec rig-backend pkill -f run_corpus_pass
sleep 3
# Recover orphaned 'processing' rows from hard-killed drains
docker exec rig-postgres psql -U rig -d rig -c \
  "UPDATE articles SET substrate_status='pending'
    WHERE substrate_status='processing'
      AND substrate_processed_at IS NULL;"
```

---

## How to pause/resume ingest (collectors workers)

Useful during heavy backfill to free Ollama capacity.

### Pause via SIGSTOP

```bash
ssh -i ~/.ssh/rig_hetzner root@178.105.63.154 'docker exec rig-backend bash -c "
PIDS=\$(ps -eo pid,cmd | grep \"queues=collectors\" | grep -v grep | awk \"{print \\\$1}\")
for p in \$PIDS; do kill -SIGSTOP \$p && echo paused \$p; done
"'
```

Beat keeps firing `collect_rss` every 15min, but tasks queue up
harmlessly (no consumer).

### Resume via SIGCONT

```bash
ssh -i ~/.ssh/rig_hetzner root@178.105.63.154 'docker exec rig-backend bash -c "
PIDS=\$(ps -eo pid,cmd | grep \"queues=collectors\" | grep -v grep | awk \"{print \\\$1}\")
for p in \$PIDS; do kill -SIGCONT \$p && echo resumed \$p; done
"'
```

Workers drain backlog. If pause was >24h, purge stale tasks first:

```bash
docker exec rig-backend celery -A backend.celery_app purge -f -Q collectors
```

**Important.** SIGSTOP state does NOT survive container restart. If
`rig-backend` restarts (manual or OOM), workers come back running.
Full runbook: `docs/PAUSE_INGEST_RUNBOOK.md`.

---

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

A healthy response is a 3-line body ending with `Auth=...`. A 403 or
empty body = admin user broken — recovery in `07-known-issues.md` E1.

Count of subscribed feeds (sanity-check after recreation):

```bash
docker exec rig-backend bash -c '
  curl -s "http://rig-freshrss:80/api/greader.php/reader/api/0/subscription/list?output=json" \
    -H "Authorization: GoogleLogin auth=$AUTH" | jq ".subscriptions | length"
'
```

Should be 574 in steady state.

---

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

Should print `tier_used=1`, `2`, or `3` and `body_len` > 500. **Note:**
tier 4 (Playwright) is currently DISABLED (`PLAYWRIGHT_ENABLED=false`)
— never expect tier_used=4 today. If a source needs Playwright, it'll
fail through tier 3.

---

## How to check Cerebras / Groq quota

```bash
# Probe scripts (live at /tmp on Hetzner; copy from repo if missing)
docker exec rig-backend python /tmp/probe_cerebras_keys.py
docker exec rig-backend python /tmp/probe_groq_keys.py
```

`probe_cerebras_keys.py` iterates all 27 keys, reports
`(key_index, used_today, remaining, %_remaining)`. Aggregate < 5% =
watchdog should have already flipped to LOCAL_ONLY.

If probes are missing on Hetzner, copy from
`scripts/audit/probe_{cerebras,groq}_keys.py`.

### Reset Cerebras model identifier (if Cerebras retires another tag)

Cerebras retired `qwen-3-235b-a22b-instruct-2507` on 2026-05-27. List
currently-available models with:

```bash
docker exec rig-backend python -c '
import httpx
from backend.nlp.groq_client import _CEREBRAS_KEYS
r = httpx.get("https://api.cerebras.ai/v1/models",
              headers={"Authorization": f"Bearer {_CEREBRAS_KEYS[0]}"})
for m in r.json()["data"]:
    print(m["id"])
'
```

If our `_GROQ_TO_CEREBRAS_MODEL` mapping target is missing from that
list, edit `backend/nlp/groq_client.py` and redeploy.

---

## How to spot a stalled drain

Three telltale signals:

1. **PID alive but `(3, ok)` count flat.** Drain exists but isn't
   processing. Most common cause: Ollama daemon on Trijya died and
   `LLM_LOCAL_ONLY=1` is set, so no failover.

2. **`/var/log/d1_drain*.log` mtime is old.** Check with
   `ls -l /var/log/d1_drain*.log`. If mtime >5min old, drain wedged.

3. **`substrate_status='processing'` count growing without 'ok'
   growing.** Articles are being claimed but never finished. Likely a
   hung LLM call. Recover:
   ```bash
   docker exec rig-backend pkill -f run_corpus_pass
   sleep 3
   docker exec rig-postgres psql -U rig -d rig -c \
     "UPDATE articles SET substrate_status='pending'
       WHERE substrate_status='processing'
         AND substrate_processed_at IS NULL;"
   # Then relaunch drain — see above
   ```

---

## How to verify Trijya / Ollama health

```bash
# From Hetzner via Tailscale
curl -s http://100.92.126.27:11434/api/version
curl -s http://100.92.126.27:11434/api/ps | jq
```

`api/version` returns `{"version":"0.23.4"}` if healthy.
`api/ps` returns currently-loaded models + VRAM usage. With our 8-slot
pool, expect qwen3:14b loaded (~10.7 GB VRAM).

### How to re-tune Ollama on Trijya (requires admin access on Trijya)

If you have RDP/console access to Trijya as Admin: paste the script
in `scripts/deploy/trijya_ollama_tune.ps1` into a PowerShell
elevated console. Sets `OLLAMA_NUM_PARALLEL=8`, `FLASH_ATTENTION=1`,
`KV_CACHE_TYPE=q8_0`, and restarts the Ollama service.

**Do NOT** SSH to Trijya with the password from
`Connection_Guide.pdf` — security policy forbids AI from using
passwords. Hand the script to the user, they paste it themselves.

---

## How to flush a stale collectors queue

`worker-collectors` is concurrency=3 (D44 — was 1). A 30-60min RSS
scrape can still back up Beat-scheduled jobs. If queue depth is
hundreds of stale tasks:

```bash
docker exec rig-backend celery -A backend.celery_app \
  purge -Q collectors -f
```

Then re-fire canonical beat tasks manually:

```bash
docker exec rig-backend celery -A backend.celery_app call \
  tasks.collect_rss
docker exec rig-backend celery -A backend.celery_app call \
  tasks.collect_html
```

> **Don't** purge other queues without thinking. Purging `nlp` means
> losing all queued substrate work. Purging `relevance` means
> re-scoring entire backlogs.

---

## How to inspect Celery worker state

```bash
docker exec rig-backend celery -A backend.celery_app inspect \
  registered 2>&1 | head -50

docker exec rig-backend celery -A backend.celery_app inspect \
  active 2>&1 | head -50

docker exec rig-backend celery -A backend.celery_app inspect \
  reserved 2>&1 | head -50
```

**Note.** `inspect` sometimes returns `"No nodes replied"` even when
workers are alive — celery's control plane has known reliability
issues. Cross-check with `ps -ef | grep celery`.

---

## How to query the DB ad-hoc

```bash
docker exec rig-postgres psql -U rig -d rig -c "<your SQL here>"
```

Or interactive:

```bash
docker exec -it rig-postgres psql -U rig -d rig
```

### Useful one-liners

```sql
-- Country breakdown of last 24h articles (post-migration 075)
SELECT source_country, COUNT(*) FROM articles
 WHERE collected_at > NOW() - INTERVAL '24 hours'
 GROUP BY 1 ORDER BY 2 DESC;

-- SPO completeness on recent claims (post-D1)
SELECT COUNT(*) total, COUNT(predicate) pred, COUNT(object_text) obj
  FROM article_claims
 WHERE extracted_at > NOW() - INTERVAL '1 hour';

-- Effective event date distribution (post-migration 072)
SELECT EXTRACT(YEAR FROM effective_event_date) AS yr, COUNT(*)
  FROM article_events
 WHERE effective_event_date IS NOT NULL
 GROUP BY 1 ORDER BY 1 DESC LIMIT 10;
```

---

## How to follow logs

```bash
# All container logs
docker logs -f rig-backend
docker logs -f rig-freshrss
docker logs -f rig-postgres

# Just the FastAPI side (inside container)
docker exec rig-backend tail -f /tmp/uvicorn.log

# Just a specific drain (post-D19 4-parallel pattern)
docker exec rig-backend tail -f /var/log/d1_drain_A.log
```

---

## How to restart a container without rebuilding

```bash
docker restart rig-backend
docker restart rig-frontend
docker restart rig-freshrss
```

> **Reminder.** `rig-backend` and `rig-frontend` do NOT bind-mount
> `site-packages` / `node_modules`. Editing `requirements.txt` /
> `package.json` on the host and restarting won't pick up new deps.
> You must `docker compose build` for dep changes to land.

---

## How to deploy a backend code change

```bash
# On laptop
git push origin <branch>

# On Hetzner
ssh -i ~/.ssh/rig_hetzner root@178.105.63.154
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

### Hot-patch single file (faster than rebuild)

For small fixes during sessions, you can `docker cp` and re-import:

```bash
scp -i ~/.ssh/rig_hetzner backend/nlp/groq_client.py \
  root@178.105.63.154:/root/rig/backend/nlp/groq_client.py
ssh -i ~/.ssh/rig_hetzner root@178.105.63.154 \
  "docker cp /root/rig/backend/nlp/groq_client.py \
   rig-backend:/app/backend/nlp/groq_client.py"
# Drains running at the time keep their old module loaded; restart drains
# to pick up the change.
```

---

## How to apply a new migration

```bash
scp -i ~/.ssh/rig_hetzner scripts/migrations/0XX_*.sql \
  root@178.105.63.154:/tmp/0XX.sql
ssh -i ~/.ssh/rig_hetzner root@178.105.63.154 "
  docker cp /tmp/0XX.sql rig-postgres:/tmp/0XX.sql
  docker exec rig-postgres psql -U rig -d rig -v ON_ERROR_STOP=1 -f /tmp/0XX.sql
"
```

Check `migrations/` numbered order — current latest is **075**
(source.country + article.source_country trigger, 2026-05-28).

---

## How to reset super-admin bootstrap

Super-admins are seeded from `SUPER_ADMIN_EMAILS` env var (CSV) on
every backend boot:

```bash
ssh ... "nano /root/rig/infrastructure/.env"
# Add to SUPER_ADMIN_EMAILS
docker restart rig-backend
```

See `docs/RUNBOOK_SUPER_ADMIN_BOOTSTRAP.md`.

---

## See also

- `05-llm-infrastructure.md` — LLM pool internals.
- `07-known-issues.md` — symptoms + recovery for common failures.
- `09-todos-prioritized.md` — D8 publish_at anchor, D13 cron fix.
- `docs/PAUSE_INGEST_RUNBOOK.md` — full SIGSTOP/SIGCONT procedure.
- `docs/RUNBOOK_DEPLOY.md` — full deploy runbook.
- `scripts/deploy/trijya_ollama_tune.ps1` — Windows PS admin script.
- `11-session-2026-05-28-learnings.md` — every fix shipped today.
