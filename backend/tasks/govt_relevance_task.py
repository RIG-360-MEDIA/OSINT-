"""
Govt-doc per-user relevance Celery tasks.

Mirrors backend/tasks/relevance_task.py pattern:
  - tasks.score_govt_doc_relevance(doc_id, user_id)        -> single (doc, user) pair
  - tasks.score_govt_doc_for_all_users(doc_id)             -> fan-out to active users

Triggered lazily by GET /api/documents/feed when an unseen doc is returned.
"""
from __future__ import annotations

import asyncio
import logging

from backend.celery_app import app

logger = logging.getLogger(__name__)


@app.task(
    name="tasks.score_govt_doc_relevance",
    bind=True,
    max_retries=2,
    queue="relevance",
)
def score_govt_doc_relevance(self, doc_id: str, user_id: str):  # type: ignore[no-untyped-def]
    """Score a single (doc, user) pair end-to-end and cache the result."""
    try:
        result = asyncio.run(_score_one(doc_id=doc_id, user_id=user_id))
        logger.info(
            "Govt-doc relevance scored: doc=%s user=%s tier=%s score=%.3f",
            doc_id,
            user_id,
            result.get("relevance_tier"),
            float(result.get("score_final") or 0.0),
        )
        return result
    except Exception as exc:
        logger.error(
            "Govt-doc relevance failed for doc=%s user=%s: %s",
            doc_id,
            user_id,
            exc,
        )
        raise self.retry(exc=exc, countdown=30)


@app.task(
    name="tasks.score_govt_doc_for_all_users",
    bind=True,
    max_retries=2,
    queue="relevance",
)
def score_govt_doc_for_all_users(self, doc_id: str):  # type: ignore[no-untyped-def]
    """Fan-out: score this doc against every active user profile.

    Pulls up to 100 active users (there's typically only 1 today).
    Dispatches one score_govt_doc_relevance task per user.
    """
    try:
        user_ids = asyncio.run(_active_user_ids(limit=100))
        for uid in user_ids:
            score_govt_doc_relevance.apply_async(args=[doc_id, uid])
        logger.info(
            "Fan-out scoring queued for doc=%s users=%d",
            doc_id,
            len(user_ids),
        )
        return {"doc_id": doc_id, "users_queued": len(user_ids)}
    except Exception as exc:
        logger.error(
            "Fan-out scoring failed for doc=%s: %s", doc_id, exc
        )
        raise self.retry(exc=exc, countdown=30)


# --- async helpers -----------------------------------------------------------
async def _score_one(*, doc_id: str, user_id: str) -> dict:
    from backend.database import get_db
    from backend.relevance.govt_relevance import score_govt_doc_for_user

    async with get_db() as db:
        return await score_govt_doc_for_user(
            db=db, doc_id=doc_id, user_id=user_id
        )


async def _active_user_ids(*, limit: int = 100) -> list[str]:
    from sqlalchemy import text

    from backend.database import get_db

    async with get_db() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT user_id::text AS uid
                    FROM user_profiles
                    ORDER BY user_id
                    LIMIT :lim
                    """
                ),
                {"lim": limit},
            )
        ).fetchall()
        return [r.uid for r in rows]
