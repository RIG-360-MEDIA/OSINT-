"""
Manual relevance backfill — dispatches unscored NLP-processed articles
to the relevance queue for scoring.

Usage:
    docker exec rig-backend python scripts/backfill_relevance.py
    docker exec rig-backend python scripts/backfill_relevance.py --user-id UUID
    docker exec rig-backend python scripts/backfill_relevance.py --limit 500
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import text

BATCH_SIZE = 100


async def run_backfill(user_id: str | None = None, limit: int | None = None) -> None:
    from backend.celery_app import app as celery
    from backend.database import get_db

    effective_limit = limit if limit is not None else 99_999

    async with get_db() as db:
        if user_id:
            query = text(
                """
                SELECT a.id::text
                FROM articles a
                WHERE a.nlp_processed = TRUE
                  AND a.nlp_confidence <> 'error'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM user_article_relevance uar
                      WHERE uar.article_id = a.id
                        AND uar.user_id = CAST(:user_id AS uuid)
                  )
                ORDER BY a.collected_at DESC
                LIMIT :lim
                """
            )
            result = await db.execute(query, {"user_id": user_id, "lim": effective_limit})
        else:
            query = text(
                """
                SELECT a.id::text
                FROM articles a
                WHERE a.nlp_processed = TRUE
                  AND a.nlp_confidence <> 'error'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM user_article_relevance uar
                      WHERE uar.article_id = a.id
                  )
                ORDER BY a.collected_at DESC
                LIMIT :lim
                """
            )
            result = await db.execute(query, {"lim": effective_limit})

        ids = [r[0] for r in result.fetchall()]

    if not ids:
        print("Nothing to score — all articles already scored", flush=True)
        return

    scope = f"for user {user_id}" if user_id else "for all users"
    print(f"Scoring {len(ids)} articles {scope}", flush=True)

    batches = 0
    for i in range(0, len(ids), BATCH_SIZE):
        celery.send_task(
            "tasks.score_relevance_batch",
            args=[ids[i : i + BATCH_SIZE]],
            queue="relevance",
        )
        batches += 1

    print(f"Dispatched {batches} batches of {BATCH_SIZE}", flush=True)
    print(f"ETA: ~{batches * 3} minutes at current rate", flush=True)
    print(
        "Monitor: docker exec rig-postgres psql -U rig -d rig "
        '-c "SELECT COUNT(*) FROM user_article_relevance;"',
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", type=str, default=None, help="Score for one user only")
    parser.add_argument("--limit", type=int, default=None, help="Max articles to score")
    args = parser.parse_args()
    asyncio.run(run_backfill(args.user_id, args.limit))


if __name__ == "__main__":
    main()
