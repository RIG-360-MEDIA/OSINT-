#!/usr/bin/env python3
"""leiden_knee.py — Leiden-resolution knee finder for a window clustering CSV.

For known real-event ANCHORS (keyword-defined) measures how each sits in the clustering:
  cohesion = anchor articles in its LARGEST cluster / all anchor articles in the window
  purity   = anchor articles in that cluster / that cluster's TOTAL size
  spread   = number of clusters holding >=3 of the anchor's articles
Run across a resolution sweep to read the knee:
  - a MIXED community (real event fused with unrelated news) has LOW purity at coarse
    resolution and RISING purity as finer resolution splits it out — the mixed-community
    recall cost being fixed (clean cluster -> high entity-core -> §2b spares it -> surfaces).
  - a CLEAN real event has HIGH cohesion until resolution is too fine and it FRAGMENTS
    (cohesion falls, spread climbs) — over-splitting.
Knee = finest resolution where mixed anchors have separated (purity up) but clean anchors
have NOT fragmented (cohesion still high). Read-only (TEMP tables).

Env: AB_DSN/DATABASE_URL_SYNC · IN (window CSV)
"""
from __future__ import annotations

import os
import sys

import psycopg2

IN = os.environ.get("IN", "/tmp/win_new_leiden.csv")
ANCHORS = {
    "IPL-final": r"\m(ipl|rcb|royal challengers|gujarat titans)\M",
    "PSG-UCL": r"\m(psg|paris saint-germain|champions league)\M",
    "Iran-US": r"\m(iran|tehran|hormuz)\M",
    "Ebola-DRC": r"\m(ebola)\M",
    "RBI-rupee": r"\m(rbi|reserve bank|rupee)\M",
    "PSC-results": r"\m(q4 results|net profit|quarterly results)\M",
}


def main() -> int:
    dsn = os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC") or os.environ.get("DATABASE_URL")
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute("CREATE TEMP TABLE _wc(article_id uuid, cluster_id text, source_id text)")
    with open(IN) as f:
        cur.copy_expert("COPY _wc FROM STDIN WITH (FORMAT csv, HEADER true)", f)
    cur.execute("CREATE INDEX ON _wc(cluster_id)")
    cur.execute("CREATE TEMP TABLE _sz AS SELECT cluster_id, count(*) n FROM _wc GROUP BY 1")
    cur.execute("CREATE INDEX ON _sz(cluster_id)")
    print(f"IN={IN}")
    print(f"  {'anchor':12s} {'total':>5s} {'topCluSz':>8s} {'topAnc':>6s} {'cohesion':>8s} {'purity':>6s} {'spread':>6s}")
    for name, pat in ANCHORS.items():
        cur.execute(
            """
            WITH anc AS (
              SELECT w.cluster_id FROM _wc w JOIN articles a ON a.id = w.article_id
              WHERE a.title ~* %s
            ), dist AS (SELECT cluster_id, count(*) ac FROM anc GROUP BY 1)
            SELECT (SELECT count(*) FROM anc) total,
                   (SELECT max(ac) FROM dist) top_anc,
                   (SELECT cluster_id FROM dist ORDER BY ac DESC, cluster_id LIMIT 1) top_cid,
                   (SELECT count(*) FROM dist WHERE ac >= 3) spread
            """,
            (pat,),
        )
        total, top_anc, top_cid, spread = cur.fetchone()
        if not total:
            print(f"  {name:12s} {0:5d}  (no matches)")
            continue
        cur.execute("SELECT n FROM _sz WHERE cluster_id = %s", (top_cid,))
        top_sz = cur.fetchone()[0]
        cohes, purity = (top_anc or 0) / total, (top_anc or 0) / max(top_sz, 1)
        print(f"  {name:12s} {total:5d} {top_sz:8d} {top_anc:6d} {cohes:8.2f} {purity:6.2f} {spread:6d}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
