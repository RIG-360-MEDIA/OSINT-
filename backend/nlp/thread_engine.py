"""
Thread formation engine.
Incremental HNSW-based clustering.

Design decisions:
  - One article belongs to one thread
  - Threshold: 0.45 cosine distance
  - Centroid is rolling average of all member article embeddings
  - Momentum computed from article arrival rate within thread
  - Entity edges disabled (NER artifacts)
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import text

logger = logging.getLogger(__name__)

ASSIGNMENT_THRESHOLD = 0.45
MERGE_THRESHOLD = 0.20
STALE_DAYS = 7


def _parse_vec(v: object) -> list[float]:
    """Parse a pgvector value to a Python float list."""
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [float(x) for x in v]
    s = str(v).strip()
    if s.startswith("["):
        return json.loads(s)
    return []


def _format_vec(floats: list[float]) -> str:
    """Serialize float list to pgvector literal string."""
    return "[" + ",".join(f"{x:.8f}" for x in floats) + "]"


def _format_pg_text_array(items: list[str]) -> str:
    """Serialize Python string list to PostgreSQL text[] literal."""
    if not items:
        return "{}"
    escaped = ['"' + item.replace("\\", "\\\\").replace('"', '\\"') + '"' for item in items]
    return "{" + ",".join(escaped) + "}"


async def assign_article_to_thread(
    article_id: str,
    db: object,
) -> str | None:
    """
    Assign an article to an existing thread or create a new thread.

    Steps:
    1. Get article's labse_embedding
    2. Find nearest thread centroid via cosine distance (<=> operator)
    3. If distance < 0.45: assign to that thread, update centroid (rolling avg in Python)
    4. If no thread within 0.45: create new thread seeded from this article
    5. Update article_count, last_updated_at, thread_id FK
    """
    # Note: use CAST(:param AS type) — asyncpg rejects :param::type syntax
    art_result = await db.execute(
        text("""
        SELECT
          id::text,
          title,
          topic_category,
          labse_embedding,
          entities_extracted,
          collected_at
        FROM articles
        WHERE id = CAST(:aid AS uuid)
        AND labse_embedding IS NOT NULL
        """),
        {"aid": article_id},
    )
    article = art_result.fetchone()

    if not article or not article.labse_embedding:
        logger.debug("Article %s has no embedding — skipping", article_id)
        return None

    emb_list = _parse_vec(article.labse_embedding)
    emb_str = _format_vec(emb_list)

    # Find nearest thread centroid
    thread_result = await db.execute(
        text("""
        SELECT
          id::text as thread_id,
          title,
          article_count,
          centroid_embedding,
          (centroid_embedding <=> CAST(:emb AS vector)) as distance
        FROM story_threads
        WHERE is_active = TRUE
        AND centroid_embedding IS NOT NULL
        ORDER BY centroid_embedding <=> CAST(:emb AS vector)
        LIMIT 1
        """),
        {"emb": emb_str},
    )
    nearest = thread_result.fetchone()

    if nearest and nearest.distance < ASSIGNMENT_THRESHOLD:
        thread_id = nearest.thread_id
        n = nearest.article_count or 0

        # Rolling average centroid update computed in Python
        old_centroid = _parse_vec(nearest.centroid_embedding)
        if old_centroid and len(old_centroid) == len(emb_list) and n > 0:
            new_centroid = [(old_centroid[i] * n + emb_list[i]) / (n + 1) for i in range(len(emb_list))]
            new_centroid_str = _format_vec(new_centroid)
        else:
            new_centroid_str = emb_str

        await db.execute(
            text("""
            UPDATE story_threads
            SET
              centroid_embedding = CAST(:new_centroid AS vector),
              article_count      = article_count + 1,
              last_updated_at    = NOW()
            WHERE id = CAST(:tid AS uuid)
            """),
            {"new_centroid": new_centroid_str, "tid": thread_id},
        )

        await db.execute(
            text("UPDATE articles SET thread_id = CAST(:tid AS uuid) WHERE id = CAST(:aid AS uuid)"),
            {"tid": thread_id, "aid": article_id},
        )

        logger.info(
            "Article assigned to thread %s (distance=%.3f)",
            thread_id[:8],
            nearest.distance,
        )

    else:
        # Create new thread seeded from this article
        primary_entities: list[str] = []
        if article.entities_extracted:
            try:
                entities = article.entities_extracted
                if isinstance(entities, str):
                    entities = json.loads(entities)
                primary_entities = [
                    e.get("name", "")
                    for e in (entities or [])
                    if e.get("type") in ("person", "organization", "organisation")
                    and 3 < len(e.get("name", "")) < 50
                ][:5]
            except Exception:
                primary_entities = []

        thread_title = article.title[:120] if article.title else "Untitled Thread"

        create_result = await db.execute(
            text("""
            INSERT INTO story_threads (
              title, primary_entities, article_count, source_count,
              momentum, centroid_embedding, first_seen_at, last_updated_at, is_active
            ) VALUES (
              :title, :entities, 1, 1,
              'stable', CAST(:emb AS vector), NOW(), NOW(), TRUE
            )
            RETURNING id::text as thread_id
            """),
            {"title": thread_title, "entities": primary_entities, "emb": emb_str},
        )
        thread_id = create_result.fetchone().thread_id

        await db.execute(
            text("UPDATE articles SET thread_id = CAST(:tid AS uuid) WHERE id = CAST(:aid AS uuid)"),
            {"tid": thread_id, "aid": article_id},
        )

        logger.info("New thread created: %s — '%s'", thread_id[:8], thread_title[:50])

    return thread_id


async def update_thread_momentum(thread_id: str, db: object) -> str:
    """
    Compute and update momentum for a thread based on article arrival rate.

    ESCALATING: articles last 24h > 1.4x articles in prev 24h
    FADING:     articles last 24h < 0.6x articles in prev 24h
    STABLE:     everything else (or fewer than 2 articles total)
    """
    result = await db.execute(
        text("""
        SELECT
          COUNT(*) FILTER (
            WHERE collected_at > NOW() - INTERVAL '24 hours'
          ) as last_24h,
          COUNT(*) FILTER (
            WHERE collected_at > NOW() - INTERVAL '48 hours'
            AND   collected_at <= NOW() - INTERVAL '24 hours'
          ) as prev_24h,
          COUNT(*) as total
        FROM articles
        WHERE thread_id = CAST(:tid AS uuid)
        """),
        {"tid": thread_id},
    )
    row = result.fetchone()

    last_24h = row.last_24h or 0
    prev_24h = row.prev_24h or 0
    total = row.total or 0

    if total < 2:
        momentum = "stable"
    elif prev_24h == 0:
        momentum = "escalating" if last_24h >= 3 else "stable"
    else:
        ratio = last_24h / prev_24h
        if ratio > 1.4:
            momentum = "escalating"
        elif ratio < 0.6:
            momentum = "fading"
        else:
            momentum = "stable"

    await db.execute(
        text("UPDATE story_threads SET momentum = :momentum WHERE id = CAST(:tid AS uuid)"),
        {"momentum": momentum, "tid": thread_id},
    )
    return momentum


async def nightly_recluster(db: object) -> dict:
    """
    Nightly maintenance:
    1. Find thread pairs with centroid distance < 0.20 → merge smaller into larger
    2. Deactivate threads with no new articles in 7 days
    3. Update all momentum scores
    """
    summary: dict = {"merged": 0, "deactivated": 0, "momentum_updated": 0}

    # Step 1: Merge very similar threads
    merge_result = await db.execute(
        text("""
        SELECT
          t1.id::text as id1,
          t2.id::text as id2,
          t1.article_count as count1,
          t2.article_count as count2,
          (t1.centroid_embedding <=> t2.centroid_embedding) as centroid_distance
        FROM story_threads t1
        JOIN story_threads t2 ON t1.id < t2.id
        WHERE t1.is_active = TRUE
        AND t2.is_active = TRUE
        AND t1.centroid_embedding IS NOT NULL
        AND t2.centroid_embedding IS NOT NULL
        AND (t1.centroid_embedding <=> t2.centroid_embedding) < :threshold
        ORDER BY centroid_distance ASC
        LIMIT 20
        """),
        {"threshold": MERGE_THRESHOLD},
    )
    mergeable = merge_result.fetchall()

    deactivated_ids: set[str] = set()

    for pair in mergeable:
        if pair.id1 in deactivated_ids or pair.id2 in deactivated_ids:
            continue
        keep_id = pair.id1 if pair.count1 >= pair.count2 else pair.id2
        drop_id = pair.id2 if keep_id == pair.id1 else pair.id1

        await db.execute(
            text("UPDATE articles SET thread_id = CAST(:keep AS uuid) WHERE thread_id = CAST(:drop AS uuid)"),
            {"keep": keep_id, "drop": drop_id},
        )
        await db.execute(
            text("UPDATE story_threads SET is_active = FALSE WHERE id = CAST(:drop AS uuid)"),
            {"drop": drop_id},
        )
        await db.execute(
            text("""
            UPDATE story_threads
            SET article_count = (SELECT COUNT(*) FROM articles WHERE thread_id = CAST(:keep AS uuid))
            WHERE id = CAST(:keep AS uuid)
            """),
            {"keep": keep_id},
        )
        deactivated_ids.add(drop_id)
        summary["merged"] += 1
        logger.info("Merged thread %s into %s", drop_id[:8], keep_id[:8])

    # Step 2: Deactivate stale threads
    await db.execute(
        text("""
        UPDATE story_threads
        SET is_active = FALSE
        WHERE is_active = TRUE
        AND last_updated_at < NOW() - INTERVAL '7 days'
        """),
    )

    stale_count_result = await db.execute(
        text("""
        SELECT COUNT(*) as cnt FROM story_threads
        WHERE is_active = FALSE
        AND last_updated_at > NOW() - INTERVAL '1 minute'
        """)
    )
    summary["deactivated"] = stale_count_result.fetchone().cnt or 0

    # Step 3: Update momentum for all active threads
    active_result = await db.execute(
        text("SELECT id::text as thread_id FROM story_threads WHERE is_active = TRUE")
    )
    for t in active_result.fetchall():
        await update_thread_momentum(t.thread_id, db)
        summary["momentum_updated"] += 1

    logger.info("Nightly recluster complete: %s", summary)
    return summary
