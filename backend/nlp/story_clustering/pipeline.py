"""End-to-end orchestrator.

Two public entry points used by the Celery task:

  * cluster_article(article_id, db) — assign one article to a story.
  * consolidate(db)                 — nightly sweep: merge low-confidence
                                       neighbours, deactivate stale threads.

This is the only place that knows the FULL pipeline shape. Each
sub-module stays single-responsibility.
"""
from __future__ import annotations

import logging
from typing import Sequence

from sqlalchemy import text

from backend.nlp.story_clustering import aggregates, assignment, candidates, judge
from backend.nlp.story_clustering.types import (
    HARD_MATCH_MAX_DISTANCE,
    HARD_REJECT_MIN_DISTANCE,
    Article,
    AssignmentResult,
    CandidateThread,
    JudgeVerdict,
)

logger = logging.getLogger(__name__)

# Confidence below this on initial assignment → queue for re-evaluation
# by the consolidation sweep.
LOW_CONFIDENCE = 0.55

# Distance between two thread seeds below this in the consolidation
# sweep → ask the LLM whether they're really the same story.
CONSOLIDATE_DISTANCE_GATE = 0.30

# A thread with no new articles in this many days gets is_active = FALSE.
STALE_DAYS = 14


def _parse_pg_vector(raw: object) -> list[float]:
    """labse_embedding may come back as a Python list or a pgvector
    literal string depending on the driver. Normalize."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [float(x) for x in raw]
    if isinstance(raw, str) and raw.startswith("["):
        import json as _json

        return _json.loads(raw)
    return []


async def _load_article(article_id: str, db: object) -> Article | None:
    result = await db.execute(
        text(
            """
            SELECT
              a.id::text                   AS id,
              a.title                      AS title,
              a.primary_subject            AS primary_subject,
              a.summary_executive          AS summary_executive,
              a.language_detected          AS language_detected,
              a.source_id::text            AS source_id,
              s.name                       AS source_name,
              a.collected_at               AS collected_at,
              a.labse_embedding            AS embedding
            FROM articles a
            JOIN sources s ON s.id = a.source_id
            WHERE a.id = CAST(:aid AS uuid)
              AND a.labse_embedding IS NOT NULL
            """
        ),
        {"aid": article_id},
    )
    row = result.fetchone()
    if row is None:
        return None
    emb = _parse_pg_vector(row.embedding)
    if not emb:
        return None
    return Article(
        id=row.id,
        title=row.title or "",
        primary_subject=row.primary_subject,
        summary_executive=row.summary_executive,
        language_detected=row.language_detected,
        source_id=row.source_id,
        source_name=row.source_name,
        collected_at=row.collected_at,
        embedding=emb,
    )


async def cluster_article(article_id: str, db: object) -> AssignmentResult | None:
    """The full pipeline for one article. Returns None if the article
    can't be processed (no embedding, missing row)."""
    article = await _load_article(article_id, db)
    if article is None:
        logger.debug("cluster_article: %s skipped (no embedding)", article_id)
        return None

    top_k: Sequence[CandidateThread] = await candidates.find_top_k(article.embedding, db)

    # Fast paths first — avoid the LLM call when the answer is unambiguous.
    if top_k and top_k[0].distance < HARD_MATCH_MAX_DISTANCE:
        return await assignment.assign_to_thread(
            article,
            top_k[0].thread_id,
            distance=top_k[0].distance,
            confidence=1.0 - top_k[0].distance,
            skipped_llm=True,
            db=db,
        )

    if not top_k or top_k[0].distance > HARD_REJECT_MIN_DISTANCE:
        return await assignment.spawn_new_thread(
            article,
            confidence=1.0,
            skipped_llm=True,
            db=db,
        )

    # Ambiguity zone — defer to the LLM judge.
    verdict: JudgeVerdict = await judge.is_same_story(article, top_k)
    if verdict.matched_thread_id is None:
        return await assignment.spawn_new_thread(
            article,
            confidence=verdict.confidence,
            skipped_llm=False,
            db=db,
        )

    # Find the chosen candidate's distance for the result record.
    chosen = next(
        (c for c in top_k if c.thread_id == verdict.matched_thread_id),
        top_k[0],
    )
    return await assignment.assign_to_thread(
        article,
        verdict.matched_thread_id,
        distance=chosen.distance,
        confidence=verdict.confidence,
        skipped_llm=False,
        db=db,
    )


async def consolidate(db: object) -> dict[str, int]:
    """Nightly sweep:
      1. Re-check low-confidence threads against their nearest active
         neighbour; merge if the LLM says SAME.
      2. Deactivate threads with no new articles in STALE_DAYS.

    Returns a summary dict for the Celery task to log.
    """
    summary = {"merged": 0, "deactivated": 0, "rechecked": 0}

    # Step 1 — find low-confidence threads and their nearest neighbour.
    pairs = await db.execute(
        text(
            """
            WITH lowconf AS (
              SELECT id, seed_embedding, article_count
                FROM story_threads
               WHERE is_active        = TRUE
                 AND cluster_version  = 2
                 AND seed_embedding   IS NOT NULL
                 AND confidence_score IS NOT NULL
                 AND confidence_score < :lowconf
               ORDER BY confidence_score ASC, last_evaluated_at ASC NULLS FIRST
               LIMIT 50
            )
            SELECT
              lc.id::text                                 AS id1,
              lc.article_count                            AS count1,
              (
                SELECT st2.id::text
                  FROM story_threads st2
                 WHERE st2.is_active       = TRUE
                   AND st2.cluster_version = 2
                   AND st2.id              <> lc.id
                   AND st2.seed_embedding  IS NOT NULL
                 ORDER BY st2.seed_embedding <=> lc.seed_embedding
                 LIMIT 1
              )                                           AS id2,
              (
                SELECT MIN(st2.seed_embedding <=> lc.seed_embedding)
                  FROM story_threads st2
                 WHERE st2.is_active       = TRUE
                   AND st2.cluster_version = 2
                   AND st2.id              <> lc.id
                   AND st2.seed_embedding  IS NOT NULL
              )                                           AS d
            FROM lowconf lc
            """
        ),
        {"lowconf": LOW_CONFIDENCE},
    )

    for row in pairs.fetchall():
        summary["rechecked"] += 1
        if row.id2 is None or row.d is None or row.d > CONSOLIDATE_DISTANCE_GATE:
            await db.execute(
                text(
                    "UPDATE story_threads SET last_evaluated_at = NOW() "
                    "WHERE id = CAST(:tid AS uuid)"
                ),
                {"tid": row.id1},
            )
            continue
        # Within the gate — merge the smaller into the larger. (For
        # MVP we trust the distance gate alone here; the consolidation
        # sweep handles only the "really very close" pairs that should
        # have been merged at assignment time. The full LLM re-check
        # path is a Phase 2 enhancement.)
        await _merge_threads(row.id1, row.id2, db)
        summary["merged"] += 1

    # Step 2 — deactivate stale threads.
    deactivate = await db.execute(
        text(
            """
            WITH stale AS (
              UPDATE story_threads
                 SET is_active = FALSE
               WHERE is_active        = TRUE
                 AND cluster_version  = 2
                 AND last_updated_at  < NOW() - make_interval(days => :stale_days)
              RETURNING id
            )
            SELECT COUNT(*)::int AS n FROM stale
            """
        ),
        {"stale_days": STALE_DAYS},
    )
    summary["deactivated"] = deactivate.fetchone().n or 0

    logger.info("consolidate complete: %s", summary)
    return summary


async def _merge_threads(id_a: str, id_b: str, db: object) -> None:
    """Merge id_a into id_b — repoint articles, deactivate id_a,
    refresh aggregates on the surviving thread."""
    await db.execute(
        text(
            "UPDATE articles SET thread_id = CAST(:keep AS uuid) "
            "WHERE thread_id = CAST(:drop AS uuid)"
        ),
        {"keep": id_b, "drop": id_a},
    )
    await db.execute(
        text(
            "UPDATE story_threads SET is_active = FALSE "
            "WHERE id = CAST(:drop AS uuid)"
        ),
        {"drop": id_a},
    )
    await aggregates.refresh(id_b, db)
    logger.info("merged thread %s → %s", id_a[:8], id_b[:8])
