# THE NEWSROOM — Overnight Build Log (2026-05-09 → 2026-05-10)

Single source of truth for the autonomous build session. Updated after every phase.

## Status legend
- ✅ done + verified
- 🟡 done + verified with caveats (caveats listed)
- ⏳ in progress
- 🛑 blocked — needs your decision
- ❌ failed — rollback issued

---

## Phase 0 — Whisper queue infrastructure
✅ **DONE 2026-05-09 12:55 UTC**

- Worktree: commit `213e910` on `claude/vigilant-morse-ffdcc9`, pushed to origin.
- Hetzner: cherry-picked as `af2a6f6` onto `fix/brief-prod-readiness` (was `cb6eeeb`).
- Image rebuilt: `rig-backend:prod` (8m44s; LaBSE warmup + image export, not pip).
- Worker process verified: `celery worker --queues=whisper --concurrency=1 --prefetch=1 --hostname=worker-whisper@%h`.
- Round-trip task `25d5d24b…` returned SUCCESS with correct payload.
- All 7 queues operational. `/health` reports `db_connected=true, articles_today=4957` — no regression.

Detour cost: ~30 s of postgres downtime when I incorrectly tried to merge dev + prod compose files. Recovered. Lessons saved to memory (`reference_hetzner_access.md`) — won't repeat.

---

## Phase 1 — Schema migrations
✅ **DONE 2026-05-09 13:10 UTC**

- 7 migrations written, committed `9e8e813`, pushed, cherry-picked onto Hetzner as `86b8771`.
- Applied via `docker exec rig-postgres psql -U rig -d rig -f ...` for each.
- All 7 tables created on Hetzner DB:
  `newsroom_channels`, `newsroom_broadcasts`, `newsroom_segments`,
  `newsroom_entity_mentions`, `newsroom_breaking_clusters`,
  `newsroom_breaking_segments`, `newsroom_briefs`.
- `newsroom_segments` schema verified: 18 columns, 6 indexes (incl. 4 partial), FK to entity_dictionary(id), SSE NOTIFY trigger live.

## Phase 2 — 3-Lens Consensus pipeline
🟡 **CODE COMPLETE; VERIFICATION BLOCKED** by YouTube IP-level bot wall on Hetzner

### What's done
- All Phase 2 modules written, type-clean, committed `5a0aa02` and cherry-picked onto Hetzner.
- `rig-backend:prod` image rebuilt with faster-whisper, ffmpeg, pyphonetics, metaphone (image now 6.32GB, up from ~2GB).
- Container recreated successfully on the new image; ffmpeg + faster-whisper + pyphonetics + metaphone all import cleanly.
- VOD fixture seeded: `newsroom_channels` row for "Aadab Hyderabad News" (`6b08e8fd-2cd8-4a0c-af61-b98872a7d1cb`).

### Verification blocker — YouTube anti-bot wall
At 2026-05-09 13:30 UTC, every yt-dlp / youtube_transcript_api call from rig-backend returns `Sign in to confirm you're not a bot` or `RequestBlocked`. Tested:
- yt-dlp 2024.11.18 → upgraded inside container to 2026.03.17, still walled
- All player_client variants (tv, web_embedded, mediaconnect, ios_creator, android) → walled
- Transcript-only mode (no audio download) → walled
- `youtube_transcript_api.fetch()` with cookies (production pattern) → `RequestBlocked` on both my fixture and a video the production pipeline ingested 17 min ago
- Cookies file present + fresh (`/app/youtube-cookies.txt`, 70 KB, modified 13:23 today)
- `YOUTUBE_PROXY_URL` env passthrough exists but is empty in production (no WARP proxy active)

The existing /clips pipeline DID ingest 1576 clips in the last 3 days (latest 17 min ago) — but its `_ip_block_streak` counter looks like it tripped during my session, suggesting YouTube's rate limit on this IP escalated tonight.

### Resolution path for the user
This is an **external blocker**, not a code defect. Three options when you wake up:
1. **Wait it out.** YT IP blocks tend to lift after a few hours of zero traffic.
2. **Re-export YouTube cookies** from a fresh logged-in browser session and replace `/root/youtube-cookies.txt` (mounts into container at `/app/youtube-cookies.txt`).
3. **Add a WARP/VPN proxy** and set `YOUTUBE_PROXY_URL=` in `.env.prod`. The newsroom code already passes it through.

### Once unblocked, this command verifies Phase 2 end-to-end
```
docker exec rig-backend python -c "
from backend.tasks.newsroom.process_broadcast import process_broadcast
r = process_broadcast.apply_async(
    args=['afX1BQu0DZ8', '6b08e8fd-2cd8-4a0c-af61-b98872a7d1cb'],
    kwargs={'language': 'te', 'title': 'Domestic Worker To BJP MLA'},
)
print('task_id:', r.id)
"
# Then: docker exec rig-postgres psql -U rig -d rig -c \
#   "SELECT count(*), min(start_sec), max(end_sec) FROM newsroom_segments WHERE broadcast_id = (SELECT id FROM newsroom_broadcasts WHERE yt_video_id='afX1BQu0DZ8');"
```

Bible-rule audio audit (3 random segment timestamps to spot-check) cannot be performed by me anyway — that's user action even when verification succeeds.

## Phase 3 — Quote / sentiment / framing
🟡 **CODE COMPLETE; VERIFICATION BLOCKED** (downstream of Phase 2)

Code shipped:
- `backend/tasks/newsroom/extract_quotes.py` — Cerebras-failover Groq classifier, batched 8 segments/call, idempotent on `framing IS NULL`. Driven by a beat schedule `newsroom-extract-quotes-every-5-min`.

## Phase 4 — Live channel monitor
🟡 **CODE COMPLETE; VERIFICATION BLOCKED** (downstream of Phase 2 — yt-dlp pull walled)

Code shipped:
- `backend/tasks/newsroom/live_monitor.py` — long-running task, Postgres advisory lock per channel (`pg_try_advisory_lock(hashtext(channel_id))`), self-respawning via beat tick.
- `enqueue_live_monitors` beat task — every 5 min, fires one monitor per active 24×7 channel; duplicates lose the lock race and exit.
- Default cap: 1 hour per monitor task (then beat respawns) so failure blast radius is bounded.

## Phase 5 — Cross-channel breaking detection
🟡 **CODE COMPLETE; VERIFICATION BLOCKED**

Code shipped:
- `backend/tasks/newsroom/detect_breaking.py` — every 2 min, sweeps last 20 min of segments, groups by entity, ≥3 distinct channels = candidate, Cerebras quality gate sets `is_real_event` + severity. Distinct from existing `breaking_clusters` table (042) — different signal source.

## Phase 6 — Backend API + SSE
✅ **CODE COMPLETE** (smoke-testable on Hetzner; data-dependent endpoints will return empty until Phase 2 unblocks)

Code shipped:
- `backend/routers/newsroom_router.py` — 9 routes, all gated by `Depends(require_page("clips"))` (re-using existing slug; URL stays at /clips per the brief).
- Routes: `/channels`, `/wall`, `/stream` (cursor-paginated), `/echo?entity_id=&hours=`, `/dossier?entity_id=&days=`, `/brief?date=`, `/breaking`, `/segments/{id}`, `/stream/live` (SSE).
- SSE driver: `asyncpg.add_listener("newsroom_segment", ...)` listens on the LISTEN/NOTIFY channel emitted by migration 053's trigger. 15s heartbeat. Client uses `new EventSource('/api/newsroom/stream/live')`.
- Registered in `backend/main.py` between `clips_router` and `documents_router`.

## Phase 7 — Frontend /clips redesign
🛑 **NOT STARTED — HARD-GATED ON RECONCILIATION** (origin ↔ Hetzner, see `project_branch_divergence.md`)

Per your explicit instruction earlier today: "reconciliation must complete before any Phase 7 frontend work begins." I held to that. Reconciliation packet is being prepared as the next step.

## Phase 8 — Daily NEWSROOM brief
🟡 **BACKEND CODE COMPLETE**; UI portion lives behind Phase 7 reconciliation gate

Code shipped:
- `backend/tasks/newsroom/generate_daily_brief.py` — beat-driven 00:30 UTC (06:00 IST), pulls prior calendar day's segments, scores entity-clustered candidates, single Cerebras call composes 5-7 stories, upserts on `for_date`. Idempotent.
- API surface for the brief is `/api/newsroom/brief?date=YYYY-MM-DD` (Phase 6).

## Beat schedule additions (`backend/celery_app.py`)
- `newsroom-extract-quotes-every-5-min` → tasks.newsroom.extract_quotes (nlp queue)
- `newsroom-enqueue-live-monitors-every-5-min` → tasks.newsroom.enqueue_live_monitors (whisper queue)
- `newsroom-detect-breaking-every-2-min` → tasks.newsroom.detect_breaking (nlp queue)
- `newsroom-daily-brief-0030-utc` → tasks.newsroom.generate_daily_brief (brief queue)

---

(Subsequent phases appended here as they complete.)
