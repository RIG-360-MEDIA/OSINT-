"""
Repair clippings whose stored image is missing or unusably small.

The bbox columns are kept as-is (some are normalized 0..100, some are raw
PDF points) — render_article_clipping now auto-detects the scale. We just
need to re-fetch the source PDF for each broken row and re-render.

Run:
    docker exec rig-backend python /app/backend/scripts/repair_clipping_images.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from collections import defaultdict

sys.path.insert(0, "/app")

from sqlalchemy import text

from backend.collectors.newspaper_collector import (
    download_pdf_from_url,
    get_pdf_url_from_careerswave,
    render_article_clipping,
)
from backend.database import get_db


async def repair() -> None:
    async with get_db() as db:
        # Group broken rows by (newspaper_id, edition_date) so we download
        # each PDF only once.
        rows = await db.execute(
            text(
                """
                SELECT id::text AS id,
                       newspaper_id::text AS nid,
                       newspaper_name AS name,
                       edition_date,
                       page_number,
                       bbox_left, bbox_bottom, bbox_right, bbox_top
                FROM newspaper_clippings
                WHERE edition_date = CURRENT_DATE
                  AND (
                    clipping_image_b64 IS NULL
                    OR LENGTH(clipping_image_b64) < 2000
                  )
                ORDER BY newspaper_id, edition_date
                """
            )
        )
        broken = rows.fetchall()
        print(f"Broken rows to repair: {len(broken)}")
        if not broken:
            return

        groups: dict[tuple[str, str], list] = defaultdict(list)
        for r in broken:
            groups[(r.nid, r.edition_date.isoformat())].append(r)

        for (nid, ed), batch in groups.items():
            paper_name = batch[0].name
            print(f"\n— {paper_name} ({ed}) — {len(batch)} broken")

            src = await db.execute(
                text(
                    "SELECT careerswave_url FROM newspaper_sources "
                    "WHERE id = CAST(:nid AS uuid)"
                ),
                {"nid": nid},
            )
            src_row = src.fetchone()
            if not src_row or not src_row.careerswave_url:
                print("  no careerswave_url — skip")
                continue

            pdf_url = await get_pdf_url_from_careerswave(src_row.careerswave_url)
            if not pdf_url:
                print("  no PDF URL — skip")
                continue

            with tempfile.TemporaryDirectory() as tmpdir:
                pdf_path = os.path.join(tmpdir, "edition.pdf")
                ok = await download_pdf_from_url(pdf_url, pdf_path)
                if not ok or os.path.getsize(pdf_path) < 1024:
                    print("  PDF download failed — skip")
                    continue

                fixed = 0
                for r in batch:
                    bbox = [
                        r.bbox_left or 0.0, r.bbox_bottom or 0.0,
                        r.bbox_right or 0.0, r.bbox_top or 0.0,
                    ]
                    page = r.page_number or 1
                    try:
                        new_b64 = render_article_clipping(pdf_path, page, bbox)
                    except Exception as exc:
                        print(f"  {r.id[:8]} render failed: {exc}")
                        continue
                    if not new_b64 or len(new_b64) < 2000:
                        continue
                    await db.execute(
                        text(
                            """
                            UPDATE newspaper_clippings
                            SET clipping_image_b64 = :b64
                            WHERE id = CAST(:cid AS uuid)
                            """
                        ),
                        {"b64": new_b64, "cid": r.id},
                    )
                    fixed += 1
                await db.commit()
                print(f"  fixed {fixed}/{len(batch)}")


if __name__ == "__main__":
    asyncio.run(repair())
