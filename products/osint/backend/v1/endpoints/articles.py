"""Article (coverage) endpoints — the filterable feed + single-item lookup."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from db import get_db

from .. import queries
from ..errors import not_found, ok
from ..filters import CoverageFilters, coverage_filters
from ..scope import ApiContext, effective_entity_ids, get_context
from ..serializers import serialize_article
from ..util import as_uuid

router = APIRouter(prefix="/v1", tags=["coverage"])


@router.get("/articles", summary="Filterable coverage feed")
async def list_articles(
    request: Request,
    ctx: ApiContext = Depends(get_context),
    filters: CoverageFilters = Depends(coverage_filters),
) -> dict:
    # Intersect the client's requested entities with what they're allowed to see.
    eids = effective_entity_ids(ctx.scope, filters.entity)
    # Scope keywords are intentionally INERT on the feed (kws = ()). Measured
    # 2026-07-17: a real client keyword list (~50 terms) is dominated by generic
    # words (education, floods, investments) that match ~135k articles / 90d — as a
    # raw "entity OR keyword" widener that is an 8-minute query AND a feed flooded
    # with off-topic national news. The correct routing is by term type: distinctive
    # proper nouns (Kaleshwaram, Rythu Bharosa) become ENTITIES (they extract + tag +
    # carry history); generic terms are served by the `topics` scope filter below.
    # The keyword-UNION path in queries.py stays committed but dormant behind this.
    kws: tuple[str, ...] = ()
    # Non-all_entities org with nothing to match on => empty (never the corpus).
    if not ctx.scope.all_entities and not eids and not kws:
        request.state.result_count = 0
        return ok([], meta={"count": 0, "next_cursor": None})

    async with get_db() as db:
        rows, next_cursor = await queries.list_scoped_articles(
            db,
            entity_ids=eids,
            all_entities=ctx.scope.all_entities,
            window_hours=filters.window_hours,
            language=filters.language,
            sentiment=filters.sentiment,
            cursor=filters.cursor,
            limit=filters.limit,
            source=filters.source,
            mute_terms=ctx.scope.mute_terms,
            keywords=kws,
            regions=ctx.scope.regions,
            topics=ctx.scope.topics,
        )
    request.state.result_count = len(rows)
    return ok(
        [serialize_article(r) for r in rows],
        meta={"count": len(rows), "next_cursor": next_cursor},
    )


@router.get("/articles/{article_id}", summary="A single coverage item")
async def get_article(article_id: str, request: Request, ctx: ApiContext = Depends(get_context)) -> dict:
    aid = as_uuid(article_id)
    if aid is None:
        raise not_found()
    async with get_db() as db:
        row = await queries.get_scoped_article(
            db, aid, list(ctx.scope.entity_ids), ctx.scope.all_entities
        )
        if row is None:
            raise not_found()  # missing OR out-of-scope — identical
        entities = await queries.article_entities(
            db, aid, list(ctx.scope.entity_ids), ctx.scope.all_entities
        )
    request.state.result_count = 1
    return ok(serialize_article(row, entities=entities))
