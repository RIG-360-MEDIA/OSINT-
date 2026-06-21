"""Fuse corpus docs and web results into one ranked, citable list (RRF).

Web results become RetrievedDoc rows (id ``web:N``, source_id ``web``) so the
existing answer + cite-ID guardrail treats every source uniformly. Provenance is
carried on ``source_id`` (== "web") so the UI can badge web vs corpus.
"""
from __future__ import annotations

from app.retrieval import reciprocal_rank_fusion
from app.schemas import RetrievedDoc
from app.schemas_account import WebResult


def web_to_doc(w: WebResult, index: int, snippet_cap: int = 300) -> RetrievedDoc:
    return RetrievedDoc(
        id=f"web:{index}",
        title=w.title,
        snippet=(w.snippet or "")[:snippet_cap] or None,
        url=w.url,
        published_at=None,
        source_id="web",
        language="en",
        score=0.0,
        vec_rank=None,
        lex_rank=None,
    )


def fuse_web_corpus(
    corpus_docs: list[RetrievedDoc],
    web_results: list[WebResult],
    rrf_k: int = 60,
    snippet_cap: int = 300,
) -> list[RetrievedDoc]:
    web_docs = [web_to_doc(w, i, snippet_cap) for i, w in enumerate(web_results)]
    scores = reciprocal_rank_fusion(
        [[d.id for d in corpus_docs], [d.id for d in web_docs]], rrf_k
    )
    by_id = {d.id: d for d in (*corpus_docs, *web_docs)}
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    fused: list[RetrievedDoc] = []
    for doc_id, score in ordered:
        base = by_id[doc_id]
        fused.append(RetrievedDoc(**{**base.model_dump(), "score": round(score, 6)}))
    return fused
