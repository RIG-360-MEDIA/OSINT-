"""Trigger relevance scoring for all NLP-processed articles."""
import asyncio

from sqlalchemy import text

from backend.celery_app import app as celery_app
from backend.database import get_db


async def trigger() -> None:
    async with get_db() as db:
        result = await db.execute(
            text(
                "SELECT id::text FROM articles "
                "WHERE nlp_processed = TRUE AND nlp_confidence != 'error'"
            )
        )
        ids = [row[0] for row in result.fetchall()]

    print(f"Queuing {len(ids)} articles for relevance scoring")
    celery_app.send_task("tasks.score_relevance_batch", args=[ids], queue="relevance")
    print("Task queued.")


if __name__ == "__main__":
    asyncio.run(trigger())
