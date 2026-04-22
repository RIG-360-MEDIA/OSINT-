"""
Daily 07:00 UTC: check that every active govt source has been scraped within
the last 25 hours. Logs warnings for any stale source. Returns a summary dict
for telemetry.

If you wire this into Celery Beat (see _register_govt_doctor.py), it auto-runs.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from backend.celery_app import app

logger = logging.getLogger(__name__)


@app.task(name="tasks.govt_collection_doctor", bind=True)
def govt_collection_doctor(self):
    """Beat-triggered. Returns dict with stale_count and recent_run_count."""
    return asyncio.run(_check_health())


async def _check_health() -> dict:
    from backend.database import get_db

    async with get_db() as db:
        stale = (await db.execute(text("""
            SELECT name, last_scraped_at, health_score, consecutive_failures
            FROM govt_document_sources
            WHERE is_active = TRUE
              AND (last_scraped_at IS NULL OR last_scraped_at < NOW() - INTERVAL '25 hours')
        """))).fetchall()
        for s in stale:
            logger.warning(
                "Stale govt source: %s (last_scraped=%s, health=%s, fails=%s)",
                s.name, s.last_scraped_at, s.health_score, s.consecutive_failures,
            )

        runs = (await db.execute(text("""
            SELECT COUNT(*) AS n FROM govt_collection_runs
            WHERE started_at > NOW() - INTERVAL '24 hours'
        """))).fetchone()

        return {
            "stale_sources": len(stale),
            "stale_names": [s.name for s in stale],
            "recent_runs_24h": int(runs.n) if runs else 0,
        }
