"""drain_tick_task.py — D13 part 2: auto-trigger v3 substrate extraction.

Runs every 10 min. Fires `run_corpus_pass.run()` over the pending backlog so
new articles reach **v3** within minutes of collection — no more manual
`nohup` drains, no v1/v2 lag.

WHY THIS EXISTS
---------------
The substrate v3 extractor (`run_corpus_pass`) was only ever launched
manually. New articles are born `extraction_version=1` (column default) with
`substrate_processed_at=NULL`; without a scheduled drain they sit at v1 until
someone runs one by hand (or the nightly repass bumps them to v2). This task
closes that gap: v3 now happens automatically.

The complementary NLP stage (`process_nlp_batch`, every 30s) independently
sets `topic_category` + `labse_embedding` and does NOT set
`substrate_processed_at`, so it never blocks this drain. Between the two, a
fresh article gets: topic+embedding within ~30s, full v3 facts within ~10min.

NO-OVERLAP DESIGN
-----------------
`limit=300` + `soft_time_limit=540` (9 min) guarantees a tick finishes before
the next 10-min tick fires, so two drains never run concurrently (which would
waste LLM calls and tie up nlp worker slots). At observed cloud-only ~37/min,
300 articles ≈ 8 min. Throughput ceiling ≈ 1,800/hr, comfortably above the
~1,000/hr ingest rate. If a tick is ever killed mid-batch by the soft limit,
the claimed rows are recovered by `reset_stale_processing_task` (the D13
part-1 cron) within the hour — self-healing, no manual intervention.

For a large catch-up backlog (e.g. after an outage) a manual high-`--limit`
drain is still the fast path; this task is for steady-state.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Any

from celery import shared_task

logger = logging.getLogger(__name__)

# Per-tick cap. Sized so a tick finishes inside the 9-min soft limit at
# cloud-only throughput (~37/min) → no overlap with the next 10-min tick.
_PER_TICK_LIMIT = 300


async def _run(limit: int) -> dict[str, Any]:
    import backend.nlp.groq_client as gc
    from backend.tasks.substrate import run_corpus_pass

    # ── TEMPORARY (Trijya offline / being wiped) — force CLOUD-ONLY ──────────
    # `_LOCAL_LLM_ENABLED` is read at import time and the UnifiedPool is a
    # cached singleton, so an env var can't flip it at task-time. While Trijya
    # is down, the 8 local slots only waste cycles (each call cools 10s before
    # rotating to cloud), dragging mixed-mode to ~12/min vs ~37/min cloud-only.
    # This guarded flip disables local + forces ONE pool rebuild (Groq +
    # Cerebras only). It's process-global, which is what we want while Trijya
    # is dead — process_nlp_batch stops wasting cycles on dead local slots too.
    #
    # ►► REVERT WHEN TRIJYA IS BACK: delete this whole block + restart
    #    rig-backend. The pool then rebuilds with local slots and mixed-mode
    #    (faster) resumes automatically.
    if gc._LOCAL_LLM_ENABLED:
        gc._LOCAL_LLM_ENABLED = False
        gc._unified_pool_singleton = None  # next _get_unified_pool() rebuilds cloud-only
        logger.warning("drain_tick: forced CLOUD-ONLY (Trijya offline) — local slots disabled")
    # ────────────────────────────────────────────────────────────────────────

    ns = argparse.Namespace(all=False, since=None, limit=limit)
    processed = await run_corpus_pass.run(ns)
    return {"processed": int(processed or 0), "limit": limit}


@shared_task(
    name="tasks.substrate.drain_tick",
    bind=True,
    queue="nlp",
    soft_time_limit=540,   # 9 min — stop before the next 10-min tick
    time_limit=570,
)
def drain_tick_task(self, limit: int = _PER_TICK_LIMIT) -> dict[str, Any]:
    try:
        out = asyncio.run(_run(limit))
        if out.get("processed"):
            logger.info("drain_tick: extracted %s articles to v3", out["processed"])
        return out
    except Exception as exc:  # noqa: BLE001 — periodic task must never crash the worker
        # SoftTimeLimitExceeded lands here too; claimed-but-unfinished rows are
        # reclaimed by reset_stale_processing_task within the hour.
        logger.warning("drain_tick stopped early: %s", str(exc)[:200])
        return {"error": str(exc)[:200]}
