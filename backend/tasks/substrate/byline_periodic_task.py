"""Periodic byline backfill — every 6h.

Walks every extraction_version=2 article that still has byline=NULL and
re-fetches its HTML to extract the journalist's name (no LLM cost).
Designed to be cheap and idempotent — the candidate query naturally
shrinks as articles get filled in.
"""
from __future__ import annotations

import asyncio
import logging

from backend.celery_app import app
from backend.tasks.substrate.backfill_bylines import backfill

log = logging.getLogger(__name__)


@app.task(
    name="tasks.backfill_bylines_periodic",
    autoretry_for=(Exception,),
    max_retries=2,
    default_retry_delay=300,
    soft_time_limit=3600,
    time_limit=3900,
)
def backfill_bylines_periodic() -> dict[str, int]:
    """Process up to 1500 candidate articles per 6h-tick.

    1500 at 4-5 articles/sec ≈ 5-7 min wall time. Concurrency 6 stays
    well under the kind of outbound bandwidth that other collectors use.
    """
    log.info("backfill_bylines_periodic: tick started")
    asyncio.run(backfill(batch=200, limit=1500, concurrency=6))
    log.info("backfill_bylines_periodic: tick complete")
    return {"status": "ok"}
