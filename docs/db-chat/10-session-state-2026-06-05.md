# Session state snapshot — 2026-06-04 → 06-05

Single source of truth for "where things stand right now." Pair with the
numbered incident docs (01–09) for detail.

## Access / how to operate
- **SSH:** `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154`
- **DB:** `docker exec rig-postgres psql -U rig -d rig -c "<sql>"`
- **Safe rig-backend recreate (MEMORIZE):**
  `docker compose --env-file .env.prod up -d --force-recreate --no-deps rig-backend`
- **Safe rig-caddy recreate (it's in prod.yml):**
  `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --no-deps rig-caddy`
- Compose dir: `/root/rig/infrastructure`. MC dashboard repo (separate, host-only, NOT a git repo): `/root/rig-mc`.

## THE rule that explains most of this session's pain
`docker compose up -d rig-backend` **without `--no-deps`** silently recreates
**rig-postgres** too → kills all DB connections → cascades. Always
`--no-deps` + `--env-file .env.prod`. Full detail: `08-...md`.
- Pools self-heal now (collectors asyncpg + mc-backend psycopg2). **Celery beat does NOT** — after any PG bounce it needs a `--no-deps` recreate or article scraping silently stalls.

## What was FIXED this session (all live on prod)
| Fix | File | Doc |
|---|---|---|
| NLP wedge (dedup corrupted shared session) | `backend/nlp/nlp_embedding.py` — rollback on dedup fail | 06 |
| 1,486 backlogged rows unblocked | bulk SQL flip | 06 |
| Collector pool resilience (PG-restart survival) | `backend/collectors/{direct_rss,rss,html}_collector.py` | 08 |
| thumbnail crash-loop (month-old) | `backend/tasks/thumbnail_task.py` `inserted_at`→`collected_at` | 07 |
| Dashboard stuck-red latch | `/root/rig-mc/backend/app/metrics/system.py` `_health_history_ok` self-exclusion | 07 |
| mc-backend pool resilience (dashboard self-heals PG bounce) | `/root/rig-mc/backend/app/db.py` | 08 |
| `LOCAL_LLM_ENABLED` never reached container | `docker-compose.yml` line 100 passthrough | 03 |
| stale `YOUTUBE_PROXY_URL` breaking transcripts | `.env.prod` line 46 commented | 03 |

## What was DEPLOYED
- **`https://desk.rig360media.com` — LIVE.** night-desk SPA + `/osint/*`→osint-backend (same-origin). Caddy block + `/srv/night-desk` volume (mounts `/root/rig/night-desk-dist`) + Cloudflare A record (user added) + cert issued. Backups: `Caddyfile.bak-20260605-desk`, `docker-compose.prod.yml.bak-20260605-desk`.

## Source coverage work
- **Added 7 new intl sources** (verified scrapable): Semafor, Axios, CBS News, NBC News, Euronews, Middle East Eye, The Hill.
- **Revived 6** disabled-but-working: Bloomberg, FT (healthy, wrongly disabled), Bhutan Times, US DoD, Nikkei + Anadolu (stale URL fixed).
- **Finding:** 556/1157 sources disabled; of 445 disabled-with-RSS, only ~4 revivable as-is — most are genuinely dead URLs OR stale URLs that moved (Nikkei/Anadolu pattern). Reuters/AP RSS are dead (Reuters killed public feeds); reuters.com 401-walls scrapers; only Google News RSS gives Reuters *headline-only*.
- **Auto-disable trap:** sources auto-disable after 25 failures; the weekly reset only re-tests `is_active=true` → disabled sources never recover. Architectural gap.

## YouTube / Clips — current verdict (don't keep fighting it for free)
- Wall is **BotGuard** ("confirm you're not a bot") on the player endpoint, gating captions AND audio.
- `rig-bgutil-pot` (PoToken server, :4416) is wired into `newsroom/_audio_io.py`; **cookies + PoToken clears BotGuard** but YouTube then returns **storyboards only, no audio formats**.
- The other session's **IPv6-rotation proxy `:4417`** (`/app/proxy.py`) makes it **WORSE** (fresh datacenter IPv6 = instant bot-flag). **Do NOT set `YOUTUBE_PROXY_URL`.** Tested live.
- Bottom line: **free YouTube audio extraction from this datacenter box still doesn't work.** Clips is the lowest-priority pillar. Detail: 02, 07.

## Open / pending (not done)
1. **Blank summary cards** — root cause: v3's single-call translate+extract overflows output budget for non-English → JSON truncates → summary NULL (en 75%, te 67%, ml 49%, ja 3%). **Fix = two-pass (translate→extract), spec in `09-...md`** for the substrate session. **Immediate mitigation offered, not yet done:** mc-frontend feed-card fallback `summary_snippet || summary_preview || lead_text_translated`.
2. **`collect_rss` runtime ~53 min** (scheduled every 15 min) — perpetually overlapping, contributes ~nothing new; needs parallelization. Not blocking (collect_rss_direct carries bulk).
3. **Social pillar dead** — Reddit ~5 weeks, Telegram ~10 days. Worker alive but **no social collection task is dispatched by beat**. Undiagnosed.
4. **441 dead/stale disabled feeds** — URL-rediscovery pass would resurrect the stale-URL ones (like Nikkei). Real project.
5. **summary backlog ~16.6k** — do NOT blanket re-run v3 (it re-fetches URLs → expensive + stale-URL failures). Use frontend fallback now; later a `--reuse-body` capped re-run after the two-pass fix.
6. **bgutil-pot container + IPv6 /64 pool** still running (harmless). `:4417` proxy is the other session's, unmanaged (no restart policy).

## Concurrent session boundary (DO NOT edit their files)
A parallel **story-clustering / substrate / OSINT-brief** session owns:
`products/osint/**`, `backend/tasks/substrate/run_corpus_pass.py`, `night-desk/**`,
`WarRoom.jsx`, `Analytics.jsx`, `Dossier.jsx`, etc. Hand them specs (like 09), don't edit under them.

## Operating constraints (banked)
- Off-peak for heavy jobs; host >600 MiB free; off the 12 GiB cgroup.
- NEVER probe yt-dlp/transcript-api raw (IP reputation; recovery 24–72h). Use throttle.
- Cold-start deadlock: `process_broadcast` hangs as first task after restart — warm workers with pings first.
- No fabricated numbers; verify against code+DB before asserting (this session corrected itself 3× by checking).
