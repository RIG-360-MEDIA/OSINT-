# Integrate Ask-RIG (agentic chat) into the OSINT / night-desk product

Paste the **PROMPT** block at the bottom into a fresh session that has Hetzner +
night-desk access. Everything above it is the context that prompt refers to.

---

## What Ask-RIG is (the thing to integrate)
A standalone FastAPI service at `products/ask-rig/` (branch `feat/ask-rig-chat`) — a
read-only, **mode-aware agentic chat** over the SAME corpus the OSINT product uses.
- One SSE endpoint: `POST /chat` `{query, history, article_id?}` → streams events
  `{type: status|sources|token|list|chart|done|error}`.
- Single-page UI: `app/static/index.html` (vanilla JS, Chart.js via CDN, no build step) —
  served at `GET /`. It already renders: streaming markdown answers with citations +
  Sources panel; **enumerate** list-cards (with per-item Explain); **charts** (line /
  stacked-bar / doughnut via Chart.js); **dossier**; copy / export-to-markdown / new-chat;
  light+dark theme; conversation persistence.
- Modes (router picks one per turn, ONE LLM call): synthesize · enumerate ("all/latest
  articles") · quantify ("how many / trend / sentiment chart / by language|outlet") ·
  dossier ("everything on X") · drill-down (explain one article by id).

## Its dependencies (all already on Hetzner)
- **Postgres corpus** — connects as `analytics_user` (read-only). Locally via a tunnel
  (`localhost:15432`); on Hetzner it should hit `rig-postgres:5432` directly on the
  `infrastructure_rig-network` docker network.
- **SearXNG** — web search. Locally tunneled to `:8899`; on Hetzner it's
  `http://rig-searxng:8080` (internal, no host port).
- **Groq** LLM (`llama-3.3-70b-versatile`) via a key pool. Embeddings = local LaBSE
  (CPU, in-process; ~20s cold-load, warmed at startup).
- All config is `ASKRIG_*` env (see `products/ask-rig/.env.example`). Secrets live in
  `products/ask-rig/.env` (gitignored — never commit).

## The OSINT side (where it's going)
- Live product = the Vite **night-desk** SPA: `products/osint/design/night-desk/`,
  built to static dist → `/root/rig/night-desk-dist`, served by **`rig-caddy`** at
  **desk.rig360media.com** (Caddyfile: `/root/rig/infrastructure/Caddyfile`).
- Backend = **`osint-backend`** container (separate from `rig-backend`; baked image,
  deploy = `docker cp` + restart — host `/root/rig` source can be stale vs the running
  image, so verify what's actually running).
- Hetzner: `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154` (Docker host). Caddy, postgres
  (`rig-postgres`), searxng (`rig-searxng`) all on `infrastructure_rig-network`.

## Recommended integration architecture (least coupling)
Run Ask-RIG as **its own container** on `infrastructure_rig-network`, expose it through
`rig-caddy`, and add an entry point in night-desk. Do NOT merge it into osint-backend
(different deps — LaBSE/torch, its own pool) — keep it a sidecar service.

1. **Containerize Ask-RIG**: add `infrastructure/Dockerfile.askrig` (python:3.11-slim +
   `pip install -r requirements.txt`; CMD `uvicorn app.main:app --host 0.0.0.0 --port 8010`)
   and a compose service `rig-askrig` on `infrastructure_rig-network`, with env:
   - `ASKRIG_DB_URL=postgresql+asyncpg://analytics_user:<pw>@rig-postgres:5432/rig`
   - `ASKRIG_SEARXNG_URL=http://rig-searxng:8080`
   - `ASKRIG_LLM_API_KEYS=<groq keys>`  (+ `ASKRIG_LLM_MODEL=llama-3.3-70b-versatile`)
   - `ASKRIG_CORS_ORIGINS=https://desk.rig360media.com`
   - Bind-mount the LaBSE HF cache (or bake it) so it doesn't re-download each restart.
2. **Caddy**: route `desk.rig360media.com/ask/*` (or `ask.rig360media.com`) → `rig-askrig:8010`.
   Critical for SSE: disable buffering (`flush_interval -1` in Caddy reverse_proxy) so
   tokens stream live.
3. **Frontend** — two paths, pick per effort:
   - **(A) Fast**: add an "Ask"/"Chat" tab in night-desk that loads the Ask-RIG page in an
     `<iframe src="/ask/">` (or links out). Zero re-implementation; all modes/charts work.
   - **(B) Native**: port `app/static/index.html`'s logic into a React page in night-desk
     (reuse the SSE loop + `list`/`chart`/markdown renderers; Chart.js as an npm dep).
     Point `fetch` at `/ask/chat`. More work, but matches the night-desk look/theme.
   Recommend (A) to ship, then (B) for polish.

## Hard constraints (carry over)
- Corpus is **READ-ONLY** (`analytics_user`); Ask-RIG never writes to it.
- **No clusters/stories** dependency (per-article tables only).
- **Never fabricate**; sentiment is on-the-fly classification (sparse stored flag).
- Anonymous / no-auth (matches how it runs today). If OSINT has auth, decide whether
  `/ask` sits behind it.

## Verify after deploy
- `docker exec rig-askrig curl -s localhost:8010/health` → `{"status":"ok"}`.
- From the host: `curl -N -X POST https://desk.rig360media.com/ask/chat -d '{"query":"who is Revanth Reddy","history":[]}' -H 'Content-Type: application/json'` → streams tokens.
- In the browser: open the Ask tab, run "latest in Telangana" (synthesis), "give me all
  articles about Revanth Reddy in 24h" (list cards), "sentiment chart over 7 days for the
  Telangana govt" (chart), "dossier on Revanth Reddy" (export). Confirm SSE streams (not
  buffered) and charts render.

## Source of truth
- Ask-RIG: `products/ask-rig/` on branch `feat/ask-rig-chat`; full history in
  `memory/project_ask_rig_build.md`.
- Resume/context for Ask-RIG itself: `docs/handoffs/ask-rig-continue-prompt.md`.

---

## PROMPT (paste this)

> You're integrating **Ask-RIG** — a read-only agentic chat (FastAPI, at
> `products/ask-rig/`, branch `feat/ask-rig-chat`) — into the **OSINT night-desk**
> product (Vite SPA at `products/osint/design/night-desk/`, served by `rig-caddy` at
> desk.rig360media.com; backend `osint-backend`). Read
> `docs/handoffs/ask-rig-osint-integration.md` IN FULL and `memory/project_ask_rig_build.md`
> first.
>
> Goal: run Ask-RIG as its own container (`rig-askrig`) on `infrastructure_rig-network`,
> reaching `rig-postgres:5432` (as `analytics_user`, read-only) and `rig-searxng:8080`
> directly (no tunnels on Hetzner); expose it via `rig-caddy` at
> `desk.rig360media.com/ask/*` with SSE buffering disabled (`flush_interval -1`); and add
> an **Ask** entry in night-desk (start with an `<iframe src="/ask/">` to ship, then port
> to a native React page reusing the SSE/list/chart renderers from `app/static/index.html`).
>
> Constraints: corpus READ-ONLY; no clusters/stories; never fabricate; secrets via env
> only (mirror `products/ask-rig/.env.example`), never commit `.env`. Bake or mount the
> LaBSE HF cache so it doesn't re-download.
>
> Plan: (1) read both repos + confirm what's actually running on Hetzner
> (`docker ps`, the Caddyfile, the night-desk build/serve setup); (2) write
> `Dockerfile.askrig` + the compose service + env; (3) add the Caddy route (SSE-safe);
> (4) wire the night-desk Ask tab; (5) verify health + a streaming `/ask/chat` call + each
> mode (synthesis, list, chart, dossier) in the browser. Show me the plan before deploying.
