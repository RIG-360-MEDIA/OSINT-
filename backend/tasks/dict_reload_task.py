"""
Celery task: periodically check entity_dictionary version and reload
the in-memory singleton if it has changed.

Runs every 5 minutes via Beat. Eliminates the need to restart backend
containers when new entities are added to entity_dictionary.
"""
from __future__ import annotations

import asyncio
import logging

from backend.celery_app import app

logger = logging.getLogger(__name__)


@app.task(
    name="tasks.check_entity_dict_version",
    queue="nlp",
    max_retries=1,
)
def check_entity_dict_version() -> None:
    asyncio.run(_check_version())


async def _check_version() -> None:
    from backend.database import get_db
    from backend.nlp.nlp_entities import check_and_reload_if_stale

    async with get_db() as db:
        reloaded = await check_and_reload_if_stale(db)
        if reloaded:
            logger.info("Entity dictionary reloaded by version check task")
        else:
            logger.debug("Entity dictionary version current — no reload needed")
