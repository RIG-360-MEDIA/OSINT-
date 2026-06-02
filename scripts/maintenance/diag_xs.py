#!/usr/bin/env python3
"""diag_xs.py — WHY did the cross-source guard under-fire on the Q4 blob?
Finds the Q4-template blob in a run CSV, samples its pairs, and reports the trgm_subject vs
trgm_title distribution + per-condition pass rates + the veto% at a T_STRUCT sweep (using
subject vs title as the structural signal). Tells us the right structural feature + threshold
to lock — instead of guessing. Read-only."""
from __future__ import annotations

import importlib.util
import itertools
import os
import statistics
import sys

import psycopg2
from psycopg2.extras import execute_values


def _load(p, n):
    s = importlib.util.spec_from_file_location(n, p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


pf = _load(os.environ.get("PF_PATH", "/tmp/pair_features.py"), "pair_features")
CSV = os.environ.get("CSV", "/tmp/whole_corpus_xs.csv")
SAMPLE = int(os.environ.get("SAMPLE", "55"))
FIND = os.environ.get("FIND", "q[1-4] result|quarterly|net profit|results:| pat |share price")
SZ_LO = int(os.environ.get("SZ_LO", "300"))
SZ_HI = int(os.environ.get("SZ_HI", "700"))


def main() -> int:
    dsn = (os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC")
           or os.environ.get("DATABASE_URL"))
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute("CREATE TEMP TABLE _x(article_id uuid, cluster_id uuid, source_id uuid)")
    with open(CSV) as f:
        cur.copy_expert("COPY _x FROM STDIN WITH (FORMAT csv, HEADER true)", f)
    cur.execute("""
        WITH cl AS (SELECT cluster_id, count(*) sz, count(DISTINCT source_id) src FROM _x GROUP BY 1)
        SELECT c.cluster_id, c.sz, c.src
        FROM cl c JOIN _x x ON x.cluster_id=c.cluster_id JOIN articles a ON a.id=x.article_id
        WHERE c.sz BETWEEN %s AND %s
        GROUP BY 1,2,3
        HAVING bool_or(a.title ~* %s)
        ORDER BY c.src DESC LIMIT 1
    """, (SZ_LO, SZ_HI, FIND))
    row = cur.fetchone()
    if not row:
        print("no Q4/template blob found in", CSV)
        return 0
    cid, sz, src = row
    cur.execute("SELECT primary_subject, title FROM articles a JOIN _x x ON x.article_id=a.id "
                "WHERE x.cluster_id=%s LIMIT 4", (cid,))
    print(f"Q4/template blob: size={sz} sources={src}")
    for ps, t in cur.fetchall():
        print(f"   subj={ps!r:40.40}  title={t!r:.46}")

    cur.execute("SELECT article_id FROM _x WHERE cluster_id=%s LIMIT %s", (cid, SAMPLE))
    ids = [str(r[0]) for r in cur.fetchall()]
    pairs = list(itertools.combinations(ids, 2))
    cur.execute("CREATE TEMP TABLE _p(a_id uuid, b_id uuid, label int)")
    execute_values(cur, "INSERT INTO _p VALUES %s", [(a, b, 0) for a, b in pairs])
    cur.execute("""SELECT id, (SELECT array_agg(lower(e->>'name')) FROM (
                     SELECT e FROM jsonb_array_elements(coalesce(entities_extracted,'[]'::jsonb)) e
                     WHERE e->>'name' IS NOT NULL
                     ORDER BY (e->>'prominence')::float DESC NULLS LAST LIMIT 3) t)
                   FROM articles WHERE id = ANY(%s::uuid[])""", (ids,))
    ents = {str(i): set(e or []) for i, e in cur.fetchall()}

    cur.execute(pf.structured_sql("_p"))
    feats = pf.rows_to_features(cur)
    n = len(feats)

    def f(x):
        return float(x) if x not in ("", None) else 0.0

    subj = [f(fr["trgm_subject"]) for fr in feats]
    titl = [f(fr["trgm_title"]) for fr in feats]

    def ediv(fr):
        a, b = ents.get(str(fr["a_id"]), set()), ents.get(str(fr["b_id"]), set())
        return bool(a and b and (a - b) and (b - a))

    def ndiv(fr):
        return bool(fr.get("a_has_numbers") and fr.get("b_has_numbers") and int(f(fr["shared_numbers"])) == 0)

    def loc(fr):
        return int(f(fr["shared_locations"])) > 0

    def pct(x):
        return f"{100.0*x/max(n,1):.0f}%"

    print(f"\npairs sampled={n}")
    for name, arr in [("trgm_subject", subj), ("trgm_title", titl)]:
        print(f"  {name}: median={statistics.median(arr):.2f} mean={statistics.mean(arr):.2f}  "
              f">=.75:{pct(sum(s>=.75 for s in arr))} >=.6:{pct(sum(s>=.6 for s in arr))} "
              f">=.5:{pct(sum(s>=.5 for s in arr))} >=.4:{pct(sum(s>=.4 for s in arr))}")
    print(f"  entity-divergent={pct(sum(ediv(fr) for fr in feats))}  "
          f"numbers-divergent={pct(sum(ndiv(fr) for fr in feats))}  "
          f"shared-location(protects)={pct(sum(loc(fr) for fr in feats))}")
    print("\n  veto% (structural>=T AND entity-div AND numbers-div AND no-location):")
    for label, sig in [("subject", subj), ("title", titl)]:
        out = []
        for T in (0.75, 0.6, 0.5, 0.4, 0.3):
            v = sum(1 for i, fr in enumerate(feats) if sig[i] >= T and ediv(fr) and ndiv(fr) and not loc(fr))
            out.append(f"T{T}:{pct(v)}")
        print(f"    using {label}-trgm:  " + "  ".join(out))
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
