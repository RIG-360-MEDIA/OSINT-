"""
Score the political stance of recent articles + social posts that don't yet
have a row in cm_stance_scores. Scheduled every 5 minutes on the `nlp` queue.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db
from backend.nlp.cm import coalitions
from backend.nlp.cm.stance import score as score_stance

logger = logging.getLogger(__name__)

BATCH_SIZE_ARTICLES = 60
BATCH_SIZE_POSTS = 60


async def _score_articles(state_filter: str | None = None) -> int:
    """Score articles published in the last 7 days that have no stance row."""
    # `articles` in this deployment has no relevance score column; we
    # filter by source_tier (1 = T1 / 2 = T2) to keep the volume bounded
    # and let the downstream stance signal speak for itself.
    sql = """
        SELECT a.id,
               a.title,
               a.lead_text_translated,
               a.lead_text_original,
               a.geo_primary
        FROM articles a
        LEFT JOIN cm_stance_scores s
          ON s.source_kind = 'article' AND s.source_id = a.id
        WHERE s.id IS NULL
          AND a.published_at > now() - interval '7 days'
          AND COALESCE(a.source_tier, 9) <= 2
        ORDER BY a.published_at DESC
        LIMIT :lim
    """
    upsert = """
        INSERT INTO cm_stance_scores (
            source_kind, source_id, state, stance, party, party_kind,
            confidence, model, scored_at
        ) VALUES (
            'article', :sid, :state, :stance, NULL, :pk,
            :conf, :model, now()
        )
        ON CONFLICT (source_kind, source_id) DO UPDATE
            SET stance = EXCLUDED.stance,
                party_kind = EXCLUDED.party_kind,
                confidence = EXCLUDED.confidence,
                model = EXCLUDED.model,
                scored_at = EXCLUDED.scored_at
    """
    n = 0
    async with get_db() as db:
        rows = (await db.execute(text(sql), {"lim": BATCH_SIZE_ARTICLES})).all()
        for r in rows:
            body = r.lead_text_translated or r.lead_text_original or r.title or ""
            geo = (r.geo_primary or "").lower()
            state = "TG" if "telangana" in geo or "hyderabad" in geo else (
                "AP" if "andhra" in geo or "vizag" in geo or "vijayawada" in geo else None
            )
            try:
                result = await score_stance(text=body, state=state)
            except Exception as exc:  # noqa: BLE001
                logger.warning("stance score failed for article %s: %s", r.id, exc)
                continue
            await db.execute(
                text(upsert),
                {
                    "sid": r.id,
                    "state": state,
                    "stance": result.stance,
                    "pk": result.party_kind,
                    "conf": result.confidence,
                    "model": result.model,
                },
            )
            n += 1
        await db.commit()
    return n


async def _score_social_posts() -> int:
    sql = """
        SELECT sp.id,
               sp.post_text_translated,
               sp.post_text,
               sp.post_language,
               sp.matched_entities
        FROM social_posts sp
        LEFT JOIN cm_stance_scores s
          ON s.source_kind = 'social_post' AND s.source_id = sp.id
        WHERE s.id IS NULL
          AND sp.collected_at > now() - interval '3 days'
          AND length(COALESCE(sp.post_text_translated, sp.post_text, '')) >= 60
        ORDER BY sp.collected_at DESC
        LIMIT :lim
    """
    upsert = """
        INSERT INTO cm_stance_scores (
            source_kind, source_id, stance, party, party_kind,
            confidence, model, scored_at
        ) VALUES (
            'social_post', :sid, :stance, NULL, :pk,
            :conf, :model, now()
        )
        ON CONFLICT (source_kind, source_id) DO UPDATE
            SET stance = EXCLUDED.stance,
                party_kind = EXCLUDED.party_kind,
                confidence = EXCLUDED.confidence,
                model = EXCLUDED.model,
                scored_at = EXCLUDED.scored_at
    """
    n = 0
    async with get_db() as db:
        rows = (await db.execute(text(sql), {"lim": BATCH_SIZE_POSTS})).all()
        for r in rows:
            text_in = (r.post_text_translated or r.post_text or "")
            try:
                result = await score_stance(text=text_in, state=None)
            except Exception as exc:  # noqa: BLE001
                logger.warning("stance score failed for post %s: %s", r.id, exc)
                continue
            await db.execute(
                text(upsert),
                {
                    "sid": r.id,
                    "stance": result.stance,
                    "pk": result.party_kind,
                    "conf": result.confidence,
                    "model": result.model,
                },
            )
            n += 1
        await db.commit()
    return n


@app.task(name="tasks.cm.tag_stance", bind=True, max_retries=2)
def tag_stance(self) -> dict[str, Any]:
    """Celery entry point. Returns {articles, posts} counts scored."""
    try:
        n_articles = asyncio.run(_score_articles())
        n_posts = asyncio.run(_score_social_posts())
        return {"articles": n_articles, "posts": n_posts}
    except Exception as exc:
        logger.exception("tag_stance failed")
        raise self.retry(exc=exc, countdown=120)
