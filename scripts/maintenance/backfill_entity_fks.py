"""Backfill subject_entity_id / speaker_entity_id / actor_entity_id via
PostgreSQL trigram similarity.

Run AFTER migration 078 (needs pg_trgm + gin trgm index on canonical_name).

Idempotent: only touches rows where the FK is currently NULL. Re-running
after dictionary growth picks up newly-resolvable rows.

Usage:
    python scripts/maintenance/backfill_entity_fks.py \\
        --dsn "postgresql://rig:PASSWORD@178.105.63.154:5433/rig" \\
        --threshold 0.85 --batch 5000

Defaults: threshold=0.85 (high precision, fewer false matches),
batch=5000 rows per UPDATE.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from contextlib import closing

import psycopg2  # type: ignore


# Tables we backfill: (table, text_column, fk_column)
TARGETS: list[tuple[str, str, str]] = [
    ("article_claims",  "subject_text",  "subject_entity_id"),
    ("article_quotes",  "speaker_name",  "speaker_entity_id"),
    # article_stances actor_text column was not found in schema probe;
    # add here once confirmed: ("article_stances", "actor_name", "actor_entity_id"),
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--dsn",
        default=os.environ.get("PG_DSN"),
        help="Postgres DSN (or set PG_DSN env var)",
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=0.85,
        help="Trigram similarity threshold (0..1). Higher = more precise, fewer matches.",
    )
    p.add_argument(
        "--batch",
        type=int,
        default=5000,
        help="Rows updated per batch (controls lock duration).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Count matches without applying UPDATEs.",
    )
    return p.parse_args()


def ensure_match_index(conn: "psycopg2.extensions.connection") -> None:
    """Build/refresh a flat (entity_id, match_str) table covering canonical
    names AND aliases. Trigram backfill then matches against this — so
    'Trump' (alias) links to 'Donald Trump' (canonical), 'PM Modi' (alias)
    links to 'Narendra Modi', etc.
    """
    cur = conn.cursor()
    cur.execute("""
        DROP TABLE IF EXISTS entity_match_index;
        CREATE TABLE entity_match_index AS
          SELECT id AS ent_id, canonical_name AS match_str FROM entity_dictionary
          UNION
          SELECT id AS ent_id, UNNEST(aliases) AS match_str FROM entity_dictionary
           WHERE aliases IS NOT NULL AND array_length(aliases, 1) > 0;
        CREATE INDEX entity_match_index_str_trgm_idx
          ON entity_match_index USING gin (match_str gin_trgm_ops);
        CREATE INDEX entity_match_index_ent_idx ON entity_match_index (ent_id);
    """)
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM entity_match_index")
    n = cur.fetchone()[0]
    print(f"[match_index] rebuilt — {n:,} entries (canonical + alias rows)")


def backfill_table(
    conn: "psycopg2.extensions.connection",
    table: str,
    text_col: str,
    fk_col: str,
    threshold: float,
    batch: int,
    dry_run: bool,
) -> None:
    """Backfill one table's FK via trigram match against canonical+aliases.

    Picks the BEST match per source row (DISTINCT ON), filters by threshold.
    Runs in batches limited by ORDER BY id to avoid table-wide UPDATEs.
    """
    cur = conn.cursor()
    cur.execute(f"SET pg_trgm.similarity_threshold = {threshold};")

    # Reject obvious garbage placeholders
    reject = "('article','this','it','they','them','none','unknown','n/a','na')"

    # Quick stats up front
    cur.execute(
        f"""
        SELECT COUNT(*) FROM {table}
         WHERE {fk_col} IS NULL
           AND {text_col} IS NOT NULL
           AND {text_col} != ''
           AND LOWER({text_col}) NOT IN {reject}
        """
    )
    total_unlinked = cur.fetchone()[0]
    print(f"[{table}] unlinked rows eligible: {total_unlinked:,}")

    if total_unlinked == 0:
        return

    total_updated = 0
    start = time.time()
    cur_id: str | None = None  # cursor for batched scan (uuid as text)

    while True:
        cur_filter = f"AND s.id > '{cur_id}'" if cur_id else ""
        sql = f"""
        WITH candidates AS (
            SELECT s.id AS src_id, s.{text_col} AS src_text
              FROM {table} s
             WHERE s.{fk_col} IS NULL
               AND s.{text_col} IS NOT NULL
               AND s.{text_col} != ''
               AND LOWER(s.{text_col}) NOT IN {reject}
               {cur_filter}
             ORDER BY s.id
             LIMIT {batch}
        ),
        best AS (
            SELECT DISTINCT ON (c.src_id)
                   c.src_id,
                   m.ent_id,
                   similarity(c.src_text, m.match_str) AS sim
              FROM candidates c
              JOIN entity_match_index m
                ON m.match_str % c.src_text
             ORDER BY c.src_id, sim DESC
        )
        SELECT src_id::text, ent_id, sim FROM best WHERE sim >= {threshold};
        """
        cur.execute(sql)
        rows = cur.fetchall()
        if not rows:
            # Advance cursor past the empty window
            cur.execute(
                f"""
                SELECT MAX(id_text) FROM (
                  SELECT s.id::text AS id_text FROM {table} s
                   WHERE s.{fk_col} IS NULL
                     AND s.{text_col} IS NOT NULL
                     {cur_filter}
                   ORDER BY s.id LIMIT {batch}
                ) z
                """
            )
            adv = cur.fetchone()
            if adv is None or adv[0] is None:
                break
            cur_id = adv[0]
            continue

        if not dry_run:
            # Apply matches
            for src_id, ent_id, _sim in rows:
                cur.execute(
                    f"UPDATE {table} SET {fk_col} = %s WHERE id = %s AND {fk_col} IS NULL",
                    (ent_id, src_id),
                )
            conn.commit()

        total_updated += len(rows)
        cur_id = rows[-1][0]
        elapsed = time.time() - start
        rate = total_updated / max(elapsed, 1)
        print(
            f"[{table}] updated {total_updated:,} (rate {rate:,.0f}/s, last_id {cur_id[:8]}…)"
        )

    elapsed = time.time() - start
    print(
        f"[{table}] DONE — {total_updated:,} rows linked of {total_unlinked:,} eligible "
        f"in {elapsed:.1f}s"
    )


def main() -> int:
    args = parse_args()
    if not args.dsn:
        print("ERROR: --dsn or PG_DSN required", file=sys.stderr)
        return 2

    with closing(psycopg2.connect(args.dsn)) as conn:
        conn.autocommit = False
        ensure_match_index(conn)
        # Tier 1: trigram match at configured threshold (default 0.85)
        for table, text_col, fk_col in TARGETS:
            backfill_table(
                conn, table, text_col, fk_col,
                threshold=args.threshold,
                batch=args.batch,
                dry_run=args.dry_run,
            )
        # Tier 2: case-sensitive substring with word boundaries
        # (catches "President Bola Tinubu" → "Bola Tinubu",
        #  "US President Donald Trump" → "Donald Trump")
        if not args.dry_run:
            for table, text_col, fk_col in TARGETS:
                backfill_substring(conn, table, text_col, fk_col)
    return 0


def backfill_substring(
    conn: "psycopg2.extensions.connection",
    table: str,
    text_col: str,
    fk_col: str,
) -> None:
    """Tier-2: link remaining NULL FKs by exact word-boundary substring match
    against entity_dictionary CANONICAL names only (not aliases).

    Tightened after the 078-079 quality audit to avoid:
      - Short-name false positives (e.g. alias "Brent" matching "Brent crude")
      - Type mismatches (e.g. "X Public School" → location "X")

    Rules:
      - Match against canonical_name only (not aliases — those are too short)
      - canonical_name ≥ 8 chars
      - canonical_name MUST contain a space (multi-word; rules out lone first
        names like "Modi", "Trump", "Brent")
      - case-sensitive substring with space-padded word boundaries
      - REJECT subjects ending in school/hospital/hotel/university/college/
        institute/foundation/airport/stadium/club/society/association — these
        are organizations we don't have entries for, NOT the location of the
        first word.
      - REJECT matched entity_type='location' when subject ends in any of the
        above org-indicator words (defence in depth — also handled by reject)
      - If multiple matches, pick LONGEST canonical_name (more specific)
    """
    cur = conn.cursor()
    cur.execute(f"SET pg_trgm.similarity_threshold = 0.30;")
    cur.execute(
        f"""
        WITH candidates AS (
          SELECT s.id, s.{text_col}
            FROM {table} s
           WHERE s.{fk_col} IS NULL
             AND s.{text_col} IS NOT NULL
             AND length(s.{text_col}) >= 8
             AND NOT LOWER(s.{text_col}) ~
                 '\\m(school|hospital|hotel|university|college|institute|foundation|airport|stadium|club|society|association|federation|trust|board|committee)\\s*$'
        ),
        matches AS (
          SELECT DISTINCT ON (c.id)
                 c.id  AS src_id,
                 ed.id AS ent_id,
                 length(ed.canonical_name) AS ml
            FROM candidates c
            JOIN entity_dictionary ed
              ON ed.canonical_name % c.{text_col}
             AND length(ed.canonical_name) >= 8
             AND position(' ' in ed.canonical_name) > 0   -- multi-word only
             AND ed.canonical_name ~ '[A-Z]'              -- entity-like
             AND (' ' || c.{text_col} || ' ') LIKE
                 ('% ' || ed.canonical_name || ' %')
           ORDER BY c.id, ml DESC
        )
        UPDATE {table} t
           SET {fk_col} = matches.ent_id
          FROM matches
         WHERE t.id = matches.src_id
           AND t.{fk_col} IS NULL
        """
    )
    affected = cur.rowcount
    conn.commit()
    print(f"[{table}] substring tier-2 (tightened) linked {affected:,} rows")


if __name__ == "__main__":
    sys.exit(main())
