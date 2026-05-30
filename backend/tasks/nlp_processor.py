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
    Process up to 50 articles through the 4-step NLP pipeline.
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
    """Fetch one batch of 50 articles and run them through the pipeline."""
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
                LIMIT 50
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
            if _is_junk_article(article.title):
                logger.info("Junk article skipped: %s", repr(article.title)[:80])
                try:
                    # Always set topic_category — leaving it NULL would break
                    # frontend topic filters that assume the column is
                    # populated post-NLP. C-4 of the coverage audit.
                    await db.execute(
                        text(
                            "UPDATE articles SET nlp_processed = TRUE, "
                            "nlp_confidence = 'error', "
                            "topic_category = COALESCE(topic_category, 'OTHER') "
                            "WHERE id = :id"
                        ),
                        {"id": article.id},
                    )
                    await db.commit()
                except Exception:
                    await db.rollback()
                skipped_count += 1
                continue

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
                    # Always set topic_category — leaving it NULL would break
                    # frontend topic filters that assume the column is
                    # populated post-NLP. C-4 of the coverage audit.
                    await db.execute(
                        text(
                            "UPDATE articles SET nlp_processed = TRUE, "
                            "nlp_confidence = 'error', "
                            "topic_category = COALESCE(topic_category, 'OTHER') "
                            "WHERE id = :id"
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


_JUNK_TITLE_PATTERNS = (
    ".pdf", ".xlsx", ".doc", ".docx", ".ppt", ".pptx",
)

def _is_junk_article(title: str | None) -> bool:
    """
    True when the article title is clearly a scraped document or page fragment
    rather than a news article. These waste NLP tokens and pollute relevance.

    Catches: PDF filenames, bare numbers ("221"), very short strings ("tenders").
    """
    if not title:
        return True
    t = title.strip()
    if len(t) < 8:
        return True
    if t.isdigit():
        return True
    tl = t.lower()
    if any(tl.endswith(ext) for ext in _JUNK_TITLE_PATTERNS):
        return True
    return False


async def _process_single(article, db, nlp_model, precomputed_embedding: list[float] | None = None) -> None:
    """Run a single article through all 4 NLP steps and persist results."""
    from sqlalchemy import text

    from backend.nlp.cm.geo_district import load_gazetteer, tag_districts
    from backend.nlp.nlp_embedding import check_semantic_duplicate, generate_embedding, LABSE_REVISION
    from backend.nlp.nlp_entities import extract_entities
    from backend.nlp.nlp_geo import tag_geography
    from backend.nlp.nlp_language import detect_and_translate
    from backend.nlp.nlp_topic import classify_topic, classify_topic_fine

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
    # topic_category: original 15-bucket classifier, LEFT UNTOUCHED so every
    # existing consumer keeps the same contract.
    topic = await classify_topic(
        title=title,
        lead_text_translated=working_text if has_good_text else None,
    )
    # topic_fine (migration 084): additive 25-bucket classifier with a
    # don't-hedge instruction + India-aware buckets. Populated only for
    # articles processed from 2026-05-30 onward; older rows stay NULL.
    topic_fine = await classify_topic_fine(
        title=title,
        lead_text_translated=working_text if has_good_text else None,
    )

    # ── Step 4: Geographic tagging (state-level) ──────────────────────────────
    # NOTE (fix 2026-05-29): geo_secondary is no longer persisted. The column
    # was dropped by scripts/backfill/category_a_fixes.sql (~2026-05-24), which
    # moved geo to a single geo_primary synced from article_locations via
    # trg_sync_geo_primary. The NLP UPDATE still wrote geo_secondary, raising
    # UndefinedColumnError that aborted the ENTIRE _process_single UPDATE —
    # zeroing entities_extracted + labse_embedding for every article from
    # 2026-05-26 (gradual from 05-24 as asyncpg prepared statements recycled).
    geo_primary, _geo_secondary = await tag_geography(
        title=title,
        lead_text_translated=working_text if has_good_text else None,
        entities_extracted=entities,
    )

    # ── Step 5: District tagging (CM Page v2) ────────────────────────────────
    # Reuses entities already extracted in Step 2 — no re-NER. Returns
    # zero or more (district_id, mention_count, confidence, is_primary)
    # rows. The gazetteer is cached per worker process by load_gazetteer.
    # If the districts table is empty (fresh deploy, seed not yet
    # applied), this returns [] and the INSERT loop below is a no-op.
    try:
        gazetteer = await load_gazetteer(db)
        district_matches = tag_districts(
            title=title,
            body=working_text if has_good_text else None,
            entities=entities,
            gazetteer=gazetteer,
        )
    except Exception as exc:  # noqa: BLE001 — district step is best-effort
        logger.warning(
            "district tagging failed for article %s — continuing without districts: %s",
            article.id,
            exc,
        )
        district_matches = []

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
              topic_fine            = :topic_fine,
              geo_primary           = :geo_primary,
              labse_embedding       = CAST(:labse_embedding AS vector),
              embedded_at           = CASE WHEN :embedding_model IS NOT NULL THEN now() ELSE embedded_at END,
              embedding_model       = COALESCE(:embedding_model, embedding_model),
              embedding_revision    = COALESCE(:embedding_revision, embedding_revision),
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
            "topic_fine": topic_fine,
            "geo_primary": geo_primary,
            "labse_embedding": embedding_str,
            "embedding_model": "sentence-transformers/LaBSE" if embedding else None,
            "embedding_revision": LABSE_REVISION if embedding else None,
            "is_duplicate": is_duplicate,
            "duplicate_of": duplicate_of,
            "nlp_confidence": nlp_confidence,
        },
    )

    # ── Persist district tags (CM Page v2) ────────────────────────────────────
    # Wrapped in a savepoint so a per-row failure (e.g. stale gazetteer
    # mapping a district_id no longer in the districts table) doesn't
    # abort the surrounding article batch transaction.
    if district_matches:
        try:
            async with db.begin_nested():
                for m in district_matches:
                    await db.execute(
                        text(
                            """
                            INSERT INTO article_districts
                                (article_id, district_id, mention_count, confidence, is_primary)
                            VALUES
                                (:aid, :did, :n, :c, :p)
                            ON CONFLICT (article_id, district_id) DO UPDATE SET
                                mention_count = EXCLUDED.mention_count,
                                confidence    = EXCLUDED.confidence,
                                is_primary    = EXCLUDED.is_primary
                            """
                        ),
                        {
                            "aid": article.id,
                            "did": m.district_id,
                            "n": m.mention_count,
                            "c": m.confidence,
                            "p": m.is_primary,
                        },
                    )
        except Exception as exc:  # noqa: BLE001 — district persist is best-effort
            logger.warning(
                "article_districts persist failed for article %s: %s",
                article.id,
                exc,
            )
