"""c1_c2_labse_embeddings.py — backfill LaBSE embeddings on claims + articles.

C1: article_claims.embedding (0% → 95% target) ~297K rows
C2: articles.labse_embedding (95.8% → ~99%) ~4,500 missing rows

Uses the model's batch encoding API (32 texts per pass) which is
~30x faster than per-row generate_embedding(). No LLM API cost.
"""
from __future__ import annotations

import asyncio
import logging
import sys

sys.path.insert(0, "/app")
from sqlalchemy import text
from backend.database import get_db
from backend.nlp.nlp_embedding import get_labse_model

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("c1c2")

BATCH = 32   # SentenceTransformer batch size
DB_BATCH = 500  # rows per DB fetch
MIN_LEN = 30   # skip text shorter than this


def encode_batch(model, texts: list[str]) -> list[list[float]]:
    """Batch-encode N texts. Returns N 768-dim vectors."""
    if not texts:
        return []
    embeddings = model.encode(texts, batch_size=BATCH, show_progress_bar=False)
    return [v.tolist() for v in embeddings]


async def backfill_claims(model) -> int:
    """C1: backfill article_claims.embedding."""
    total = 0
    fetched_total = 0
    while True:
        async with get_db() as db:
            rows = (await db.execute(text("""
                SELECT id::text AS cid, claim_text
                  FROM article_claims
                 WHERE embedding IS NULL
                   AND claim_text IS NOT NULL
                   AND LENGTH(claim_text) >= :ml
                 ORDER BY extracted_at DESC NULLS LAST
                 LIMIT :lim
            """), {"ml": MIN_LEN, "lim": DB_BATCH})).mappings().all()
        if not rows:
            break
        fetched_total += len(rows)

        texts = [r["claim_text"][:512] for r in rows]
        vectors = encode_batch(model, texts)

        async with get_db() as db:
            for r, v in zip(rows, vectors):
                # pgvector accepts the vector as a string '[v1,v2,...]'
                v_str = "[" + ",".join(f"{x:.6f}" for x in v) + "]"
                await db.execute(text("""
                    UPDATE article_claims SET embedding = CAST(:v AS vector)
                     WHERE id::text = :id
                """), {"v": v_str, "id": r["cid"]})
            await db.commit()
        total += len(rows)

        if total % (DB_BATCH * 4) == 0:
            log.info("[C1 claims] fetched=%d embedded=%d", fetched_total, total)

    log.info("[C1 DONE] total claims embedded: %d", total)
    return total


async def backfill_articles(model) -> int:
    """C2: backfill articles.labse_embedding."""
    total = 0
    while True:
        async with get_db() as db:
            rows = (await db.execute(text("""
                SELECT id::text AS aid,
                       COALESCE(NULLIF(full_text_translated, ''), full_text_scraped, title) AS txt
                  FROM articles
                 WHERE labse_embedding IS NULL
                   AND substrate_status = 'ok'
                 ORDER BY collected_at DESC NULLS LAST
                 LIMIT :lim
            """), {"lim": DB_BATCH})).mappings().all()
        if not rows:
            break

        texts = [(r["txt"] or "")[:512] for r in rows]
        # Filter out too-short rows so the model doesn't waste time
        good_idx = [i for i, t in enumerate(texts) if len(t) >= MIN_LEN]
        if not good_idx:
            break
        good_texts = [texts[i] for i in good_idx]
        vectors = encode_batch(model, good_texts)

        async with get_db() as db:
            for i, v in zip(good_idx, vectors):
                v_str = "[" + ",".join(f"{x:.6f}" for x in v) + "]"
                await db.execute(text("""
                    UPDATE articles SET labse_embedding = CAST(:v AS vector)
                     WHERE id::text = :id
                """), {"v": v_str, "id": rows[i]["aid"]})
            await db.commit()
        total += len(good_idx)
        if total % (DB_BATCH * 2) == 0:
            log.info("[C2 articles] embedded=%d", total)

    log.info("[C2 DONE] total articles embedded: %d", total)
    return total


async def main() -> int:
    log.info("Loading LaBSE model (cached after first call)...")
    model = get_labse_model()
    log.info("Model ready. Starting C2 (articles, smaller) first.")
    await backfill_articles(model)
    log.info("Starting C1 (claims, ~297K).")
    await backfill_claims(model)
    log.info("ALL DONE")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
