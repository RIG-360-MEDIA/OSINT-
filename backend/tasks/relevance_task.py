"""
Relevance scoring Celery task.

Triggered by process_nlp_batch after each NLP batch completes.
Not on a timer — event-driven.

Stage 1: algorithmic scoring for all articles × all users.
Stage 2: Groq explanation for articles scoring >= 0.25.
"""
from __future__ import annotations

import asyncio
import json
import logging

from backend.celery_app import app

logger = logging.getLogger(__name__)


@app.task(
    name="tasks.score_relevance_batch",
    bind=True,
    max_retries=3,
    queue="relevance",
)
def score_relevance_batch(self, article_ids: list[str]):  # type: ignore[no-untyped-def]
    """
    Score a batch of NLP-processed articles against all active user profiles.
    Called by process_nlp_batch after each NLP batch completes.
    """
    try:
        result = asyncio.run(_score_batch(article_ids))
        logger.info(
            "Relevance scoring complete: %d scores written for %d articles",
            result["scored"],
            result["articles"],
        )
        return result
    except Exception as exc:
        logger.error("Relevance batch failed: %s", exc)
        raise self.retry(exc=exc, countdown=30)


async def _score_batch(article_ids: list[str]) -> dict:
    """
    Core scoring logic.
    For each article × each user: compute Stage 1 score.
    For scores >= 0.25: run Stage 2 Groq in batches of 5 concurrent.
    """
    from sqlalchemy import text

    from backend.database import get_db
    from backend.nlp.relevance_scorer import (
        compute_stage1_score,
    )

    async with get_db() as db:
        # ── Fetch articles ────────────────────────────────────────────────
        articles_raw = await db.execute(
            text(
                """
                SELECT
                    a.id,
                    a.title,
                    a.lead_text_original,
                    a.lead_text_translated,
                    a.topic_category,
                    a.geo_primary,
                    a.source_tier,
                    a.entities_extracted,
                    a.nlp_confidence,
                    s.geo_states AS source_geo_states
                FROM articles a
                JOIN sources s ON a.source_id = s.id
                WHERE a.id = ANY(CAST(:ids AS uuid[]))
                AND a.nlp_confidence != 'error'
                """
            ),
            {"ids": article_ids},
        )
        articles = articles_raw.fetchall()

        # ── Fetch all user profiles with their entities ───────────────────
        users_raw = await db.execute(
            text(
                """
                SELECT
                    up.user_id,
                    up.role_type,
                    up.geo_primary,
                    up.geo_secondary,
                    up.signal_priorities,
                    up.role_context,
                    COALESCE(
                        json_agg(
                            json_build_object(
                                'canonical_name', ue.canonical_name,
                                'priority', ue.priority
                            )
                        ) FILTER (WHERE ue.id IS NOT NULL),
                        '[]'::json
                    ) AS entities
                FROM user_profiles up
                LEFT JOIN user_entities ue ON ue.user_id = up.user_id
                GROUP BY
                    up.user_id, up.role_type, up.geo_primary,
                    up.geo_secondary, up.signal_priorities, up.role_context
                """
            )
        )
        users = users_raw.fetchall()

        if not users:
            logger.info("No users to score against")
            return {"articles": len(articles), "scored": 0}

        total_scored = 0
        stage2_queue: list[dict] = []

        for article in articles:
            article_dict = dict(article._mapping)

            # Parse JSONB fields returned as strings
            entities = article_dict.get("entities_extracted")
            if isinstance(entities, str):
                entities = json.loads(entities)
            article_dict["entities_extracted"] = entities or []

            source_geo = article_dict.get("source_geo_states") or []

            for user in users:
                user_dict = dict(user._mapping)

                priorities = user_dict.get("signal_priorities")
                if isinstance(priorities, str):
                    priorities = json.loads(priorities)
                user_dict["signal_priorities"] = priorities or {}

                user_entities = user_dict.get("entities") or []
                if isinstance(user_entities, str):
                    user_entities = json.loads(user_entities)

                geo_sec = user_dict.get("geo_secondary") or []
                if isinstance(geo_sec, str):
                    try:
                        geo_sec = json.loads(geo_sec)
                    except Exception:
                        geo_sec = []
                user_dict["geo_secondary"] = geo_sec

                stage1_score, debug = compute_stage1_score(
                    article=article_dict,
                    user_profile=user_dict,
                    user_entities=user_entities,
                    source_geo_states=source_geo,
                )

                tier = (
                    1 if stage1_score >= 0.50
                    else 2 if stage1_score >= 0.25
                    else 3 if stage1_score >= 0.10
                    else 0
                )

                # Matched entity names: intersection of article entities and watched
                watched_names = {
                    ue["canonical_name"].lower() for ue in user_entities
                }
                matched = [
                    e["name"]
                    for e in article_dict["entities_extracted"]
                    if e.get("name")
                    and e["name"] != "None"
                    and e["name"].lower() in watched_names
                ]

                await db.execute(
                    text(
                        """
                        INSERT INTO user_article_relevance (
                            user_id, article_id,
                            score_stage1, score_final,
                            relevance_tier,
                            geo_multiplier_applied,
                            matched_entity_names
                        ) VALUES (
                            :user_id, CAST(:article_id AS uuid),
                            :score, :score,
                            :tier, :geo_mult,
                            :entities
                        )
                        ON CONFLICT (user_id, article_id) DO UPDATE SET
                            score_stage1           = EXCLUDED.score_stage1,
                            score_final            = EXCLUDED.score_final,
                            relevance_tier         = EXCLUDED.relevance_tier,
                            geo_multiplier_applied = EXCLUDED.geo_multiplier_applied,
                            matched_entity_names   = EXCLUDED.matched_entity_names,
                            scored_at              = NOW()
                        """
                    ),
                    {
                        "user_id": str(user_dict["user_id"]),
                        "article_id": str(article_dict["id"]),
                        "score": stage1_score,
                        "tier": tier,
                        "geo_mult": debug["geo_multiplier"],
                        "entities": matched,
                    },
                )
                total_scored += 1

                if stage1_score >= 0.25 and tier > 0:
                    stage2_queue.append(
                        {
                            "article": article_dict,
                            "user": user_dict,
                            "user_id": str(user_dict["user_id"]),
                            "article_id": str(article_dict["id"]),
                        }
                    )

        await db.commit()

        # ── Stage 2: Groq explanations ────────────────────────────────────
        if stage2_queue:
            await _run_stage2_batch(stage2_queue, db)

        return {
            "articles": len(articles),
            "users": len(users),
            "scored": total_scored,
            "stage2_count": len(stage2_queue),
        }


async def _run_stage2_batch(queue: list[dict], db) -> None:  # type: ignore[type-arg]
    """
    Run Stage 2 Groq calls in batches of 5 concurrent.
    Updates score_final and relevance_explanation.
    """
    from sqlalchemy import text

    from backend.nlp.relevance_scorer import compute_stage2_explanation

    BATCH_SIZE = 5

    for i in range(0, len(queue), BATCH_SIZE):
        batch = queue[i : i + BATCH_SIZE]

        tasks = [
            compute_stage2_explanation(item["article"], item["user"])
            for item in batch
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for item, result in zip(batch, results):
            if isinstance(result, Exception):
                logger.warning(
                    "Stage 2 failed for article %s: %s",
                    item["article_id"],
                    result,
                )
                continue

            score = float(result["score"])
            tier = (
                1 if score >= 0.50
                else 2 if score >= 0.25
                else 3 if score >= 0.10
                else 0
            )

            await db.execute(
                text(
                    """
                    UPDATE user_article_relevance
                    SET
                        score_final           = :score,
                        relevance_explanation = :explanation,
                        sentiment_for_user    = :sentiment,
                        relevance_tier        = :tier
                    WHERE user_id    = :user_id
                    AND   article_id = CAST(:article_id AS uuid)
                    """
                ),
                {
                    "score": score,
                    "explanation": result["explanation"],
                    "sentiment": result["sentiment_for_user"],
                    "tier": tier,
                    "user_id": item["user_id"],
                    "article_id": item["article_id"],
                },
            )

        await db.commit()
