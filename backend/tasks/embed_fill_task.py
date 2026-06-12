"""embed_fill_task.py — fills MISSING LaBSE embeddings, decoupled from extraction.

Why this exists: embeddings were only ever produced inline by the legacy
nlp_processor. When articles moved to the substrate pipeline (run_corpus_pass,
which has NO embedding step), embeddings silently stopped — labse_embedding stayed
NULL with no error (2026-06-11). This task embeds ANY article that has good text
but no embedding, so the gap can never silently reopen regardless of which
pipeline does extraction.

Runs every 4 min via beat (keeps new articles embedded). For a one-shot backfill
of an existing gap, call _backfill_all().
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from celery import shared_task
from sqlalchemy import text

logger = logging.getLogger(__name__)

# best available body text, in preference order (translated > scraped > lead)
_PICK_TEXT = (
    "COALESCE(NULLIF(full_text_translated,''), NULLIF(full_text_scraped,''), "
    "NULLIF(lead_text_translated,''), NULLIF(lead_text_original,''), '')"
)


async def _embed_batch(limit: int = 250) -> int:
    """Embed up to `limit` newest articles that have good text but no embedding."""
    from backend.database import get_db
    from backend.nlp.nlp_embedding import get_labse_model, LABSE_MODEL_ID, LABSE_REVISION

    async with get_db() as db:
        rows = (await db.execute(text(
            f"SELECT id::text AS id, left({_PICK_TEXT}, 512) AS txt "
            f"FROM articles "
            f"WHERE labse_embedding IS NULL AND length({_PICK_TEXT}) >= 100 "
            f"ORDER BY collected_at DESC LIMIT :lim"
        ), {"lim": limit})).fetchall()
        if not rows:
            return 0

        # batch-encode (far faster than one-at-a-time for a backfill)
        model = get_labse_model()
        vecs = await asyncio.to_thread(model.encode, [r.txt for r in rows])

        for r, v in zip(rows, vecs):
            await db.execute(text(
                "UPDATE articles SET labse_embedding = CAST(:emb AS vector), "
                "embedded_at = now(), embedding_model = :m, "
                "embedding_revision = COALESCE(embedding_revision, :rev) "
                "WHERE id = CAST(:id AS uuid)"
            ), {"emb": str(v.tolist()), "m": LABSE_MODEL_ID, "rev": LABSE_REVISION, "id": r.id})
        await db.commit()
        return len(rows)


@shared_task(
    name="tasks.quality.embed_fill",
    bind=True,
    queue="nlp",
    soft_time_limit=240,
    time_limit=300,
)
def embed_fill_task(self) -> dict[str, Any]:
    try:
        n = asyncio.run(_embed_batch(250))
        if n:
            logger.info("embed_fill: embedded %d articles", n)
        return {"embedded": n}
    except Exception as exc:  # noqa: BLE001
        logger.exception("embed_fill failed: %s", exc)
        return {"error": str(exc)[:200]}


async def _backfill_all(batch: int = 400) -> dict[str, Any]:
    """One-shot: keep embedding until no NULL-embedding good-text articles remain."""
    total = 0
    while True:
        n = await _embed_batch(batch)
        total += n
        print(f"embed backfill: +{n} (total {total})", flush=True)
        if n == 0:
            break
    return {"total_embedded": total}
