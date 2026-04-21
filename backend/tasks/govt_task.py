"""
Government document collection Celery task.

Daily at 06:30 UTC: scrape every active govt portal → download PDFs →
extract text → translate non-English → run NLP (entities, topic, geo) →
embed summary + chunks → upsert into govt_documents and govt_document_chunks.

Mirrors the RSS collector's task pattern: async core wrapped by asyncio.run().
"""
from __future__ import annotations

import asyncio
import json
import logging
import tempfile

from sqlalchemy import text

from backend.celery_app import app

logger = logging.getLogger(__name__)


@app.task(
    name="tasks.collect_govt_documents",
    bind=True,
    max_retries=2,
)
def collect_govt_documents(self):  # type: ignore[no-untyped-def]
    """Collect new government documents from all active portals."""
    try:
        result = asyncio.run(_collect_govt_docs())
        logger.info(
            "Govt collection complete: %d new documents",
            result["documents_inserted"],
        )
        return result
    except Exception as exc:
        logger.error("Govt collection failed: %s", exc)
        raise self.retry(exc=exc, countdown=300)


async def _collect_govt_docs() -> dict:
    """Async core — orchestrate portal scrape → extract → NLP → store."""
    import spacy

    from backend.collectors.govt_collector import (
        chunk_document,
        download_pdf,
        extract_text_from_pdf,
        fetch_document_urls,
    )
    from backend.database import get_db
    from backend.nlp.nlp_embedding import generate_embedding
    from backend.nlp.nlp_entities import extract_entities
    from backend.nlp.nlp_geo import tag_geography
    from backend.nlp.nlp_language import detect_and_translate
    from backend.nlp.nlp_topic import classify_topic

    nlp_model = spacy.load("en_core_web_sm")
    documents_inserted = 0

    async with get_db() as db:
        sources_result = await db.execute(
            text(
                """
                SELECT id, name, portal_url, source_geography, document_type
                FROM govt_document_sources
                WHERE is_active = TRUE
                """
            )
        )
        sources = sources_result.fetchall()

        for source in sources:
            logger.info("Scraping govt portal: %s", source.name)

            try:
                doc_urls = await fetch_document_urls(
                    source.portal_url,
                    source.document_type,
                )
            except Exception as exc:
                logger.warning(
                    "Source %s scrape failed: %s — continuing",
                    source.name,
                    exc,
                )
                doc_urls = []

            for doc_info in doc_urls:
                url = doc_info["url"]

                existing = await db.execute(
                    text(
                        "SELECT id FROM govt_documents WHERE document_url = :url"
                    ),
                    {"url": url},
                )
                if existing.fetchone():
                    continue

                with tempfile.TemporaryDirectory() as tmpdir:
                    pdf_path = await download_pdf(url, tmpdir)
                    if not pdf_path:
                        continue

                    full_text = await extract_text_from_pdf(pdf_path)
                    if not full_text or len(full_text) < 100:
                        continue

                    title = doc_info["title"]

                    try:
                        lang, translated = await detect_and_translate(
                            full_text[:2000],
                            title,
                        )
                    except Exception as exc:
                        logger.warning("Translation failed: %s", exc)
                        lang, translated = "en", None

                    text_for_nlp = (translated or full_text)[:3000]

                    try:
                        entities = extract_entities(
                            title,
                            text_for_nlp,
                            nlp_model,
                        )
                    except Exception as exc:
                        logger.warning("Entity extraction failed: %s", exc)
                        entities = []

                    try:
                        topic = await classify_topic(title, text_for_nlp)
                    except Exception as exc:
                        logger.warning("Topic classification failed: %s", exc)
                        topic = "OTHER"

                    try:
                        geo, _ = await tag_geography(
                            title,
                            text_for_nlp,
                            entities,
                        )
                    except Exception as exc:
                        logger.warning("Geo tagging failed: %s", exc)
                        geo = None

                    embedding = generate_embedding(text_for_nlp[:512])

                    inserted = await db.execute(
                        text(
                            """
                            INSERT INTO govt_documents (
                                source_id,
                                source_name,
                                source_geography,
                                document_type,
                                title,
                                document_url,
                                full_text,
                                full_text_translated,
                                language_detected,
                                topic_category,
                                geo_primary,
                                entities_extracted,
                                labse_embedding,
                                nlp_processed
                            ) VALUES (
                                :source_id,
                                :source_name,
                                :source_geo,
                                :doc_type,
                                :title,
                                :url,
                                :full_text,
                                :translated,
                                :lang,
                                :topic,
                                :geo,
                                CAST(:entities AS JSONB),
                                CAST(:embedding AS vector),
                                TRUE
                            )
                            ON CONFLICT (document_url) DO NOTHING
                            RETURNING id
                            """
                        ),
                        {
                            "source_id": str(source.id),
                            "source_name": source.name,
                            "source_geo": source.source_geography,
                            "doc_type": source.document_type,
                            "title": title[:1000],
                            "url": url,
                            "full_text": full_text[:50000],
                            "translated": (translated or "")[:50000] or None,
                            "lang": lang,
                            "topic": topic,
                            "geo": geo,
                            "entities": json.dumps(entities),
                            "embedding": str(embedding) if embedding else None,
                        },
                    )

                    doc_row = inserted.fetchone()
                    if not doc_row:
                        continue
                    doc_id = doc_row.id

                    chunks = chunk_document(text_for_nlp)
                    for chunk in chunks[:20]:
                        chunk_emb = generate_embedding(chunk["text"])
                        await db.execute(
                            text(
                                """
                                INSERT INTO govt_document_chunks (
                                    document_id,
                                    chunk_index,
                                    chunk_text,
                                    labse_embedding
                                ) VALUES (
                                    CAST(:doc_id AS uuid),
                                    :idx,
                                    :text,
                                    CAST(:emb AS vector)
                                )
                                ON CONFLICT (document_id, chunk_index) DO NOTHING
                                """
                            ),
                            {
                                "doc_id": str(doc_id),
                                "idx": chunk["index"],
                                "text": chunk["text"],
                                "emb": str(chunk_emb) if chunk_emb else None,
                            },
                        )

                    documents_inserted += 1
                    logger.info(
                        "Stored govt doc: %s",
                        title[:60],
                    )

            await db.execute(
                text(
                    """
                    UPDATE govt_document_sources
                    SET last_scraped_at = NOW()
                    WHERE id = :sid
                    """
                ),
                {"sid": str(source.id)},
            )

        await db.commit()

    return {"documents_inserted": documents_inserted}
