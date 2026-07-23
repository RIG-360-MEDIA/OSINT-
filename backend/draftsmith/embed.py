"""backend.draftsmith.embed — async LaBSE embedding for draftsmith.

Reuses backend.nlp.nlp_embedding's module-level LaBSE singleton
(generate_embedding / get_labse_model). NEVER instantiate a second
SentenceTransformer here — the box has ~3.6 GB free RAM and a second 1.8 GB
model load would starve the other pillars sharing the process.

generate_embedding is synchronous (model.encode blocks); it is wrapped via
asyncio.to_thread so draftsmith's async pipeline never blocks its event
loop on CPU-bound encoding. Batches run through a single worker thread
(sequential encode calls) rather than one thread per item, so concurrent
callers never hit the shared model object from multiple threads at once.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Sequence

from backend.nlp import nlp_embedding

logger = logging.getLogger(__name__)

# nlp_embedding.generate_embedding's own floor — texts shorter than this
# return None rather than a vector. Surfaced here so callers get an
# actionable error instead of a bare "embedding is None".
_MIN_TEXT_CHARS = 50


class EmbeddingError(Exception):
    """Raised when LaBSE embedding generation fails or returns nothing
    usable for a given text (too short, remote+local both errored, etc.)."""


def _embed_one_sync(text: str) -> list[float] | None:
    return nlp_embedding.generate_embedding(text)


def _embed_many_sync(texts: list[str]) -> list[list[float] | None]:
    # Sequential on purpose: one thread, one pass through the shared model
    # instance (or one pass of remote-server calls), so batch callers never
    # race concurrent to_thread() calls against the same singleton.
    return [nlp_embedding.generate_embedding(t) for t in texts]


async def embed_text(text: str) -> list[float]:
    """Embed a single string. Raises EmbeddingError if `text` is empty/too
    short for LaBSE, or if the model (remote server + in-process fallback)
    could not produce a vector."""
    if not text or not text.strip():
        raise EmbeddingError("embed_text: empty text")
    if len(text) < _MIN_TEXT_CHARS:
        raise EmbeddingError(
            f"embed_text: text too short for LaBSE ({len(text)} chars, "
            f"need >= {_MIN_TEXT_CHARS})"
        )
    vector = await asyncio.to_thread(_embed_one_sync, text)
    if vector is None:
        raise EmbeddingError(
            f"LaBSE returned no embedding for text of length {len(text)} "
            "(see backend.nlp.nlp_embedding logs for the underlying cause)"
        )
    return vector


async def embed_batch(texts: Sequence[str]) -> list[list[float]]:
    """Embed a batch of strings, preserving input order. Raises
    EmbeddingError (naming the first failing index) if ANY text is empty,
    too short, or fails to embed — callers that want partial-success
    semantics should filter their inputs before calling this."""
    if not texts:
        return []
    texts_list = list(texts)
    for i, t in enumerate(texts_list):
        if not t or not t.strip():
            raise EmbeddingError(f"embed_batch: empty text at index {i}")
        if len(t) < _MIN_TEXT_CHARS:
            raise EmbeddingError(
                f"embed_batch: text at index {i} too short for LaBSE "
                f"({len(t)} chars, need >= {_MIN_TEXT_CHARS})"
            )

    results = await asyncio.to_thread(_embed_many_sync, texts_list)

    vectors: list[list[float]] = []
    for i, vector in enumerate(results):
        if vector is None:
            raise EmbeddingError(
                f"LaBSE returned no embedding for batch item at index {i} "
                "(see backend.nlp.nlp_embedding logs for the underlying cause)"
            )
        vectors.append(vector)
    return vectors
