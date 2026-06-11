# ROBIN-OSINT — production deploy notes

> Note: the on-disk folder is still `night-desk/` and the Caddy mount paths
> below keep that name; only the product branding changed to ROBIN-OSINT.

Status: **not deployed to prod yet.** Runs locally (`localhost:5180`) against the
prod API at `https://robin-osi.rig360media.com/osint`. Caddy currently proxies only
`/osint/*` → `osint-backend:8000`; it does **not** serve the ROBIN-OSINT SPA.

When you deploy, you need: (1) a built static bundle, (2) a way to serve it, and
(3) a **Caddy SPA fallback** so client-side routes (`/map`, `/war-room`, …) don't 404
on reload. Client-side routing uses the History API (`src/App.jsx`, `SLUGS`).

## 1. Build

```bash
cd products/osint/design/night-desk
npm ci && npm run build      # outputs dist/
```

`VITE_BRIEF_API` must point at the prod API (`https://robin-osi.rig360media.com/osint`)
at build time (set in `.env.production` or the build environment).

## Option A — own subdomain (recommended)

Routing works as-is (root paths). Add a DNS A record for `desk.rig360media.com`
→ `178.105.63.154`, copy `dist/` to the host (e.g. `/root/rig/night-desk-dist`),
bind-mount it into `rig-caddy`, and add this Caddy site block (auto-TLS):

```caddy
desk.rig360media.com {
    encode gzip zstd
    root * /srv/night-desk
    try_files {path} /index.html      # <-- SPA fallback
    file_server
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
    }
}
```

(Mount the dist dir at `/srv/night-desk` in the rig-caddy service in
`infrastructure/docker-compose.yml`.) No Vite `base` change needed.

## Option B — subpath on the existing domain (e.g. /desk/)

Requires `base: '/desk/'` in `vite.config.js` AND base-aware routing
(`SLUGS`/`indexToPath`/`pathToIndex` in `src/App.jsx` must prefix `/desk`).
Then add inside the existing `robin-osi.rig360media.com { … }` block:

```caddy
    handle /desk/* {
        root * /srv/night-desk
        uri strip_prefix /desk
        try_files {path} /index.html   # <-- SPA fallback
        file_server
    }
```

Place this BEFORE the catch-all `handle { reverse_proxy rig-frontend:3000 }`.

## 3. Reload Caddy (no restart needed)

```bash
docker exec rig-caddy caddy reload --config /etc/caddy/Caddyfile
```

The Caddyfile lives at `/root/rig/infrastructure/Caddyfile` and is mounted into the
dockerized `rig-caddy` (not a host service). Validate first:
`docker exec rig-caddy caddy validate --config /etc/caddy/Caddyfile`.
