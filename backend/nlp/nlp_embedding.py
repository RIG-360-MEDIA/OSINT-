"""
LaBSE semantic embedding and deduplication.

Model loaded once at module level and reused across all calls in the worker process.
Title-only articles (< 100 chars) must NOT be passed to generate_embedding.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ── LaBSE model pin (Worldwide Phase 0a, 2026-05-30) ─────────────────────────
# The embedding model is PINNED to a fixed HuggingFace commit. By default LaBSE
# resolves live from HF; a silent upstream update shifts the 768-dim vector
# space so new vectors stop matching stored ones and clustering breaks with NO
# error thrown. This revision is the exact snapshot on disk that produced the
# current corpus. Changing it REQUIRES a full coordinated re-embed (Phase 0c).
LABSE_MODEL_ID = "sentence-transformers/LaBSE"
LABSE_REVISION = "836121a0533e5664b21c7aacc5d22951f2b8b25b"

# Module-level singleton — loaded once per worker process, never reloaded.
_LABSE_MODEL = None


def get_labse_model():
    """Return the cached LaBSE SentenceTransformer, loading it on first call."""
    global _LABSE_MODEL
    if _LABSE_MODEL is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading LaBSE (768-dim, ~1.8 GB) pinned @ %s ...", LABSE_REVISION[:12])
        _LABSE_MODEL = SentenceTransformer(LABSE_MODEL_ID, revision=LABSE_REVISION)
        logger.info("LaBSE loaded (pinned). 768-dim embeddings ready.")
    return _LABSE_MODEL


def generate_embedding(text: str) -> list[float] | None:
    """
    Generate a 768-dim LaBSE embedding for the given text.

    Returns None if text is too short (< 50 chars) or on error.
    Only call for articles with substantial text (> 100 chars).
    """
    if not text or len(text) < 50:
        return None
    try:
        model = get_labse_model()
        embedding = model.encode([text[:512]])
        return embedding[0].tolist()
    except Exception as exc:
        logger.error("LaBSE embedding failed: %s", exc)
        return None


async def check_semantic_duplicate(
    embedding: list[float],
    article_id: str,
    db_conn,
) -> str | None:
    """
    Query pgvector HNSW index for a near-duplicate article.

    Returns the id of the older matching article if cosine distance < 0.08
    (similarity > 0.92), else None.

    The newer article is the duplicate; the older one is kept.
    Search is limited to articles published in the past 7 days to bound
    the comparison set and keep the index warm.
    """
    if not embedding:
        return None
    try:
        from sqlalchemy import text

        result = await db_conn.execute(
            text(
                """
                SELECT id FROM articles
                WHERE labse_embedding IS NOT NULL
                  AND id != :article_id
                  AND nlp_processed = TRUE
                  AND published_at > NOW() - INTERVAL '7 days'
                  AND labse_embedding <=> CAST(:embedding AS vector) < 0.08
                ORDER BY labse_embedding <=> CAST(:embedding AS vector)
                LIMIT 1
                """
            ),
            {
                "article_id": article_id,
                "embedding": str(embedding),
            },
        )
        row = result.fetchone()
        return str(row.id) if row else None
    except Exception as exc:
        logger.warning("Semantic dedup check failed: %s", exc)
        # CRITICAL: rollback the caller's session before returning. The pgvector
        # query above shares the SQLAlchemy session with _process_single in
        # nlp_processor.py; on failure SQLAlchemy marks the transaction
        # invalid, and every subsequent `await db.execute(...)` on the same
        # session raises "Can't reconnect until invalid transaction is rolled
        # back". That wedged the entire NLP batch on 2026-06-04 (1,486-row
        # backlog, Feed lagging 2h+). Swallow any rollback failure too — we
        # never want this helper to raise.
        try:
            await db_conn.rollback()
        except Exception:
            pass
        return None
