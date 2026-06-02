#!/usr/bin/env python3
"""validate_loader.py — acceptance checks for the story loader (spec §7).
§7.1 partition preserved (CSV cluster_id <-> DB story_id is a bijection over the window);
§7.5 old tables untouched; + a top-stories sanity sample. Read-only on the DB."""
from __future__ import annotations

import os
import sys

import psycopg2

MEMBERS = os.environ.get("MEMBERS", "/tmp/win_members.csv")
EC_BASE = int(os.environ.get("EC_BASE", "6859"))
ST_BASE = int(os.environ.get("ST_BASE", "7409"))


def main() -> int:
    dsn = (os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC")
           or os.environ.get("DATABASE_URL"))
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute("CREATE TEMP TABLE _c(article_id uuid, cluster_id uuid, source_id uuid)")
    with open(MEMBERS) as f:
        cur.copy_expert("COPY _c FROM STDIN WITH (FORMAT csv, HEADER true)", f)

    cur.execute("""
        SELECT count(DISTINCT c.cluster_id) csv_clusters,
               count(DISTINCT m.story_id) db_stories,
               count(DISTINCT (c.cluster_id::text || '|' || m.story_id::text)) pairs,
               count(*) FILTER (WHERE m.story_id IS NULL) unmapped
        FROM _c c LEFT JOIN analytics.story_cluster_members m ON m.article_id = c.article_id
    """)
    csvc, dbs, pairs, unmapped = cur.fetchone()
    ok = (csvc == dbs == pairs) and unmapped == 0
    print(f"[7.1 partition] csv_clusters={csvc}  db_stories={dbs}  distinct_pairs={pairs}  "
          f"unmapped_articles={unmapped}  ->  {'PARTITION PRESERVED (bijection)' if ok else 'MISMATCH!'}")

    cur.execute("SELECT (SELECT count(*) FROM public.event_clusters), (SELECT count(*) FROM public.story_threads)")
    ec, st = cur.fetchone()
    print(f"[7.5 untouched] event_clusters={ec} (base {EC_BASE})  story_threads={st} (base {ST_BASE})  ->  "
          f"{'OK untouched' if ec == EC_BASE and st == ST_BASE else 'CHANGED!'}")

    cur.execute("""SELECT count(*) FILTER (WHERE is_canonical), count(*) FILTER (WHERE is_representative),
                          count(DISTINCT story_id) FROM analytics.story_cluster_members""")
    canon, reps, stories_with_members = cur.fetchone()
    print(f"[members] canonical={canon}  representatives={reps}  stories_with_members={stories_with_members}")

    cur.execute("""SELECT independent_source_count, article_count, source_count,
                          coalesce(subject_region,'-'), left(representative_title,58)
                   FROM analytics.story_clusters
                   ORDER BY independent_source_count DESC NULLS LAST, article_count DESC LIMIT 8""")
    print("[sample] top stories by independent_source_count:")
    for i, (ind, ac, sc, reg, rt) in enumerate(cur.fetchall(), 1):
        print(f"  {i}. indep={ind} art={ac} src={sc} [{reg}] {rt}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
