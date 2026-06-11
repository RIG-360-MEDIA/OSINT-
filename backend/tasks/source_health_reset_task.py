"""source_health_reset_task.py — weekly circuit-breaker reset for RSS sources.

Background
----------
The RSS collector tracks `health_score` (0.0-1.0) on each source. Once a
source fails to fetch 6 times in a row, health hits the floor and the
priority-sort effectively skips it. Before 2026-05-27 the floor was 0.0,
which meant a source that had ONE bad afternoon could be permanently
locked out — no automatic recovery.

This task gives every active source a fresh chance every Monday 00:00 UTC.

What it does
------------
1. Find all `is_active = true` sources whose `health_score <= 0.2`
   (i.e. caught by the circuit breaker)
2. Reset them to `health_score = 0.5` and `consecutive_failures = 0`
3. Log how many were revived

Healthy sources are untouched. Sources that are actually broken will
re-fail on the next poll cycle and re-trip the breaker organically.
Sources that were unfairly disabled come back online.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db

logger = logging.getLogger(__name__)


@app.task(
    name="tasks.reset_source_circuit_breakers",
    autoretry_for=(Exception,),
    max_retries=2,
    default_retry_delay=300,
    soft_time_limit=120,
    time_limit=180,
)
def reset_source_circuit_breakers() -> dict[str, int]:
    """Weekly reset of low-health RSS / scrape / api sources."""
    return asyncio.run(_run())


async def _run() -> dict[str, int]:
    async with get_db() as db:
        # Reset RSS / scrape / api sources stuck at low health
        result = await db.execute(text("""
            UPDATE sources
               SET health_score = 0.5,
                   consecutive_failures = 0
             WHERE is_active = true
               AND health_score <= 0.2
            RETURNING id::text
        """))
        rows = result.fetchall()
        revived_main = len(rows)

        # Same for govt_document_sources (kept on a sibling table)
        govt_revived = 0
        try:
            result_govt = await db.execute(text("""
                UPDATE govt_document_sources
                   SET health_score = 0.5,
                       consecutive_failures = 0
                 WHERE is_active = true
                   AND health_score <= 0.2
                RETURNING id::text
            """))
            govt_revived = len(result_govt.fetchall())
        except Exception as e:  # noqa: BLE001 — table may not exist in some envs
            logger.warning("govt_document_sources reset skipped: %s", e)

        await db.commit()

    summary = {
        "revived_sources": revived_main,
        "revived_govt_sources": govt_revived,
        "total_revived": revived_main + govt_revived,
    }
    logger.info("reset_source_circuit_breakers: %s", summary)
    return summary
