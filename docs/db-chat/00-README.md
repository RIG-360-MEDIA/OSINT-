# db-chat — session handoff docs

This folder is the **resume point** for any session continuing work from the
**2026-06-04 → 06-05** ops/engineering sessions. Read in order before asking
new questions; this captures context lost when the chat is cleared.

## ▶ STARTING A NEW CHAT? → open `NEW-CHAT-PROMPT.md` and paste its block.
## ▶ WANT CURRENT STATE FAST? → read `10-session-state-2026-06-05.md` first.

## Read order

| # | File | What it covers |
|---|---|---|
| ⭐ | `NEW-CHAT-PROMPT.md` | **Paste-ready prompt to start a fresh chat with full context + persona + working style.** |
| ⭐ | `10-session-state-2026-06-05.md` | **Current state snapshot: what's fixed/deployed/pending, access, the `--no-deps` rule.** Start here. |
| 01 | `01-session-summary-2026-06-04.md` | Chronological log: YouTube IP-bypass attempt, rollback, two silent regressions. |
| 02 | `02-youtube-pipeline-state.md` | YouTube/Clips pipeline state — what works, what's blocked. |
| 03 | `03-env-regressions-fixed.md` | `LOCAL_LLM_ENABLED` orphan + stale `YOUTUBE_PROXY_URL` regressions. |
| 04 | `04-resume-youtube-test.md` | Ready-to-run YouTube end-to-end test script. |
| 05 | `05-operational-rules-banked.md` | Operational rules (SSH, DB, YouTube IP reputation, cold-start). |
| 06 | `06-feed-wedge-incident-2026-06-04.md` | NLP-wedge deep dive: dedup corrupted the shared SQLAlchemy session. |
| 07 | `07-full-incident-chain-2026-06-04.md` | The full chain of 7 stacked problems + all fixes + known-stale pillars. |
| 08 | `08-postgres-cascade-rootcause-2026-06-05.md` | **THE `--no-deps` root cause** + pool resilience + beat-recovery rule. Most important ops doc. |
| 09 | `09-v3-multilingual-twopass-spec.md` | Spec for the substrate session: fix non-English summary loss via two-pass (translate→extract). |

## What was NOT touched

Per banked memory, a **concurrent parallel session** is editing OSINT brief
files (`products/osint/**`, `WarRoom.jsx`, `Analytics.jsx`, etc.). Today's
work in this chat did NOT touch those files. If a future Claude session is
restored with cross-talk pollution suggesting OSINT work — that belongs to
the other window, not here.

## Quick TLDR for the impatient

1. **Two silent prod regressions** were hiding in `.env.prod` / `docker-compose.yml`. Both are patched in-file but the running container still has the old (broken) env until the next legitimate `docker compose --env-file .env.prod up -d --force-recreate rig-backend`.
2. **YouTube transcripts blocked at the Hetzner IP** — confirmed via direct probe today. The captions endpoint returns `RequestBlocked`. Production correctly falls back to metadata-only clip generation.
3. **YouTube bypass infra** (`rig-bgutil-pot` container, IPv6 `/64` pool bound on host with `preferred_lft 0`) is deployed but NOT wired into `youtube_collector.py` (code was reverted because Docker bridge networking made the SOCKS approach unworkable). Proper architecture = host-network yt-dlp sidecar; out of scope for today.
4. **End-to-end YouTube quality test is paused** at the `process_video` step. Test video chosen, RSS listing verified, IP-block gate confirmed. Script is on Hetzner at `/tmp/yt_e2e.py` — see `04-resume-youtube-test.md` to finish it in one shot.

## Folder convention

Future sessions: append new files as `NN-<topic>.md`. Keep one topic per
file. Update this README's read-order table when adding.
