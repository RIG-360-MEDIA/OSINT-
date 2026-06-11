"""Apply migration 074 (location_scope derive) in deadlock-safe batches.

Why: the naive single-statement UPDATE deadlocked with sync_geo_primary trigger
which writes back to articles (contended with D1 catch-up). Batching keeps each
transaction short enough that deadlocks resolve naturally on retry.

Runs inside rig-postgres container via psql calls.
"""
from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass


def psql(sql: str, *, capture: bool = True) -> str:
    """Execute SQL via psql, return stdout."""
    args = ["psql", "-U", "rig", "-d", "rig", "-tAc", sql]
    result = subprocess.run(args, capture_output=capture, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"psql failed: {result.stderr}")
    return result.stdout.strip()


@dataclass
class BatchStats:
    total: int
    batches_run: int
    rows_updated: int
    elapsed_s: float


def setup_objects() -> None:
    """Create function, scope trigger, and backup table. Idempotent."""
    psql("""
        CREATE TABLE IF NOT EXISTS article_locations_scope_backup_20260528 AS
        SELECT id, location_scope FROM article_locations WHERE 1=0;
    """)
    # Only insert backup rows that aren't already there
    psql("""
        INSERT INTO article_locations_scope_backup_20260528 (id, location_scope)
        SELECT l.id, l.location_scope FROM article_locations l
         LEFT JOIN article_locations_scope_backup_20260528 b ON b.id = l.id
         WHERE b.id IS NULL;
    """)

    psql("""
        CREATE OR REPLACE FUNCTION compute_location_scope(
          p_location_text text, p_country text, p_region text, p_city text
        ) RETURNS text AS $f$
        DECLARE v_norm text;
        BEGIN
          v_norm := LOWER(TRIM(COALESCE(p_location_text, '')));
          IF v_norm IN (
            'africa','asia','europe','north america','south america',
            'oceania','antarctica','eurasia','middle east'
          ) THEN RETURN 'continent'; END IF;
          IF p_city    IS NOT NULL AND TRIM(p_city)    != '' THEN RETURN 'city';    END IF;
          IF p_region  IS NOT NULL AND TRIM(p_region)  != '' THEN RETURN 'state';   END IF;
          IF p_country IS NOT NULL AND TRIM(p_country) != '' THEN RETURN 'country'; END IF;
          RETURN 'unknown';
        END;
        $f$ LANGUAGE plpgsql IMMUTABLE;
    """)

    psql("""
        CREATE OR REPLACE FUNCTION trg_set_location_scope() RETURNS trigger AS $f$
        BEGIN
          NEW.location_scope := compute_location_scope(
            NEW.location_text, NEW.country, NEW.region, NEW.city
          );
          RETURN NEW;
        END;
        $f$ LANGUAGE plpgsql;
    """)

    psql("DROP TRIGGER IF EXISTS trg_article_locations_scope ON article_locations;")
    psql("""
        CREATE TRIGGER trg_article_locations_scope
          BEFORE INSERT OR UPDATE OF location_text, country, region, city
          ON article_locations
          FOR EACH ROW EXECUTE FUNCTION trg_set_location_scope();
    """)


def run_batched_backfill(batch_size: int = 5000) -> BatchStats:
    """Update location_scope in batches to avoid deadlock with geo_primary trigger."""
    total = int(psql("SELECT COUNT(*) FROM article_locations;"))
    start = time.monotonic()

    batches = 0
    rows = 0
    while True:
        # Update one batch — only rows whose computed scope differs from stored
        n_str = psql(f"""
            WITH batch AS (
              SELECT id FROM article_locations
               WHERE location_scope IS DISTINCT FROM compute_location_scope(
                 location_text, country, region, city
               )
               LIMIT {batch_size}
               FOR UPDATE SKIP LOCKED
            )
            UPDATE article_locations l
               SET location_scope = compute_location_scope(
                 l.location_text, l.country, l.region, l.city
               )
              FROM batch
             WHERE l.id = batch.id;
        """)
        # psql returns "UPDATE n" but with -tAc we get empty for non-SELECT
        # Re-query count of remaining mismatches
        remaining = int(psql("""
            SELECT COUNT(*) FROM article_locations
             WHERE location_scope IS DISTINCT FROM compute_location_scope(
               location_text, country, region, city
             );
        """))
        batches += 1
        rows = total - remaining
        elapsed = time.monotonic() - start
        rate = rows / elapsed if elapsed > 0 else 0
        print(f"  batch {batches:3d} | updated={rows:>7d}/{total} | remaining={remaining:>6d} | {rate:>6.0f} rows/s")
        if remaining == 0:
            break
        if batches > 200:
            print("WARN: hit batch ceiling, stopping")
            break
        # tiny pause to let geo_primary trigger drain
        time.sleep(0.1)

    return BatchStats(total=total, batches_run=batches, rows_updated=rows,
                      elapsed_s=time.monotonic() - start)


def main() -> int:
    print("=== Setup function + trigger + backup ===")
    setup_objects()
    print("  done\n")

    print("=== Verify pre-state ===")
    print(psql("""
        SELECT location_scope || ': ' || COUNT(*)::text
          FROM article_locations
         GROUP BY 1 ORDER BY 2 DESC LIMIT 8;
    """))

    print("\n=== Run batched backfill ===")
    stats = run_batched_backfill(batch_size=5000)
    print(f"\n  total={stats.total} rows_updated={stats.rows_updated} batches={stats.batches_run} time={stats.elapsed_s:.1f}s")

    print("\n=== Post-state ===")
    print(psql("""
        SELECT location_scope || ': ' || COUNT(*)::text
          FROM article_locations
         GROUP BY 1 ORDER BY 2 DESC LIMIT 10;
    """))

    print("\n=== Sample rows (verify correctness) ===")
    print(psql("""
        SELECT location_text || ' | ' || COALESCE(city,'')
            || ' | ' || COALESCE(region,'') || ' | ' || COALESCE(country,'')
            || ' | scope=' || location_scope
          FROM article_locations
         ORDER BY random() LIMIT 12;
    """))

    return 0


if __name__ == "__main__":
    sys.exit(main())
