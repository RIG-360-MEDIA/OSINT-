"""reset_stale_processing_task.py — D13: auto-reset orphaned substrate claims.

Runs every 30 min. Single SQL UPDATE — no LLM, no per-row Python.

THE BUG THIS FIXES
------------------
`run_corpus_pass` claims a batch of articles atomically by setting
`substrate_status = 'processing'` (FOR UPDATE SKIP LOCKED). When a drain
process is killed / crashes / exits mid-batch, the rows it claimed stay
frozen in `'processing'` forever. The claim query only re-picks rows whose
status is in (NULL, 'pending'), so an orphaned 'processing' row becomes
permanently invisible to every future drain — the queue silently leaks.

Observed 2026-05-29: 17 real articles (US-Iran war, election results, etc.)
were stuck after drains were killed during the Trijya-offline and autovacuum
incidents. The run_corpus_pass comment promised these are "re-picked by the
next D1 reset cycle" — but that cycle never existed as a running job. This is
that job.

THE FIX
-------
Reset any row that is still unprocessed (`substrate_processed_at IS NULL`),
stuck in `'processing'`, and whose claim is older than a 1-hour grace window,
back to `'pending'` so the next drain re-claims it.

WHY 1 HOUR IS SAFE
------------------
A live drain finishes an article in seconds (whole batches in minutes). A
claim older than an hour therefore *cannot* belong to a working drain — the
worker that placed it is dead. The grace window guarantees we never steal a
row a live drain is actively processing.

Depends on the claim query stamping `updated_at = now()` at claim time
(added to run_corpus_pass.py in the same change). `COALESCE(updated_at,
collected_at)` is a defensive fallback for any pre-fix row.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from celery import shared_task
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Reset orphaned 'processing' claims older than the 1-hour grace window.
SQL = """
UPDATE articles
   SET substrate_status = 'pending'
 WHERE substrate_processed_at IS NULL
   AND substrate_status = 'processing'
   AND COALESCE(updated_at, collected_at) < NOW() - INTERVAL '1 hour'
"""


async def _run() -> dict[str, Any]:
    from backend.database import get_db
    async with get_db() as db:
        r = await db.execute(text(SQL))
        await db.commit()
    return {"reset_to_pending": r.rowcount or 0}


@shared_task(
    name="tasks.substrate.reset_stale_processing",
    bind=True,
    queue="nlp",
    soft_time_limit=30,
    time_limit=60,
)
def reset_stale_processing_task(self) -> dict[str, Any]:
    try:
        out = asyncio.run(_run())
        # Surface non-zero resets at WARNING so a recurring leak is visible.
        if out.get("reset_to_pending"):
            logger.warning("reset_stale_processing: recovered %s orphaned claim(s)", out["reset_to_pending"])
        else:
            logger.info("reset_stale_processing: %s", out)
        return out
    except Exception as exc:  # noqa: BLE001 — periodic task must never crash the worker
        logger.exception("reset_stale_processing failed: %s", exc)
        return {"error": str(exc)[:200]}
