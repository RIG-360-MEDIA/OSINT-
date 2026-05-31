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

        from backend.nlp.embedding_recipe import RECIPE

        logger.info("Loading LaBSE (768-dim, ~1.8 GB) pinned @ %s ...", LABSE_REVISION[:12])
        _LABSE_MODEL = SentenceTransformer(LABSE_MODEL_ID, revision=LABSE_REVISION)
        # max_seq_length is PART OF THE RECIPE (0a/0c must match). LaBSE defaults
        # to 256; a recipe with a >512-char window silently truncates without this.
        try:
            _LABSE_MODEL.max_seq_length = RECIPE.max_seq_length
        except Exception:  # noqa: BLE001 — never block embedding on this
            pass
        logger.info(
            "LaBSE loaded (pinned, max_seq_length=%s). 768-dim embeddings ready.",
            getattr(_LABSE_MODEL, "max_seq_length", "?"),
        )
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


def encode_text(texts: "str | list[str]") -> list[list[float] | None]:
    """Batch-encode text that is ALREADY recipe-windowed (0a/0c path).

    Unlike generate_embedding, this does NOT char-truncate — the caller applied
    the recipe's char_window via embedding_recipe.build_embedding_text(), and the
    model's max_seq_length (set from RECIPE in get_labse_model) handles token cap.

    Accepts a single string or a list; always returns a list with one entry per
    input (a 768-dim list, or None on failure), so callers can zip with their ids.
    """
    if isinstance(texts, str):
        texts = [texts]
    if not texts:
        return []
    try:
        model = get_labse_model()
        vecs = model.encode(texts)
        return [v.tolist() for v in vecs]
    except Exception as exc:
        logger.error("LaBSE encode_text failed: %s", exc)
        return [None] * len(texts)


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
        return None
