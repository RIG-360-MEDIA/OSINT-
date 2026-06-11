"""v3_upgrade_task.py — Celery beat wrapper for semantic_repass.

Schedules nightly v2→v3 upgrade so every article in the corpus ends up
with translation + register fields + breaking-news flag.

Wraps `backend.tasks.substrate.semantic_repass.run()` — does NOT modify
the substrate/ module itself.

Schedule: every night at 22:30 UTC = 04:00 IST.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Any

from celery import shared_task

logger = logging.getLogger(__name__)


def _build_args(limit: int | None = None) -> argparse.Namespace:
    """Mimic the argparse Namespace semantic_repass.run() expects."""
    ns = argparse.Namespace()
    ns.all = limit is None
    ns.limit = limit
    return ns


@shared_task(
    name="tasks.quality.v3_upgrade",
    bind=True,
    queue="nlp",
    soft_time_limit=7200,    # 2h soft cap per nightly run
    time_limit=10800,        # 3h hard cap
)
def v3_upgrade_task(self, limit: int | None = None) -> dict[str, Any]:
    """Nightly v3 upgrade — runs semantic_repass against any non-v3 articles."""
    try:
        from backend.tasks.substrate.semantic_repass import run
        args = _build_args(limit=limit)
        rc = asyncio.run(run(args))
        return {"ok": rc == 0, "return_code": rc, "limit": limit}
    except Exception as exc:
        logger.exception("v3_upgrade failed: %s", exc)
        return {"error": str(exc)[:200]}
