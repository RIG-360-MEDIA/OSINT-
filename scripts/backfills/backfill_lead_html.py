"""Strip HTML from articles.lead_text_original -- batched, resumable, detached.

Run INSIDE rig-backend (it bind-mounts /root/rig/backend -> /app/backend), so
this imports the very same backend.collectors.text_clean.strip_html_lead that
cleans rows on the way in. That is the point: history and new rows are cleaned
by one implementation, so they cannot drift.

    An earlier draft did the cleaning in SQL instead. It was rejected: a
    hand-listed entity table in Postgres decoded only the entities someone
    thought to add, and turned the rest into spaces. Measured against the Python
    cleaner on 3,000 real rows it disagreed on 433 of them (14%) -- "dell'assalto"
    came out as "dell assalto". Python's html.unescape knows the whole HTML5
    entity table; reproducing it in SQL is whack-a-mole that silently rots.

WHY THIS SHAPE (2026-07-16 incident, KB 01-rig-surveillance-backend/issues.md#I-20):
an unbatched whole-table UPDATE on `articles` row-locks it; collectors upsert via
INSERT .. ON CONFLICT (url_hash) DO UPDATE, so they block behind those locks, the
single-concurrency collectors worker wedges, and ingestion stops. That cost 12h.
Hence: small batches, one transaction each, committed immediately; SKIP LOCKED so
we never wait on a row a collector holds; a sleep between batches so collectors
always get a turn; detached, because a dropped SSH must not orphan a blocked
statement; and the backup table doubles as the worklist, so this is resumable and
never re-scans `articles` to find work.

Usage (from the box):
    docker exec -d rig-backend python /app/scripts/backfills/backfill_lead_html.py
Watch:
    docker exec rig-backend tail -f /tmp/backfill_lead_html_20260717.log
"""
from __future__ import annotations

import logging
import os
import sys
import time

sys.path.insert(0, "/app")

import psycopg2
from psycopg2.extras import execute_values

from backend.collectors.text_clean import strip_html_lead

# Overridable so a small worklist can be rehearsed end-to-end before the real
# 209k-row run. The default is the real one.
TAG = os.environ.get("BACKFILL_TAG", "20260717")
BACKUP = f"analytics.lead_orig_html_backup_{TAG}"
LOG_PATH = f"/tmp/backfill_lead_html_{TAG}.log"
BATCH = 2000
SLEEP = 0.25
MAX_STALL = 20
DIRTY_RE = r"<[a-zA-Z/]"
RECOVER_CHARS = 300

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("backfill")


def connect():
    dsn = os.environ.get("DATABASE_URL_SYNC")
    if not dsn:
        raise SystemExit("DATABASE_URL_SYNC not set")
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    return conn


def build_worklist(conn) -> None:
    """Create the backup/worklist once. CREATE TABLE AS takes only ACCESS SHARE
    on articles, so it does not block the collectors' upserts."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s) IS NOT NULL", (BACKUP,))
        if cur.fetchone()[0]:
            log.info("worklist %s exists -- resuming", BACKUP)
        else:
            log.info("building worklist/backup %s ...", BACKUP)
            cur.execute(
                f"CREATE TABLE {BACKUP} AS "
                f"SELECT id, lead_text_original AS old_lead, "
                f"       NULL::timestamptz AS cleaned_at, "
                f"       NULL::timestamptz AS recovered_at "
                f"  FROM articles WHERE lead_text_original ~ %s",
                (DIRTY_RE,),
            )
            cur.execute(f"ALTER TABLE {BACKUP} ADD PRIMARY KEY (id)")
            cur.execute(
                f"CREATE INDEX ON {BACKUP} (id) WHERE cleaned_at IS NULL"
            )
            conn.commit()
            cur.execute(f"SELECT count(*) FROM {BACKUP}")
            log.info("worklist rows: %s", cur.fetchone()[0])

        # A worklist row whose article no longer exists can never be locked and
        # would stall the loop forever. Retire those up front.
        cur.execute(
            f"UPDATE {BACKUP} b SET cleaned_at = now() "
            f" WHERE b.cleaned_at IS NULL "
            f"   AND NOT EXISTS (SELECT 1 FROM articles a WHERE a.id = b.id)"
        )
        log.info("retired %s orphaned worklist rows", cur.rowcount)
        conn.commit()


def phase1(conn) -> None:
    """Strip markup from every dirty lead."""
    stall = 0
    total_cleaned = total_seen = 0
    while True:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT a.id, a.lead_text_original "
                f"  FROM articles a JOIN {BACKUP} b ON b.id = a.id "
                f" WHERE b.cleaned_at IS NULL "
                f" ORDER BY a.id LIMIT %s "
                f" FOR UPDATE OF a SKIP LOCKED",
                (BATCH,),
            )
            rows = cur.fetchall()

            if not rows:
                conn.rollback()
                with conn.cursor() as c2:
                    c2.execute(f"SELECT count(*) FROM {BACKUP} WHERE cleaned_at IS NULL")
                    remaining = c2.fetchone()[0]
                conn.commit()
                if remaining == 0:
                    log.info("phase 1 complete: %s updated / %s seen", total_cleaned, total_seen)
                    return
                stall += 1
                log.info("no progress (remaining=%s, stall=%s/%s) -- rows locked, backing off",
                         remaining, stall, MAX_STALL)
                if stall >= MAX_STALL:
                    raise SystemExit(f"stalled with {remaining} rows locked -- stopping")
                time.sleep(5)
                continue

            stall = 0
            # max_chars=None: only strip markup here. Re-slicing historical rows
            # would change data beyond the defect we are fixing, and the API caps
            # length on read anyway (v1 serializers._SUMMARY_MAX).
            changed = []
            for rid, raw in rows:
                clean = strip_html_lead(raw, max_chars=None)
                if clean != raw:  # skip no-ops: an identical write is a dead tuple
                    changed.append((str(rid), clean))

            if changed:
                execute_values(
                    cur,
                    # ::text is required, not cosmetic: if a batch's first row
                    # cleans to NULL, VALUES types the column `unknown` and the
                    # UPDATE errors out.
                    "UPDATE articles a SET lead_text_original = v.clean::text "
                    "  FROM (VALUES %s) AS v(id, clean) "
                    " WHERE a.id = v.id::uuid",
                    changed,
                )
            # ::uuid[] -- psycopg2 sends the list as text[], and Postgres has no
            # uuid = text operator.
            cur.execute(
                f"UPDATE {BACKUP} SET cleaned_at = now() WHERE id = ANY(%s::uuid[])",
                ([str(rid) for rid, _ in rows],),
            )
            conn.commit()

            total_seen += len(rows)
            total_cleaned += len(changed)
            log.info("batch: %s locked, %s updated (cumulative %s/%s)",
                     len(rows), len(changed), total_cleaned, total_seen)
        time.sleep(SLEEP)


def phase2(conn) -> None:
    """Recover leads that cleaned away to nothing.

    Those rows were pure markup -- a bare <img> thumbnail or an <a href> with no
    text -- so there was never a lead to preserve. Where we scraped a body, take
    a lead from it; otherwise leave NULL, which is honest, and still better than
    shipping a raw <img src=...> to the client as `summary_original`.
    """
    log.info("phase 2: recovering NULLed leads from full_text_scraped")
    recovered = 0
    while True:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT a.id, a.full_text_scraped "
                f"  FROM articles a JOIN {BACKUP} b ON b.id = a.id "
                f" WHERE a.lead_text_original IS NULL "
                f"   AND a.full_text_scraped IS NOT NULL AND a.full_text_scraped <> '' "
                f"   AND b.recovered_at IS NULL "
                f" ORDER BY a.id LIMIT %s "
                f" FOR UPDATE OF a SKIP LOCKED",
                (BATCH,),
            )
            rows = cur.fetchall()
            if not rows:
                conn.commit()
                log.info("phase 2 complete: %s leads recovered", recovered)
                return

            vals = []
            for rid, body in rows:
                clean = strip_html_lead(body, max_chars=RECOVER_CHARS)
                if clean:
                    vals.append((str(rid), clean))
            if vals:
                execute_values(
                    cur,
                    "UPDATE articles a SET lead_text_original = v.clean "
                    "  FROM (VALUES %s) AS v(id, clean) "
                    " WHERE a.id = v.id::uuid AND a.lead_text_original IS NULL",
                    vals,
                )
            # Mark EVERY row we looked at, not just the ones we filled. A row
            # whose body also cleans to nothing stays NULL; without this marker
            # it would be re-selected forever.
            cur.execute(
                f"UPDATE {BACKUP} SET recovered_at = now() WHERE id = ANY(%s::uuid[])",
                ([str(rid) for rid, _ in rows],),
            )
            conn.commit()
            recovered += len(vals)
            log.info("phase 2 batch: %s looked at, %s recovered (cumulative %s)",
                     len(rows), len(vals), recovered)
        time.sleep(SLEEP)


def main() -> None:
    log.info("=== backfill start (batch=%s) ===", BATCH)
    conn = connect()
    try:
        build_worklist(conn)
        with conn.cursor() as cur:
            cur.execute(
                f"ALTER TABLE {BACKUP} ADD COLUMN IF NOT EXISTS recovered_at timestamptz"
            )
            conn.commit()
        phase1(conn)
        phase2(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM articles WHERE lead_text_original ~ %s",
                        (DIRTY_RE,))
            log.info("remaining dirty rows in articles: %s", cur.fetchone()[0])
        log.info("backup retained at %s (id, old_lead) -- drop only after verification", BACKUP)
        log.info("=== DONE ===")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
