"""Unified, validated filter params for every /v1 coverage endpoint.

One filter language across /articles, /stories, /entities/{id}/coverage and
/geo so a client learns it once. FastAPI validates types/enums/ranges at the
boundary; anything outside the allowed set is rejected (422) or, for entity
ids, silently dropped if malformed (so a name typed in place of an id just
yields no match rather than an error).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Query

from .settings import DEFAULT_PAGE_SIZE, DEFAULT_WINDOW_DAYS, MAX_PAGE_SIZE, MAX_WINDOW_DAYS


def _coerce_uuids(values: list[str] | None) -> tuple[str, ...]:
    """Keep only well-formed UUIDs; drop the rest (forgiving, SQL-safe)."""
    out: list[str] = []
    for v in values or []:
        v = (v or "").strip()
        if not v:
            continue
        try:
            out.append(str(uuid.UUID(v)))
        except (ValueError, AttributeError, TypeError):
            continue
    # de-dup, preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for v in out:
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    return tuple(uniq)


@dataclass(frozen=True)
class CoverageFilters:
    entity: tuple[str, ...]      # entity ids (UUIDs) only
    topic: tuple[str, ...]
    match: str                   # 'any' (OR) | 'all' (AND)
    sentiment: str | None        # supportive | neutral | critical
    window_hours: int
    language: str | None
    source: tuple[str, ...]      # outlet display name(s) — drill-down from /analytics/outlets
    limit: int
    cursor: str | None


def coverage_filters(
    entity: list[str] | None = Query(None, description="Entity id(s) to filter by (repeatable)"),
    topic: list[str] | None = Query(None, description="Topic(s) to filter by (repeatable)"),
    match: str = Query("any", pattern="^(any|all)$", description="Combine filters with OR (any) or AND (all)"),
    sentiment: str | None = Query(None, pattern="^(supportive|neutral|critical)$"),
    window: int = Query(DEFAULT_WINDOW_DAYS, ge=1, le=MAX_WINDOW_DAYS, description="Days to look back"),
    language: str | None = Query(None, max_length=8, pattern="^[A-Za-z-]{2,8}$"),
    source: list[str] | None = Query(None, description="Outlet name(s) to filter by (repeatable) — drill-down from /analytics/outlets"),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1,
                       description=f"Items per page (values above {MAX_PAGE_SIZE} are clamped to {MAX_PAGE_SIZE})"),
    cursor: str | None = Query(None, max_length=512),
) -> CoverageFilters:
    topics = tuple(t.strip()[:80] for t in (topic or []) if t and t.strip())[:25]
    sources = tuple(s.strip()[:120] for s in (source or []) if s and s.strip())[:25]
    return CoverageFilters(
        entity=_coerce_uuids(entity),
        topic=topics,
        match=match,
        sentiment=sentiment,
        window_hours=window * 24,
        language=language,
        source=sources,
        limit=min(limit, MAX_PAGE_SIZE),  # clamp, don't 422 on a large ask
        cursor=cursor,
    )
