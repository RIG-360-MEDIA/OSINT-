"""Residential transcript worker — drains the discovery queue.

RUNS ON A RESIDENTIAL MACHINE (laptop now; a reused phone via Termux or a $35
Pi later for always-on). YouTube blocks datacenter IPs, so this is the only
component that talks to the timed-text endpoint. It is deliberately
self-contained: it needs youtube-transcript-api + SQLAlchemy + a DB URL, not
the whole backend.

Flow per tick:
  SELECT status='pending' (FOR UPDATE SKIP LOCKED)
    → fetch_transcript (residential IP)
    → write transcript_json + status='transcribed'   (success)
    → status='no_transcript'                          (no captions, terminal)
    → attempts++ , status='failed' after MAX_ATTEMPTS (ip_blocked/error)

Extraction + storage run separately on Hetzner (Groq) off the 'transcribed'
rows — keeping the LLM keys server-side and this worker dumb.

Config (env):
  YOUTUBE_WORKER_DB_URL   async SQLAlchemy URL to the Postgres (e.g. over an
                          SSH tunnel: postgresql+asyncpg://user:pw@127.0.0.1:5433/rig)
  YOUTUBE_WORKER_BATCH    rows per tick (default 5)
  YOUTUBE_WORKER_SLEEP    seconds between videos (default 4, be gentle)
  YOUTUBE_WORKER_IDLE     seconds to sleep when queue empty (default 30)
  YOUTUBE_WORKER_MAX_ATTEMPTS  default 4

Run:  python -m backend.collectors.youtube_v2.worker
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

from .models import Transcript, TranscriptFailure
from .transcript import fetch_transcript

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("youtube_v2.worker")

_BATCH = int(os.getenv("YOUTUBE_WORKER_BATCH", "5"))
_SLEEP = float(os.getenv("YOUTUBE_WORKER_SLEEP", "4"))
_IDLE = float(os.getenv("YOUTUBE_WORKER_IDLE", "30"))
_MAX_ATTEMPTS = int(os.getenv("YOUTUBE_WORKER_MAX_ATTEMPTS", "4"))


def _transcript_to_json(t: Transcript) -> str:
    return json.dumps(
        {
            "language": t.language,
            "source": t.source.value,
            "segments": [
                {"start": s.start, "duration": s.duration, "text": s.text}
                for s in t.segments
            ],
        }
    )


async def _claim_batch(conn):
    from sqlalchemy import text

    rows = (
        await conn.execute(
            text(
                """
                SELECT id, video_id, video_title
                FROM pending_youtube_videos
                WHERE status = 'pending'
                ORDER BY discovered_at
                LIMIT :batch
                FOR UPDATE SKIP LOCKED
                """
            ),
            {"batch": _BATCH},
        )
    ).fetchall()
    return rows


async def _process_one(conn, row) -> str:
    """Fetch transcript for one row and update its status. Returns the outcome."""
    from sqlalchemy import text

    result = await asyncio.to_thread(fetch_transcript, row.video_id)

    if isinstance(result, Transcript):
        await conn.execute(
            text(
                """
                UPDATE pending_youtube_videos
                SET status='transcribed', transcript_json=CAST(:tj AS JSONB),
                    transcript_language=:lang, transcript_source=:src,
                    transcribed_at=now(), updated_at=now(), last_error=NULL
                WHERE id=:id
                """
            ),
            {
                "tj": _transcript_to_json(result),
                "lang": result.language,
                "src": result.source.value,
                "id": row.id,
            },
        )
        return f"transcribed({len(result.segments)} segs, {result.language})"

    failure: TranscriptFailure = result
    if failure.reason == "no_transcript":
        await conn.execute(
            text(
                """
                UPDATE pending_youtube_videos
                SET status='no_transcript', updated_at=now(), last_error=:err
                WHERE id=:id
                """
            ),
            {"err": failure.detail, "id": row.id},
        )
        return "no_transcript"

    # ip_blocked / unplayable / error → bump attempts, fail after the cap
    await conn.execute(
        text(
            """
            UPDATE pending_youtube_videos
            SET attempts = attempts + 1,
                status = CASE WHEN attempts + 1 >= :maxa THEN 'failed' ELSE 'pending' END,
                last_error = :err, updated_at = now()
            WHERE id = :id
            """
        ),
        {"maxa": _MAX_ATTEMPTS, "err": f"{failure.reason}: {failure.detail}", "id": row.id},
    )
    return f"retry/{failure.reason}"


async def run_forever() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    db_url = os.getenv("YOUTUBE_WORKER_DB_URL")
    if not db_url:
        raise SystemExit("YOUTUBE_WORKER_DB_URL is required")

    engine = create_async_engine(db_url, pool_pre_ping=True)
    logger.info("youtube_v2 worker started batch=%d sleep=%.1f", _BATCH, _SLEEP)

    while True:
        processed = 0
        async with engine.begin() as conn:
            rows = await _claim_batch(conn)
            for row in rows:
                outcome = await _process_one(conn, row)
                processed += 1
                logger.info("video=%s title=%r -> %s",
                            row.video_id, row.video_title[:50], outcome)
                await asyncio.sleep(_SLEEP)
        if processed == 0:
            await asyncio.sleep(_IDLE)


if __name__ == "__main__":
    asyncio.run(run_forever())
