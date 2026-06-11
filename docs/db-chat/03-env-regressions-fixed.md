# Two silent env regressions — patched, awaiting recreate

Both regressions live in `/root/rig/infrastructure/` on the Hetzner
host. Both have been corrected **in-file**. Neither is active in the
**running** container yet — they activate the next time `rig-backend`
is recreated with `--env-file .env.prod`.

## Regression 1 — `LOCAL_LLM_ENABLED` orphan

### Symptom
LLM pool kept probing Ollama / Trijya slots that have been offline for
6+ days. Each substrate batch ate ~10s in retry+cooldown before falling
to Cerebras.

### Root cause
The flag was set in `.env.prod` a week ago **and** wired into
`osint-backend.environment:`, but the patch missed `rig-backend.environment:`.
There is no `env_file:` directive — every env var must be explicitly
interpolated per service.

### Fix
`infrastructure/docker-compose.yml`, line 100, in `rig-backend.environment:`:

```yaml
    GROQ_API_KEYS: ${GROQ_API_KEYS:-}
    CEREBRAS_API_KEYS: ${CEREBRAS_API_KEYS:-}
    LOCAL_LLM_ENABLED: ${LOCAL_LLM_ENABLED:-1}   # 0 disables Trijya/Ollama slots in the LLM pool
    DOSSIER_ENABLED: ${DOSSIER_ENABLED:-false}
```

Default `1` is intentional: if `.env.prod` is missing, behave like the
old code. With `.env.prod` present (`LOCAL_LLM_ENABLED=0`), the var
renders as `"0"` in `docker compose config` for both services.

### Backup
`infrastructure/docker-compose.yml.bak-20260604-llm-passthrough`

### Verification
```
docker compose --env-file .env.prod config | grep -A1 rig-backend: | grep LOCAL_LLM
# → LOCAL_LLM_ENABLED: "0"
```

## Regression 2 — stale `YOUTUBE_PROXY_URL`

### Symptom
Every transcript fetch since the 14:48 recreate failed with
`SOCKSHTTPSConnection ... Connection closed unexpectedly` against
`172.30.0.1:1081` (Docker bridge gateway).

### Root cause
This morning we tested a SOCKS5 proxy approach for YouTube IP-bypass,
ran a sidecar container (`rig-ipv6-socks`) on the bridge gateway, and
set `YOUTUBE_PROXY_URL=socks5h://172.30.0.1:1081` in `.env.prod`. We
then **reverted the code** that would have used it, but **didn't scrub
the env var**. The SOCKS container was removed, the env var stayed.

`docker-compose.yml` line 111 passes any value of `YOUTUBE_PROXY_URL`
through unconditionally:
```yaml
YOUTUBE_PROXY_URL: ${YOUTUBE_PROXY_URL:-}
```
So the 14:48 recreate baked the dead-proxy address into the running
container. `_get_proxy_url()` in `youtube_collector.py:458` returned it.
Every captions request went to the dead proxy and timed out.

### Fix
`.env.prod` line 46, commented out:

```
# YOUTUBE_PROXY_URL=  # commented 2026-06-04: SOCKS experiment was reverted, stale value caused transcript fetches to fail
```

Compose-side passthrough left untouched — when the env var is absent,
the `${VAR:-}` default makes it an empty string, and
`_get_proxy_url()` returns `None`.

### Backup
`infrastructure/.env.prod.bak-20260604-proxy-scrub`

### Verification (post-recreate)
```
docker exec rig-backend env | grep PROXY    # should be empty
```

## When to apply

Both fixes are **inert** in the running container. They activate the
next time someone runs:

```bash
cd /root/rig/infrastructure
docker compose --env-file .env.prod up -d --force-recreate rig-backend
```

### Cold-start deadlock warning
Per banked memory: `process_broadcast` reliably hangs as the first
task after a worker restart due to an asyncio Lock + Celery prefork
interaction in `groq_manager`. **Before invoking any substrate task
after recreate, warm the worker with ping tasks first.** Tooling for
this is in the operations runbook.

## How to prevent the same pattern next time

The shared compose pattern is asymmetric env var interpolation per
service. Add this to the runbook:

> **Before declaring an env var "set," verify it appears in the output
> of `docker compose config | grep <VAR>` against EVERY service that
> should read it.**

A 5-line `make` target or shell function that lists every env var
referenced by each service block + cross-checks against `.env.prod`
would have caught both regressions instantly. Future work.
