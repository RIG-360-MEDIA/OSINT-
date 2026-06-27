#!/usr/bin/env python3
"""time_topic_fill.py — measure topic_fill classification throughput on a live 200 sample.

Mirrors topic_fill_task._classify_batch (Semaphore(8), classify_topic_fine), but times it
and counts errors/429s so we get a REAL articles/sec + a corpus ETA instead of a guess.
READ-ONLY: does NOT write topic_fine (timing only). Run inside rig-backend.
"""
from __future__ import annotations

import asyncio
import time


async def main():
    from backend.database import get_db
    from sqlalchemy import text
    from backend.nlp.nlp_topic import classify_topic_fine

    pick = "COALESCE(NULLIF(lead_text_translated,''), NULLIF(lead_text_original,''), NULLIF(full_text_scraped,''), '')"
    async with get_db() as db:
        rows = (await db.execute(text(
            f"SELECT id::text id, title, left({pick},500) lead FROM articles "
            f"WHERE topic_fine IS NULL AND length(trim(COALESCE(title,'')))>=8 "
            f"ORDER BY collected_at DESC LIMIT 200"
        ))).fetchall()
    n = len(rows)
    print(f"sample: {n} unclassified articles", flush=True)
    if not n:
        return

    sem = asyncio.Semaphore(8)
    ok = err = 0
    errs = []

    async def one(r):
        nonlocal ok, err
        async with sem:
            try:
                t = await classify_topic_fine(r.title, r.lead)
                ok += 1
                return t
            except Exception as e:  # noqa: BLE001
                err += 1
                errs.append(f"{type(e).__name__}: {str(e)[:90]}")
                return None

    t0 = time.perf_counter()
    results = await asyncio.gather(*[one(r) for r in rows])
    dt = time.perf_counter() - t0
    rate = n / dt if dt else 0

    import collections
    labels = collections.Counter(x for x in results if x)
    print(f"elapsed: {dt:.1f}s  ->  {rate:.2f} articles/sec  (ok={ok} err={err})", flush=True)
    if errs:
        print("error sample (first 3):", flush=True)
        for e in collections.Counter(errs).most_common(3):
            print(f"   x{e[1]}: {e[0]}", flush=True)
    print(f"label spread (top 6): {dict(labels.most_common(6))}", flush=True)
    remaining = 131454
    if rate > 0 and ok > n * 0.5:
        print(f"PROJECTED full backfill: {remaining/rate/3600:.1f} h for {remaining:,} at {rate:.2f}/s", flush=True)
    else:
        print(f"RATE UNRELIABLE (too many errors) — likely quota-throttled; cannot project honestly", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
