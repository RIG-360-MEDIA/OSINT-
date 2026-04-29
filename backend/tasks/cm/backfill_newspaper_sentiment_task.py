"""
One-time + daily catch-up task: populate sentiment_score on newspaper
clippings that are missing it. Used by the print-vs-digital divergence
endpoint.

Runs lightly — VADER/TextBlob via the existing compute_sentiment helper,
so this is fast and free. No Groq cost.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from backend.celery_app import app
from backend.collectors.social_collector import compute_sentiment
from backend.database import get_db

logger = logging.getLogger(__name__)


async def _run() -> int:
    fetch = """
        SELECT id,
               article_text_translated,
               article_text,
               headline_translated,
               headline,
               newspaper_language
        FROM newspaper_clippings
        WHERE sentiment IS NULL
          AND COALESCE(article_text_translated, article_text, headline_translated, headline) IS NOT NULL
        ORDER BY edition_date DESC NULLS LAST
        LIMIT 200
    """
    # newspaper_clippings.sentiment is TEXT — store the categorical label
    # rather than the raw float so this column matches the rest of the
    # newspaper pipeline (which expects positive / negative / neutral).
    update = "UPDATE newspaper_clippings SET sentiment = :s WHERE id = :id"
    n = 0
    async with get_db() as db:
        try:
            rows = (await db.execute(text(fetch))).all()
        except Exception as exc:  # noqa: BLE001
            logger.info("backfill_newspaper_sentiment skipped: %s", exc)
            return 0
        for r in rows:
            txt = (
                r.article_text_translated
                or r.article_text
                or r.headline_translated
                or r.headline
                or ""
            ).strip()
            if len(txt) < 30:
                continue
            try:
                score = compute_sentiment(txt, language=r.newspaper_language or "en")
            except Exception as exc:  # noqa: BLE001
                logger.debug("compute_sentiment failed for %s: %s", r.id, exc)
                continue
            # Map [-1, +1] to a categorical label that fits the existing
            # TEXT column.
            if score >= 0.15:
                label = "positive"
            elif score <= -0.15:
                label = "negative"
            else:
                label = "neutral"
            await db.execute(text(update), {"s": label, "id": r.id})
            n += 1
        await db.commit()
    return n


@app.task(name="tasks.cm.backfill_newspaper_sentiment", bind=True, max_retries=1)
def backfill_newspaper_sentiment(self) -> dict[str, int]:
    try:
        return {"updated": asyncio.run(_run())}
    except Exception as exc:
        logger.exception("backfill_newspaper_sentiment failed")
        raise self.retry(exc=exc, countdown=600)
