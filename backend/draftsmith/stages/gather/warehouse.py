"""backend.draftsmith.stages.gather.warehouse — Stage 2 adapter: public.articles.

    items = await gather_warehouse(plan)

Read-only hybrid retrieval over the shared rig-postgres warehouse:
  1. `websearch_to_tsquery('english', ...)` over `articles.fts` for each of
     plan.queries.warehouse_fts (<=3, contract-capped).
  2. One LaBSE cosine-ANN search (`labse_embedding <=> ...`) seeded by
     plan.queries.warehouse_vector_seed, embedded via backend.draftsmith.embed
     (reuses the shared LaBSE singleton; never loads a second model).

Both engines are scoped to the plan's time window and exclude
`is_duplicate` rows. A row hit by both engines is merged into one
EvidenceItem (extra.engine becomes "fts+vector") rather than emitted twice.
Every query is a short, indexed SELECT — never a write, never a lock on
`articles`.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import text

from backend.database import get_db
from backend.draftsmith import config
from backend.draftsmith.embed import EmbeddingError, embed_text
from backend.draftsmith.models import EvidenceItem, QueryPlan
from backend.draftsmith.stages.gather._shared import (
    clip_text,
    make_source_id,
    resolve_time_window,
)

logger = logging.getLogger(__name__)

_SOURCE_TYPE = "corpus_article"
_SOURCE_ID_PREFIX = config.SOURCE_ID_PREFIX[_SOURCE_TYPE]
_TRUST_TIER = config.BASE_TRUST_TIER[_SOURCE_TYPE]

_SELECT_COLUMNS = """
    a.id, a.title, a.full_text_translated, a.lead_text_translated, a.url,
    a.published_at, a.topic_category, a.geo_primary, s.name AS outlet
"""

_FTS_SQL = f"""
    SELECT {_SELECT_COLUMNS},
           ts_rank(a.fts, websearch_to_tsquery('english', :q)) AS ts_score
    FROM public.articles a
    LEFT JOIN public.sources s ON s.id = a.source_id
    WHERE a.fts @@ websearch_to_tsquery('english', :q)
      AND NOT a.is_duplicate
      AND a.published_at >= :since
      AND (CAST(:until AS timestamptz) IS NULL OR a.published_at <= CAST(:until AS timestamptz))
    ORDER BY ts_score DESC
    LIMIT :cap
"""

_VECTOR_SQL = f"""
    SELECT {_SELECT_COLUMNS},
           (a.labse_embedding <=> CAST(:vec AS vector)) AS cosine_distance
    FROM public.articles a
    LEFT JOIN public.sources s ON s.id = a.source_id
    WHERE a.labse_embedding IS NOT NULL
      AND NOT a.is_duplicate
      AND a.published_at >= :since
      AND (CAST(:until AS timestamptz) IS NULL OR a.published_at <= CAST(:until AS timestamptz))
    ORDER BY a.labse_embedding <=> CAST(:vec AS vector)
    LIMIT :cap
"""


async def gather_warehouse(
    plan: QueryPlan, seed_vec: Optional[list[float]] = None,
) -> list[EvidenceItem]:
    """Stage 2 — FTS + LaBSE-vector retrieval over public.articles, merged
    by article id and normalised to EvidenceItem. `relevance` is left at 0.0
    (the rank stage's job, per config.RELEVANCE_WEIGHTS); the raw per-engine
    signal (ts_score / cosine_distance) is preserved in `extra` so rank can
    use it without re-querying.

    `seed_vec` is the shared warehouse-seed embedding, computed exactly once
    per job by gather_all (the remote LaBSE server is ~30-40s/call, so it is
    never re-embedded per adapter). Only when it is None AND a seed exists do
    we embed the seed here as a standalone fallback (e.g. this adapter called
    outside gather_all)."""
    if plan is None:
        raise ValueError("gather_warehouse: plan is required")

    fts_queries = [q.strip() for q in plan.queries.warehouse_fts if q and q.strip()][:3]
    seed = (plan.queries.warehouse_vector_seed or "").strip()
    if not fts_queries and not seed:
        return []

    since, until = resolve_time_window(plan.time_window)
    fts_cap = config.FETCH_CAPS["warehouse_fts"]
    vector_cap = config.FETCH_CAPS["warehouse_vector"]

    # article id -> accumulated EvidenceItem-in-progress (merged across engines)
    merged: dict[str, dict[str, Any]] = {}

    async with get_db() as session:
        for q in fts_queries:
            try:
                result = await session.execute(
                    text(_FTS_SQL), {"q": q, "since": since, "until": until, "cap": fts_cap},
                )
                rows = result.mappings().all()
            except Exception:
                logger.exception("gather_warehouse: FTS query failed (q=%r)", q)
                continue
            for row in rows:
                _merge_row(merged, row, engine="fts", score_key="ts_score", score_value=float(row["ts_score"] or 0.0))

        if seed:
            vector: Optional[list[float]] = seed_vec
            if vector is None:
                try:
                    vector = await embed_text(seed)
                except EmbeddingError as exc:
                    logger.warning("gather_warehouse: vector seed embedding failed: %s", exc)
            if vector is not None:
                try:
                    result = await session.execute(
                        text(_VECTOR_SQL),
                        {"vec": str(vector), "since": since, "until": until, "cap": vector_cap},
                    )
                    rows = result.mappings().all()
                except Exception:
                    logger.exception("gather_warehouse: vector query failed")
                    rows = []
                for row in rows:
                    _merge_row(
                        merged, row, engine="vector",
                        score_key="cosine_distance", score_value=float(row["cosine_distance"]),
                    )

    items: list[EvidenceItem] = []
    for article_id, acc in merged.items():
        row = acc["row"]
        text_value = (
            row.get("full_text_translated") or row.get("lead_text_translated") or row.get("title") or ""
        )
        items.append(
            EvidenceItem(
                source_id=make_source_id(_SOURCE_ID_PREFIX, article_id),
                source_type=_SOURCE_TYPE,  # type: ignore[arg-type]
                trust_tier=_TRUST_TIER,  # type: ignore[arg-type]
                text=clip_text(text_value),
                title=row.get("title"),
                url=row.get("url"),
                outlet=row.get("outlet"),
                author=None,
                published_at=row.get("published_at"),
                relevance=0.0,
                extra={
                    "engine": "+".join(sorted(acc["engines"])),
                    "topic_category": row.get("topic_category"),
                    "geo_primary": row.get("geo_primary"),
                    **acc["scores"],
                },
            )
        )
    return items


def _merge_row(
    merged: dict[str, dict[str, Any]], row: Any, *, engine: str, score_key: str, score_value: float,
) -> None:
    article_id = str(row["id"])
    acc = merged.get(article_id)
    if acc is None:
        merged[article_id] = {
            "row": row,
            "engines": {engine},
            "scores": {score_key: score_value},
        }
        return
    acc["engines"].add(engine)
    acc["scores"][score_key] = score_value
    # prefer whichever row copy carries the richer body text (both engines
    # select the same columns, so this only matters if one query race
    # returned a slightly staler snapshot than the other).
    if not acc["row"].get("full_text_translated") and row.get("full_text_translated"):
        acc["row"] = row
