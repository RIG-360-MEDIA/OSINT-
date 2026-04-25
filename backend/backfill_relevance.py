"""One-shot backfill: dispatch unscored articles to the relevance queue."""
import asyncio
from backend.celery_app import app as celery_app


async def backfill() -> None:
    from sqlalchemy import text
    from backend.database import get_db

    async with get_db() as db:
        result = await db.execute(text("""
            SELECT a.id::text FROM articles a
            WHERE a.nlp_processed = TRUE
              AND a.nlp_confidence <> 'error'
              AND NOT EXISTS (
                SELECT 1 FROM user_article_relevance uar
                WHERE uar.article_id = a.id
                  AND uar.user_id = 'db4b9207-51aa-4d39-a7bf-e6fab34c3465'
              )
            ORDER BY a.collected_at DESC
        """))
        ids = [r[0] for r in result.fetchall()]

    print(f"Unscored articles: {len(ids)}", flush=True)

    BATCH = 100
    for i in range(0, len(ids), BATCH):
        celery_app.send_task(
            "tasks.score_relevance_batch",
            args=[ids[i : i + BATCH]],
            queue="relevance",
        )

    dispatched = (len(ids) + BATCH - 1) // BATCH
    print(f"Dispatched {dispatched} batches of {BATCH}", flush=True)


asyncio.run(backfill())
