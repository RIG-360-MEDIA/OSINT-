"""
Celery tasks: YouTube channel discovery + clip extraction.

Two tasks on the youtube queue (plus discovery on collectors — RSS is safe
from Hetzner datacenter IPs, transcript fetch is not):

  discover_youtube_channels()
    Reads active rows from youtube_channels, runs RSS discovery for each,
    upserts new video IDs into pending_youtube_videos. Runs every 30 min on
    the collectors queue (RSS from Hetzner is confirmed not IP-blocked).

  run_youtube_extraction(limit)
    Drains 'transcribed' rows from pending_youtube_videos — rows the
    residential worker already fetched captions for — runs the Groq extraction
    pipeline, and writes clips to youtube_clips_v2 (substrate_status='pending'
    so the enrich drain picks them up within 10 min). Runs every 5 min on the
    youtube queue.

RESIDENTIAL WORKER (not a Celery task — runs on the laptop):
  python -m backend.collectors.youtube_v2.worker
  Needs YOUTUBE_WORKER_DB_URL (SSH tunnel to Hetzner postgres).
  See scripts/run_yt_worker.bat.
"""
from __future__ import annotations

import asyncio
import logging

from backend.celery_app import app

logger = logging.getLogger(__name__)


# ── Discovery ─────────────────────────────────────────────────────────────────

@app.task(name="tasks.discover_youtube_channels", queue="collectors")
def discover_youtube_channels() -> dict:
    """RSS discovery for all active channels → upsert new videos into queue."""
    return asyncio.run(_discover())


async def _discover() -> dict:
    from sqlalchemy import text
    from backend.database import get_db
    from backend.collectors.youtube_v2.discovery import (
        discover_channel_videos, DiscoveryError,
    )

    async with get_db() as db:
        channels = (
            await db.execute(
                text(
                    "SELECT channel_id, channel_name, last_checked_at "
                    "FROM youtube_channels WHERE is_active = TRUE "
                    "ORDER BY COALESCE(last_checked_at, '1970-01-01') ASC"
                )
            )
        ).fetchall()

    if not channels:
        logger.info("discover_youtube_channels: no active channels")
        return {"channels": 0, "new_videos": 0}

    total_new = 0
    for ch in channels:
        try:
            videos = await discover_channel_videos(
                ch.channel_id,
                since=ch.last_checked_at,
                max_results=15,
            )
        except DiscoveryError as exc:
            logger.warning("discovery failed channel=%s: %s", ch.channel_id, exc)
            continue

        inserted = 0
        async with get_db() as db:
            for v in videos:
                result = await db.execute(
                    text(
                        """
                        INSERT INTO pending_youtube_videos
                          (video_id, video_title, channel_id, channel_name,
                           video_published_at)
                        VALUES (:vid, :title, :cid, :cname, :pub)
                        ON CONFLICT (video_id) DO NOTHING
                        """
                    ),
                    {
                        "vid":   v.video_id,
                        "title": v.title[:500],
                        "cid":   v.channel_id,
                        "cname": v.channel_name[:200],
                        "pub":   v.published_at or None,
                    },
                )
                if result.rowcount:
                    inserted += 1
            await db.execute(
                text(
                    "UPDATE youtube_channels "
                    "SET last_checked_at = NOW() "
                    "WHERE channel_id = :cid"
                ),
                {"cid": ch.channel_id},
            )
            await db.commit()

        total_new += inserted
        logger.info(
            "discovery channel=%s (%s) found=%d new=%d",
            ch.channel_id, ch.channel_name, len(videos), inserted,
        )

    logger.info(
        "discover_youtube_channels: channels=%d total_new=%d",
        len(channels), total_new,
    )
    return {"channels": len(channels), "new_videos": total_new}


# ── Extraction ────────────────────────────────────────────────────────────────

# Compat alias — Hetzner __init__.py (fix/brief-prod-readiness branch) imports this name
collect_youtube = discover_youtube_channels


@app.task(name="tasks.run_youtube_extraction", queue="youtube")
def run_youtube_extraction(limit: int = 10) -> dict:
    """Drain transcribed rows → run Groq extraction → write clips."""
    return asyncio.run(_extract(limit))


async def _extract(limit: int) -> dict:
    from backend.database import get_db
    from backend.collectors.youtube_v2.pipeline import run_extraction_batch

    async with get_db() as db:
        result = await run_extraction_batch(db, limit=limit)

    logger.info(
        "run_youtube_extraction: processed=%d clips_stored=%d",
        result.get("processed", 0), result.get("clips_stored", 0),
    )
    return result
