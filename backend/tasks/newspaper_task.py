"""
Celery task — daily newspaper clipping collection (P16 Cutting Room).

Runs at 07:30 UTC, after CareersWave.in has posted the day's PDFs.
Walks every active newspaper_source, downloads the PDF, extracts
articles with bounding boxes, scores them, renders visual clippings
for relevant articles, and writes newspaper_clippings rows.
"""

import asyncio
import logging
import os
import tempfile
from datetime import date

from sqlalchemy import text

from backend.celery_app import app

logger = logging.getLogger(__name__)


@app.task(
    name="tasks.collect_newspapers",
    queue="collectors",
    max_retries=2,
)
def collect_newspapers() -> None:
    """Celery entrypoint. Delegates to the async implementation."""
    asyncio.run(_collect_newspapers())


async def _collect_newspapers() -> None:
    from backend.database import get_db
    from backend.collectors.newspaper_collector import (
        download_pdf_from_url,
        extract_articles_from_pdf,
        get_pdf_url_from_careerswave,
        is_relevant_to_user,
        render_article_clipping,
    )
    from backend.nlp.nlp_embedding import generate_embedding
    from backend.nlp.nlp_language import detect_and_translate

    today = date.today()

    async with get_db() as db:
        papers_result = await db.execute(
            text(
                """
                SELECT id, name, language, careerswave_url
                FROM newspaper_sources
                WHERE is_active = TRUE
                  AND careerswave_url IS NOT NULL
                """
            )
        )
        papers = papers_result.fetchall()

        entities_result = await db.execute(
            text("SELECT DISTINCT canonical_name FROM user_entities")
        )
        user_entities = [
            r.canonical_name for r in entities_result.fetchall()
        ]

        geo_result = await db.execute(
            text("SELECT geo_primary FROM user_profiles LIMIT 1")
        )
        geo_row = geo_result.fetchone()
        user_geo = geo_row.geo_primary if geo_row else "Telangana"

        total_clippings = 0

        for paper in papers:
            logger.info(f"Processing: {paper.name}")

            existing = await db.execute(
                text(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM newspaper_clippings
                    WHERE newspaper_id = CAST(:pid AS uuid)
                      AND edition_date = :today
                    """
                ),
                {"pid": str(paper.id), "today": today},
            )
            if existing.fetchone().cnt > 5:
                logger.info(f"{paper.name} already processed today")
                continue

            pdf_url = await get_pdf_url_from_careerswave(paper.careerswave_url)
            if not pdf_url:
                logger.warning(f"No PDF URL found for {paper.name}")
                continue

            with tempfile.TemporaryDirectory() as tmpdir:
                safe_name = paper.name.replace(" ", "_").replace("/", "_")
                pdf_path = os.path.join(tmpdir, f"{safe_name}.pdf")
                ok = await download_pdf_from_url(pdf_url, pdf_path)
                if not ok or not os.path.exists(pdf_path) or os.path.getsize(pdf_path) < 1024:
                    logger.warning(
                        "PDF download failed or too small for %s (%s)",
                        paper.name,
                        pdf_url,
                    )
                    continue
                logger.info(
                    "Downloaded %s: %d bytes",
                    paper.name,
                    os.path.getsize(pdf_path),
                )

                articles = await extract_articles_from_pdf(
                    pdf_path, paper.language
                )
                logger.info(
                    f"{paper.name}: found {len(articles)} articles"
                )

                for article in articles[:50]:
                    headline = article.get("headline") or ""
                    body = article.get("text") or ""
                    if not headline or len(body) < 50:
                        continue

                    is_rel, score, reason = await is_relevant_to_user(
                        headline, body, user_entities, user_geo,
                    )
                    if not is_rel:
                        continue

                    headline_translated: str | None = None
                    text_translated: str | None = None
                    if paper.language != "en":
                        try:
                            _, headline_translated = await detect_and_translate(
                                None, headline
                            )
                        except Exception as e:
                            logger.debug(f"Headline translate failed: {e}")
                        try:
                            _, text_translated = await detect_and_translate(
                                body[:2000], headline
                            )
                        except Exception as e:
                            logger.debug(f"Body translate failed: {e}")

                    clipping_b64: str | None = None
                    bbox = article.get("bounding_box", []) or []
                    if bbox:
                        clipping_b64 = render_article_clipping(
                            pdf_path,
                            article.get("page_number", 1),
                            bbox,
                        )

                    embed_text = (text_translated or body)[:512]
                    embedding: list[float] | None = None
                    try:
                        embedding = generate_embedding(embed_text)
                    except Exception as e:
                        logger.debug(f"Embedding failed: {e}")

                    try:
                        await db.execute(
                            text(
                                """
                                INSERT INTO newspaper_clippings (
                                    newspaper_id,
                                    newspaper_name,
                                    newspaper_language,
                                    edition_date,
                                    page_number,
                                    headline,
                                    headline_translated,
                                    article_text,
                                    article_text_translated,
                                    bbox_left,
                                    bbox_bottom,
                                    bbox_right,
                                    bbox_top,
                                    clipping_image_b64,
                                    relevance_score,
                                    relevance_explanation,
                                    labse_embedding
                                ) VALUES (
                                    CAST(:nid AS uuid),
                                    :name,
                                    :lang,
                                    :edition_date,
                                    :page_num,
                                    :headline,
                                    :headline_tr,
                                    :text,
                                    :text_tr,
                                    :bbox_l,
                                    :bbox_b,
                                    :bbox_r,
                                    :bbox_t,
                                    :clipping,
                                    :score,
                                    :reason,
                                    CAST(:emb AS vector)
                                )
                                ON CONFLICT (
                                    newspaper_id, edition_date, headline
                                ) DO NOTHING
                                """
                            ),
                            {
                                "nid": str(paper.id),
                                "name": paper.name,
                                "lang": paper.language,
                                "edition_date": today,
                                "page_num": article.get("page_number"),
                                "headline": headline[:500],
                                "headline_tr": headline_translated,
                                "text": body[:10000],
                                "text_tr": text_translated,
                                "bbox_l": bbox[0] if len(bbox) > 0 else None,
                                "bbox_b": bbox[1] if len(bbox) > 1 else None,
                                "bbox_r": bbox[2] if len(bbox) > 2 else None,
                                "bbox_t": bbox[3] if len(bbox) > 3 else None,
                                "clipping": clipping_b64,
                                "score": score,
                                "reason": reason,
                                "emb": str(embedding) if embedding else None,
                            },
                        )
                        total_clippings += 1
                    except Exception as e:
                        logger.warning(f"Clipping insert failed: {e}")

            await db.execute(
                text(
                    """
                    UPDATE newspaper_sources
                    SET last_scraped_at = NOW()
                    WHERE id = CAST(:pid AS uuid)
                    """
                ),
                {"pid": str(paper.id)},
            )

        await db.commit()
        logger.info(
            f"Newspaper collection done: {total_clippings} clippings"
        )
