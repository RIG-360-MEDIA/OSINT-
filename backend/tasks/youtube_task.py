"""
Celery task: collect YouTube clips from monitored channels.

Runs every 6 hours. For each active channel in youtube_channels,
fetches recent videos, extracts transcripts, detects entity mentions,
and stores 30-second clip records.
"""
from __future__ import annotations

import asyncio
import logging
import os

from backend.celery_app import app

logger = logging.getLogger(__name__)


@app.task(
    name="tasks.collect_youtube",
    queue="youtube",
    max_retries=2,
)
def collect_youtube() -> None:
    """Entry point — synchronous wrapper for Celery."""
    asyncio.run(_collect_youtube())


async def _collect_youtube() -> None:
    from sqlalchemy import text

    from backend.collectors.youtube_collector import (
        fetch_channel_videos,
        get_api_keys,
        process_video,
    )
    from backend.database import get_db
    from backend.nlp.nlp_entities import _ENTITY_DICT

    api_keys = get_api_keys()
    if not api_keys:
        logger.warning("No YOUTUBE_API_KEY* set — skipping YouTube collection")
        return
    logger.info("YouTube collection using %d API key(s)", len(api_keys))

    async with get_db() as db:
        channels_result = await db.execute(
            text("SELECT channel_id, channel_name FROM youtube_channels WHERE is_active = TRUE")
        )
        channels = channels_result.fetchall()

        if not channels:
            logger.info("No YouTube channels configured — skipping")
            return

        entities_result = await db.execute(
            text("SELECT DISTINCT canonical_name FROM user_entities")
        )
        user_entities = [r.canonical_name for r in entities_result.fetchall()]

        if not user_entities:
            logger.info("No user entities configured — skipping YouTube collection")
            return

        total_clips = 0

        for channel in channels:
            logger.info("Checking channel: %s", channel.channel_name)

            videos = await fetch_channel_videos(
                channel_id=channel.channel_id,
                api_key=api_keys,
                since_days=2,
            )
            logger.info("Found %d videos for %s", len(videos), channel.channel_name)

            for video in videos:
                clips = await process_video(
                    video=video,
                    channel_id=channel.channel_id,
                    user_entities=user_entities,
                    entity_dictionary=_ENTITY_DICT,
                    db=db,
                )
                total_clips += clips

            await db.execute(
                text("UPDATE youtube_channels SET last_checked_at = NOW() WHERE channel_id = :cid"),
                {"cid": channel.channel_id},
            )
            # Commit per channel so progress is visible and clips appear immediately
            await db.commit()
        logger.info(
            "YouTube collection done: %d new clips from %d channels",
            total_clips, len(channels),
        )
