"""
NLP batch processor — Celery task that runs every 30 seconds.

Processes up to 100 articles through the 4-step pipeline:
  Step 1: Language detection + translation
  Step 2: Entity extraction with prominence scoring
  Step 3: Topic classification
  Step 4: Geographic tagging
  + LaBSE embedding (full-text articles only, batch-encoded in one model call)
  + Semantic deduplication (full-text articles only)

Processing order: collected_at DESC (newest first — mandatory for demo quality).
"""
from __future__ import annotations

import asyncio
import json
import logging

from backend.celery_app import app

logger = logging.getLogger(__name__)


@app.task(
    name="tasks.process_nlp_batch",
    bind=True,
    max_retries=3,
    queue="nlp",
)
def process_nlp_batch(self):  # type: ignore[no-untyped-def]
    """
    Process up to 100 articles through the 4-step NLP pipeline.
    Runs every 30 seconds via Celery Beat.
    """
    try:
        result = asyncio.run(_process_batch())
        logger.info(
            "NLP batch complete: %d processed, %d skipped",
            result["processed"],
            result["skipped"],
        )
        return result
    except Exception as exc:
        logger.error("NLP batch failed: %s", exc)
        raise self.retry(exc=exc, countdown=30)


async def _process_batch() -> dict:
    """Fetch one batch of 100 articles and run them through the pipeline."""
    import spacy
    from sqlalchemy import text

    from backend.database import get_db
    from backend.nlp.nlp_entities import extract_entities, load_entity_dictionary
    from backend.nlp.nlp_embedding import generate_embedding, get_labse_model

    # Load SpaCy model once per batch — fast (already on disk)
    nlp_model = spacy.load("en_core_web_sm")

    # Load LaBSE once — used for pre-batch encoding below
    labse_model = get_labse_model()

    async with get_db() as db:
        # Load entity dictionary once per batch (cached after first load)
        await load_entity_dictionary(db)

        # CRITICAL: DESC order — newest articles first
        result = await db.execute(
            text(
                """
                SELECT id, title, lead_text_original, lead_text_translated,
                       source_id, url
                FROM articles
                WHERE nlp_processed = FALSE
                ORDER BY collected_at DESC
                LIMIT 100
                """
            )
        )
        articles = result.fetchall()

        if not articles:
            return {"processed": 0, "skipped": 0, "message": "No pending articles"}

        # Lever 2: batch-encode all article texts in one LaBSE call instead of
        # calling model.encode() once per article inside _process_single.
        # LaBSE is multilingual — using lead_text_original is correct here.
        _embed_texts: list[str] = []
        _embed_ids: list[str] = []
        for art in articles:
            lead = art.lead_text_original
            if lead and not _is_valid_text(lead):
                lead = None
            if lead and len(lead) > 100:
                _embed_texts.append((art.lead_text_translated or lead)[:512])
                _embed_ids.append(str(art.id))

        precomputed_embeddings: dict[str, list[float]] = {}
        if _embed_texts:
            batch_vecs = labse_model.encode(_embed_texts)
            precomputed_embeddings = {
                aid: vec.tolist()
                for aid, vec in zip(_embed_ids, batch_vecs)
            }

        processed_ids: list[str] = []
        processed_count = 0
        skipped_count = 0

        for article in articles:
            try:
                await _process_single(
                    article=article,
                    db=db,
                    nlp_model=nlp_model,
                    precomputed_embedding=precomputed_embeddings.get(str(article.id)),
                )
                await db.commit()  # Commit each article independently
                processed_ids.append(str(article.id))
                processed_count += 1
            except Exception as exc:
                import traceback as tb
                logger.error(
                    "Article %s failed:\n%s", article.id, tb.format_exc()
                )
                # Rollback aborted transaction BEFORE error-recovery UPDATE
                await db.rollback()
                try:
                    await db.execute(
                        text(
                            "UPDATE articles SET nlp_processed = TRUE, "
                            "nlp_confidence = 'error' WHERE id = :id"
                        ),
                        {"id": article.id},
                    )
                    await db.commit()
                except Exception as recovery_exc:
                    logger.error(
                        "Error recovery also failed for %s: %s",
                        article.id,
                        recovery_exc,
                    )
                    await db.rollback()
                skipped_count += 1

        if processed_ids:
            from backend.celery_app import app as celery_app
            celery_app.send_task(
                "tasks.score_relevance_batch",
                args=[processed_ids],
                queue="relevance",
            )
            logger.info(
                "Relevance scoring queued for %d articles",
                len(processed_ids),
            )

        return {"processed": processed_count, "skipped": skipped_count}


def _is_valid_text(text: str) -> bool:
    """Return False if text is binary garbage rather than readable prose."""
    if not text or len(text) < 20:
        return False
    sample = text[:200]
    printable = sum(1 for c in sample if c.isprintable() or c in "\n\r\t")
    return (printable / len(sample)) > 0.85


async def _process_single(article, db, nlp_model, precomputed_embedding: list[float] | None = None) -> None:
    """Run a single article through all 4 NLP steps and persist results."""
    from sqlalchemy import text

    from backend.nlp.nlp_embedding import check_semantic_duplicate, generate_embedding
    from backend.nlp.nlp_entities import extract_entities
    from backend.nlp.nlp_geo import tag_geography
    from backend.nlp.nlp_language import detect_and_translate
    from backend.nlp.nlp_topic import classify_topic

    title = article.title or ""
    lead_original = article.lead_text_original

    # Discard binary/corrupted content — fall through to title-only path
    if lead_original and not _is_valid_text(lead_original):
        logger.info("Binary content detected for article %s — title-only path", article.id)
        lead_original = None

    has_good_text = lead_original is not None and len(lead_original) > 100

    # ── Step 1: Language detection + translation ──────────────────────────────
    if has_good_text:
        language, lead_translated = await detect_and_translate(lead_original, title)
    else:
        language = "en"
        lead_translated = title

    # ── Step 2: Entity extraction ─────────────────────────────────────────────
    working_text = lead_translated if has_good_text else title
    entities = extract_entities(title=title, text=working_text, nlp_model=nlp_model)

    # ── Step 3: Topic classification ──────────────────────────────────────────
    topic = await classify_topic(
        title=title,
        lead_text_translated=working_text if has_good_text else None,
    )

    # ── Step 4: Geographic tagging ────────────────────────────────────────────
    geo_primary, geo_secondary = await tag_geography(
        title=title,
        lead_text_translated=working_text if has_good_text else None,
        entities_extracted=entities,
    )

    # ── LaBSE embedding + semantic dedup (full-text only) ────────────────────
    embedding: list[float] | None = None
    is_duplicate = False
    duplicate_of: str | None = None

    if has_good_text:
        embedding = precomputed_embedding or generate_embedding(working_text)
        if embedding:
            dup_id = await check_semantic_duplicate(
                embedding=embedding,
                article_id=str(article.id),
                db_conn=db,
            )
            if dup_id:
                is_duplicate = True
                duplicate_of = dup_id

    nlp_confidence = "normal" if has_good_text else "low"

    # ── Persist results ───────────────────────────────────────────────────────
    embedding_str = str(embedding) if embedding else None

    await db.execute(
        text(
            """
            UPDATE articles SET
              language_detected     = :language_detected,
              lead_text_translated  = :lead_text_translated,
              entities_extracted    = CAST(:entities_extracted AS jsonb),
              topic_category        = :topic_category,
              geo_primary           = :geo_primary,
              geo_secondary         = :geo_secondary,
              labse_embedding       = CAST(:labse_embedding AS vector),
              is_duplicate          = :is_duplicate,
              duplicate_of          = CAST(:duplicate_of AS uuid),
              nlp_processed         = TRUE,
              nlp_confidence        = :nlp_confidence
            WHERE id = :id
            """
        ),
        {
            "id": article.id,
            "language_detected": language,
            "lead_text_translated": lead_translated if has_good_text else None,
            "entities_extracted": json.dumps(entities),
            "topic_category": topic,
            "geo_primary": geo_primary,
            "geo_secondary": geo_secondary,
            "labse_embedding": embedding_str,
            "is_duplicate": is_duplicate,
            "duplicate_of": duplicate_of,
            "nlp_confidence": nlp_confidence,
        },
    )
