"""Standalone single-process NLP backlog drain.

Runs `_process_batch()` (the exact same NLP pipeline the celery worker uses)
in a LOOP inside ONE process. Because there is no Celery prefork here, the
LaBSE/torch model loads once in a single process and never hits the
fork-thread deadlock that froze the 4 prefork workers.

Use to recover the entities/embeddings/geo/topic backlog after the
geo_secondary bug. Stops after 3 consecutive empty batches.
"""
from __future__ import annotations

import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("nlp_drain")


async def main() -> None:
    from backend.tasks.nlp_processor import _process_batch

    total = 0
    idle = 0
    for i in range(1000):  # safety cap: 1000 batches × 50 = 50k max
        try:
            r = await _process_batch()
        except Exception as exc:  # noqa: BLE001
            log.error("batch %d errored: %s", i, str(exc)[:200])
            break
        n = int(r.get("processed", 0) or 0)
        total += n
        print(f"[batch {i}] processed={n} skipped={r.get('skipped',0)} "
              f"running_total={total} msg={r.get('message','')}", flush=True)
        if n == 0:
            idle += 1
            if idle >= 3:
                print(f"DRAIN COMPLETE — no more pending. total={total}", flush=True)
                break
        else:
            idle = 0
    print(f"FINAL total_processed={total}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
