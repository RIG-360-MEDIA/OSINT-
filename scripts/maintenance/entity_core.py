#!/usr/bin/env python3
"""entity_core.py — the §2b separator: does a cluster have a shared ENTITY CORE?
For each big cluster, core_cov = fraction of its articles that contain the single most-common
entity. Hypothesis: real events have high core_cov (one actor in ~all articles); cross-source
TOPIC over-merges (the financial blob) have low core_cov (no common entity). Read-only."""
from __future__ import annotations

import os
import sys
from collections import Counter, defaultdict

import psycopg2

CSV = os.environ.get("CSV", "/tmp/whole_corpus_xs.csv")
MIN_SZ = int(os.environ.get("MIN_SZ", "60"))


def main() -> int:
    dsn = (os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC")
           or os.environ.get("DATABASE_URL"))
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute("CREATE TEMP TABLE _x(article_id uuid, cluster_id uuid, source_id uuid)")
    with open(CSV) as f:
        cur.copy_expert("COPY _x FROM STDIN WITH (FORMAT csv, HEADER true)", f)
    cur.execute(f"""
        SELECT x.cluster_id, x.source_id, a.title, coalesce(a.language_detected,'?'),
               (SELECT array_agg(lower(e->>'name')) FROM (
                  SELECT e FROM jsonb_array_elements(coalesce(a.entities_extracted,'[]'::jsonb)) e
                  WHERE e->>'name' IS NOT NULL
                  ORDER BY (e->>'prominence')::float DESC NULLS LAST LIMIT 3) t)
        FROM _x x JOIN articles a ON a.id = x.article_id
        WHERE x.cluster_id IN (SELECT cluster_id FROM _x GROUP BY 1 HAVING count(*) >= {MIN_SZ})
    """)
    cl = defaultdict(lambda: {"n": 0, "src": set(), "ent": Counter(), "titles": []})
    for cid, sid, title, lang, ents in cur:
        d = cl[str(cid)]
        d["n"] += 1
        if sid:
            d["src"].add(str(sid))
        for e in set(ents or []):
            d["ent"][e] += 1
        if lang == "en" and title and 25 <= len(title) <= 95:
            d["titles"].append(title)
    rows = []
    for d in cl.values():
        core, cov = d["ent"].most_common(1)[0] if d["ent"] else ("-", 0)
        rep = sorted(d["titles"], key=len)[len(d["titles"]) // 2] if d["titles"] else "?"
        rows.append((d["n"], len(d["src"]), cov / max(d["n"], 1), core, rep))
    rows.sort(reverse=True)
    print(f"{len(rows)} clusters >= {MIN_SZ} articles. core_cov = max single-entity article coverage:")
    print("size  src  core_cov  core_entity        | rep_title")
    for n, src, cov, core, rep in rows[:20]:
        flag = "  <-- LOW core (topic over-merge?)" if cov < 0.35 else ""
        print(f"{n:4d} {src:3d}   {cov:.2f}   {core[:18]:18s} | {rep[:46]}{flag}")
    los = [r for r in rows if r[2] < 0.35]
    print(f"\nclusters with core_cov < 0.35 (candidate topic over-merges): {len(los)} of {len(rows)}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
