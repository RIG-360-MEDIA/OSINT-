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
    """Async core — orchestrate portal scrape → extract → NLP → store.

    Per-source: writes a govt_collection_runs audit row and updates
    govt_document_sources health (mirrors RSS pattern).
    """
    import spacy

    from backend.collectors.govt_collector import (
        download_pdf,
        extract_text_from_pdf,
        fetch_document_urls,
    )
    from backend.database import get_db
    from backend.nlp.govt_chunker import chunk_document_smart
    from backend.nlp.govt_intel import compute_intrinsic_importance, extract_intel
    from backend.nlp.nlp_embedding import generate_embedding
    from backend.nlp.nlp_entities import extract_entities
    from backend.nlp.nlp_geo import tag_geography
    from backend.nlp.nlp_language import detect_and_translate
    from backend.nlp.nlp_topic import classify_topic
    from backend.observability.govt_runs import (
        finish_collection_run,
        start_collection_run,
        update_source_health,
    )

    nlp_model = spacy.load("en_core_web_sm")
    documents_inserted = 0

    async with get_db() as _src_db:
        sources_result = await _src_db.execute(
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
            async with get_db() as db:

                run_id = await start_collection_run(
                    db, source_id=str(source.id), source_name=source.name,
                )
                urls_discovered = 0
                pdfs_downloaded = 0
                source_inserted = 0
                docs_failed = 0
                source_error: str | None = None

                from backend.collectors.sources.registry import (
                    read_junk_counter,
                    reset_junk_counter,
                )
                reset_junk_counter()
                from backend.config.govt_config import DEFAULT_SINCE_DAYS
                try:
                    doc_urls = await fetch_document_urls(
                        source.portal_url,
                        source.document_type,
                        since_days=DEFAULT_SINCE_DAYS,
                    )
                except Exception as exc:
                    logger.warning(
                        "Source %s scrape failed: %s — continuing",
                        source.name,
                        exc,
                    )
                    doc_urls = []
                    source_error = f"discovery: {exc}"
                urls_discovered = len(doc_urls)
                urls_filtered_junk = read_junk_counter()

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
                            docs_failed += 1
                            continue
                        pdfs_downloaded += 1

                        full_text = await extract_text_from_pdf(pdf_path)
                        if not full_text or len(full_text) < 100:
                            docs_failed += 1
                            continue

                        title = doc_info["title"]
                        published_at = doc_info.get("published_at")

                        try:
                            lang, translated = await detect_and_translate(
                                full_text[:2000],
                                title,
                            )
                        except Exception as exc:
                            logger.warning("Translation failed: %s", exc)
                            lang, translated = "en", None

                        text_for_nlp = (translated or full_text)[:3000]

                        # Structured intel extraction (Groq) + intrinsic importance score
                        try:
                            intel = await extract_intel(translated or full_text, title)
                            intrinsic = compute_intrinsic_importance(intel)
                        except Exception as exc:
                            logger.warning("Intel extraction failed for %s: %s", title[:60], exc)
                            from backend.nlp.govt_intel_schema import GovtDocIntel
                            intel = GovtDocIntel(what_it_does="(extraction failed)")
                            intrinsic = 0.0

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

                        intel_dump = intel.model_dump(mode="json")
                        # asyncpg refuses to coerce a string into a DATE column
                        # ('str' has no attribute 'toordinal'). Convert here.
                        effective_date_iso = intel_dump.get("effective_date")
                        if isinstance(effective_date_iso, str):
                            try:
                                from datetime import date as _date
                                effective_date_iso = _date.fromisoformat(
                                    effective_date_iso.replace("Z", "")[:10]
                                )
                            except ValueError:
                                effective_date_iso = None
                        geography_affected_json = json.dumps(
                            intel_dump.get("geography_affected") or []
                        )
                        winners_json = json.dumps(intel_dump.get("winners") or [])
                        losers_json = json.dumps(intel_dump.get("losers") or [])

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
                                    nlp_processed,
                                    intel_json,
                                    intrinsic_importance,
                                    document_nature,
                                    action_posture,
                                    geography_affected,
                                    financial_magnitude_inr,
                                    effective_date,
                                    winners,
                                    losers,
                                    enforcement_strength,
                                    published_at
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
                                    TRUE,
                                    CAST(:intel_json AS JSONB),
                                    :intrinsic,
                                    :doc_nature,
                                    :action_posture,
                                    CAST(:geo_affected AS JSONB),
                                    :fin_magnitude,
                                    CAST(:eff_date AS DATE),
                                    CAST(:winners AS JSONB),
                                    CAST(:losers AS JSONB),
                                    :enforcement,
                                    :published_at
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
                                "intel_json": intel.model_dump_json(),
                                "intrinsic": float(intrinsic),
                                "doc_nature": intel.document_nature,
                                "action_posture": intel.action_posture,
                                "geo_affected": geography_affected_json,
                                "fin_magnitude": intel.financial_magnitude_inr,
                                "eff_date": effective_date_iso,
                                "winners": winners_json,
                                "losers": losers_json,
                                "enforcement": intel.enforcement_strength,
                                "published_at": published_at,
                            },
                        )

                        doc_row = inserted.fetchone()
                        if not doc_row:
                            continue
                        doc_id = doc_row.id

                        # Section-aware chunking over the FULL translated/native doc
                        chunks = chunk_document_smart(translated or full_text)
                        for chunk in chunks:
                            chunk_emb = generate_embedding(chunk["text"][:512])
                            await db.execute(
                                text(
                                    """
                                    INSERT INTO govt_document_chunks (
                                        document_id,
                                        chunk_index,
                                        chunk_text,
                                        labse_embedding,
                                        section_heading,
                                        start_char,
                                        end_char
                                    ) VALUES (
                                        CAST(:doc_id AS uuid),
                                        :idx,
                                        :text,
                                        CAST(:emb AS vector),
                                        :section_heading,
                                        :start_char,
                                        :end_char
                                    )
                                    ON CONFLICT (document_id, chunk_index) DO NOTHING
                                    """
                                ),
                                {
                                    "doc_id": str(doc_id),
                                    "idx": chunk["index"],
                                    "text": chunk["text"],
                                    "emb": str(chunk_emb) if chunk_emb else None,
                                    "section_heading": chunk.get("section_heading"),
                                    "start_char": chunk.get("start_char"),
                                    "end_char": chunk.get("end_char"),
                                },
                            )

                        documents_inserted += 1
                        source_inserted += 1
                        logger.info(
                            "Stored govt doc: %s",
                            title[:60],
                        )

                        # Fan-out: per-user relevance scoring (P15 govt-relevance pipeline)
                        try:
                            from backend.tasks.govt_relevance_task import (
                                score_govt_doc_for_all_users,
                            )
                            score_govt_doc_for_all_users.delay(str(doc_id))
                        except Exception as exc:
                            logger.warning(
                                "Failed to queue relevance scoring for new doc %s: %s",
                                doc_id, exc,
                            )

                success = source_error is None
                await finish_collection_run(
                    db,
                    run_id=run_id,
                    status="completed" if success else "failed",
                    urls_discovered=urls_discovered,
                    urls_filtered_junk=urls_filtered_junk,
                    pdfs_downloaded=pdfs_downloaded,
                    docs_inserted=source_inserted,
                    docs_failed=docs_failed,
                    error_summary=source_error,
                )
                await update_source_health(
                    db, source_id=str(source.id), success=success,
                )

                await db.commit()
        except Exception as exc:
            logger.exception(
                "Source %s isolated failure: %s — continuing",
                source.name, exc,
            )
            continue

    return {"documents_inserted": documents_inserted}
