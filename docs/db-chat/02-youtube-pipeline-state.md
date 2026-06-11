# YouTube clip ingestion — current production state (2026-06-04)

## Data layer

- Table: `public.youtube_clips`
- Total rows: **12,764**
- Last successful collection: **2026-05-25 17:49 UTC** (10 days ago)
- Clips with real captions transcript: **11,742**
- Clips with metadata-only (`transcript_source='metadata'`): **1,022**
- Avg `confidence` for metadata-only clips: ~0.27
- Avg `confidence` for captions clips: higher (≥0.6 default in code)

### Channels tracked

| Tier | Count |
|---|---|
| tier_1 | 11 |
| tier_2 | 34 |
| tier_3 | 26 |
| **active total** | **71** |

All channels show `last_checked_at = 2026-05-25` — meaning the periodic
task has run since then but **silently produced zero clips** because of
the two regressions documented in `03-env-regressions-fixed.md`.

## Code path (one full ingestion cycle)

```
celery_beat triggers tasks.collect_youtube  (every 6h, queue=youtube)
    └─> _collect_youtube()                                   [youtube_task.py:29]
         └─> for each active channel:
              ├─> fetch_channel_videos(channel_id, …)        [youtube_collector.py:305]
              │     ├─> _fetch_channel_videos_rss     ← RSS, NO IP burn
              │     └─> _fetch_channel_videos_ytdlp  ← yt-dlp fallback, IP burn
              └─> for each video:
                   └─> process_video(…)                      [youtube_collector.py:1024]
                        ├─> fetch_transcript(video_id)       [youtube_collector.py:463]
                        │     ├─> youtube_transcript_api  ← BLOCKED on Hetzner IP
                        │     ├─> _fetch_transcript_ytdlp ← yt-dlp .vtt
                        │     └─> _fetch_transcript_via_whisper ← audio
                        ├─> _chunk_transcript / _analyse_chunk
                        ├─> analyze_video_metadata_with_groq  ← metadata-fallback path
                        └─> insert into youtube_clips
```

## What's working

- ✅ RSS-based video listing (Hetzner IP can hit `youtube.com/feeds/videos.xml`).
- ✅ The `process_video` metadata-fallback path (Groq title+description
  analysis) — confirmed by the 1,022 historical metadata-only clips.
- ✅ Entity matching against `user_entities` (the join is local).
- ✅ Embedding storage (LaBSE, 768-d, hnsw index).

## What's blocked

- ❌ `youtube_transcript_api` direct fetch → `RequestBlocked` from
  Hetzner data-center IP. Confirmed by today's probe (8s, streak=1).
- ❌ yt-dlp direct fetch → never tested today end-to-end, but historical
  evidence (and the IP-reputation memory) say it's the same block.
- ❌ Whisper fallback → would need yt-dlp to download audio first, so
  same blocker.

## Effective production behaviour right now

With the captions path blocked and the proxy regression in place,
**every video for the last 10 days fell into the `transcript=None`
branch and produced ZERO clips**. The 0 clip count is real — not a DB
write failure. The historical 1,022 metadata-only clips are from
earlier weeks when the metadata fallback was wired in.

## Once the regressions are fixed (next planned recreate)

Expected new state after `docker compose --env-file .env.prod up -d
--force-recreate rig-backend`:

- Periodic `tasks.collect_youtube` runs every 6h
- For each video: transcript fetch hits the captions block, falls back
  to metadata-only Groq analysis, produces 0–N clips per video based on
  entity matches in title/description
- Expected clip rate: ~1,000/week (matching the historical metadata-only
  pace), confidence ~0.27, `transcript_source='metadata'`

## To recover real-transcript ingestion

Requires the deferred bypass work:

1. Host-network yt-dlp sidecar (bind to `eth0`)
2. Use one of the 256 IPv6 addresses in
   `2a01:4f8:1c18:c8ba::1000–10ff` per request via `--source-address`
3. Pass `--extractor-args 'youtube:player_client=web,getpot_bgutil_baseurl=http://localhost:4416'`
4. Call from `rig-backend` via HTTP RPC, not in-process

This was scoped, partially designed, and rejected for today because
of the Docker bridge networking discovery. Architecture doc:
`docs/plans/youtube-ip-block-bypass-architecture-2026-06-04.md`.
