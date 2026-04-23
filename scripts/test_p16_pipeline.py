"""One-shot test of P16 Cutting Room pipeline — run inside rig-backend."""

import asyncio
import logging
import os
import sys
import tempfile
from datetime import date

from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


async def run_one(paper_name: str) -> None:
    from backend.collectors.newspaper_collector import (
        download_pdf_from_url,
        extract_articles_from_pdf,
        get_pdf_url_from_careerswave,
        is_relevant_to_user,
        render_article_clipping,
    )
    from backend.database import get_db

    today = date.today()
    async with get_db() as db:
        row = (
            await db.execute(
                text(
                    "SELECT id,name,language,careerswave_url FROM newspaper_sources WHERE name=:n"
                ),
                {"n": paper_name},
            )
        ).fetchone()
        if not row:
            print("NO PAPER")
            return

        user_entities = [
            "Revanth Reddy",
            "Congress",
            "KCR",
            "BRS",
            "BJP",
            "Telangana",
        ]
        user_geo = "Telangana"

        pdf_url = await get_pdf_url_from_careerswave(row.careerswave_url)
        print(f"PDF URL: {pdf_url}")
        if not pdf_url:
            return

        with tempfile.TemporaryDirectory() as td:
            pdf_path = os.path.join(td, "paper.pdf")
            ok = await download_pdf_from_url(pdf_url, pdf_path)
            size = os.path.getsize(pdf_path) if os.path.exists(pdf_path) else 0
            print(f"Downloaded ok={ok} size={size}")
            if not ok or size < 1024:
                return

            articles = await extract_articles_from_pdf(pdf_path, row.language)
            print(f"Articles extracted: {len(articles)}")
            if not articles:
                return

            relevant = saved = 0
            for a in articles[:80]:
                if not a.get("headline") or len(a.get("text", "")) < 50:
                    continue
                is_rel, score, reason = await is_relevant_to_user(
                    a["headline"], a["text"], user_entities, user_geo,
                )
                if not is_rel:
                    continue
                relevant += 1
                bbox = a.get("bounding_box") or []
                clip_b64 = None
                if bbox:
                    clip_b64 = render_article_clipping(
                        pdf_path, a.get("page_number", 1), bbox,
                    )

                try:
                    await db.execute(
                        text(
                            """
                            INSERT INTO newspaper_clippings (
                                newspaper_id,newspaper_name,newspaper_language,edition_date,
                                page_number,headline,article_text,
                                bbox_left,bbox_bottom,bbox_right,bbox_top,
                                clipping_image_b64,relevance_score,relevance_explanation
                            ) VALUES (CAST(:nid AS uuid),:name,:lang,:ed,:pg,:h,:t,:bl,:bb,:br,:bt,:clip,:s,:r)
                            ON CONFLICT (newspaper_id,edition_date,headline) DO NOTHING
                            """
                        ),
                        {
                            "nid": str(row.id),
                            "name": row.name,
                            "lang": row.language,
                            "ed": today,
                            "pg": a.get("page_number"),
                            "h": a["headline"][:500],
                            "t": a["text"][:10000],
                            "bl": bbox[0] if len(bbox) > 0 else None,
                            "bb": bbox[1] if len(bbox) > 1 else None,
                            "br": bbox[2] if len(bbox) > 2 else None,
                            "bt": bbox[3] if len(bbox) > 3 else None,
                            "clip": clip_b64,
                            "s": score,
                            "r": reason,
                        },
                    )
                    saved += 1
                except Exception as e:
                    print(f"insert fail: {type(e).__name__}: {str(e)[:200]}")

            await db.commit()
            print(f"Relevant: {relevant}, saved: {saved}")


if __name__ == "__main__":
    asyncio.run(run_one(sys.argv[1] if len(sys.argv) > 1 else "Times of India"))
