# Resume — YouTube end-to-end quality test

This test was paused at the `process_video` step. Everything below is
ready to copy-paste into a fresh session.

## Background (30-second version)

We are validating that the production YouTube clip-ingestion pipeline
still produces useful clips end-to-end on a fresh video, given that:
1. The captions endpoint is IP-blocked at Hetzner (confirmed today).
2. Two env regressions just got patched (`LOCAL_LLM_ENABLED` orphan +
   stale `YOUTUBE_PROXY_URL`), inert until next recreate.
3. The pipeline has produced zero new clips for 10 days; we want a
   per-video answer to "what would it produce now?"

## What's been verified

- ✅ RSS listing fetched 10 fresh videos from NTV Telugu
  (UCumtYpCY26F6Jr3satUgMvA) including `iKnHROultEA` "AP Cabinet
  Approves Key Decisions" (published 2026-06-04 15:05 UTC).
- ✅ `fetch_transcript('iKnHROultEA')` returned `None` after 8.0s with
  `RequestBlocked`, `_ip_block_streak=1`. Production correctly logs
  "skipping to metadata".

## What's NOT done — the actual quality test

Run `process_video(target_video)` for `iKnHROultEA` and inspect the
resulting rows. Expected: ≥1 clip with `transcript_source='metadata'`,
matched entity from {`Andhra Pradesh`, `CM Chandrababu`}, embedding
present, confidence ~0.27.

## Step 1 — ensure prerequisites

In a fresh chat (so context is clean):

```bash
# verify the test script is on Hetzner from today's session
ssh -i ~/.ssh/rig_hetzner root@178.105.63.154 'ls -la /tmp/yt_e2e.py'
```

If it's gone, recreate it from the appendix at the bottom of this file.

## Step 2 — run the test

```bash
ssh -i ~/.ssh/rig_hetzner root@178.105.63.154 \
  "docker cp /tmp/yt_e2e.py rig-backend:/tmp/yt_e2e.py && \
   docker exec -e YOUTUBE_PROXY_URL='' rig-backend python /tmp/yt_e2e.py"
```

The `-e YOUTUBE_PROXY_URL=''` is critical — the running container still
has the stale proxy in its env until someone does a clean recreate
(see `03-env-regressions-fixed.md`). Stripping it for this one
subprocess gives the real-world answer.

## Step 3 — interpret results

Look for in the output:

| Field | Expected value | Meaning if different |
|---|---|---|
| `process_video returned` | ≥1 | Zero → metadata-fallback path is broken too; this is a P0 |
| `transcript_source` | `metadata` | `captions` → IP-block has lifted, great; `whisper` → audio fallback worked |
| `matched_entity` | political AP figure | Generic / wrong → entity dictionary needs refit |
| `confidence` | ~0.27 ± 0.1 | Much lower → Groq metadata analysis degraded |
| `has_embed` | true | false → embedding pipeline broken |
| Elapsed time | ≤20s | >60s → Groq latency / cold start |

## Step 4 — write findings

Append a `06-test-results-NN.md` to this folder with the actual output
and a 1-paragraph quality verdict. If clips look usable, the
metadata-fallback path is healthy and we can defer the bypass work; if
not, escalate.

## Appendix — the test script

If `/tmp/yt_e2e.py` is missing on Hetzner, write this and re-upload:

```python
import asyncio, sys, time
sys.path.insert(0,'/app')
from sqlalchemy import text
from backend.collectors.youtube_collector import fetch_channel_videos, get_api_keys, process_video
from backend.database import get_db
from backend.nlp.nlp_entities import _ENTITY_DICT

CHANNEL = 'UCumtYpCY26F6Jr3satUgMvA'  # NTV Telugu
TARGET_VID = 'iKnHROultEA'             # AP Cabinet Approves Key Decisions

async def main():
    t0 = time.time()
    keys = get_api_keys()
    async with get_db() as db:
        r = await db.execute(text("SELECT count(*) FROM youtube_clips WHERE video_id=:v"), {"v": TARGET_VID})
        print(f"existing clips for {TARGET_VID}: {r.scalar()}")

        er = await db.execute(text("SELECT DISTINCT canonical_name FROM user_entities"))
        user_entities = [row.canonical_name for row in er.fetchall()]
        print(f"user_entities loaded: {len(user_entities)} sample: {user_entities[:5]}")

        vids = await fetch_channel_videos(channel_id=CHANNEL, api_key=keys, since_days=2, max_results=10, exclude_shorts=True)
        target = next((v for v in vids if v.get('video_id') == TARGET_VID), None)
        if target is None:
            target = next((v for v in vids if 'LIVE' not in (v.get('title') or '').upper()), vids[0])
            print(f"picked alt: {target.get('video_id')} | {target.get('title','')[:60]}")
        else:
            print(f"target found: {target.get('title','')[:60]}")

        ts = time.time()
        n_clips = await process_video(
            video=target, channel_id=CHANNEL,
            user_entities=user_entities,
            entity_dictionary=_ENTITY_DICT,
            db=db,
        )
        await db.commit()
        print(f"\nRESULT: process_video returned {n_clips} clips in {time.time()-ts:.1f}s")

        r = await db.execute(text("""
          SELECT video_id, matched_entity, matched_entity_type, transcript_source,
                 confidence, length(transcript_segment) AS tlen,
                 clip_start_seconds, clip_end_seconds,
                 (labse_embedding IS NOT NULL) AS has_embed,
                 relevance_score, transcript_language
          FROM youtube_clips WHERE video_id=:v
          ORDER BY clip_start_seconds
        """), {"v": target['video_id']})
        rows = r.fetchall()
        print(f"\n=== {len(rows)} rows in youtube_clips for {target['video_id']} ===")
        for row in rows[:8]:
            print(f"  [{row.clip_start_seconds:>4}-{row.clip_end_seconds:<4}] "
                  f"entity={row.matched_entity[:28]!r:32} "
                  f"type={row.matched_entity_type or '-':10} "
                  f"src={row.transcript_source:10} "
                  f"conf={float(row.confidence):.2f} tlen={row.tlen:4} "
                  f"embed={row.has_embed} rel={row.relevance_score}")
        print(f"\nTOTAL TIME: {time.time()-t0:.1f}s")

asyncio.run(main())
```

If the video `iKnHROultEA` is no longer in NTV Telugu's last-2-day RSS
window (likely by 2026-06-06), the script auto-picks the freshest
non-Live video. That's fine — the goal is end-to-end quality, not a
specific video.
