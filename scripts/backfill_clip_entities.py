"""Backfill: re-enrich existing single-entity YouTube clips so entities_extracted
holds ALL entities the transcript mentions (canonical English), matching the new
multi-entity path. Resumable — only touches clips still at <=1 entity that have a
usable transcript. Refreshes the entity-mention matview at the end.

Run: docker exec rig-backend python /app/scripts/backfill_clip_entities.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text

from backend.database import get_db
from backend.tasks.youtube_clip_enrich import _enrich_claimed


async def backfill() -> None:
    async with get_db() as db:
        rows = (await db.execute(text(
            """
            SELECT id FROM youtube_clips_v2
            WHERE transcript_segment IS NOT NULL AND length(transcript_segment) >= 20
              AND (entities_extracted IS NULL
                   OR jsonb_typeof(entities_extracted) <> 'array'
                   OR jsonb_array_length(entities_extracted) <= 1)
            ORDER BY created_at DESC
            """
        ))).fetchall()
    ids = [int(r.id) for r in rows]
    print(f"clips to backfill: {len(ids)}", flush=True)

    done = fail = 0
    for i, cid in enumerate(ids):
        try:
            ok = await _enrich_claimed(cid)
            done += 1 if ok else 0
            fail += 0 if ok else 1
        except Exception as exc:  # noqa: BLE001
            fail += 1
            if fail <= 5:
                print(f"  fail clip {cid}: {type(exc).__name__}: {exc}", flush=True)
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(ids)} processed (ok={done} fail={fail})", flush=True)

    async with get_db() as db:
        multi = (await db.execute(text(
            "SELECT count(*) FROM youtube_clips_v2 WHERE jsonb_typeof(entities_extracted)='array' "
            "AND jsonb_array_length(entities_extracted) > 1"
        ))).scalar()
    print(f"ENRICH DONE: ok={done} fail={fail} | clips now multi-entity={multi}", flush=True)

    # refresh the entity-mention matview so the new entities surface in analytics
    async with get_db() as db:
        try:
            await db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY youtube_clip_entity_mentions"))
            await db.commit()
            print("matview refreshed (concurrently)", flush=True)
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            try:
                await db.execute(text("REFRESH MATERIALIZED VIEW youtube_clip_entity_mentions"))
                await db.commit()
                print("matview refreshed (plain)", flush=True)
            except Exception as exc2:  # noqa: BLE001
                print(f"matview refresh skipped: {exc2}", flush=True)


if __name__ == "__main__":
    asyncio.run(backfill())
