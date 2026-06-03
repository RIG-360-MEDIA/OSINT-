#!/usr/bin/env python3
"""subcluster_rescue.py — prototype the §2b sub-cluster RESCUE.

The premise the resolution sweep disproved: global Leiden resolution can't separate a buried
real story from a category-blob without also shredding genuine big stories — it can't tell
them apart by size. The rescue fixes that by being TARGETED:

  Stage 1 (existing §2b): flag clusters with src>=25 AND core<0.45 AND title_coh<0.35.
  Stage 2 (NEW rescue): re-cluster ONLY the flagged blobs at high Leiden resolution, then
     re-apply the SAME cohesion test to each sub-community. A sub-community that is
     src>=MIN_SRC_SUB AND (core>=0.45 OR title_coh>=0.35) is a BURIED REAL STORY -> surface
     it; the rest of the blob stays suppressed.

Because only already-flagged blobs are re-split, genuine big stories (never flagged) are never
touched. Proves the discrimination: a category-blob (e.g. mixed Q4 results) yields NO coherent
sub-community (nothing rescued); a real story tangled into a blob surfaces as a high-core
sub-community (rescued). Read-only (TEMP table).

Env: AB_DSN/DATABASE_URL_SYNC · IN (/tmp/win.csv) · EDGES (/tmp/win_edges.csv) · RES_RESCUE (4.0)
"""
from __future__ import annotations

import csv as _csv
import os
import re
import sys
from collections import Counter, defaultdict

import psycopg2

IN = os.environ.get("IN", "/tmp/win.csv")
EDGES = os.environ.get("EDGES", "/tmp/win_edges.csv")
RES_RESCUE = float(os.environ.get("RES_RESCUE", "4.0"))
MIN_SRC = int(os.environ.get("MIN_SRC", "25"))          # §2b flag floor (a cluster only flaggable if this big)
MIN_SRC_SUB = int(os.environ.get("MIN_SRC_SUB", "10"))  # a rescued sub-story needs >= this many sources
MIN_SZ_SUB = int(os.environ.get("MIN_SZ_SUB", "10"))
CORE_T, TCOH_T = 0.45, 0.35

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


def core_of(members, ent_of):
    n = len(members)
    c: Counter = Counter()
    for m in members:
        for e in {x for x in (ent_of.get(m) or []) if x and x not in STOP_ENT}:
            c[e] += 1
    if not c:
        return 0.0, "-"
    e, cnt = c.most_common(1)[0]
    return cnt / max(n, 1), e


def tcoh_of(members, title_of):
    n = len(members)
    g: Counter = Counter()
    for m in members:
        for x in grams(title_of.get(m, "")):
            g[x] += 1
    return (g.most_common(1)[0][1] / max(n, 1)) if g else 0.0


def main() -> int:
    dsn = os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC") or os.environ.get("DATABASE_URL")
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute("CREATE TEMP TABLE _wc(article_id uuid, cluster_id text, source_id text)")
    with open(IN) as f:
        cur.copy_expert("COPY _wc FROM STDIN WITH (FORMAT csv, HEADER true)", f)
    cur.execute(
        """SELECT w.article_id, w.cluster_id, w.source_id, a.title,
             (SELECT array_agg(lower(e->>'name')) FROM (
                SELECT e FROM jsonb_array_elements(coalesce(a.entities_extracted,'[]'::jsonb)) e
                WHERE e->>'name' IS NOT NULL
                ORDER BY (e->>'prominence')::float DESC NULLS LAST LIMIT 3) t)
           FROM _wc w JOIN articles a ON a.id = w.article_id"""
    )
    cl = defaultdict(list)
    ent_of, title_of, src_of = {}, {}, {}
    for aid, cid, sid, title, ents in cur:
        aid = str(aid)
        cl[cid].append(aid)
        src_of[aid], title_of[aid], ent_of[aid] = sid, title or "", ents or []

    adj = defaultdict(list)
    with open(EDGES) as f:
        r = _csv.reader(f)
        next(r, None)
        for a, b, s in r:
            w = float(s)
            adj[a].append((b, w))
            adj[b].append((a, w))

    flagged = []
    for cid, mem in cl.items():
        src = len({src_of[m] for m in mem if src_of[m]})
        if len(mem) < MIN_SZ_SUB or src < MIN_SRC:
            continue
        core, _ = core_of(mem, ent_of)
        tcoh = tcoh_of(mem, title_of)
        if core < CORE_T and tcoh < TCOH_T:
            flagged.append((cid, mem, src, core, tcoh))
    print(f"IN={IN}  flagged blobs (src>={MIN_SRC}, core<{CORE_T}, tcoh<{TCOH_T}): {len(flagged)}")

    import networkx as nx

    rescued, dry = [], []
    for cid, mem, src, core, tcoh in flagged:
        memset = set(mem)
        g = nx.Graph()
        g.add_nodes_from(mem)
        for a in mem:
            for b, w in adj.get(a, []):
                if b in memset:
                    g.add_edge(a, b, weight=w)
        try:
            comms = nx.community.louvain_communities(g, weight="weight", resolution=RES_RESCUE, seed=42)
        except Exception:  # noqa: BLE001
            comms = [set(mem)]
        got = 0
        for comm in comms:
            if len(comm) < MIN_SZ_SUB:
                continue
            ssrc = len({src_of[m] for m in comm if src_of[m]})
            if ssrc < MIN_SRC_SUB:
                continue
            score, sent = core_of(comm, ent_of)
            stc = tcoh_of(comm, title_of)
            if score >= CORE_T or stc >= TCOH_T:
                got += 1
                titles = [title_of[m][:58] for m in list(comm)[:3]]
                rescued.append((len(comm), ssrc, score, sent, stc, len(mem), round(core, 2), titles))
        if got == 0:
            _, dent = core_of(mem, ent_of)
            dgram = Counter()
            for m in mem:
                for x in grams(title_of.get(m, "")):
                    dgram[x] += 1
            topgram = dgram.most_common(1)[0][0] if dgram else "-"
            dry.append((len(mem), src, round(core, 2), dent, topgram))
    rescued.sort(key=lambda r: -r[0])
    print(f"RESCUED buried stories: {len(rescued)}  |  blobs that yielded NOTHING (true category-blobs): "
          f"{len(dry)}/{len(flagged)}")
    print("  (a rescued sub = src>=%d & (core>=%.2f or tcoh>=%.2f); blob it came from shown as 'from blob N core C')"
          % (MIN_SRC_SUB, CORE_T, TCOH_T))
    for sz, ssrc, score, sent, stc, blobsz, blobcore, titles in rescued:
        print(f"  RESCUE n={sz:3d} src={ssrc:3d} core={score:.2f}({sent[:18]:18s}) tcoh={stc:.2f}  "
              f"<- from blob {blobsz} (core {blobcore})")
        print(f"         ex: {' | '.join(titles)}")
    print(f"\n-- the {len(dry)} blobs that yielded NOTHING (correctly stay suppressed — true category-blobs) --")
    for sz, src, core, ent, topgram in sorted(dry, reverse=True):
        print(f"  DRY n={sz:4d} src={src:3d} core={core:.2f}({ent[:18]:18s}) topgram={topgram[:22]}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
