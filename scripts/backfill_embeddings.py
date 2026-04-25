"""
Backfill LaBSE embeddings for articles that were NLP-processed
but never got their embedding written.

Touches only the labse_embedding column. Batch size 50.
"""
import asyncio
import sys
import os

sys.path.insert(0, "/app")

from sqlalchemy import text
from backend.database import get_db
from backend.nlp.nlp_embedding import get_labse_model


async def backfill():
    model = get_labse_model()
    print("LaBSE model loaded.")

    async with get_db() as db:
        count_result = await db.execute(text("""
            SELECT COUNT(*) as cnt
            FROM articles
            WHERE nlp_processed = TRUE
              AND nlp_confidence != 'error'
              AND labse_embedding IS NULL
        """))
        total = count_result.scalar()
        print(f"Articles needing embeddings: {total}")

        if total == 0:
            print("Nothing to backfill.")
            return

        processed = 0
        batch_size = 50

        while True:
            rows_result = await db.execute(text("""
                SELECT id,
                       lead_text_translated,
                       lead_text_original,
                       title
                FROM articles
                WHERE nlp_processed = TRUE
                  AND nlp_confidence != 'error'
                  AND labse_embedding IS NULL
                ORDER BY collected_at DESC
                LIMIT :batch_size
            """), {"batch_size": batch_size})
            rows = rows_result.fetchall()

            if not rows:
                break

            for row in rows:
                text_to_embed = (
                    row.lead_text_translated
                    or row.lead_text_original
                    or row.title
                    or ""
                )
                text_to_embed = text_to_embed[:512]

                embedding = model.encode([text_to_embed])[0].tolist()
                embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

                await db.execute(text("""
                    UPDATE articles
                    SET labse_embedding = CAST(:embedding AS vector)
                    WHERE id = :id
                """), {"embedding": embedding_str, "id": row.id})

                processed += 1

            await db.commit()

            if processed % 200 == 0 or processed == total:
                print(f"  Progress: {processed}/{total}")

        print(f"\nDone. {processed} embeddings written.")


if __name__ == "__main__":
    asyncio.run(backfill())
