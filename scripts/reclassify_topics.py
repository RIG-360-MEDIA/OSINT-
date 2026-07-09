"""Reclassify articles stamped topic_category='OTHER' using the (working) classifier.

The ingest pipeline marks most articles OTHER as a placeholder and never runs
classify_topic on them. This drains that backlog: pick recent OTHER articles,
run the real classifier (Groq-backed, verified working), write back the topic.
Idempotent + safe to run repeatedly (only touches rows still == 'OTHER').

Env: CAP (rows/run, default 500), HOURS (lookback, default 72), CONC (default 6).
"""
import asyncio
import os

import asyncpg

from backend.nlp.nlp_topic import classify_topic

DSN = os.environ["DATABASE_URL_SYNC"]
CAP = int(os.environ.get("CAP", "500"))
HOURS = int(os.environ.get("HOURS", "72"))
CONC = int(os.environ.get("CONC", "6"))


async def main() -> None:
    conn = await asyncpg.connect(DSN)
    try:
        rows = await conn.fetch(
            "SELECT id, title, lead_text_translated FROM public.articles "
            "WHERE topic_category='OTHER' AND title IS NOT NULL "
            "AND collected_at > now() - ($1 || ' hours')::interval "
            "ORDER BY collected_at DESC LIMIT $2",
            str(HOURS), CAP,
        )
        if not rows:
            print("reclassify: no OTHER backlog in window")
            return
        sem = asyncio.Semaphore(CONC)

        async def one(r):
            async with sem:
                try:
                    t = await classify_topic(r["title"], r["lead_text_translated"])
                except Exception:  # noqa: BLE001 — one failure must not abort the batch
                    return None
            return (r["id"], t) if (t and t != "OTHER") else None

        results = await asyncio.gather(*[one(r) for r in rows])
        updates = [x for x in results if x]
        if updates:
            await conn.executemany(
                "UPDATE public.articles SET topic_category=$2 WHERE id=$1 AND topic_category='OTHER'",
                updates,
            )
        print(f"reclassify: scanned={len(rows)} reclassified={len(updates)}")
    finally:
        await conn.close()


asyncio.run(main())
