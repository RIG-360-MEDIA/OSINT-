"""backend.draftsmith.stages.gather.facts — Stage 2 adapter: analytics.story_facts_v8.

    items = await gather_facts(plan)

Two hops, both read-only:
  1. Match the plan's entities/aliases + planner cluster hint against
     `analytics.story_clusters_v8` — the CURRENT `_v8` keeper clustering
     family (never the archived un-suffixed `story_clusters`/`event_clusters`
     — see 00-global/decisions). `story_clusters_v8` carries no FTS/vector
     column of its own, so matching is substring (ILIKE) against the
     representative title and the `primary_entities` jsonb cast to text.
  2. Pull the reconciled fact rows for the matched clusters from
     `analytics.story_facts_v8`, then join each fact's `citing_article_ids`
     back to `public.articles`/`sources` for a citable title + outlet.

Always trust_tier == 1 (config.BASE_TRUST_TIER['story_fact']) — these are
reconciled, multi-member-corroborated facts, the highest-trust evidence
family gather produces.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import text

from backend.database import get_db
from backend.draftsmith import config
from backend.draftsmith.models import EvidenceItem, QueryPlan
from backend.draftsmith.stages.gather._shared import make_source_id, resolve_time_window

logger = logging.getLogger(__name__)

_SOURCE_TYPE = "story_fact"
_SOURCE_ID_PREFIX = config.SOURCE_ID_PREFIX[_SOURCE_TYPE]
_TRUST_TIER = config.BASE_TRUST_TIER[_SOURCE_TYPE]

_MIN_TERM_LEN = 3
_CLUSTER_CAP = 8  # candidate clusters considered before pulling facts

_CLUSTER_MATCH_SQL = """
    SELECT story_id, representative_title
    FROM analytics.story_clusters_v8
    WHERE status = 'active'
      AND last_seen_at >= :since
      AND (CAST(:until AS timestamptz) IS NULL OR last_seen_at <= CAST(:until AS timestamptz))
      AND (
        representative_title ILIKE ANY(:patterns)
        OR primary_entities::text ILIKE ANY(:patterns)
      )
    ORDER BY importance_score DESC NULLS LAST
    LIMIT :cluster_cap
"""

_FACTS_SQL = """
    SELECT id, story_id, fact_key, unit, value_min, value_max, value_latest,
           member_count, citing_article_ids, single_source, sample_claim
    FROM analytics.story_facts_v8
    WHERE story_id = ANY(:story_ids)
    ORDER BY member_count DESC NULLS LAST
    LIMIT :cap
"""

_CITED_ARTICLES_SQL = """
    SELECT a.id, a.title, a.published_at, s.name AS outlet
    FROM public.articles a
    LEFT JOIN public.sources s ON s.id = a.source_id
    WHERE a.id = ANY(:ids)
"""


async def gather_facts(plan: QueryPlan) -> list[EvidenceItem]:
    """Stage 2 — reconciled numeric facts for clusters matching the plan.
    `relevance` is left at 0.0 (the rank stage's job); `member_count` /
    `single_source` / value spread are preserved in `extra` as the
    corroboration signal rank should weigh."""
    if plan is None:
        raise ValueError("gather_facts: plan is required")

    patterns = _match_patterns(plan)
    if not patterns:
        return []

    since, until = resolve_time_window(plan.time_window)
    cap = config.FETCH_CAPS["story_fact"]

    async with get_db() as session:
        try:
            cluster_rows = (
                await session.execute(
                    text(_CLUSTER_MATCH_SQL),
                    {"since": since, "until": until, "patterns": patterns, "cluster_cap": _CLUSTER_CAP},
                )
            ).mappings().all()
        except Exception:
            logger.exception("gather_facts: cluster match query failed")
            return []
        if not cluster_rows:
            return []

        story_ids = [r["story_id"] for r in cluster_rows]
        cluster_titles = {r["story_id"]: r["representative_title"] for r in cluster_rows}

        try:
            fact_rows = (
                await session.execute(text(_FACTS_SQL), {"story_ids": story_ids, "cap": cap})
            ).mappings().all()
        except Exception:
            logger.exception("gather_facts: story_facts_v8 query failed")
            return []
        if not fact_rows:
            return []

        cited_ids = {
            str(aid) for row in fact_rows for aid in (row.get("citing_article_ids") or [])
        }
        article_lookup: dict[str, Any] = {}
        if cited_ids:
            try:
                cited_rows = (
                    await session.execute(text(_CITED_ARTICLES_SQL), {"ids": list(cited_ids)})
                ).mappings().all()
                article_lookup = {str(r["id"]): r for r in cited_rows}
            except Exception:
                logger.exception("gather_facts: cited-article join failed")
                article_lookup = {}

    items: list[EvidenceItem] = []
    for row in fact_rows:
        items.append(_row_to_item(row, cluster_titles.get(row["story_id"]), article_lookup))
    return items


def _match_patterns(plan: QueryPlan) -> list[str]:
    """Free-text ILIKE patterns from entity names/aliases + the planner's
    cluster hint. Deliberately substring-based (no FTS column on
    story_clusters_v8) — a false-positive candidate cluster just yields
    zero matched facts downstream, never a wrong citation."""
    terms: set[str] = set()
    for entity in plan.entities:
        for candidate in (entity.name, *entity.aliases):
            candidate = (candidate or "").strip()
            if len(candidate) >= _MIN_TERM_LEN:
                terms.add(candidate)
    hint = (plan.queries.facts_cluster_hint or "").strip()
    if hint:
        for token in hint.split():
            token = token.strip(".,;:!?\"'")
            if len(token) >= _MIN_TERM_LEN:
                terms.add(token)
    return [f"%{t}%" for t in terms]


def _fact_text(row: Any, cluster_title: Optional[str]) -> str:
    parts: list[str] = [str(row.get("fact_key") or "fact")]
    value_bits: list[str] = []
    if row.get("value_latest") is not None:
        value_bits.append(f"latest {row['value_latest']}")
    value_min, value_max = row.get("value_min"), row.get("value_max")
    if value_min is not None and value_max is not None and value_min != value_max:
        value_bits.append(f"range {value_min}-{value_max}")
    if row.get("unit"):
        value_bits.append(str(row["unit"]))
    if value_bits:
        parts.append("(" + ", ".join(value_bits) + ")")
    if row.get("sample_claim"):
        parts.append("-- " + str(row["sample_claim"]).strip())
    if cluster_title:
        parts.append(f"[{cluster_title}]")
    return " ".join(parts)


def _row_to_item(
    row: Any, cluster_title: Optional[str], article_lookup: dict[str, Any],
) -> EvidenceItem:
    cites: list[dict[str, Any]] = []
    latest_published = None
    for aid in row.get("citing_article_ids") or []:
        article = article_lookup.get(str(aid))
        if article is None:
            continue
        cites.append({"article_id": str(aid), "title": article.get("title"), "outlet": article.get("outlet")})
        published = article.get("published_at")
        if published is not None and (latest_published is None or published > latest_published):
            latest_published = published

    return EvidenceItem(
        source_id=make_source_id(_SOURCE_ID_PREFIX, str(row["id"])),
        source_type=_SOURCE_TYPE,  # type: ignore[arg-type]
        trust_tier=_TRUST_TIER,  # type: ignore[arg-type]
        text=_fact_text(row, cluster_title),
        title=cluster_title,
        url=None,
        outlet=None,
        author=None,
        published_at=latest_published,
        relevance=0.0,
        extra={
            "story_id": str(row["story_id"]),
            "fact_key": row.get("fact_key"),
            "unit": row.get("unit"),
            "value_min": _as_float(row.get("value_min")),
            "value_max": _as_float(row.get("value_max")),
            "value_latest": _as_float(row.get("value_latest")),
            "member_count": row.get("member_count") or 0,
            "single_source": bool(row.get("single_source")),
            "cites": cites,
        },
    )


def _as_float(value: Any) -> Optional[float]:
    """`analytics.story_facts_v8`'s value_* columns are `numeric` -> Decimal
    over the wire; Decimal isn't JSON-serialisable and `extra` is persisted
    via plain `json.dumps` (see db._evidence.save_evidence), so every
    numeric must be coerced before it ever reaches that call."""
    return None if value is None else float(value)
