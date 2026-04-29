"""
Backfill English translations for non-English clippings whose stored
headline_translated / article_text_translated is missing or never made it
to actual English (transliteration / source-script echo).

Run:
    docker exec rig-backend python /app/backend/scripts/backfill_translations.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text

from backend.database import get_db
from backend.nlp.nlp_language import _looks_like_english, detect_and_translate


async def main() -> None:
    async with get_db() as db:
        rows = await db.execute(
            text(
                """
                SELECT id::text AS id,
                       newspaper_name,
                       newspaper_language,
                       headline,
                       article_text,
                       headline_translated,
                       article_text_translated
                FROM newspaper_clippings
                WHERE edition_date = CURRENT_DATE
                  AND newspaper_language <> 'en'
                """
            )
        )
        all_rows = rows.fetchall()
        print(f"Inspecting {len(all_rows)} non-English clippings…")

        fixed = 0
        for r in all_rows:
            need_h = not r.headline_translated or not _looks_like_english(
                r.headline_translated
            )
            need_b = not r.article_text_translated or not _looks_like_english(
                r.article_text_translated
            )
            if not (need_h or need_b):
                continue

            new_headline = r.headline_translated
            new_body = r.article_text_translated

            if need_h:
                try:
                    _, new_headline = await detect_and_translate(None, r.headline or "")
                except Exception as exc:
                    print(f"  {r.id[:8]} headline failed: {exc}")
            if need_b:
                try:
                    _, new_body = await detect_and_translate(
                        (r.article_text or "")[:2000], r.headline or "",
                    )
                except Exception as exc:
                    print(f"  {r.id[:8]} body failed: {exc}")

            if (need_h and new_headline) or (need_b and new_body):
                await db.execute(
                    text(
                        """
                        UPDATE newspaper_clippings
                        SET headline_translated = :h,
                            article_text_translated = :b
                        WHERE id = CAST(:cid AS uuid)
                        """
                    ),
                    {"h": new_headline, "b": new_body, "cid": r.id},
                )
                fixed += 1

        await db.commit()
        print(f"Backfilled {fixed} clippings.")


if __name__ == "__main__":
    asyncio.run(main())
