#!/usr/bin/env python3
"""
swap_v4_inplace.py — Phase 0c atomic swap: make the LOCKED V4 vectors the live
``articles.labse_embedding``, IN PLACE (no column rename).

WHY IN-PLACE (not a column rename swap)
---------------------------------------
Four DB objects reference the ``labse_embedding`` column by name:
``v_freshness_now`` / ``v_freshness_fresh_window`` / ``v_freshness_coverage_by_age``
and ``analytics.worldwide_candidates`` (the cross-product view the analytics chat
reads). Postgres views bind columns by *attribute number*, so a column RENAME would
make every one of them silently follow to the renamed (OLD) column and keep reading
the pre-swap vectors — a correctness bug that would poison the re-baseline.
Overwriting the column in place keeps every view, application query, and index
transparently correct.

SAFETY
------
* Old vectors are copied to ``labse_embedding_v0_backup`` BEFORE any overwrite
  (recoverable until the analytics re-baseline; the V0 recipe is also
  deterministically re-runnable, so this is belt-and-braces).
* COALESCE semantics: the freshest ~3.4K rows that have no V4 vector yet
  (not-yet-translated) KEEP their existing vector — they are never nulled.
* Batched + resumable: every phase has an idempotent ``WHERE`` predicate and
  ``FOR UPDATE SKIP LOCKED`` short per-batch locks, so live collector / NLP writes
  are never blocked and the job can be killed and rerun at any point.
* The HNSW self-maintains during the update (NO unavailability window), then
  ``REINDEX INDEX CONCURRENTLY`` rebuilds it cleanly while the old index keeps
  serving — so semantic-dedup never loses its index.
* Provenance: ``embedding_revision`` is stamped in the SAME statement that swaps the
  vector, so swap+stamp are atomic per row and resumability is a cheap TEXT compare
  (no vector-equality dependency).

Env: AB_DSN / DATABASE_URL_SYNC / DATABASE_URL · S_BATCH (5000) · REV (v4-tr-title-1024)
"""
from __future__ import annotations

import logging
import os
import sys
import time

import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("swap")

BATCH: int = int(os.environ.get("S_BATCH", "5000"))
REV: str = os.environ.get("REV", "v4-tr-title-1024")
MODEL: str = "sentence-transformers/LaBSE"
STALL_LIMIT: int = 30  # consecutive all-locked batches before giving up (rerun finishes)


def connect() -> "psycopg2.extensions.connection":
    dsn = (
        os.environ.get("AB_DSN")
        or os.environ.get("DATABASE_URL_SYNC")
        or os.environ.get("DATABASE_URL")
    )
    if not dsn:
        raise SystemExit("no DSN in AB_DSN / DATABASE_URL_SYNC / DATABASE_URL")
    return psycopg2.connect(dsn)


def batched(conn, label: str, count_sql: str, count_params: tuple,
            upd_sql: str, upd_params: tuple) -> int:
    """Run ``upd_sql`` in batches until ``count_sql`` reports 0 remaining.

    Each batch is its own short transaction (commit-per-batch) so locks held against
    live writers are momentary. Returns the total number of rows updated.
    """
    cur = conn.cursor()
    cur.execute(count_sql, count_params)
    start_rem = cur.fetchone()[0]
    conn.commit()
    log.info("phase %s: %d rows to process", label, start_rem)

    total = 0
    stalls = 0
    while True:
        cur = conn.cursor()
        cur.execute(upd_sql, upd_params)
        n = cur.rowcount
        conn.commit()
        if n and n > 0:
            total += n
            stalls = 0
            if (total // BATCH) % 4 == 0:
                log.info("  %s: %d / %d", label, total, start_rem)
            continue
        # A zero-row batch means either done, or every remaining row is locked.
        cur.execute(count_sql, count_params)
        rem = cur.fetchone()[0]
        conn.commit()
        if rem == 0:
            break
        stalls += 1
        if stalls > STALL_LIMIT:
            log.warning("  %s: %d rows still locked — leaving for a rerun", label, rem)
            break
        time.sleep(2)
    log.info("phase %s: COMPLETE (%d updated)", label, total)
    return total


def reindex_and_vacuum(conn) -> None:
    """REINDEX CONCURRENTLY (no availability window) then VACUUM ANALYZE.

    Both must run outside a transaction block, hence autocommit. A CONCURRENTLY
    failure leaves the ORIGINAL index valid + an ``_ccnew`` invalid leftover; we log
    and continue so the swap itself is never blocked by index housekeeping.
    """
    conn.autocommit = True
    cur = conn.cursor()
    try:
        log.info("phase REINDEX: rebuilding idx_articles_embedding CONCURRENTLY ...")
        cur.execute("REINDEX INDEX CONCURRENTLY idx_articles_embedding")
        log.info("phase REINDEX: done")
    except Exception as exc:  # noqa: BLE001
        log.warning("REINDEX failed (original index still valid): %s", str(exc)[:160])
    try:
        log.info("phase VACUUM: VACUUM (ANALYZE) articles ...")
        cur.execute("VACUUM (ANALYZE) articles")
        log.info("phase VACUUM: done")
    except Exception as exc:  # noqa: BLE001
        log.warning("VACUUM failed: %s", str(exc)[:160])
    conn.autocommit = False


def verify(conn) -> None:
    cur = conn.cursor()
    cur.execute(
        "SELECT count(*) FILTER (WHERE labse_embedding_v0_backup IS NOT NULL), "
        "       count(*) FILTER (WHERE embedding_revision = %s), "
        "       count(*) FILTER (WHERE labse_embedding_v4 IS NOT NULL "
        "                        AND embedding_revision IS DISTINCT FROM %s), "
        "       count(*) "
        "FROM articles",
        (REV, REV),
    )
    backup_n, stamped, not_swapped, total = cur.fetchone()
    cur.execute("SELECT indisvalid, indisready FROM pg_index "
                "WHERE indexrelid = 'idx_articles_embedding'::regclass")
    row = cur.fetchone()
    conn.commit()
    log.info("VERIFY: backup=%d | swapped+stamped=%d | v4-not-swapped(should be 0)=%d "
             "| total=%d | hnsw valid=%s ready=%s",
             backup_n, stamped, not_swapped, total, row[0], row[1])
    log.info("SWAP DONE")


def main() -> int:
    log.info("swap start: batch=%d rev=%s", BATCH, REV)
    conn = connect()
    conn.autocommit = False

    # Phase A — add the recoverable backup column (idempotent).
    cur = conn.cursor()
    cur.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS "
                "labse_embedding_v0_backup vector(768)")
    conn.commit()
    log.info("phase A: backup column ready")

    # Phase B — preserve OLD vectors before anything is overwritten.
    batched(
        conn, "B/backup-old",
        "SELECT count(*) FROM articles "
        "WHERE labse_embedding_v0_backup IS NULL AND labse_embedding IS NOT NULL",
        (),
        "WITH b AS (SELECT id FROM articles "
        "  WHERE labse_embedding_v0_backup IS NULL AND labse_embedding IS NOT NULL "
        "  LIMIT %s FOR UPDATE SKIP LOCKED) "
        "UPDATE articles a SET labse_embedding_v0_backup = a.labse_embedding "
        "FROM b WHERE a.id = b.id",
        (BATCH,),
    )

    # Phase C — atomic per-row swap + provenance stamp (TEXT-resumable).
    batched(
        conn, "C/swap+stamp",
        "SELECT count(*) FROM articles "
        "WHERE labse_embedding_v4 IS NOT NULL AND embedding_revision IS DISTINCT FROM %s",
        (REV,),
        "WITH b AS (SELECT id FROM articles "
        "  WHERE labse_embedding_v4 IS NOT NULL AND embedding_revision IS DISTINCT FROM %s "
        "  LIMIT %s FOR UPDATE SKIP LOCKED) "
        "UPDATE articles a "
        "   SET labse_embedding = a.labse_embedding_v4, "
        "       embedding_revision = %s, "
        "       embedding_model = %s "
        "FROM b WHERE a.id = b.id",
        (REV, BATCH, REV, MODEL),
    )

    # Phase REINDEX + VACUUM — clean the HNSW dead entries with no window.
    reindex_and_vacuum(conn)

    # Final verification.
    verify(conn)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
