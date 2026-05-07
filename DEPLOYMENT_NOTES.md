# RIG Surveillance - Production Deployment Notes

**Server:** rig-prod-sin (despite the "sin" name, hosted in Nuremberg / eu-central per CCX23 stock availability)
**Public IPv4:** 178.105.63.154
**Public URL:** http://178.105.63.154/   (HTTP only - TLS is a deferred TODO)
**Hetzner plan:** CCX23 - 4 dedicated vCPU AMD / 16 GB RAM / 160 GB NVMe / 20 TB transfer / EUR 29.39 per month
**Deployed:** 2026-04-29
**OS:** Ubuntu 24.04.3 LTS, x86_64

---

## Stack (11 containers)

Defined in `infrastructure/docker-compose.prod.yml` (NOT in the source-of-truth `docker-compose.yml`).

| Service | Image | Bind |
|---|---|---|
| rig-postgres | ankane/pgvector | 127.0.0.1:5433 |
| rig-freshrss | linuxserver/freshrss | 127.0.0.1:8081 |
| rig-searxng | searxng/searxng | docker network only |
| rig-backend | rig-backend:prod (FastAPI + 6 Celery workers + Beat) | 127.0.0.1:8000 |
| rig-frontend | rig-frontend:prod (Next.js dev mode) | 127.0.0.1:3000 |
| rig-caddy | caddy:2-alpine (only public-facing service) | 0.0.0.0:80 + 0.0.0.0:443 |
| rig-worldmonitor | rig-worldmonitor:prod | 127.0.0.1:3001 |
| rig-wm-ais-relay | rig-worldmonitor-ais-relay:prod | docker network only |
| rig-wm-redis | redis:7-alpine | docker network only |
| rig-wm-redis-rest | rig-worldmonitor-redis-rest:prod | docker network only |
| rig-wm-seeder | rig-worldmonitor-seeder:prod | docker network only |

---

## Network defenses

1. **Hetzner Cloud Firewall** (named `rig-prod-fw`): inbound TCP 22, 80, 443; ICMP. Outbound unrestricted.
2. **UFW** on the host: same allowlist (defense in depth).
3. **fail2ban** for SSH brute-force protection.
4. **SSH:** key-only (PasswordAuthentication no, PermitRootLogin prohibit-password). Key fingerprint pinned in /root/.ssh/known_hosts on laptop.

---

## Env variables (values live ONLY in /root/rig/infrastructure/.env.prod, chmod 600)

Names only:
POSTGRES_PASSWORD, ENVIRONMENT, SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_ANON_KEY, NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, SUPABASE_JWT_SECRET (HS256 legacy, see Issue 4), SUPER_ADMIN_EMAILS, GROQ_API_KEYS (22 keys), NEXT_PUBLIC_API_URL, NLP_BATCH_SIZE, BRIEF_ARTICLE_LIMIT, GOVT_DEFAULT_SINCE_DAYS, GOVT_PER_PORTAL_CAP, DOSSIER_ENABLED, NEXT_PUBLIC_DOSSIER_ENABLED, SEARXNG_URL, OPENSANCTIONS_API_KEY, OPENCORPORATES_API_KEY, DOSSIER_PER_ADAPTER_TIMEOUT_S, DOSSIER_GDELT_TIMEOUT_S, FRESHRSS_URL/USERNAME/PASSWORD, NEWSDATA_API_KEY, YOUTUBE_API_KEY x3, YOUTUBE_PROXY_URL (empty - host.docker.internal not resolvable on Linux), TWITTER_BEARER_TOKEN, TELEGRAM_BOT_TOKEN/API_ID/API_HASH/SESSION_STRING, ACLED_ACCESS_TOKEN, WM_REDIS_TOKEN, AISSTREAM/FINNHUB/EIA/FRED/NASA_FIRMS/AVIATIONSTACK_API/WM_GROQ_API_KEY/CLOUDFLARE_API_TOKEN/WM_LLM_*

---

## Caddy reverse proxy summary

`infrastructure/Caddyfile`:
- `:80` ingress
- Path matcher `/api/*`, `/health`, `/docs`, `/openapi.json`, `/redoc` -> `rig-backend:8000`
- Everything else -> `rig-frontend:3000` (which itself rewrites `/world-monitor-app/*` to `rig-worldmonitor:8080`)
- gzip + zstd compression
- TLS not configured. Adding a domain + auto-TLS is a 5-minute change once a DNS record exists.

---

## Issues encountered + resolutions

1. **`tr -d "\r"` over SSH deleted all lowercase 'r' AND backslash characters.**
   Cause: bash inside a single-quoted SSH command interprets `"\r"` as the 2-char set `\` + `r` (NOT carriage return), and `tr -d` deletes any char in that set. Wrecked the first .env.prod (`ENVIRONMENT=poduction`, `Nuembeg`, etc.) AND the first docker-compose.prod.yml (`netwoks`, `sevices`).
   Fix: rewrite via PowerShell base64 -> SSH base64 -d -> file. No shell-quoting in the value path.
   Lesson: never use `tr -d "\r"` over SSH; use either `sed 's/\r$//'` OR strip CRLF in PowerShell with `-replace`.

2. **`docker compose ps` warning "POSTGRES_PASSWORD not set" is cosmetic.**
   Comes from running compose subcommands without `--env-file`. The actual `up -d` had the env file, so containers received correct values. Always pass `--env-file .env.prod` on every compose command.

3. **Local DB was initialized at an older snapshot of `scripts/migrations/`.**
   After we restored the local dump on prod, the `users.role` column (added by migration `031_rbac_and_impersonation.sql`) was missing on prod (because local's data did not include it).
   Fix: re-applied just `031_rbac_and_impersonation.sql` on prod (idempotent - uses `IF NOT EXISTS` and `ON CONFLICT DO NOTHING`).

4. **Supabase project had been migrated to "Signing Keys" (ES256/RS256).**
   Backend code only verifies HS256, so every user JWT returned 401. The hosted SUPABASE_SERVICE_KEY was still HS256 (issued before migration), which is why backend->Supabase admin calls worked but inbound user tokens did not.
   Fix: in Supabase Dashboard -> Settings -> JWT Keys, the legacy HS256 key was still listed under "Previously used". Promoted it to Standby, then clicked "Rotate keys" to swap it back to Current. Sessions invalidated and forced re-login.
   Long-term: real fix is to teach the backend to use JWKS. Listed in deferred items.

5. **Next.js dev mode (`npm run dev`) hangs occasionally** after extended idle / memory churn. Symptoms: container "Up" for hours but every request times out at 30s.
   Recovery: `docker compose ... restart rig-frontend` (5 sec).
   Long-term: §9 item - swap to `next build && next start` in Dockerfile.frontend.

6. **`bash: line 1: \xefecho: command not found`** from PowerShell here-string piped to ssh stdin.
   Cause: PowerShell prepends a UTF-8 BOM when streaming strings. The BOM ends up at the very start of the file.
   Fix: encode bytes with `[Text.UTF8Encoding]::new($false)` (no BOM) and base64-transfer; or strip BOM server-side with `tail -c +4`.

---

## Quick reference

```bash
# View running services (always pass --env-file)
cd /root/rig/infrastructure
docker compose -f docker-compose.prod.yml --env-file .env.prod ps

# Restart any service
docker compose -f docker-compose.prod.yml --env-file .env.prod restart <service>

# Tail logs
docker logs -f rig-backend
docker logs -f rig-frontend
docker logs -f rig-caddy

# psql shell on prod DB
docker exec -it rig-postgres psql -U rig -d rig

# Manual backup (uses /root/backup-db.sh)
/root/backup-db.sh

# Pull latest from git + rebuild + restart
/root/deploy.sh

# Free RAM / disk check
free -h && df -h /

# What is the backend actually doing?
docker logs --since 5m rig-backend | tail -50
```

---

## Backup schedule

- Daily at 20:30 UTC (02:00 IST) via cron entry `30 20 * * * /root/backup-db.sh > /var/log/backup-db.log 2>&1`
- Output: `/root/backups/rig-YYYYMMDD-HHMMSS.sql.gz`
- Retention: 7 days (auto-pruned by the backup script via `find -mtime +7`)
- **Offsite backup: TODO.** Hetzner Object Storage is EU-only and not deployed. Until that lands, on-server snapshots only - vulnerable to single-disk failure.
- Restore: `gunzip -c /root/backups/rig-YYYYMMDD-HHMMSS.sql.gz | docker exec -i rig-postgres psql -U rig -d rig`. Stop rig-backend before restore.

---

## Known deferred items (§9 hardening backlog)

In rough priority order:

1. **JWT verification via JWKS** so we can re-enable Supabase Signing Keys (modern, asymmetric). Currently relying on the legacy HS256 rollback. Supabase will eventually remove legacy mode entirely; that is the deadline.
2. **Frontend production build** - replace `npm run dev` with `next build && next start` in `Dockerfile.frontend`. Eliminates the dev-mode hangs and reduces RAM/CPU footprint.
3. **CORS tightening** - the backend `main.py` allowlist is currently localhost-only. Same-origin via Caddy masks this in production, but tighten for defense in depth.
4. **Add domain + Caddy auto-TLS** - move from `http://178.105.63.154/` to `https://<domain>/`. Caddy auto-issues Let's Encrypt certs once an A record exists; trivial config update.
5. **Uvicorn worker count tuning** - currently single-process. Move to `--workers 2` or use gunicorn for better throughput (CCX23 has 4 vCPU).
6. **Container resource limits** in compose - no `mem_limit` / `cpus` set. Backend image is 15.5 GB with LaBSE in-RAM; one runaway worker could OOM the host.
7. **Offsite backups** - see Backup schedule above.
8. **Application-level monitoring + alerting** - no Sentry / Prometheus / uptime check yet. The Hetzner Console gives you basic CPU/RAM graphs but no app metrics.
9. **YouTube proxy** - local used `socks5h://host.docker.internal:40000` which doesn't resolve on Linux Docker. Currently empty in prod. If YouTube transcript pipeline starts getting rate-limited, set up a SOCKS5 proxy and update `YOUTUBE_PROXY_URL`.
10. **Twitter UI un-hide** - data layer is active (TWITTER_BEARER_TOKEN configured) but the UI page is hidden per signals-room policy decision. Re-enable when ready.
11. **CM political-handles seeds and other CM seed data** were carried over from local DB - audit before public demo (CLAUDE.md note about cite-ID guardrails on LLM outputs still applies).

---

## TODO: domain + auto-TLS (when ready)

1. Buy/configure a domain. Add an `A` record pointing to `178.105.63.154`.
2. Edit `infrastructure/Caddyfile`: replace the `:80 {` block with `your.domain {` (no port).
3. `docker compose ... restart rig-caddy`. Caddy auto-fetches a Let's Encrypt cert via HTTP-01 (port 80 already open in firewall) and starts serving HTTPS.
4. Update `NEXT_PUBLIC_API_URL` in `.env.prod` from `http://178.105.63.154` to `https://your.domain`. Restart rig-frontend.
---

## Post-deployment changes (2026-04-29)

### HTTPS via nip.io + Caddy auto-TLS
Plain HTTP did not work in production because the world-monitor app uses crypto.randomUUID, which the browser only exposes in secure contexts (HTTPS or localhost). Solution: free nip.io wildcard DNS (178-105-63-154.nip.io -> 178.105.63.154) + Caddy auto Let's Encrypt cert.
- Public URL: https://178-105-63-154.nip.io/
- HTTP -> HTTPS auto-redirect via Caddy 308.
- Cert auto-renews every ~60 days.
- Swap to a real domain later: edit Caddyfile hostname, update NEXT_PUBLIC_API_URL in .env.prod, restart caddy + frontend.

### Production frontend build
Switched from Dockerfile.frontend (npm run dev) to a new server-side-only Dockerfile.frontend.prod (next build + next start).
- Memory: ~700 MB -> ~95 MB
- HTTP response: ~6 sec first hit -> ~0.3 sec
- N DevTools badge gone, console clean, no more random dev-mode hangs.
- Companion change: added export const dynamic = "force-dynamic" to frontend/src/app/layout.tsx so all pages render per-request (required because /brief and others fetch backend with auth at runtime, which fails during build-time prerender).

Files on server that should be ported to repo for permanence:
1. frontend/src/app/layout.tsx - added one line plus comment header.
2. infrastructure/Dockerfile.frontend.prod - new file.
3. infrastructure/docker-compose.prod.yml - server-only, never commit.

### WM iframe routing in Caddy
WM ships HTML with absolute /assets/* paths and browsers strip Referer from ES module sub-requests. Solution: explicit Caddy routes for /assets/*, /manifest.webmanifest, /icons/*, /robots.txt, /sitemap.xml, /_vercel/* directly to rig-worldmonitor. Frontend does not claim any of these paths so no conflict.

### Supabase JWT mode rolled back
Project had been migrated to Signing Keys (ES256). Backend code only verifies HS256. In Supabase Dashboard -> Settings -> JWT Keys, the legacy HS256 secret was rotated back to Current. Supabase will eventually deprecate legacy mode. Real fix is the deferred §9 item: backend JWT-via-JWKS verification.

### Supabase Auth allow-list (still TODO)
For password-reset / email-confirmation links to work, update in Supabase Dashboard -> Authentication -> URL Configuration:
- Site URL: https://178-105-63-154.nip.io
- Additional Redirect URLs: https://178-105-63-154.nip.io/**

Password login itself works without this.

### Updated quick reference

Public site: https://178-105-63-154.nip.io/

Recreate frontend after env or Dockerfile change:
docker compose -f /root/rig/infrastructure/docker-compose.prod.yml --env-file /root/rig/infrastructure/.env.prod up -d --force-recreate rig-frontend

Full rebuild + recreate (after frontend code change):
docker compose -f /root/rig/infrastructure/docker-compose.prod.yml --env-file /root/rig/infrastructure/.env.prod build rig-frontend
docker compose -f /root/rig/infrastructure/docker-compose.prod.yml --env-file /root/rig/infrastructure/.env.prod up -d --force-recreate rig-frontend