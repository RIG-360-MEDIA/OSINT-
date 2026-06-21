"""Feature 2 — semantic find-similar over articles (cross-lingual).

Given an article id, return its nearest neighbours by cosine on
``labse_embedding_v4`` — using the SOURCE article's own embedding, so there is no
query text and no LLM in the path. Cross-lingual falls out for free (a Telugu
article surfaces its English / Hindi counterparts). Read-only SELECT.
"""
from __future__ import annotations

from typing import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.diversity import semantic_dedup
from app.schemas import RetrievedDoc

# Fetch the source vector as text first, then pass it as a LITERAL parameter below.
# (pgvector's HNSW index is only used when ORDER BY compares the column to a
# constant/param — comparing to another column forces a full scan → timeout.)
_SRC_VEC_SQL = (
    "SELECT labse_embedding_v4::text AS emb FROM articles "
    "WHERE id = :id AND labse_embedding_v4 IS NOT NULL"
)

_SIMILAR_SQL = """
SELECT a.id::text AS id, a.title, a.lead_text_translated AS snippet, a.url,
       a.published_at, a.source_id::text AS source_id, a.language_detected AS language,
       (a.labse_embedding_v4 <=> (:qvec)::vector) AS distance
FROM articles a
WHERE a.labse_embedding_v4 IS NOT NULL AND a.substrate_status = 'ok'
  AND NOT a.is_duplicate AND a.id <> :id{lang}
ORDER BY a.labse_embedding_v4 <=> (:qvec)::vector
LIMIT :k
"""


async def find_similar(
    conn: AsyncConnection,
    settings: Settings,
    article_id: str,
    k: int | None = None,
    languages: Sequence[str] | None = None,
    dedup: bool = True,
) -> list[RetrievedDoc] | None:
    """Nearest neighbours of ``article_id``. Returns None if the source article
    does not exist or has no v4 embedding (caller raises 404)."""
    k = k or settings.top_k
    src = (await conn.execute(text(_SRC_VEC_SQL), {"id": article_id})).first()
    if not src:
        return None
    qvec = src[0]  # pgvector ::text → "[x,y,...]" literal the param can re-cast

    lang = " AND a.language_detected = ANY(:langs)" if languages else ""
    # Over-fetch when de-duping so reprints don't eat the final slots.
    fetch_k = max(k * 3, 24) if dedup else k
    params: dict = {"id": article_id, "qvec": qvec, "k": fetch_k}
    if languages:
        params["langs"] = list(languages)

    rows = (await conn.execute(text(_SIMILAR_SQL.format(lang=lang)), params)).mappings().all()
    docs = [
        RetrievedDoc(
            id=r["id"],
            title=r["title"],
            snippet=(r["snippet"] or "")[:300] or None,
            url=r["url"],
            published_at=r["published_at"],
            source_id=r["source_id"],
            language=r["language"],
            score=round(1.0 - float(r["distance"]), 4),  # cosine similarity
            vec_rank=None,
            lex_rank=None,
        )
        for r in rows
    ]
    if dedup:
        docs = semantic_dedup(docs, settings.dedup_threshold)
    return docs[:k]
