"""Backfill: re-enrich clippings that hit the quality tail — empty entities,
null register, or (non-English) missing body translation — through the improved
prompt + entity-retry guard. Resumable: only targets still-affected rows.

Run: docker exec rig-backend python /app/scripts/backfill_clipping_quality.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text

from backend.database import get_db
from backend.tasks.clipping_enrich import _enrich_claimed

_SELECT = """
    SELECT id::text AS id FROM clippings
    WHERE enriched_at IS NOT NULL AND length(COALESCE(body_text,'')) >= 50
      AND (
        entities_extracted IS NULL OR entities_extracted::text IN ('null','[]')
        OR register_emotion IS NULL
        OR (COALESCE(detected_language, language, 'en') <> 'en'
            AND (body_text_translated IS NULL OR length(body_text_translated) = 0))
      )
    ORDER BY edition_date DESC NULLS LAST
"""


async def run() -> None:
    async with get_db() as db:
        ids = [r.id for r in (await db.execute(text(_SELECT))).fetchall()]
    print(f"clippings to re-enrich: {len(ids)}", flush=True)

    ok = fail = 0
    for i, cid in enumerate(ids):
        try:
            r = await _enrich_claimed(cid)
            ok += 1 if r else 0
            fail += 0 if r else 1
        except Exception as exc:  # noqa: BLE001
            fail += 1
            if fail <= 5:
                print(f"  fail {cid}: {type(exc).__name__}: {exc}", flush=True)
        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{len(ids)} (ok={ok} fail={fail})", flush=True)

    async with get_db() as db:
        ee = (await db.execute(text(
            "SELECT count(*) FROM clippings WHERE enriched_at IS NOT NULL "
            "AND (entities_extracted IS NULL OR entities_extracted::text IN ('null','[]'))"
        ))).scalar()
        nr = (await db.execute(text(
            "SELECT count(*) FROM clippings WHERE enriched_at IS NOT NULL AND register_emotion IS NULL"
        ))).scalar()
        nt = (await db.execute(text(
            "SELECT count(*) FROM clippings WHERE enriched_at IS NOT NULL "
            "AND COALESCE(detected_language,language,'en') <> 'en' "
            "AND (body_text_translated IS NULL OR length(body_text_translated)=0)"
        ))).scalar()
    print(f"DONE ok={ok} fail={fail} | remaining: empty_entities={ee} null_register={nr} "
          f"non_en_no_translation={nt}", flush=True)


if __name__ == "__main__":
    asyncio.run(run())
