# THE root cause of "failing again and again" — and the permanent fix (2026-06-05)

This is the most important operational finding of the whole session. Read
it before touching `rig-backend` ever again.

## The one-line cause

`docker compose up -d --force-recreate rig-backend` **without `--no-deps`**
silently recreates **rig-postgres too**, which kills every live DB
connection, which breaks any service holding a naive connection pool.

Proven by dry-run:
```
WITHOUT --no-deps:                 WITH --no-deps:
  rig-postgres  Recreate  ❌         rig-backend  Recreate  ✓
  rig-postgres  Recreated           rig-backend  Recreated
  rig-backend   Recreate            (postgres untouched)
  rig-backend   Recreated
```

## Why it recreates Postgres

After `docker-compose.yml` was edited today (the `LOCAL_LLM_ENABLED`
passthrough at line 100), compose's config-hash for the project drifted.
Any `up` that includes Postgres as a dependency (which a plain
`up rig-backend` does) "converges" it by replacing the container. It was
NOT a crash, NOT OOM, NOT a Postgres fault:
- `RestartCount: 0`, `OOMKilled: false`, `ExitCode: 0`
- `Created` timestamp = fresh each recreate → container replaced by compose
- Postgres uses ~543 MB of 15 GB → never memory-pressured

## The cascade it caused (5+ times today)

```
recreate rig-backend (no --no-deps)
  → compose ALSO recreates rig-postgres
    → fresh Postgres = all DB connections die
      → naive pools break:
          - collectors (asyncpg)  → "connection is closed" → scraping stalls
          - mc-backend (psycopg2) → 33/34 dashboard checks fail
      → user sees "failing again and again"
```

## THE RULE (must survive /clear — also add to MEMORY + onboarding runbook)

> **Always recreate rig-backend with `--no-deps`:**
> ```
> docker compose --env-file .env.prod up -d --force-recreate --no-deps rig-backend
> ```
> `--no-deps` = "restart only rig-backend; do not touch its dependencies."
> Without it, Postgres gets bounced and everything downstream breaks.

Combined with the already-banked rule:
> Always pass `--env-file .env.prod` (or `${POSTGRES_PASSWORD}` resolves
> empty → broker auth fails).

Canonical safe recreate command:
```
cd /root/rig/infrastructure
docker compose --env-file .env.prod up -d --force-recreate --no-deps rig-backend
```

## Defense-in-depth fixes shipped today (so a *legitimate* PG bounce is harmless)

Even with `--no-deps`, a real Postgres restart (host reboot, version
upgrade) will eventually happen. Both connection-pool consumers now
self-heal:

1. **Collectors (asyncpg)** — `setup=SELECT 1` checkout validator +
   `max_inactive_connection_lifetime=60` + retry-on-stale-conn.
   Files: `backend/collectors/{direct_rss_collector,rss_collector,html_collector}.py`.
   (Shipped earlier 2026-06-05; proven against a real restart.)

2. **mc-backend (psycopg2)** — `/root/rig-mc/backend/app/db.py` rewritten:
   on `OperationalError`/`InterfaceError`, discard the dead connection,
   rebuild the pool once (`_reset_pool`), retry. **Proven**: killed all
   `mc_readonly` connections via `pg_terminate_backend` (= a PG restart)
   and `/verify` self-healed to 34/34 within the same request.
   Backup: `db.py.bak-20260605-pool-resilience`.

## CELERY BEAT does NOT self-heal a broker bounce — manual recovery needed

The connection pools (collectors, mc-backend) self-heal. **Celery beat does
not.** Beat's broker connection runs over Postgres (kombu SQL transport).
When Postgres bounces, beat's connection goes stale and it throws on every
dispatch — *without recovering*:

```
amqp.exceptions.RecoverableConnectionError: channel disconnected
celery.beat.SchedulingError: Couldn't apply scheduled task
    collect-rss-every-15-min: channel disconnected
```

Observed 2026-06-05: a Postgres bounce at 20:33 left beat stuck for ~20 min.
**No scheduled task dispatched** (collect_rss, process-nlp, etc.) → articles
silently stopped (newest stuck, `LAST 15 MIN = 0` on the dashboard) while the
DB and workers looked healthy. The pools self-healed; beat did not.

### Symptom signature
- Dashboard `Live throughput → LAST 15 MIN = 0`, `NEWEST = N min ago` climbing
- `articles.max(collected_at)` frozen, but Postgres healthy + accepting conns
- Logs show repeating `channel disconnected` / `Couldn't apply scheduled task`

### Fix — one clean recreate
```
cd /root/rig/infrastructure
docker compose --env-file .env.prod up -d --force-recreate --no-deps rig-backend
```
This gives beat a fresh broker connection. `--no-deps` ensures Postgres is NOT
bounced again (verified: `pg_postmaster_start_time()` identical before/after),
so the recreate fixes beat without starting a new cascade. Within ~35s,
`channel disconnected` count drops to 0 and beat dispatches normally; trigger
one `tasks.collect_rss` to confirm inserts resume immediately.

### The rule
> After ANY Postgres restart (legitimate or accidental), do a `--no-deps`
> recreate of rig-backend to recover Celery beat — the DB pools recover on
> their own, but beat's broker connection will stay wedged until restarted.

## How to safely TEST pool resilience without bouncing Postgres

```sql
-- kills a service's pooled connections; Postgres stays up, other services untouched
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
 WHERE usename='mc_readonly' AND pid <> pg_backend_pid();
```
Then hit the service. If it self-heals, the resilience works. This is the
safe way to validate — never restart Postgres just to test.

## Net state

- Dashboard: 34/34 green, and now self-heals on any PG bounce.
- Collectors: self-heal on any PG bounce.
- Celery beat: does NOT self-heal — needs a `--no-deps` recreate after any
  PG bounce (see section above).
- The `--no-deps` rule means PG won't be bounced in the first place.
- Three layers of protection where this morning there were zero.

## Recovery order after a Postgres bounce (cheat sheet)

1. Pools (collectors, mc-backend) recover **automatically** — no action.
2. Celery **beat** stays wedged → `--no-deps` recreate of rig-backend.
3. Confirm: `channel disconnected` count = 0, trigger one `tasks.collect_rss`,
   check `articles.max(collected_at)` advances + dashboard `LAST 15 MIN > 0`.
