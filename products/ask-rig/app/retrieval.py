"""Hybrid retrieval over ``articles``: semantic (v4 vectors) + lexical (fts),
fused with Reciprocal Rank Fusion.

Article-only for V1 — clip/cutting embeddings are not in the v4 space, so
cross-pillar cosine is unreliable (see SPEC / db-field-audit). Every statement
here is a READ-ONLY SELECT.
"""
from __future__ import annotations

import asyncio
from typing import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.diversity import assemble, facet_quota, mmr_select, semantic_dedup
from app.embedding import to_pgvector
from app.schemas import RetrievedDoc

# Clean working set: enriched + de-duplicated, and embedded with the v4 recipe.
_BASE_FILTER = "labse_embedding_v4 IS NOT NULL AND substrate_status = 'ok' AND NOT is_duplicate"

_VECTOR_SQL = """
SELECT id::text AS id, title, lead_text_translated AS snippet, url,
       published_at, source_id::text AS source_id, language_detected AS language
FROM articles
WHERE {flt}{lang}
ORDER BY labse_embedding_v4 <=> (:qvec)::vector
LIMIT :k
"""

_LEXICAL_SQL = """
SELECT id::text AS id, title, lead_text_translated AS snippet, url,
       published_at, source_id::text AS source_id, language_detected AS language
FROM articles
WHERE fts @@ websearch_to_tsquery(:cfg, :q)
  AND substrate_status = 'ok' AND NOT is_duplicate{lang}
ORDER BY ts_rank_cd(fts, websearch_to_tsquery(:cfg, :q)) DESC
LIMIT :k
"""


def reciprocal_rank_fusion(ranked_lists: Sequence[Sequence[str]], k: int = 60) -> dict[str, float]:
    """RRF: ``score(d) = sum_i 1 / (k + rank_i(d))`` with 1-based ranks.

    Pure function — unit tested. Rewards docs that rank high in *either* list and
    boosts docs that appear in *both* (consensus).
    """
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for index, doc_id in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + index)
    return scores


def _lang_clause(languages: Sequence[str] | None) -> str:
    return " AND language_detected = ANY(:langs)" if languages else ""


async def _rows(conn: AsyncConnection, sql: str, params: dict) -> list[dict]:
    result = await conn.execute(text(sql), params)
    return [dict(row) for row in result.mappings().all()]


async def hybrid_search(
    conn: AsyncConnection,
    settings: Settings,
    query: str,
    qvec: list[float],
    languages: Sequence[str] | None = None,
    top_k: int | None = None,
) -> list[RetrievedDoc]:
    top_k = top_k or settings.top_k
    lang = _lang_clause(languages)

    vparams: dict = {"qvec": to_pgvector(qvec), "k": settings.k_vec}
    lparams: dict = {"cfg": settings.fts_config, "q": query, "k": settings.k_lex}
    if languages:
        vparams["langs"] = list(languages)
        lparams["langs"] = list(languages)

    vrows = await _rows(conn, _VECTOR_SQL.format(flt=_BASE_FILTER, lang=lang), vparams)
    lrows = await _rows(conn, _LEXICAL_SQL.format(lang=lang), lparams)

    by_id: dict[str, dict] = {}
    vec_rank: dict[str, int] = {}
    lex_rank: dict[str, int] = {}
    for i, row in enumerate(vrows, start=1):
        by_id[row["id"]] = row
        vec_rank[row["id"]] = i
    for i, row in enumerate(lrows, start=1):
        by_id.setdefault(row["id"], row)
        lex_rank[row["id"]] = i

    fused = reciprocal_rank_fusion(
        [[r["id"] for r in vrows], [r["id"] for r in lrows]], settings.rrf_k
    )
    ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:top_k]

    docs: list[RetrievedDoc] = []
    for doc_id, score in ordered:
        row = by_id[doc_id]
        snippet = (row.get("snippet") or "")[:300] or None
        docs.append(
            RetrievedDoc(
                id=doc_id,
                title=row.get("title"),
                snippet=snippet,
                url=row.get("url"),
                published_at=row.get("published_at"),
                source_id=row.get("source_id"),
                language=row.get("language"),
                score=round(score, 6),
                vec_rank=vec_rank.get(doc_id),
                lex_rank=lex_rank.get(doc_id),
            )
        )
    return docs


async def retrieve_and_curate(
    conn: AsyncConnection,
    settings: Settings,
    query: str,
    qvec: list[float],
    languages: Sequence[str] | None = None,
    top_k: int | None = None,
    rerank_enabled: bool | None = None,
) -> list[RetrievedDoc]:
    """Full pipeline: hybrid → fast-rerank → (deep-rerank) → dedup → quota → MMR → assemble.

    fast_rerank (FlashRank, ~12 MB, sub-100ms) always fires.
    deep_rerank (CrossEncoder, ~568 MB) only fires when rerank_enabled=True.

    top_k overrides settings.top_k; rerank_enabled overrides settings.rerank_enabled per-request.
    """
    final_k = top_k or settings.top_k
    use_deep = settings.rerank_enabled if rerank_enabled is None else rerank_enabled
    # Fetch wider when deep reranking — fast rerank is cheap so we always fetch wide.
    fetch_k = settings.rerank_fetch_k
    candidates = await hybrid_search(conn, settings, query, qvec, languages, top_k=fetch_k)

    # Drop untitled junk — an article with no title can't be cited or read.
    candidates = [d for d in candidates if (d.title or "").strip()]

    if candidates:
        from app.rerank import deep_rerank, fast_rerank  # lazy: avoids loading models at startup

        # Fast rerank runs on every request (blocking CPU → off the event loop).
        candidates = await asyncio.to_thread(
            fast_rerank, query, candidates, settings.rerank_fetch_k
        )
        if use_deep:
            # Deep rerank on the already-fast-ranked shortlist.
            candidates = await asyncio.to_thread(
                deep_rerank, settings.rerank_model, query, candidates, settings.rerank_top_n
            )

    candidates = semantic_dedup(candidates, settings.dedup_threshold)
    candidates = facet_quota(candidates, settings.max_per_source)
    candidates = mmr_select(candidates, final_k, settings.diversity_lambda)
    return assemble(candidates)


async def multi_retrieve_and_curate(
    conn: AsyncConnection,
    settings: Settings,
    queries: Sequence[str],
    qvecs: Sequence[list[float]],
    languages: Sequence[str] | None = None,
    top_k: int | None = None,
    rerank_enabled: bool | None = None,
) -> list[RetrievedDoc]:
    """RAG-Fusion: retrieve for EACH query variant, RRF-fuse the candidate lists,
    then fast-rerank → (deep-rerank) → dedup → quota → MMR → assemble.
    Broadens recall for vague/regional queries."""
    final_k = top_k or settings.top_k
    use_deep = settings.rerank_enabled if rerank_enabled is None else rerank_enabled
    fetch_k = settings.rerank_fetch_k

    ranked_lists: list[list[str]] = []
    by_id: dict[str, RetrievedDoc] = {}
    for q, qv in zip(queries, qvecs):
        docs = await hybrid_search(conn, settings, q, qv, languages, top_k=fetch_k)
        ranked_lists.append([d.id for d in docs])
        for d in docs:
            by_id.setdefault(d.id, d)

    fused = reciprocal_rank_fusion(ranked_lists, settings.rrf_k)
    ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
    candidates = [by_id[doc_id] for doc_id, _ in ordered][:fetch_k]
    candidates = [d for d in candidates if (d.title or "").strip()]

    if candidates:
        from app.rerank import deep_rerank, fast_rerank  # lazy import

        candidates = await asyncio.to_thread(
            fast_rerank, queries[0], candidates, fetch_k
        )
        if use_deep:
            candidates = await asyncio.to_thread(
                deep_rerank, settings.rerank_model, queries[0], candidates, settings.rerank_top_n
            )

    candidates = semantic_dedup(candidates, settings.dedup_threshold)
    candidates = facet_quota(candidates, settings.max_per_source)
    candidates = mmr_select(candidates, final_k, settings.diversity_lambda)
    return assemble(candidates)
