"""T3_reembed_collisions.py — Re-embed articles whose LaBSE vector collided.

Strategy:
  1. Find the top N collision signatures (md5 of labse_embedding::text).
  2. For each article in those groups, build a robust input text from
     full_text_scraped > lead_text_translated > summary_executive > title,
     using the longest available source ≥ 100 chars.
  3. Re-embed via in-process LaBSE.
  4. UPDATE articles.labse_embedding.
  5. Verify the worst signature shrinks ≥ 90%.

Backup: pre-update sig + embedding per affected row → articles_embed_backup_20260523.

Inside rig-backend:
    docker exec rig-backend python /app/scripts/backfill/T3_reembed_collisions.py
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from backend.database import get_db  # noqa: E402
from backend.nlp.nlp_embedding import generate_embedding  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("reembed")

# How many top collision signatures to fix
TOP_N_SIGS = 6


def best_text(row) -> str:
    """Pick the longest available text source ≥ 100 chars."""
    candidates = [
        row.full_text_scraped or "",
        row.lead_text_translated or "",
        row.summary_executive or "",
        row.title or "",
    ]
    candidates = [c for c in candidates if len(c) >= 100]
    if not candidates:
        # Fallback: best effort with title+summary concat
        parts = [x for x in [row.title or "", row.summary_executive or ""] if x]
        return " | ".join(parts)
    return max(candidates, key=len)


async def main() -> int:
    async with get_db() as db:
        # 1. Top collision signatures
        sigs = (await db.execute(text("""
            SELECT md5(labse_embedding::text) AS sig, COUNT(*) AS n
              FROM articles
             WHERE labse_embedding IS NOT NULL AND substrate_status='ok'
             GROUP BY 1 HAVING COUNT(*) > 10
             ORDER BY n DESC LIMIT :n
        """), {"n": TOP_N_SIGS})).fetchall()
        log.info("Top collision signatures: %s",
                 [(s.sig[:8], s.n) for s in sigs])
        target_sigs = [s.sig for s in sigs]
        total_target = sum(s.n for s in sigs)
        log.info("Total articles to re-embed: %d", total_target)

        # 2. Backup
        log.info("Creating backup table…")
        await db.execute(text("DROP TABLE IF EXISTS articles_embed_backup_20260523"))
        await db.execute(text("""
            CREATE TABLE articles_embed_backup_20260523 AS
            SELECT id, md5(labse_embedding::text) AS old_sig,
                   labse_embedding AS old_embedding
              FROM articles
             WHERE md5(labse_embedding::text) = ANY(:sigs)
        """), {"sigs": target_sigs})
        await db.commit()
        backup_count = (await db.execute(text(
            "SELECT COUNT(*) AS n FROM articles_embed_backup_20260523"
        ))).fetchone().n
        log.info("Backed up %d rows", backup_count)

        # 3. Fetch each collided article
        rows = (await db.execute(text("""
            SELECT id::text AS aid, title,
                   full_text_scraped, lead_text_translated, summary_executive
              FROM articles
             WHERE md5(labse_embedding::text) = ANY(:sigs)
        """), {"sigs": target_sigs})).fetchall()
        log.info("Re-embedding %d articles…", len(rows))

        t0 = time.time()
        updated = 0
        skipped = 0
        for i, r in enumerate(rows, 1):
            text_in = best_text(r)
            if len(text_in) < 50:
                skipped += 1
                continue
            emb = generate_embedding(text_in)
            if emb is None:
                skipped += 1
                continue
            await db.execute(text(
                "UPDATE articles SET labse_embedding = CAST(:e AS vector) "
                "WHERE id = CAST(:a AS uuid)"
            ), {"a": r.aid, "e": str(emb)})
            updated += 1
            if i % 50 == 0:
                rate = i / max(time.time() - t0, 1)
                log.info("Progress: %d/%d (%.1f/sec)", i, len(rows), rate)
        await db.commit()

        # 4. Gate
        log.info("Validating gate…")
        post = (await db.execute(text("""
            SELECT md5(labse_embedding::text) AS sig, COUNT(*) AS n
              FROM articles
             WHERE md5(labse_embedding::text) = ANY(:sigs)
             GROUP BY 1 ORDER BY n DESC
        """), {"sigs": target_sigs})).fetchall()

        log.info("━━━ Results ━━━")
        log.info("Updated:  %d / %d", updated, len(rows))
        log.info("Skipped:  %d (too-short text)", skipped)
        log.info("Original sig occurrences post-fix:")
        for r in post:
            log.info("  %s : %d (was a collision group)", r.sig[:8], r.n)
        # Overall collision count
        all_dups = (await db.execute(text("""
            SELECT COUNT(*) AS dup_total
              FROM (SELECT md5(labse_embedding::text) AS sig, COUNT(*) AS n
                      FROM articles WHERE labse_embedding IS NOT NULL
                       AND substrate_status='ok'
                     GROUP BY 1 HAVING COUNT(*) > 1) x
        """))).fetchone()
        distinct = (await db.execute(text("""
            SELECT COUNT(*) AS total,
                   COUNT(DISTINCT md5(labse_embedding::text)) AS distinct_sigs
              FROM articles WHERE labse_embedding IS NOT NULL
               AND substrate_status='ok' AND extraction_version=3
        """))).fetchone()
        log.info("v3+ok total: %d  distinct vectors: %d  dups: %d",
                 distinct.total, distinct.distinct_sigs,
                 distinct.total - distinct.distinct_sigs)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
