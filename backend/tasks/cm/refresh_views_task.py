"""
Refresh materialized views feeding the CM Page hot path.

  * mv_cm_voice_share        — every 6 hours
  * mv_cm_issue_hourly       — every 30 minutes (used by trajectory + dashboard)
  * mv_cm_constituency_daily — daily 02:00

CONCURRENTLY refresh requires a unique index on the view, which migration
028 provides.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db

logger = logging.getLogger(__name__)


async def _refresh(view: str) -> None:
    async with get_db() as db:
        try:
            await db.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}"))
            await db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("CONCURRENTLY refresh failed for %s (%s) — falling back", view, exc)
            try:
                await db.execute(text(f"REFRESH MATERIALIZED VIEW {view}"))
                await db.commit()
            except Exception as exc2:  # noqa: BLE001
                logger.warning("plain refresh failed for %s: %s", view, exc2)


@app.task(name="tasks.cm.refresh_voice_share")
def refresh_voice_share() -> dict[str, str]:
    asyncio.run(_refresh("mv_cm_voice_share"))
    return {"refreshed": "mv_cm_voice_share"}


@app.task(name="tasks.cm.refresh_issue_hourly")
def refresh_issue_hourly() -> dict[str, str]:
    asyncio.run(_refresh("mv_cm_issue_hourly"))
    return {"refreshed": "mv_cm_issue_hourly"}


@app.task(name="tasks.cm.refresh_constituency_heatmap")
def refresh_constituency_heatmap() -> dict[str, str]:
    asyncio.run(_refresh("mv_cm_constituency_daily"))
    return {"refreshed": "mv_cm_constituency_daily"}
