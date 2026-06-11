"""Persist the clustering decision.

Two operations:
  * assign_to_thread(article, thread_id, ...) — link existing thread
  * spawn_new_thread(article, ...)            — create thread seeded
                                                 from this article

Both call aggregates.refresh() afterwards so the derived fields are
always fresh. No more set-once-and-rot bugs.
"""
from __future__ import annotations

import logging

from sqlalchemy import text

from backend.nlp.story_clustering import aggregates
from backend.nlp.story_clustering.candidates import _format_vec
from backend.nlp.story_clustering.types import Article, AssignmentResult

logger = logging.getLogger(__name__)

_TITLE_MAX = 120


async def assign_to_thread(
    article: Article,
    thread_id: str,
    *,
    distance: float,
    confidence: float,
    skipped_llm: bool,
    db: object,
) -> AssignmentResult:
    """Attach the article to an existing thread; refresh aggregates."""
    await db.execute(
        text(
            "UPDATE articles SET thread_id = CAST(:tid AS uuid) "
            "WHERE id = CAST(:aid AS uuid)"
        ),
        {"tid": thread_id, "aid": article.id},
    )
    await aggregates.refresh(thread_id, db)
    logger.info(
        "Article %s → thread %s (distance=%.3f, confidence=%.2f, llm=%s)",
        article.id[:8],
        thread_id[:8],
        distance,
        confidence,
        "skip" if skipped_llm else "yes",
    )
    return AssignmentResult(
        article_id=article.id,
        thread_id=thread_id,
        spawned_new=False,
        skipped_llm=skipped_llm,
        confidence=confidence,
        distance_to_seed=distance,
    )


async def spawn_new_thread(
    article: Article,
    *,
    confidence: float,
    skipped_llm: bool,
    db: object,
) -> AssignmentResult:
    """Create a new thread anchored on this article and link it."""
    title = (article.title or article.primary_subject or "Untitled")[:_TITLE_MAX]
    emb_str = _format_vec(article.embedding)

    create = await db.execute(
        text(
            """
            INSERT INTO story_threads (
              title, primary_entities, article_count, source_count,
              momentum, centroid_embedding, seed_article_id, seed_embedding,
              confidence_score, cluster_version,
              first_seen_at, last_updated_at, last_evaluated_at, is_active
            ) VALUES (
              :title, CAST(:entities AS text[]), 0, 0,
              'stable',
              CAST(:emb AS vector), CAST(:seed_id AS uuid), CAST(:emb AS vector),
              :confidence, 2,
              NOW(), NOW(), NOW(), TRUE
            )
            RETURNING id::text AS thread_id
            """
        ),
        {
            "title": title,
            "entities": [],  # aggregates.refresh fills this from the article below
            "emb": emb_str,
            "seed_id": article.id,
            "confidence": confidence,
        },
    )
    thread_id = create.fetchone().thread_id

    await db.execute(
        text(
            "UPDATE articles SET thread_id = CAST(:tid AS uuid) "
            "WHERE id = CAST(:aid AS uuid)"
        ),
        {"tid": thread_id, "aid": article.id},
    )
    await aggregates.refresh(thread_id, db)

    logger.info(
        "Article %s → spawned thread %s (confidence=%.2f, llm=%s) '%s'",
        article.id[:8],
        thread_id[:8],
        confidence,
        "skip" if skipped_llm else "yes",
        title[:50],
    )
    return AssignmentResult(
        article_id=article.id,
        thread_id=thread_id,
        spawned_new=True,
        skipped_llm=skipped_llm,
        confidence=confidence,
        distance_to_seed=0.0,
    )
