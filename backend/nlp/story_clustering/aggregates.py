"""Recompute the derived fields on a thread.

These are the four fields the old engine left stale and ruined the
brief features:

  * source_count    — distinct sources covering the story
  * article_count   — # of articles in the cluster
  * primary_entities — top entities by frequency across cluster
                      articles (NOT just the seed's entities)
  * momentum        — escalating / stable / fading based on the 24h
                      arrival velocity

Called from assignment.py on every assign-or-spawn. No more "set once
and never touched."
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Iterable

from sqlalchemy import text

logger = logging.getLogger(__name__)

ESCALATING_RATIO = 1.4
FADING_RATIO = 0.6
TOP_N_ENTITIES = 5


def _extract_entity_names(raw: object) -> Iterable[str]:
    """articles.entities_extracted may be a list of dicts, a JSON
    string, or NULL. Normalize to a flat iterable of names."""
    if raw is None:
        return ()
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return ()
    if not isinstance(raw, list):
        return ()
    names: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        etype = (item.get("type") or "").lower()
        if etype not in ("person", "organization", "organisation", "org"):
            continue
        name = (item.get("name") or "").strip()
        if 3 < len(name) < 60:
            names.append(name)
    return names


async def refresh(thread_id: str, db: object) -> None:
    """Recompute all four derived fields for the given thread.

    Single round-trip aggregate query; writes back via a single UPDATE.
    Safe to call on every article assignment.
    """
    agg = await db.execute(
        text(
            """
            SELECT
              COUNT(*)::int                                AS n_articles,
              COUNT(DISTINCT source_id)::int               AS n_sources,
              COUNT(*) FILTER (
                WHERE collected_at > NOW() - INTERVAL '24 hours'
              )::int                                       AS last_24h,
              COUNT(*) FILTER (
                WHERE collected_at >  NOW() - INTERVAL '48 hours'
                  AND collected_at <= NOW() - INTERVAL '24 hours'
              )::int                                       AS prev_24h,
              array_agg(entities_extracted)                AS entity_blobs
            FROM articles
            WHERE thread_id = CAST(:tid AS uuid)
            """
        ),
        {"tid": thread_id},
    )
    row = agg.fetchone()
    if row is None or (row.n_articles or 0) == 0:
        # No articles at all — defensive guard for race conditions.
        logger.debug("aggregates.refresh: thread %s has no articles, skipping", thread_id)
        return

    n_articles: int = row.n_articles
    n_sources: int = row.n_sources
    last_24h: int = row.last_24h or 0
    prev_24h: int = row.prev_24h or 0

    # Momentum — same shape as the old engine, applied to FRESH counts.
    if n_articles < 2:
        momentum = "stable"
    elif prev_24h == 0:
        momentum = "escalating" if last_24h >= 3 else "stable"
    else:
        ratio = last_24h / prev_24h
        if ratio > ESCALATING_RATIO:
            momentum = "escalating"
        elif ratio < FADING_RATIO:
            momentum = "fading"
        else:
            momentum = "stable"

    # Primary entities — top-N by frequency across ALL cluster articles.
    counter: Counter[str] = Counter()
    for blob in row.entity_blobs or ():
        for name in _extract_entity_names(blob):
            counter[name] += 1
    top_entities = [name for name, _ in counter.most_common(TOP_N_ENTITIES)]

    await db.execute(
        text(
            """
            UPDATE story_threads
               SET article_count    = :n_articles,
                   source_count     = :n_sources,
                   primary_entities = CAST(:entities AS text[]),
                   momentum         = :momentum,
                   last_updated_at  = NOW()
             WHERE id = CAST(:tid AS uuid)
            """
        ),
        {
            "n_articles": n_articles,
            "n_sources": n_sources,
            "entities": top_entities,
            "momentum": momentum,
            "tid": thread_id,
        },
    )
