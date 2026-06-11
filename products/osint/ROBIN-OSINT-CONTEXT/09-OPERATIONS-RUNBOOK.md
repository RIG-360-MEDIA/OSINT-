# 09 — Operations Runbook (exact commands + landmines)

> Host: Hetzner `178.105.63.154`. All `ssh`/`scp` use `-i ~/.ssh/rig_hetzner`.

## ⚠️ LANDMINES (read before deploying)
1. **`osint-backend` uses the DEFAULT `.env`. NEVER `--env-file .env.prod`.**
   `.env` and `.env.prod` have different `ANALYTICS_DB_PASSWORD`; using the wrong
   one makes every DB call fail (`/ready` → 500). `rig-backend` is the opposite —
   it uses `--env-file .env.prod`.
2. **After editing backend Python:** `python -m py_compile <file>` locally, AND
   run the validation script (below) in the container before calling it done. A
   closure/typo bug will 500 the endpoint.
3. **`/root/rig/` may diverge from your local clone.** `diff` before overwriting a
   whole file; prefer in-place patches for `celery_app.py`-type files.
4. **Never run raw `yt-dlp` from Hetzner** (IP reputation). Use the task path.
5. **Never print/commit secrets.** `secrets/` is git-ignored.

## Deploy osint-backend (FastAPI, BAKED image)
```bash
# 1) copy changed files into the host build context
scp -i ~/.ssh/rig_hetzner products/osint/backend/<file> \
    root@178.105.63.154:/root/rig/products/osint/backend/<file>
# 2) rebuild + restart with the DEFAULT .env (NOT .env.prod)
ssh -i ~/.ssh/rig_hetzner root@178.105.63.154 \
  "cd /root/rig/infrastructure && \
   docker compose -f docker-compose.yml build osint-backend && \
   docker compose -f docker-compose.yml up -d osint-backend"
# 3) verify DB is alive
ssh ... "docker exec osint-backend python -c \"import urllib.request as u; \
   print(u.urlopen('http://localhost:8000/ready',timeout=5).read().decode())\""
#   → must print {"status":"ready"}
```

## Validate Top Stories for the AP persona (run inside the container)
Put a script at `/app/_validate_top.py` that calls
`routers.top_articles.get_top_articles(limit=6, window_hours=72, user={"id": "<AP uid>"})`
and prints summaries/geo/matched. **Run from `/app`** (not `/tmp`) so imports
resolve:
```bash
docker cp script.py osint-backend:/app/_validate_top.py
docker exec -w /app osint-backend python _validate_top.py
docker exec osint-backend rm -f /app/_validate_top.py
```
AP user id: `7343cb2f-4f13-46f8-aea8-dbdedfa385b5`.

## Deploy the frontend SPA (ROBIN-OSINT)
```bash
cd products/osint/design/night-desk
# .env.production must pin: VITE_BRIEF_API=/osint   (same-origin)
npm run build                      # → dist/
# stream dist to the host and swap CONTENTS in place (keeps Caddy mount inode):
tar -C dist -czf - . | ssh -i ~/.ssh/rig_hetzner root@178.105.63.154 \
 'NEW=/root/rig/night-desk-dist-new; LIVE=/root/rig/night-desk-dist; \
  rm -rf "$NEW"; mkdir -p "$NEW"; tar -C "$NEW" -xzf -; \
  rm -rf "$LIVE".bak; cp -a "$LIVE" "$LIVE".bak; \
  find "$LIVE" -mindepth 1 -delete; cp -a "$NEW"/. "$LIVE"/; rm -rf "$NEW"'
# verify
curl -s https://desk.rig360media.com/ | grep -o '<title>[^<]*</title>'
```
No Caddy restart needed (static files). Hard-refresh (Ctrl+F5) to bust cache.

## Deploy rig-backend (the main platform — uses .env.prod)
```bash
ssh ... "cd /root/rig/infrastructure && \
  docker compose --env-file .env.prod -f docker-compose.yml build rig-backend && \
  docker compose --env-file .env.prod -f docker-compose.yml up -d rig-backend"
```
> Cold-start caution: `process_broadcast` (NEWSROOM) can deadlock as the first
> task after a worker restart — warm with ping tasks before invoking it.

## Database access
```bash
ssh ... "docker exec -i rig-postgres psql -U rig -d rig -c \"<SQL>\""
# or copy a .sql file in:
scp file.sql root@178.105.63.154:/tmp/ && ssh ... \
 "docker cp /tmp/file.sql rig-postgres:/tmp/ && docker exec -i rig-postgres psql -U rig -d rig -f /tmp/file.sql"
# always check the clock first if 'nothing updates':
#   SELECT analytics.now_sim(), now(), now()-analytics.now_sim();
```

## YouTube clips (rig-backend)
- Beat task `collect-youtube-every-2h` runs collection; worker on the `youtube`
  queue. Cookie jar mounted RW at `/app/youtube-cookies.txt`
  (host `/root/rig/secrets/youtube_cookies.txt`).
- Check status:
  `docker logs --since 10m rig-backend | grep -i youtube`
  and `docker exec -i rig-postgres psql -U rig -d rig -c "SELECT count(*), max(collected_at) FROM youtube_clips;"`

## Rollbacks
- Frontend: `/root/rig/night-desk-dist.bak` (restore contents).
- osint-backend: previous image / re-deploy prior file.
- celery_app.py: `*.bak-preyoutube` on host.
