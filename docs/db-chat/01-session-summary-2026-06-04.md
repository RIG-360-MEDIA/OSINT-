# Session 2026-06-04 — chronological summary

> **Scope of this session**: YouTube IP-block bypass deployment +
> incident recovery + discovery of two latent env regressions.
> Everything below happened in one continuous chat between roughly
> 13:00 and 16:00 UTC on 2026-06-04.

## Phase 1 — YouTube IP-bypass deployment (13:00 – 14:00)

Plan (from `docs/plans/youtube-ip-block-bypass-architecture-2026-06-04.md`):

- **Layer 1**: rotate yt-dlp's `--source-address` across 256 IPv6 addresses
  from Hetzner's `/64` (`2a01:4f8:1c18:c8ba::/64`) — each request a new
  source IP, defeating per-IP captions rate limits.
- **Layer 2**: self-hosted PO Token provider via
  `bgutil-ytdlp-pot-provider` Docker container (port 4416) for BotGuard
  bypass.

Deployed:

- ✅ `rig-bgutil-pot` container — Up, serving valid PoTokens (12h TTL).
  **Still running.** Harmless even though unused; clean up only if
  abandoning the bypass plan.
- ✅ 256 IPv6 addresses bound to `eth0` on Hetzner host with
  `preferred_lft 0` (RFC 6724 deprecated state) so the kernel won't pick
  them as default outbound for other services. **Still bound.** Verified
  kernel still picks `2a01:4f8:1c18:c8ba::1` as default source.
- ✅ Persistence hook: `/etc/networkd-dispatcher/routable.d/50-rig-ipv6-pool.sh`
  re-binds the pool on every reboot.
- ❌ Code wiring in `backend/collectors/youtube_collector.py`
  (`apply_yt_bypass` helper) — was added then **reverted** because the
  intermediate SOCKS5 design needed `rig-backend` to reach a proxy on
  the host, which Docker bridge networking blocks. File restored from
  `/root/rig/backend/collectors/youtube_collector.py.bak-20260604`.
- ❌ `Dockerfile.backend` `pip install bgutil-ytdlp-pot-provider==1.3.1` —
  reverted from `.bak-20260604`.

**Lesson banked**: the right architecture is a **host-network yt-dlp
sidecar** invoked via RPC — not SOCKS-through-bridge. Out of scope for
today; revisit later.

## Phase 2 — The recreate incident (14:48)

Ran `docker compose up -d rig-backend` **without** `--env-file .env.prod`.
Result: `${POSTGRES_PASSWORD}` interpolated to empty string,
`DATABASE_URL` had empty password, Celery broker auth failed with
`fe_sendauth: no password supplied`, workers stopped processing for
**10 minutes**.

Recovered with `docker compose --env-file .env.prod up -d
--force-recreate rig-backend`. Pipeline drained within minutes.

**Lesson banked (now an operational rule):**
> Always use `docker compose --env-file .env.prod up -d` for `rig-backend`.
> Plain `up -d` silently empties interpolations.

## Phase 3 — Regression #1: `LOCAL_LLM_ENABLED` orphan (15:00 – 15:15)

User asked: *"why was Ollama being probed when we switched it off a week
ago?"*

Investigation:

| Layer | State |
|---|---|
| `.env.prod` | `LOCAL_LLM_ENABLED=0` (set a week ago) |
| `docker-compose.yml` `osint-backend.environment:` | `- LOCAL_LLM_ENABLED=0` (correctly wired) |
| `docker-compose.yml` `rig-backend.environment:` | **MISSING** — no passthrough |
| Running `rig-backend` container env | unset → Python defaulted `LOCAL_LLM_ENABLED=1` |

Effect: for 6+ days (since Trijya/Tailscale went offline) every
substrate batch ate a ~10s cooldown probing the dead Ollama slot before
falling through to Cerebras.

Patch (line 100 of `infrastructure/docker-compose.yml`):

```yaml
rig-backend:
  environment:
    GROQ_API_KEYS: ${GROQ_API_KEYS:-}
    CEREBRAS_API_KEYS: ${CEREBRAS_API_KEYS:-}
    LOCAL_LLM_ENABLED: ${LOCAL_LLM_ENABLED:-1}   # NEW
    DOSSIER_ENABLED: ${DOSSIER_ENABLED:-false}
```

Backup: `infrastructure/docker-compose.yml.bak-20260604-llm-passthrough`.
**Inert until next legitimate recreate.** Verified via `docker compose
--env-file .env.prod config | grep LOCAL_LLM` → renders as `"0"` for both
services.

## Phase 4 — Regression #2: stale `YOUTUBE_PROXY_URL` (15:30 – 15:45)

While running the YouTube end-to-end test, transcript fetch failed with
`SOCKSHTTPSConnection ... Connection closed unexpectedly` against host
`172.30.0.1:1081`. That's the Docker bridge gateway IP — leftover from
the morning's SOCKS experiment, where the SOCKS container was removed
but the env var stayed.

`docker exec rig-backend env | grep PROXY` confirmed
`YOUTUBE_PROXY_URL=socks5h://172.30.0.1:1081`.

Source: `.env.prod` line 46 still had it.
`docker-compose.yml` line 111 passes it through unconditionally:
`YOUTUBE_PROXY_URL: ${YOUTUBE_PROXY_URL:-}`.

**Effect: every scheduled `tasks.collect_youtube` since the recreate at
14:48 has been pointing yt-dlp / transcript-api at a dead proxy** —
guaranteed zero new transcripts until fixed.

Patch — `.env.prod` line 46 commented out:
```
# YOUTUBE_PROXY_URL=  # commented 2026-06-04: SOCKS experiment was reverted, stale value caused transcript fetches to fail
```

Backup: `infrastructure/.env.prod.bak-20260604-proxy-scrub`.
**Inert until next legitimate recreate** — the running container still
has the stale value in its env.

## Phase 5 — YouTube end-to-end test (paused mid-flight)

What was verified:

1. **RSS video listing works** — fetched 10 fresh videos from NTV Telugu
   (UCumtYpCY26F6Jr3satUgMvA) including one published 25 min before the
   probe. No yt-dlp call, no IP burn.
2. **Captions endpoint blocks Hetzner IP** — `fetch_transcript('iKnHROultEA')`
   returned `RequestBlocked` after the polite 1.5–3.5s delay
   (8.0s total). `_ip_block_streak` correctly incremented; production
   code logs `"skipping to metadata"`. This matches banked YT IP-reputation
   memory.

What was NOT completed:

3. ⏳ `process_video()` end-to-end run — the metadata-fallback path
   (Groq title/description analysis → entity match → clip write).
   Script written, copied to Hetzner at `/tmp/yt_e2e.py` but the final
   invocation hit the chat's session-timeout pattern.
4. ⏳ Quality assessment against May 25 baseline.

Resume: `docs/db-chat/04-resume-youtube-test.md`.

## Phase 6 — chat reliability issue (no fix, diagnosis only)

User reported `"Something went wrong / session stopped responding"`
after ~10 min of every run. Diagnosed as: huge accumulated transcript
+ SessionStart hook leaking the parallel OSINT session's state into
this chat + long SSH+docker exec calls compounding into upstream
streaming timeouts. Recommendation: `/clear` between distinct tasks,
keep SSH calls short, scope the SessionStart hook to current-session
only. No code action taken.

## Files actually modified today (Hetzner host)

| Path | Change |
|---|---|
| `/root/rig/infrastructure/docker-compose.yml` | Added `LOCAL_LLM_ENABLED` passthrough at line 100 |
| `/root/rig/infrastructure/.env.prod` | Commented stale `YOUTUBE_PROXY_URL` at line 46 |
| `/etc/networkd-dispatcher/routable.d/50-rig-ipv6-pool.sh` | New file — IPv6 pool persistence |

Backups left in place:
- `docker-compose.yml.bak-20260604-llm-passthrough`
- `.env.prod.bak-20260604-proxy-scrub`
- `youtube_collector.py.bak-20260604`
- `Dockerfile.backend.bak-20260604`

## Containers Still Up From Today's Work

| Container | Status | Action |
|---|---|---|
| `rig-bgutil-pot` (port 4416) | Up, idle | Keep — needed if YT bypass restarts |
| `rig-ipv6-socks` | **Removed** | n/a |

## Files written to repo today

| Path | Purpose |
|---|---|
| `docs/plans/youtube-ip-block-bypass-architecture-2026-06-04.md` | ~8KB design doc, includes rejected alternatives |
| `docs/plans/youtube-bypass-deployment-2026-06-04.md` | Deployment status |
| `docs/db-chat/00-README.md` through `05-...md` | This handoff folder |
