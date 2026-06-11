# ROBIN-OSINT — Context Pack (START HERE)

> **Purpose of this folder.** It is a complete, self-contained briefing on the
> ROBIN-OSINT product: the vision, the architecture, the personas, what has been
> built, what is broken, what is planned, and exactly how to operate it. A new
> AI chat (or a new teammate) should read **all** files here, in order, and will
> then have the same working context as the session that created this pack
> (2026-06-05).

## How to use this pack
1. Read the files in numeric order (00 → 10).
2. The most operationally important file is **09-OPERATIONS-RUNBOOK.md** — it
   contains the exact deploy commands and the **landmines** (especially the
   `.env` vs `.env.prod` gotcha that has broken the live site once).
3. To start a new chat with full context, paste the prompt in
   **NEW-CHAT-PROMPT.md**.

## File index
| File | What's in it |
|---|---|
| 00-START-HERE.md | This index + quick facts |
| 01-VISION.md | What ROBIN-OSINT is and why; the product vision |
| 02-ARCHITECTURE.md | Frontend, backend, DB, Caddy, deploy topology |
| 03-PERSONAS-AND-PERSONALIZATION.md | The users, how data is scoped per persona |
| 04-PAGES-AND-FEATURES.md | The 6 pages + endpoints (points to the walkthrough) |
| 05-DATA-AND-PIPELINES.md | Tables, `now_sim`, summary fields, relevance core |
| 06-WORK-LOG-THIS-SESSION.md | Everything done on 2026-06-05, chronologically |
| 07-KNOWN-ISSUES.md | Open problems + the precise reasons |
| 08-ROADMAP.md | What we're planning / considering next |
| 09-OPERATIONS-RUNBOOK.md | Exact commands; deploy; landmines |
| 10-GLOSSARY-AND-CONVENTIONS.md | Terms + working rules |
| NEW-CHAT-PROMPT.md | Paste this to bootstrap a new chat |

## Quick facts (the 60-second version)
- **Product:** ROBIN-OSINT — a per-persona political-intelligence "night desk"
  SPA. Live at **https://desk.rig360media.com**.
- **Was called** "Night Desk" — renamed to ROBIN-OSINT on 2026-06-05 (the
  on-disk folder is still `night-desk/`; only the branding changed).
- **Frontend:** Vite/React 18 at
  `products/osint/design/night-desk/`. Served as static files by dockerized
  Caddy. API is same-origin at `/osint/*`.
- **Backend:** FastAPI `osint-backend` at `products/osint/backend/`. Connects to
  Postgres as **read-only** `analytics_user`. Personalizes every response.
- **DB:** `rig-postgres` (Postgres 16 + pgvector) on Hetzner. `analytics.now_sim()`
  is the live clock (currently == real time).
- **Host:** Hetzner `178.105.63.154`. SSH: `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154`.
- **Primary demo persona:** the **Andhra Pradesh** user
  `andhrarig360@gmail.com` (principal = Chandrababu Naidu).

## Hard rules (do not violate)
- **Never print or commit secret values** (DB passwords, API keys, the YouTube
  cookie, Supabase service key). Reference them by location only. The AP user's
  password is hashed and **not retrievable** — don't try.
- **No fabricated data.** Every seeded/displayed fact must be source-verified.
- **Commit attribution is disabled** globally — no `Co-Authored-By` lines.
- **Deploy `osint-backend` with the DEFAULT `.env`** (NOT `--env-file .env.prod`).
  See 09-OPERATIONS-RUNBOOK.md — this has broken the site once.
- **Don't casually run raw `yt-dlp` from Hetzner** — it burns the IP reputation.
