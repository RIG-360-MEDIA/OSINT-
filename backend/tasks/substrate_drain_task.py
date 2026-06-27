"""substrate_drain_task.py — Celery beat wrapper for article substrate drain.

Runs run_corpus_pass on a rolling window of the most-recent unprocessed articles
every 2 minutes. Sized so 4 NLP workers handle 30k articles/day comfortably:
  4 workers × 200 articles/tick × 30 ticks/hr = 24,000 articles/hr headroom.

FOR UPDATE SKIP LOCKED in run_corpus_pass means concurrent worker ticks never
collide — each tick atomically claims its own batch of 200 rows.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Any

from celery import shared_task

logger = logging.getLogger(__name__)

_BATCH = 200  # articles per tick; 8-concurrent Groq calls inside → ~90s/tick


def _args(limit: int) -> argparse.Namespace:
    ns = argparse.Namespace()
    ns.all = False
    ns.since = None
    ns.limit = limit
    return ns


@shared_task(
    name="tasks.substrate_drain",
    bind=True,
    queue="nlp",
    soft_time_limit=300,   # 5 min soft — a 200-article batch should finish in ~90s
    time_limit=360,        # 6 min hard cap
    acks_late=True,        # don't ack until done so a worker crash re-queues
)
def substrate_drain(self, batch_size: int = _BATCH) -> dict[str, Any]:
    """Drain unprocessed article substrate in small rolling batches."""
    try:
        from backend.tasks.substrate.run_corpus_pass import run
        rc = asyncio.run(run(_args(batch_size)))
        return {"ok": rc == 0, "batch_size": batch_size}
    except Exception as exc:
        logger.exception("substrate_drain failed: %s", exc)
        return {"error": str(exc)[:200]}
