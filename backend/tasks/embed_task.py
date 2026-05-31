"""
embed_task.py — 0a embed-at-ingest lane.

A dedicated, lightweight Celery task that gives newly-collected articles a LaBSE
vector within ~15 s of ingest, DECOUPLED from the heavy NLP pass (entities, topic,
stance, dedup). The production clusterer needs the vector ASAP; today it waits
behind the full NLP backlog. This lane removes that coupling.

Both this lane and nlp_processor assemble the embedding input via
backend.nlp.embedding_recipe.RECIPE, so their vectors are byte-identical and the
0c full re-embed stays consistent (embedding_revision = RECIPE.recipe_version).

Wiring (see backend/celery_app.py): tasks.embed.embed_pending_batch runs every
15 s on the dedicated `embedding` queue (worker-embedding, concurrency=1).

NOTE: with the current placeholder recipe (V0 = translated), the lane only embeds
articles that already have lead_text_translated. Once the A/B locks the recipe to
ORIGINAL language (the Phase-0 decision), lead_text_original is present at ingest
and the lane embeds immediately — which is the whole point of 0a. The lane is NOT
deployed until that lock (see docs/plans/0a-embed-at-ingest-2026-05-31.md).
"""
from __future__ import annotations

import asyncio
import logging

from backend.celery_app import app

logger = logging.getLogger(__name__)

EMBED_BATCH_LIMIT = 64


@app.task(
    name="tasks.embed.embed_pending_batch",
    bind=True,
    max_retries=2,
    queue="embedding",
)
def embed_pending_batch(self):  # type: ignore[no-untyped-def]
    """Embed up to EMBED_BATCH_LIMIT articles that still lack a vector."""
    try:
        result = asyncio.run(_embed_pending())
        if result["embedded"]:
            logger.info(
                "embed lane: %d embedded, %d remaining",
                result["embedded"],
                result["remaining"],
            )
        return result
    except Exception as exc:
        logger.error("embed lane failed: %s", exc)
        raise self.retry(exc=exc, countdown=30)


async def _embed_pending() -> dict:
    from sqlalchemy import text

    from backend.database import get_db
    from backend.nlp.embedding_recipe import RECIPE, build_embedding_text
    from backend.nlp.nlp_embedding import encode_text, get_labse_model

    get_labse_model()  # warm the singleton (max_seq_length set from RECIPE inside)

    async with get_db() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT id, title, lead_text_original, lead_text_translated
                    FROM articles
                    WHERE labse_embedding IS NULL
                      AND coalesce(lead_text_original, lead_text_translated) IS NOT NULL
                      AND length(coalesce(lead_text_original, lead_text_translated)) > 100
                    ORDER BY collected_at DESC
                    LIMIT :lim
                    """
                ),
                {"lim": EMBED_BATCH_LIMIT},
            )
        ).fetchall()

        if not rows:
            return {"embedded": 0, "remaining": 0}

        texts: list[str] = []
        ids: list = []
        for r in rows:
            txt = build_embedding_text(
                RECIPE,
                title=r.title,
                lead_original=r.lead_text_original,
                lead_translated=r.lead_text_translated,
            )
            if txt and len(txt) >= 20:
                texts.append(txt)
                ids.append(r.id)

        if not texts:
            return {"embedded": 0, "remaining": 0}

        vecs = encode_text(texts)  # batch encode; list[list[float]]
        embedded = 0
        for aid, vec in zip(ids, vecs):
            if vec is None:
                continue
            vec_literal = "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
            # Guard `labse_embedding IS NULL` so we never overwrite a vector the
            # NLP pass may have written in the same window (idempotent race-safe).
            await db.execute(
                text(
                    """
                    UPDATE articles SET
                      labse_embedding    = CAST(:vec AS vector),
                      embedded_at        = now(),
                      embedding_model    = :model,
                      embedding_revision = :rev
                    WHERE id = :id AND labse_embedding IS NULL
                    """
                ),
                {
                    "vec": vec_literal,
                    "model": RECIPE.model_id,
                    "rev": RECIPE.recipe_version,
                    "id": aid,
                },
            )
            embedded += 1
        await db.commit()

        remaining = (
            await db.execute(
                text(
                    """
                    SELECT count(*) FROM articles
                    WHERE labse_embedding IS NULL
                      AND coalesce(lead_text_original, lead_text_translated) IS NOT NULL
                      AND length(coalesce(lead_text_original, lead_text_translated)) > 100
                    """
                )
            )
        ).scalar()
        return {"embedded": embedded, "remaining": int(remaining or 0)}
