#!/usr/bin/env python3
"""compare_xs.py — A/B the cross-source template guard by ranking each partition's
multi-article clusters by independent-source count (= min(distinct outlets, unique bodies)).
The guard works if the cross-source TEMPLATE blobs (per-stock Share Price, cross-company Q4)
drop out / shrink v1.1 -> v2 while REAL high-source events (Iran, Ebola, PSG) stay put.
Read-only on articles."""
from __future__ import annotations

import os
import re
import sys
from collections import defaultdict

import psycopg2


def norm(t):
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", (t or "").lower()).split())[:120]


def analyze(cur, csv, tag):
    cur.execute("DROP TABLE IF EXISTS _x")
    cur.execute("CREATE TEMP TABLE _x(article_id uuid, cluster_id uuid, source_id uuid)")
    with open(csv) as f:
        cur.copy_expert("COPY _x FROM STDIN WITH (FORMAT csv, HEADER true)", f)
    cur.execute("""
        SELECT x.cluster_id, x.source_id, a.title, coalesce(a.language_detected,'?'),
               left(a.lead_text_original, 200)
        FROM _x x JOIN articles a ON a.id = x.article_id
        WHERE x.cluster_id IN (SELECT cluster_id FROM _x GROUP BY 1 HAVING count(*) > 1)
    """)
    cl = defaultdict(lambda: {"src": set(), "titles": [], "keys": set()})
    for cid, sid, title, lang, lead in cur:
        d = cl[str(cid)]
        if sid:
            d["src"].add(str(sid))
        d["titles"].append((title, lang))
        d["keys"].add(norm(lead if lead and len(lead) >= 60 else title))
    rows = []
    for d in cl.values():
        indep = min(len(d["src"]), len(d["keys"]))
        en = sorted([t for t, l in d["titles"] if l == "en" and t and 25 <= len(t) <= 95], key=len)
        rep = en[len(en) // 2] if en else (d["titles"][0][0] or "?")
        rows.append((indep, len(d["titles"]), rep))
    rows.sort(reverse=True)
    surfaced = sum(1 for r in rows if r[0] >= 3)
    print(f"--- {tag}: {len(rows)} multi-article clusters, {surfaced} surfaced(>=3 indep). Top 15 by indep: ---")
    for indep, sz, rep in rows[:15]:
        print(f"  indep={indep:3d} sz={sz:4d} | {rep[:62]}")


def main() -> int:
    dsn = (os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC")
           or os.environ.get("DATABASE_URL"))
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    analyze(cur, os.environ.get("V1", "/tmp/whole_corpus.csv"), "v1.1 no-XS")
    analyze(cur, os.environ.get("V2", "/tmp/whole_corpus_xs.csv"), "v2 XS-guard")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
