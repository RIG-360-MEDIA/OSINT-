"""Periodic tweet enrichment — every 6h.

Catches articles upgraded from v1→v2 by semantic_repass (which doesn't
trigger inline tweet enrichment). Also catches any tweets that failed
on first attempt due to rate-limit or transient network issues.
"""
from __future__ import annotations

import asyncio
import logging

from backend.celery_app import app
from backend.tasks.substrate.backfill_tweets import backfill

log = logging.getLogger(__name__)


@app.task(
    name="tasks.backfill_tweets_periodic",
    autoretry_for=(Exception,),
    max_retries=2,
    default_retry_delay=300,
    soft_time_limit=3600,
    time_limit=3900,
)
def backfill_tweets_periodic() -> dict[str, int]:
    """Sweep up to 500 outstanding tweet enrichments per 6h tick.

    The candidate query in backfill_tweets.py already filters for v2
    articles whose article_tweets row is missing or not in 'ok' state.
    Idempotent — re-runs only touch pairs that still need work.
    """
    log.info("backfill_tweets_periodic: tick started")
    asyncio.run(backfill(batch=200, limit=500, per_call_delay=0.5))
    log.info("backfill_tweets_periodic: tick complete")
    return {"status": "ok"}
