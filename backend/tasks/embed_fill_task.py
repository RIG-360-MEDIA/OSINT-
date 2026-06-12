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

# V4 SSOT eligibility: a translated lead must exist. Embedding pre-translation in the
# original language craters cross-lingual recall (see embedding_recipe + the
# cluster-recall README), so we wait for translation rather than embed wrong-language
# text. Mirrors reembed_0c_v4.py's ELIGIBLE so new vectors match the v4 corpus exactly.
_V4_ELIGIBLE = "lead_text_translated IS NOT NULL AND length(lead_text_translated) > 50"


async def _embed_batch(limit: int = 250) -> int:
    """Embed up to `limit` newest articles that have a translated lead but no embedding,
    using the LOCKED V4 recipe (translated lead + title) so new vectors are byte-identical
    to the v4 corpus and the clustering pipeline. Writes both the live column and the
    v4 shadow, and stamps the v4 revision so the recipe-mix can never silently reopen."""
    from backend.database import get_db
    from backend.nlp.nlp_embedding import get_labse_model
    from backend.nlp.embedding_recipe import RECIPE, build_embedding_text

    async with get_db() as db:
        rows = (await db.execute(text(
            f"SELECT id::text AS id, title, lead_text_original AS lo, lead_text_translated AS lt "
            f"FROM articles "
            f"WHERE labse_embedding IS NULL AND {_V4_ELIGIBLE} "
            f"ORDER BY collected_at DESC LIMIT :lim"
        ), {"lim": limit})).fetchall()
        if not rows:
            return 0

        # build V4 input text per row (SSOT recipe), then batch-encode
        texts = [
            build_embedding_text(RECIPE, title=r.title, lead_original=r.lo, lead_translated=r.lt)
            for r in rows
        ]
        model = get_labse_model()
        vecs = await asyncio.to_thread(model.encode, texts)

        for r, v in zip(rows, vecs):
            emb = str(v.tolist())
            await db.execute(text(
                "UPDATE articles SET labse_embedding = CAST(:emb AS vector), "
                "labse_embedding_v4 = CAST(:emb AS vector), "
                "embedded_at = now(), embedding_model = :m, "
                "embedding_revision = :rev "
                "WHERE id = CAST(:id AS uuid)"
            ), {"emb": emb, "m": RECIPE.model_id, "rev": RECIPE.recipe_version, "id": r.id})
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
