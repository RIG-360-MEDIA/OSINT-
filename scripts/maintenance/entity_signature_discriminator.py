#!/usr/bin/env python3
"""entity_signature_discriminator.py — calibrate the split/keep rule across giants.

READ-ONLY. For each sampled cluster: sub-split with Leiden (res 3.0) on its member
subgraph (analytics.story_edges, score-weighted, run_id), then measure entity-signature
overlap across the >=10-member sub-communities:
  shared_core_size = #entities in the top-5 of >=50% of sub-communities
  mean_jaccard     = mean pairwise Jaccard of sub-community top-5 entity sets
  bridge           = the single entity present in >=80% of subs when it's the ONLY
                     near-ubiquitous one (actor-pile hub signature)
Entities = per member, top-3 from articles.entities_extracted by prominence (the
co-mention-validated signal; NOT the alias-expanded AEM matviews).

Sample = ALL clusters article_count>=1000 + 10 from the 100-999 band (5 suppressed,
5 surfaced). Prints a per-cluster signature block + a final raw TSV table.
Usage: python entity_signature_discriminator.py [run_id]
"""
from __future__ import annotations

import collections
import itertools
import json
import os
import sys

import igraph as ig
import psycopg2
import psycopg2.extras

RUN_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 1780452139
RES = 3.0
MIN_SUB = 10
TOPN_MEMBER = 3
TOPN_SUB = 5


def dsn():
    return (os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC")
            or os.environ["DATABASE_URL"]).replace("+asyncpg", "").replace("+psycopg2", "")


def surfaced(row):
    # mirrors the kickoff §4 surfacing predicate
    return (row["status"] == "active" and not row["is_template_family"]
            and (row["independent_source_count"] >= 3 or row["rescued_from_story_id"] is not None))


def main():
    conn = psycopg2.connect(dsn())
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # ---- sample selection. MODE 'bandb' = ALL clusters 100-999; else 24 big + 10 mixed ----
    MODE = sys.argv[2] if len(sys.argv) > 2 else "default"
    COLS = ("story_id::text, article_count, source_count, independent_source_count, "
            "status, is_template_family, rescued_from_story_id, suppression_reason, representative_title")
    if MODE == "bandb":
        cur.execute(f"SELECT {COLS} FROM analytics.story_clusters "
                    f"WHERE run_id=%s AND article_count BETWEEN 100 AND 999 ORDER BY article_count DESC", (RUN_ID,))
        sample = list(cur.fetchall())
    else:
        cur.execute(f"SELECT {COLS} FROM analytics.story_clusters "
                    f"WHERE run_id=%s AND article_count>=1000 ORDER BY article_count DESC", (RUN_ID,))
        sample = list(cur.fetchall())
        for cond in ("suppression_reason IS NOT NULL", "suppression_reason IS NULL"):
            cur.execute(f"SELECT {COLS} FROM analytics.story_clusters "
                        f"WHERE run_id=%s AND article_count BETWEEN 100 AND 999 AND {cond} "
                        f"ORDER BY article_count DESC LIMIT 5", (RUN_ID,))
            sample += list(cur.fetchall())
    ids = [r["story_id"] for r in sample]
    print(f"=== ENTITY-SIGNATURE DISCRIMINATOR  run={RUN_ID}  res={RES}  clusters={len(sample)} ===", flush=True)

    # ---- member -> story map (sampled clusters only) ----
    cur.execute("SELECT article_id::text aid, story_id::text sid FROM analytics.story_cluster_members WHERE story_id::text = ANY(%s)", (ids,))
    m2s = {r["aid"]: r["sid"] for r in cur.fetchall()}
    members_of = collections.defaultdict(list)
    for aid, sid in m2s.items():
        members_of[sid].append(aid)

    # ---- one pass over edges -> bucket intra-cluster edges by story ----
    cur.execute("SELECT article_a::text a, article_b::text b, score FROM analytics.story_edges WHERE run_id=%s", (RUN_ID,))
    edges_of = collections.defaultdict(list)
    for r in cur.fetchall():
        a, b = r["a"], r["b"]
        sa = m2s.get(a)
        if sa and sa == m2s.get(b) and a != b:
            edges_of[sa].append((a, b, float(r["score"]) if r["score"] is not None else 1.0))

    rows_out = []
    for r in sample:
        sid = r["story_id"]
        members = members_of[sid]
        n = len(members)
        idx = {m: i for i, m in enumerate(members)}
        ed = edges_of[sid]
        g = ig.Graph(n=n, edges=[(idx[a], idx[b]) for a, b, _ in ed])
        w = [s for _, _, s in ed]

        # entities: top-3 per member by prominence, conf
        cur.execute("SELECT id::text id, entities_extracted ee FROM articles WHERE id::text = ANY(%s)", (members,))
        m_ents = {}
        for er in cur.fetchall():
            ee = er["ee"]; names = []
            arr = ee if isinstance(ee, list) else (ee.get("entities") if isinstance(ee, dict) else None)
            if isinstance(arr, list):
                items = [e for e in arr if isinstance(e, dict) and e.get("name")]
                items.sort(key=lambda e: (float(e.get("prominence") or 0), float(e.get("confidence") or 0)), reverse=True)
                names = [str(e["name"]) for e in items[:TOPN_MEMBER]]
            m_ents[er["id"]] = names

        # Leiden res=3.0
        try:
            import leidenalg as la
            part = la.find_partition(g, la.RBConfigurationVertexPartition, weights=w or None,
                                     resolution_parameter=RES, seed=42)
            comms = [list(c) for c in part]
        except Exception:
            comms = [list(c) for c in g.community_leiden(objective_function="modularity", weights=w or None, resolution=RES)]

        subs = [c for c in comms if len(c) >= MIN_SUB]
        sub_top5 = []
        sub_detail = []
        for c in sorted(subs, key=len, reverse=True):
            ecount = collections.Counter()
            for j in c:
                for nm in m_ents.get(members[j], []):
                    ecount[nm] += 1
            top5 = [nm for nm, _ in ecount.most_common(TOPN_SUB)]
            sub_top5.append(set(top5))
            sub_detail.append((len(c), top5, members[c[0]]))

        S = len(sub_top5)
        # shared-core (>=50% of subs), bridge (>=80% near-ubiquitous, only one)
        present = collections.Counter()
        for s in sub_top5:
            for e in s:
                present[e] += 1
        shared_core = [e for e, ct in present.items() if S and ct >= 0.5 * S]
        ubiq80 = [e for e, ct in present.items() if S and ct >= 0.8 * S]
        if S >= 2:
            jac = []
            for a, b in itertools.combinations(sub_top5, 2):
                u = a | b
                jac.append(len(a & b) / len(u) if u else 0.0)
            mean_j = round(sum(jac) / len(jac), 3)
        else:
            mean_j = None
        bridge = ubiq80[0] if (len(ubiq80) == 1 and len(shared_core) <= 1) else None

        surf = surfaced(r)
        # detailed per-sub-community dump ONLY in the near-line zone (where the rule is tested)
        near = (mean_j is not None and 0.10 <= mean_j <= 0.16)
        if near:
            rep_ids = [d[2] for d in sub_detail]
            cur.execute("SELECT id::text id, title FROM articles WHERE id::text = ANY(%s)", (rep_ids or ['x'],))
            tt = {x["id"]: (x["title"] or "") for x in cur.fetchall()}
            print(f"\n### NEAR-LINE {sid} | arts={r['article_count']} src={r['source_count']} indep={r['independent_source_count']} | surfaced={'Y' if surf else 'N'} | supp={r['suppression_reason'] or '-'} | #subs={S}", flush=True)
            print(f"rep: {(r['representative_title'] or '')[:90]}", flush=True)
            print(f"METRICS shared_core_size={len(shared_core)} {shared_core[:6]} | mean_jaccard={mean_j} | bridge={bridge or '-'} | ubiq80={ubiq80[:5]}", flush=True)
            for sz, top5, rid in sub_detail[:8]:
                print(f"   ({sz:>4}) {', '.join(top5):<60} :: {tt.get(rid,'')[:60]}", flush=True)

        rows_out.append((sid, r["article_count"], "Y" if surf else "N", S, len(shared_core), mean_j, bridge or "-"))

    # ---- final raw TSV (sorted by jaccard so the gap is visible) ----
    print(f"\n\n=== RAW TABLE n={len(rows_out)} (story_id | arts | surfaced | #subs | shared_core | jaccard | bridge), sorted by jaccard ===", flush=True)
    for o in sorted(rows_out, key=lambda x: (x[5] is None, x[5] or 0)):
        print("\t".join(str(x) for x in o), flush=True)

    # ---- GAP CHECK: the decision question ----
    js = [o[5] for o in rows_out if o[5] is not None]
    in_gap = [o for o in rows_out if o[5] is not None and 0.112 < o[5] < 0.152]
    near = [o for o in rows_out if o[5] is not None and 0.10 <= o[5] <= 0.16]
    below = [o for o in rows_out if o[5] is not None and o[5] <= 0.112]
    above = [o for o in rows_out if o[5] is not None and o[5] >= 0.152]
    print(f"\n=== GAP CHECK (empty 0.112-0.152 gap = lockable θ=0.13) ===", flush=True)
    print(f"clusters scored: {len(js)}  |  <=0.112 (pile side): {len(below)}  |  >=0.152 (event side): {len(above)}  |  IN GAP (0.112,0.152): {len(in_gap)}", flush=True)
    if js:
        print(f"max pile-side jaccard={max((o[5] for o in below), default=None)}  min event-side jaccard={min((o[5] for o in above), default=None)}", flush=True)
    for o in in_gap:
        print(f"  IN-GAP: {o}", flush=True)
    print(f"near-line (0.10-0.16): {len(near)} clusters (detailed blocks above)", flush=True)
    conn.close()
    print("\n=== END (read-only) ===", flush=True)


if __name__ == "__main__":
    main()
