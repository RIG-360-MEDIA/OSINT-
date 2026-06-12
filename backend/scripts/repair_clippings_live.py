"""Backfill missing clipping snapshots on the LIVE `clippings` table.

Supersedes repair_clipping_images.py (which targeted the retired
`newspaper_clippings` table with separate bbox_* columns and a today-only
filter). The live table uses a single `bbox` JSON array [left,bottom,right,top]
and a local `source_pdf_path` under /data/newspapers, so we render straight
from disk — no careerswave round-trip needed.

Rows whose localization failed carry a full-page bbox; rendering that yields the
whole newspaper page, which is a usable fallback snapshot (better than blank).

Run:
    docker exec rig-backend python /app/backend/scripts/repair_clippings_live.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text

from backend.collectors.newspaper_collector import render_article_clipping
from backend.database import get_db


async def repair() -> None:
    async with get_db() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT id::text AS id, source_pdf_path,
                           page_number, bbox::text AS bbox
                    FROM clippings
                    WHERE (clipping_image_b64 IS NULL OR LENGTH(clipping_image_b64) < 2000)
                      AND source_pdf_path IS NOT NULL
                      AND bbox IS NOT NULL
                    ORDER BY edition_date DESC
                    """
                )
            )
        ).fetchall()

    print(f"candidates: {len(rows)}", flush=True)
    fixed = no_pdf = render_fail = 0

    async with get_db() as db:
        for i, r in enumerate(rows):
            if not os.path.exists(r.source_pdf_path):
                no_pdf += 1
                continue
            try:
                bbox = [float(x) for x in json.loads(r.bbox)]
                b64 = render_article_clipping(r.source_pdf_path, r.page_number or 1, bbox)
            except Exception as exc:  # noqa: BLE001
                render_fail += 1
                if render_fail <= 5:
                    print(f"  render fail {r.id[:8]}: {exc}", flush=True)
                continue
            if not b64 or len(b64) < 2000:
                render_fail += 1
                continue
            await db.execute(
                text("UPDATE clippings SET clipping_image_b64 = :b WHERE id = CAST(:i AS uuid)"),
                {"b": b64, "i": r.id},
            )
            fixed += 1
            if fixed % 25 == 0:
                await db.commit()
                print(f"  fixed {fixed}...", flush=True)
        await db.commit()

    print(f"DONE fixed={fixed} no_pdf={no_pdf} render_fail={render_fail}", flush=True)


if __name__ == "__main__":
    asyncio.run(repair())
