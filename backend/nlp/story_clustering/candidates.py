"""kNN candidate retrieval.

Single source of truth for "given this article embedding, which existing
v2 threads are plausible matches?" The query is intentionally narrow:

  * Only `is_active = TRUE` threads.
  * Only `cluster_version = 2` (legacy v1 threads are read-only).
  * Only threads updated in the last WINDOW_DAYS (stale threads
    deactivated by the consolidation sweep).
  * Top-K by cosine distance against `seed_embedding` (single-table,
    indexed; no JOIN against articles needed because we duplicated the
    seed's embedding into story_threads).

We deliberately do NOT apply a distance threshold here. The pipeline
caller decides what to do with the top-K (fast-path vs LLM judge).
"""
from __future__ import annotations

import json
import logging
from typing import Sequence

from sqlalchemy import text

from backend.nlp.story_clustering.types import (
    CANDIDATE_TOP_K,
    WINDOW_DAYS,
    CandidateThread,
)

logger = logging.getLogger(__name__)


def _format_vec(embedding: Sequence[float]) -> str:
    """Serialize a float list to pgvector literal (avoid SQLAlchemy
    binding gotchas with the asyncpg driver)."""
    return "[" + ",".join(f"{x:.8f}" for x in embedding) + "]"


def _parse_text_array(value: object) -> tuple[str, ...]:
    """Postgres text[] arrives as either a Python list or a literal
    string depending on the driver. Normalize to a frozen tuple."""
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(x) for x in value if x)
    if isinstance(value, str):
        s = value.strip("{}")
        if not s:
            return ()
        try:
            return tuple(json.loads("[" + s.replace("'", '"') + "]"))
        except json.JSONDecodeError:
            return tuple(x.strip().strip('"') for x in s.split(",") if x.strip())
    return ()


async def find_top_k(
    embedding: Sequence[float],
    db: object,
    *,
    k: int = CANDIDATE_TOP_K,
    window_days: int = WINDOW_DAYS,
) -> list[CandidateThread]:
    """Return up to k closest active v2 threads, ordered by cosine
    distance ascending (closest first).

    Threads that have no seed_embedding (mid-migration backfill rows)
    are skipped — they would short-circuit to NULL distance.
    """
    emb_str = _format_vec(embedding)
    result = await db.execute(
        text(
            """
            SELECT
              st.id::text                    AS thread_id,
              st.title                       AS title,
              st.primary_entities            AS primary_entities,
              st.article_count               AS article_count,
              st.source_count                AS source_count,
              st.seed_article_id::text       AS seed_article_id,
              a.title                        AS seed_title,
              a.summary_executive            AS seed_summary,
              (st.seed_embedding <=> CAST(:emb AS vector))
                                             AS distance
            FROM story_threads st
            LEFT JOIN articles a ON a.id = st.seed_article_id
            WHERE st.is_active        = TRUE
              AND st.cluster_version  = 2
              AND st.seed_embedding   IS NOT NULL
              AND st.last_updated_at  > NOW() - make_interval(days => :window_days)
            ORDER BY st.seed_embedding <=> CAST(:emb AS vector)
            LIMIT :k
            """
        ),
        {"emb": emb_str, "window_days": window_days, "k": k},
    )

    rows = result.fetchall()
    return [
        CandidateThread(
            thread_id=row.thread_id,
            title=row.title,
            primary_entities=_parse_text_array(row.primary_entities),
            article_count=row.article_count or 0,
            source_count=row.source_count or 0,
            seed_article_id=row.seed_article_id,
            seed_title=row.seed_title,
            seed_summary=row.seed_summary,
            distance=float(row.distance) if row.distance is not None else 1.0,
        )
        for row in rows
    ]
