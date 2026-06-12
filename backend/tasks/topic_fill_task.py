"""topic_fill_task.py — keeps article topics correct, decoupled from extraction.

Two problems it fixes (2026-06-12):
  Fix 1 (roll-up): topic_category was computed by an OLD classifier that dumps to
    OTHER, ignoring the GOOD topic_fine. Where topic_fine exists, derive
    topic_category from it (coarse_from_fine) — instant, no LLM.
  Fix 2 (classify): ~half the corpus has topic_fine NULL (the good classifier
    never ran on the substrate path). Run classify_topic_fine on those and set
    both fields. Wired as a standing 4-min task so it can never silently reopen.

Beat: every 4 min (roll-up + a classify batch). One-shot backfill: _backfill_all().
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from celery import shared_task
from sqlalchemy import text

from backend.nlp.nlp_topic import FINE_TO_COARSE, coarse_from_fine

logger = logging.getLogger(__name__)

# CASE expr collapsing topic_fine → coarse (mirror of coarse_from_fine, in SQL)
_COARSE_CASE = (
    "CASE topic_fine "
    + " ".join(f"WHEN '{k}' THEN '{v}'" for k, v in FINE_TO_COARSE.items())
    + " ELSE topic_fine END"
)
# Fix 1: copy the good label into the shown field wherever they disagree. Cheap, bulk.
_ROLLUP_SQL = (
    f"UPDATE articles SET topic_category = {_COARSE_CASE} "
    f"WHERE topic_fine IS NOT NULL AND topic_fine <> '' "
    f"AND topic_category IS DISTINCT FROM ({_COARSE_CASE})"
)

_PICK_LEAD = "COALESCE(NULLIF(lead_text_translated,''), NULLIF(lead_text_original,''), NULLIF(full_text_scraped,''), '')"


async def _rollup() -> int:
    from backend.database import get_db
    async with get_db() as db:
        r = await db.execute(text(_ROLLUP_SQL))
        await db.commit()
        return r.rowcount or 0


async def _classify_batch(limit: int = 200) -> int:
    """Run the good classifier on articles missing topic_fine; set both fields."""
    from backend.database import get_db
    from backend.nlp.nlp_topic import classify_topic_fine

    async with get_db() as db:
        rows = (await db.execute(text(
            f"SELECT id::text AS id, title, left({_PICK_LEAD}, 500) AS lead FROM articles "
            f"WHERE topic_fine IS NULL AND length(trim(COALESCE(title,''))) >= 8 "
            f"ORDER BY collected_at DESC LIMIT :lim"
        ), {"lim": limit})).fetchall()
        if not rows:
            return 0

    sem = asyncio.Semaphore(8)  # bounded concurrency; Groq pool has many keys

    async def _one(r):
        async with sem:
            try:
                t = await classify_topic_fine(r.title, r.lead)
            except Exception:  # noqa: BLE001
                t = "OTHER"
        return r.id, t

    results = await asyncio.gather(*[_one(r) for r in rows])

    async with get_db() as db:
        for cid, t in results:
            await db.execute(text(
                "UPDATE articles SET topic_fine = :tf, topic_category = :tc WHERE id = CAST(:id AS uuid)"
            ), {"tf": t, "tc": coarse_from_fine(t), "id": cid})
        await db.commit()
    return len(results)


@shared_task(
    name="tasks.quality.topic_fill",
    bind=True,
    queue="nlp",
    soft_time_limit=240,
    time_limit=300,
)
def topic_fill_task(self) -> dict[str, Any]:
    async def _go():
        rolled = await _rollup()
        classified = await _classify_batch(200)
        return {"rolled_up": rolled, "classified": classified}
    try:
        out = asyncio.run(_go())
        if out["rolled_up"] or out["classified"]:
            logger.info("topic_fill: %s", out)
        return out
    except Exception as exc:  # noqa: BLE001
        logger.exception("topic_fill failed: %s", exc)
        return {"error": str(exc)[:200]}


async def _backfill_all(batch: int = 400) -> dict[str, Any]:
    """One-shot: roll up everything, then classify until no NULL topic_fine remains."""
    rolled = await _rollup()
    print(f"rolled up {rolled} (topic_fine→topic_category)", flush=True)
    total = 0
    while True:
        n = await _classify_batch(batch)
        total += n
        print(f"classify backfill: +{n} (total {total})", flush=True)
        if n == 0:
            break
    await _rollup()  # final roll-up of the newly-classified
    return {"rolled_up": rolled, "total_classified": total}
