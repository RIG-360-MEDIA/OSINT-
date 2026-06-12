#!/usr/bin/env python3
"""sub_split_experiment.py — re-cluster ONE giant story at higher Leiden resolution.

READ-ONLY. Writes nothing to production. Reports RAW numbers; analytics interprets.

Subgraph = story_edges among the cluster's members (score = weight). Leiden
(leidenalg RBConfigurationVertexPartition; igraph community_leiden fallback) swept
over resolutions. Coherence = avg member cosine-sim to the (sub)community centroid
of labse_embedding_v4. Usage: python sub_split_experiment.py <story_id> <run_id>
"""
from __future__ import annotations

import collections
import json
import os
import sys

import numpy as np
import psycopg2
import psycopg2.extras

STORY = sys.argv[1] if len(sys.argv) > 1 else "b6f91d2b-4838-4845-90c2-0f6be08595fc"
RUN_ID = int(sys.argv[2]) if len(sys.argv) > 2 else 1780452139
RES_SWEEP = [1.0, 1.5, 2.0, 3.0, 4.0]
HEALTHY_BAR = 0.83


def dsn():
    return (os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC")
            or os.environ["DATABASE_URL"]).replace("+asyncpg", "").replace("+psycopg2", "")


def main():
    conn = psycopg2.connect(dsn())
    cur = conn.cursor()
    print(f"=== SUB-SPLIT EXPERIMENT  story={STORY}  run_id={RUN_ID} ===", flush=True)

    # ---- members ----
    cur.execute("SELECT article_id::text FROM analytics.story_cluster_members WHERE story_id=%s", (STORY,))
    members = [r[0] for r in cur.fetchall()]
    n = len(members)
    print(f"members: {n}", flush=True)
    if n < 3:
        print("too few members, abort"); return

    # temp table for efficient edge join
    cur.execute("CREATE TEMP TABLE _m(id uuid PRIMARY KEY)")
    psycopg2.extras.execute_values(cur, "INSERT INTO _m(id) VALUES %s ON CONFLICT DO NOTHING",
                                   [(m,) for m in members], page_size=2000)

    # ---- edges among members ----
    cur.execute("""
        SELECT e.article_a::text, e.article_b::text, e.score
        FROM analytics.story_edges e
        JOIN _m a ON a.id = e.article_a JOIN _m b ON b.id = e.article_b
        WHERE e.run_id = %s AND e.article_a <> e.article_b
    """, (RUN_ID,))
    raw = cur.fetchall()
    # dedup undirected
    seen = set(); edges = []
    for a, b, s in raw:
        k = (a, b) if a < b else (b, a)
        if k in seen:
            continue
        seen.add(k); edges.append((k[0], k[1], float(s) if s is not None else 1.0))
    print(f"edges among members (run {RUN_ID}, undirected dedup): {len(edges)}", flush=True)

    # ---- build graph ----
    try:
        import igraph as ig
    except ImportError:
        print("FATAL: igraph missing"); return
    idx = {m: i for i, m in enumerate(members)}
    elist = [(idx[a], idx[b]) for a, b, _ in edges]
    wlist = [w for _, _, w in edges]
    g = ig.Graph(n=n, edges=elist)
    comps = g.connected_components()
    csizes = sorted((len(c) for c in comps), reverse=True)
    print(f"connected components: {len(comps)}  giant={csizes[0]} ({100*csizes[0]/n:.1f}% of members)  top5={csizes[:5]}", flush=True)

    # ---- vectors (v4 shadow) ----
    cur.execute("SELECT id::text, labse_embedding_v4::text FROM articles WHERE id::text = ANY(%s) AND labse_embedding_v4 IS NOT NULL", (members,))
    vecs = {}
    for aid, vt in cur.fetchall():
        try:
            vecs[aid] = np.asarray(json.loads(vt), dtype=np.float32)
        except Exception:
            pass
    print(f"v4 vectors available: {len(vecs)}/{n} ({100*len(vecs)/n:.1f}%)", flush=True)

    def coherence(ids):
        vs = [vecs[i] for i in ids if i in vecs]
        if len(vs) < 2:
            return None, len(vs)
        M = np.vstack(vs)
        M = M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)
        cen = M.mean(0); cen = cen / (np.linalg.norm(cen) + 1e-9)
        return float((M @ cen).mean()), len(vs)

    gcoh, gn = coherence(members)
    print(f"GLOBAL cluster coherence (v4) = {gcoh if gcoh is None else round(gcoh,4)}  over {gn} vectored members", flush=True)

    # ---- entities + titles for labelling ----
    cur.execute("SELECT id::text, title, entities_extracted FROM articles WHERE id::text = ANY(%s)", (members,))
    title = {}; ents = {}
    for aid, t, ee in cur.fetchall():
        title[aid] = t or ""
        names = []
        if ee:
            arr = ee if isinstance(ee, list) else (ee.get("entities") if isinstance(ee, dict) else None)
            if isinstance(arr, list):
                for e in arr:
                    if isinstance(e, dict) and e.get("name"):
                        names.append(str(e["name"]))
        ents[aid] = names

    # ---- Leiden sweep ----
    def leiden(resolution):
        try:
            import leidenalg as la
            part = la.find_partition(g, la.RBConfigurationVertexPartition,
                                     weights=wlist or None, resolution_parameter=resolution, seed=42)
            return [list(c) for c in part], "leidenalg/RBConfiguration"
        except Exception as ex:
            part = g.community_leiden(objective_function="modularity",
                                      weights=wlist or None, resolution=resolution)
            return [list(c) for c in part], f"igraph/community_leiden(fallback: {type(ex).__name__})"

    print("\n--- RESOLUTION SWEEP (production was res 1.0) ---", flush=True)
    parts_by_res = {}
    for res in RES_SWEEP:
        comms, algo = leiden(res)
        parts_by_res[res] = comms
        sizes = sorted((len(c) for c in comms), reverse=True)
        hist = collections.Counter(sizes)
        # size-weighted coherence
        num = den = 0.0
        for c in comms:
            ids = [members[i] for i in c]
            ch, cn = coherence(ids)
            if ch is not None:
                num += ch * cn; den += cn
        swc = round(num / den, 4) if den else None
        small = sum(v for k, v in hist.items() if k <= 3)
        print(f"res={res:>4}: #subcomm={len(comms):>4}  top10={sizes[:10]}  singletons={hist.get(1,0)}  <=3={small}  size-weighted_coherence={swc}  [{algo}]", flush=True)

    # ---- per-subcommunity detail at each mid resolution ----
    for res in [2.0, 3.0]:
        comms = sorted(parts_by_res[res], key=len, reverse=True)
        print(f"\n--- PER-SUBCOMMUNITY @ res={res} (>=10 members) ---", flush=True)
        print(f"{'size':>5} {'coh':>6} {'topEntities':<55} repTitle", flush=True)
        for c in comms:
            if len(c) < 10:
                continue
            ids = [members[i] for i in c]
            ch, cn = coherence(ids)
            ecount = collections.Counter()
            for i in ids:
                for nm in ents.get(i, []):
                    ecount[nm] += 1
            tope = ", ".join(f"{nm}({ct})" for nm, ct in ecount.most_common(5))
            # representative title = highest-degree node in the subcommunity
            sub = g.subgraph(c)
            rep_local = max(range(len(c)), key=lambda j: sub.degree(j)) if len(c) else 0
            rep = title.get(ids[rep_local], "")[:70]
            chs = "NA" if ch is None else f"{ch:.3f}"
            print(f"{len(c):>5} {chs:>6} {tope[:55]:<55} {rep}", flush=True)
        # outliers
        outl = sum(1 for c in parts_by_res[res] if len(c) <= 3)
        outl_m = sum(len(c) for c in parts_by_res[res] if len(c) <= 3)
        print(f"outliers @res={res}: {outl} tiny subcommunities (<=3) holding {outl_m} members (eject candidates)", flush=True)

    conn.close()
    print("\n=== END (read-only; nothing written) ===", flush=True)


if __name__ == "__main__":
    main()
