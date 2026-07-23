"""backend.draftsmith.stages.gather.youtube — Stage 2 adapter:
analytics.youtube_clips_v2 (the /clips pillar's warehouse, vector search).

    items = await gather_youtube_warehouse(plan)

LaBSE cosine-ANN search over `youtube_clips_v2.labse_embedding`, seeded by
the same plan.queries.warehouse_vector_seed used for the article warehouse
(one 768-dim LaBSE space, one query embedding — never re-embed per source).
Prefers `is_watchlisted` clips (monitored entities, tier 1) but keeps
well-matched off-watchlist clips too (migration 111 keep-all mode, tier 2).

Note: this is distinct from the on-demand `search_youtube` innertube keyword
search in gather_social (cheap_stack) — that one also emits
source_type='youtube_clip' evidence for the same job. Their source_ids never
collide: this adapter hashes the warehouse clip's own `clip_uuid`, prefixed
`warehouse:`; the cheap_stack one hashes a live video id.
"""
from __future__ import annotations

import logging
from typing import Optional

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

_SOURCE_TYPE = "youtube_clip"
_SOURCE_ID_PREFIX = config.SOURCE_ID_PREFIX[_SOURCE_TYPE]
_TIER_WATCHLISTED = 1
_TIER_DEFAULT = config.BASE_TRUST_TIER[_SOURCE_TYPE]  # 2, refined to 1 when watchlisted

_VECTOR_SQL = """
    SELECT clip_uuid, video_id, video_title, channel_name, video_url, embed_url,
           clip_start_seconds, clip_end_seconds, transcript_segment,
           video_published_at, is_watchlisted,
           (labse_embedding <=> CAST(:vec AS vector)) AS cosine_distance
    FROM analytics.youtube_clips_v2
    WHERE labse_embedding IS NOT NULL
      AND (video_published_at IS NULL OR video_published_at >= :since)
      AND (CAST(:until AS timestamptz) IS NULL OR video_published_at IS NULL OR video_published_at <= CAST(:until AS timestamptz))
    ORDER BY is_watchlisted DESC, labse_embedding <=> CAST(:vec AS vector)
    LIMIT :cap
"""


async def gather_youtube_warehouse(
    plan: QueryPlan, seed_vec: Optional[list[float]] = None,
) -> list[EvidenceItem]:
    """Stage 2 — vector search over the YouTube clips warehouse. `relevance`
    is left at 0.0 (the rank stage's job); `cosine_distance` is preserved in
    `extra` for it to use.

    `seed_vec` is the shared warehouse-seed embedding, computed exactly once
    per job by gather_all (the remote LaBSE server is ~30-40s/call, so it is
    never re-embedded per adapter). Only when it is None AND a seed exists do
    we embed the seed here as a standalone fallback."""
    if plan is None:
        raise ValueError("gather_youtube_warehouse: plan is required")

    seed = (plan.queries.warehouse_vector_seed or "").strip()
    if not seed:
        return []

    vector: Optional[list[float]] = seed_vec
    if vector is None:
        try:
            vector = await embed_text(seed)
        except EmbeddingError as exc:
            logger.warning("gather_youtube_warehouse: vector seed embedding failed: %s", exc)
            return []

    since, until = resolve_time_window(plan.time_window)
    cap = config.FETCH_CAPS["youtube_clip"]

    async with get_db() as session:
        try:
            result = await session.execute(
                text(_VECTOR_SQL), {"vec": str(vector), "since": since, "until": until, "cap": cap},
            )
            rows = result.mappings().all()
        except Exception:
            logger.exception("gather_youtube_warehouse: vector query failed")
            return []

    items: list[EvidenceItem] = []
    for row in rows:
        watchlisted = bool(row.get("is_watchlisted"))
        distance = float(row["cosine_distance"])
        items.append(
            EvidenceItem(
                source_id=make_source_id(_SOURCE_ID_PREFIX, f"warehouse:{row['clip_uuid']}"),
                source_type=_SOURCE_TYPE,  # type: ignore[arg-type]
                trust_tier=_TIER_WATCHLISTED if watchlisted else _TIER_DEFAULT,  # type: ignore[arg-type]
                text=clip_text(row["transcript_segment"] or ""),
                title=row.get("video_title"),
                url=row.get("video_url"),
                outlet=row.get("channel_name"),
                author=None,
                published_at=row.get("video_published_at"),
                relevance=0.0,
                extra={
                    "embed_url": row.get("embed_url"),
                    "clip_start_seconds": row.get("clip_start_seconds"),
                    "clip_end_seconds": row.get("clip_end_seconds"),
                    "video_id": row.get("video_id"),
                    "is_watchlisted": watchlisted,
                    "cosine_distance": distance,
                },
            )
        )
    return items
