"""Query embedding via LaBSE — the model family behind ``articles.labse_embedding_v4``.

The v4 doc recipe (``v4-tr-title-1024``) embeds the English-translated title with
``sentence-transformers/LaBSE``. LaBSE is cross-lingual, so embedding a raw user
query (in any language) with the same model lands in the same vector space — an
English query can retrieve Telugu/Hindi articles. Confirm this empirically with
``scripts/verify_embedding.py`` before trusting production.
"""
from __future__ import annotations

from typing import Protocol

_model = None  # lazy module-level singleton; the model is ~1.8 GB on disk


class QueryEmbedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


class LabseEmbedder:
    """Lazy-loading LaBSE embedder. The heavy import happens on first ``embed``."""

    def __init__(self, model_name: str = "sentence-transformers/LaBSE") -> None:
        self._model_name = model_name

    def _load(self):
        global _model
        if _model is None:
            from sentence_transformers import SentenceTransformer  # heavy, lazy

            _model = SentenceTransformer(self._model_name)
        return _model

    def embed(self, text: str) -> list[float]:
        if not text or not text.strip():
            raise ValueError("Cannot embed an empty query")
        vec = self._load().encode(text.strip(), normalize_embeddings=True)
        return [float(x) for x in vec]


def to_pgvector(vec: list[float]) -> str:
    """Format a float vector as a pgvector literal, e.g. ``[0.1,0.2,...]``.

    Bound as a text parameter and cast ``(:qvec)::vector`` in SQL, so no value is
    ever string-concatenated into the query.
    """
    if not vec:
        raise ValueError("Cannot format an empty vector")
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"
