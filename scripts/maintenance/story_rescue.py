#!/usr/bin/env python3
"""story_rescue.py — §2b flag + sub-cluster RESCUE, as a loader-callable module.

Validated design (subcluster_rescue.py prototype): §2b flags low-cohesion high-source blobs;
the rescue re-clusters ONLY those flagged blobs at high Leiden resolution and re-applies the
SAME cohesion test, surfacing buried real stories as first-class sub-clusters while the residual
stays suppressed. Good clusters are never flagged, so they are never touched.

The loader calls `rescue()` BEFORE its ID-stability step, so each rescued sub-story becomes a
first-class cluster and rides the existing greedy-Jaccard stable-ID path (a split: dominant
successor inherits the prior id, the others get fresh stable ids). No side channel.

Defaults (per the 2026-06-02 15-tcoh spot-check): rescue on core>=0.45 ONLY. The tcoh-only
path is opt-in (allow_tcoh=False) because at title-cohesion alone it admits sports/topic
roundups ("world cup squad" across many countries). min_src_sub default 12 (off the window
source-floor distribution: src>=10 -> 191, >=12 -> 117, >=15 -> 50 rescues).

Standalone (validation): reproduces the prototype on the window CSVs + DB entities.
  AB_DSN=... IN=/tmp/win.csv EDGES=/tmp/win_edges.csv python3 story_rescue.py
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

STOP_ENT = {
    "bbc", "reuters", "afp", "pti", "ani", "ap", "ians", "bloomberg", "ndtv", "cnn",
    "agence france-presse", "associated press", "press trust of india",
    "indo-asian news service", "the associated press", "reuters india",
    "rebel wilson", "russia and china",
}
STOPWORDS = set(
    "the a an of in on at to for and or but with from by as is are was were be been over "
    "after into amid say says said new latest update live news his her its it he she they "
    "this that will more than has have had not no".split()
)


def grams(title: str) -> set[str]:
    toks = [t for t in re.sub(r"[^a-z0-9 ]", " ", (title or "").lower()).split() if t]
    out: set[str] = set()
    for nlen in (2, 3):
        for i in range(len(toks) - nlen + 1):
            g = toks[i : i + nlen]
            if not all(w in STOPWORDS for w in g):
                out.add(" ".join(g))
    return out


def _core(members, art_ents):
    n = len(members)
    c: Counter = Counter()
    for m in members:
        for e in {x for x in (art_ents.get(m) or []) if x and x not in STOP_ENT}:
            c[e] += 1
    if not c:
        return 0.0, "-"
    e, cnt = c.most_common(1)[0]
    return cnt / max(n, 1), e


def _tcoh(members, art_titles):
    n = len(members)
    g: Counter = Counter()
    for m in members:
        for x in grams(art_titles.get(m, "")):
            g[x] += 1
    return (g.most_common(1)[0][1] / max(n, 1)) if g else 0.0


def _src(members, src_of):
    return len({src_of.get(m) for m in members if src_of.get(m)})


def _community_split(members, edge_triples, resolution):
    """Louvain community detection — igraph (C-backed: tens of MB even at 100k+ nodes) when
    available, networkx fallback. edge_triples: list of (a,b,weight) with NO duplicate undirected
    edges (igraph would make them multi-edges). Returns a list of sets of member ids."""
    members = list(members)
    et = list(edge_triples)
    try:
        import igraph as ig
        idx = {v: i for i, v in enumerate(members)}
        elist = [(idx[a], idx[b]) for a, b, _ in et if a in idx and b in idx]
        wlist = [w for a, b, w in et if a in idx and b in idx]
        g = ig.Graph(n=len(members), edges=elist)
        vc = g.community_multilevel(weights=(wlist or None), resolution=resolution)
        return [set(members[i] for i in comm) for comm in vc]
    except ImportError:
        import networkx as nx
        g = nx.Graph()
        g.add_nodes_from(members)
        for a, b, w in et:
            g.add_edge(a, b, weight=w)
        try:
            return [set(c) for c in nx.community.louvain_communities(
                g, weight="weight", resolution=resolution, seed=42)]
        except Exception:  # noqa: BLE001
            return [set(members)]


def s2b(members, art_ents, art_titles, src_of, flag_min_src=25, core_t=0.45, tcoh_t=0.35, tcoh_cap=1000):
    """§2b fields for one cluster's member list. The title-cohesion spare (tcoh>=tcoh_t) protects
    a BOUNDED real-event-with-broken-entities (the Myanmar class). It does NOT apply above
    tcoh_cap articles — a cluster that large is a broad TOPIC (e.g. a 46-day "IPL 2026"
    season-pile), not an event, so it stays flagged and is handed to the rescue to unpack.
    (Cap locked off the 2026-06-03 band-check: tcoh-spared clusters were 4305(IPL),522,330,<=9 —
    nothing real in 522..4305, so 1000 sits in the empty gap.)"""
    core, ent = _core(members, art_ents)
    tcoh = _tcoh(members, art_titles)
    src = _src(members, src_of)
    spared_by_tcoh = tcoh >= tcoh_t and len(members) <= tcoh_cap
    is_tf = src >= flag_min_src and core < core_t and not spared_by_tcoh
    return {"core": round(core, 3), "core_ent": ent, "tcoh": round(tcoh, 3), "src": src, "is_tf": is_tf}


def rescue(members_by_cluster, edges, art_ents, art_titles, src_of, *,
           res=4.0, min_sz_sub=10, min_src_sub=12, core_t=0.45, tcoh_t=0.35,
           allow_tcoh=False, flag_min_src=25, tcoh_cap=1000):
    """Flag §2b blobs and rescue buried real stories out of them.

    members_by_cluster: {cluster_id: [article_id,...]}
    edges:              {(a_id,b_id): score}  (undirected; a<b not required)
    art_ents:           {article_id: [entity_name,...]}   art_titles/src_of: {article_id: str}
    Returns (final_of, s2b_of, stats):
      final_of: {article_id: final_cluster_id}  — rescued subs get id 'cid::rN'; rest keep cid
      s2b_of:   {final_cluster_id: {core,core_ent,tcoh,src,is_tf,rescued_from}}
      stats:    {flagged, rescued, dry}
    """
    final_of, s2b_of = {}, {}
    stats = {"flagged": 0, "rescued": 0, "dry": 0}
    flagged = {}
    for cid, members in members_by_cluster.items():
        info = s2b(members, art_ents, art_titles, src_of, flag_min_src, core_t, tcoh_t, tcoh_cap)
        if info["is_tf"]:
            flagged[cid] = members
        else:
            for m in members:
                final_of[m] = cid
            s2b_of[cid] = {**info, "rescued_from": None}

    flagged_members = set()
    for ms in flagged.values():
        flagged_members.update(ms)
    adj = defaultdict(list)
    for (a, b), sc in edges.items():
        if a in flagged_members and b in flagged_members:
            adj[a].append((b, sc))
            adj[b].append((a, sc))

    for cid, members in flagged.items():
        stats["flagged"] += 1
        memset = set(members)
        et, seen_e = [], set()
        for a in members:
            for b, sc in adj.get(a, []):
                if b in memset:
                    k = (a, b) if a < b else (b, a)
                    if k not in seen_e:
                        seen_e.add(k)
                        et.append((a, b, sc))
        comms = _community_split(members, et, res)
        residual, got = set(members), 0
        for i, comm in enumerate(sorted((set(c) for c in comms), key=len, reverse=True)):
            if len(comm) < min_sz_sub or _src(comm, src_of) < min_src_sub:
                continue
            core, ent = _core(comm, art_ents)
            tcoh = _tcoh(comm, art_titles)
            if not (core >= core_t or (allow_tcoh and tcoh >= tcoh_t)):
                continue
            sub_id = f"{cid}::r{i}"
            for m in comm:
                final_of[m] = sub_id
                residual.discard(m)
            s2b_of[sub_id] = {"core": round(core, 3), "core_ent": ent, "tcoh": round(tcoh, 3),
                              "src": _src(comm, src_of), "is_tf": False, "rescued_from": cid}
            got += 1
        for m in residual:
            final_of[m] = cid
        if residual:
            s2b_of[cid] = {**s2b(list(residual), art_ents, art_titles, src_of, flag_min_src, core_t, tcoh_t, tcoh_cap),
                           "rescued_from": None}
        stats["rescued"] += got
        stats["dry"] += 1 if got == 0 else 0
    return final_of, s2b_of, stats


def _selftest():
    """Standalone validation: reproduce the prototype on the window CSVs + DB entities."""
    import csv as _csv
    import os
    import sys

    import psycopg2

    dsn = os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC") or os.environ.get("DATABASE_URL")
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute("CREATE TEMP TABLE _wc(article_id uuid, cluster_id text, source_id text)")
    with open(os.environ.get("IN", "/tmp/win.csv")) as f:
        cur.copy_expert("COPY _wc FROM STDIN WITH (FORMAT csv, HEADER true)", f)
    cur.execute(
        """SELECT w.article_id, w.cluster_id, w.source_id, a.title,
             (SELECT array_agg(lower(e->>'name')) FROM (
                SELECT e FROM jsonb_array_elements(coalesce(a.entities_extracted,'[]'::jsonb)) e
                WHERE e->>'name' IS NOT NULL
                ORDER BY (e->>'prominence')::float DESC NULLS LAST LIMIT 3) t)
           FROM _wc w JOIN articles a ON a.id = w.article_id"""
    )
    mbc = defaultdict(list)
    art_ents, art_titles, src_of = {}, {}, {}
    for aid, cid, sid, title, ents in cur:
        aid = str(aid)
        mbc[cid].append(aid)
        art_ents[aid], art_titles[aid], src_of[aid] = ents or [], title or "", sid
    edges = {}
    with open(os.environ.get("EDGES", "/tmp/win_edges.csv")) as f:
        r = _csv.reader(f)
        next(r, None)
        for a, b, s in r:
            edges[(a, b)] = float(s)
    # prototype params (min_src_sub=10, allow_tcoh=True) to confirm parity, then prod defaults
    for label, kw in (("PROTOTYPE-parity (src>=10, tcoh ON)", dict(min_src_sub=10, allow_tcoh=True)),
                      ("PROD default (src>=12, core-only)", dict(min_src_sub=12, allow_tcoh=False))):
        _, s2b_of, stats = rescue(mbc, edges, art_ents, art_titles, src_of, **kw)
        rescued_ids = [k for k, v in s2b_of.items() if v.get("rescued_from")]
        sys.stderr.write(f"  {label}: flagged={stats['flagged']} rescued={stats['rescued']} "
                         f"dry={stats['dry']} (rescued clusters in s2b_of={len(rescued_ids)})\n")
    conn.close()


if __name__ == "__main__":
    _selftest()
