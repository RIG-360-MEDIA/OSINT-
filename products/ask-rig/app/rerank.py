"""Two-tier reranking.

fast_rerank() — FlashRank nano model (~12 MB, sub-100ms on CPU).
               Always runs — lifts precision with negligible latency.

deep_rerank() — BAAI/bge-reranker-v2-m3 via CrossEncoder (~568 MB, ~0.8s/doc).
               Opt-in: toggled by the "deep rerank" checkbox in the UI or
               ASKRIG_RERANK_ENABLED=true in env.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache

from app.schemas import RetrievedDoc

logger = logging.getLogger(__name__)

# ── Fast path: FlashRank ──────────────────────────────────────────────────────

_FAST_MODEL_DEFAULT = "ms-marco-MiniLM-L-12-v2"


@lru_cache(maxsize=4)
def _fast_ranker(model_name: str):
    from flashrank import Ranker

    logger.info("Loading FlashRank %s (once)", model_name)
    return Ranker(model_name=model_name)


def fast_rerank(
    query: str,
    docs: list[RetrievedDoc],
    top_n: int,
    model_name: str = _FAST_MODEL_DEFAULT,
) -> list[RetrievedDoc]:
    """FlashRank reranking — runs on every request, sub-100ms on CPU."""
    if not docs:
        return docs
    top_n = min(top_n, len(docs))

    from flashrank import RerankRequest

    ranker = _fast_ranker(model_name)
    passages = [
        {"id": i, "text": (d.title or "") + ". " + (d.snippet or "")}
        for i, d in enumerate(docs)
    ]
    results = ranker.rerank(RerankRequest(query=query, passages=passages))
    # results are already sorted descending by score; `id` is the original index.
    return [
        RetrievedDoc(
            id=docs[r["id"]].id,
            title=docs[r["id"]].title,
            snippet=docs[r["id"]].snippet,
            url=docs[r["id"]].url,
            published_at=docs[r["id"]].published_at,
            source_id=docs[r["id"]].source_id,
            language=docs[r["id"]].language,
            score=round(float(r["score"]), 6),
            vec_rank=docs[r["id"]].vec_rank,
            lex_rank=docs[r["id"]].lex_rank,
        )
        for r in results[:top_n]
    ]


# ── Deep path: CrossEncoder (opt-in) ─────────────────────────────────────────

_MAX_LEN = 256


@lru_cache(maxsize=1)
def _deep_encoder(model_name: str):
    from sentence_transformers import CrossEncoder

    logger.info("Loading CrossEncoder %s (once)", model_name)
    try:
        import torch

        torch.set_num_threads(os.cpu_count() or 4)
    except Exception:  # noqa: BLE001 - threading hint is best-effort
        pass
    return CrossEncoder(model_name, max_length=_MAX_LEN)


def deep_rerank(
    model_name: str,
    query: str,
    docs: list[RetrievedDoc],
    top_n: int,
) -> list[RetrievedDoc]:
    """CrossEncoder reranking — highest quality, opt-in only (~0.8s/doc on CPU)."""
    if not docs:
        return docs
    top_n = min(top_n, len(docs))
    encoder = _deep_encoder(model_name)
    pairs = [(query, (d.title or "") + ". " + (d.snippet or "")) for d in docs]
    raw: list[float] = encoder.predict(pairs, show_progress_bar=False).tolist()
    ranked = sorted(zip(raw, docs), key=lambda t: t[0], reverse=True)
    return [
        RetrievedDoc(
            id=doc.id,
            title=doc.title,
            snippet=doc.snippet,
            url=doc.url,
            published_at=doc.published_at,
            source_id=doc.source_id,
            language=doc.language,
            score=round(score, 6),
            vec_rank=doc.vec_rank,
            lex_rank=doc.lex_rank,
        )
        for score, doc in ranked[:top_n]
    ]


# Backward-compat alias — retrieval.py imports this name.
def rerank(
    model_name: str,
    query: str,
    docs: list[RetrievedDoc],
    top_n: int,
) -> list[RetrievedDoc]:
    return deep_rerank(model_name, query, docs, top_n)
