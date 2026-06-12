#!/usr/bin/env python3
"""entity_signature_classify.py — FINAL multi-signal split/keep classifier, all clusters >=100.

READ-ONLY. Pinned params (analytics locks numbers, not adjectives):
  THETA             = 0.13   primary jaccard threshold (>= -> lean keep)
  HUB_UBIQ_FRAC     = 0.80   an entity is a 'hub' if in >= this frac of sub-communities
  GENERIC_DF_MIN    = 25     hub is GENERIC actor/geo if it is a primary_entity in >= this many
                             run clusters (data-driven: event-subjects DF<=6, generics DF>=84)
  SHARED_CORE_KEEP  = 4      few-subs rescue keeps if shared_core >= this
  MIN_SUBS          = 4      below this, jaccard is unstable -> trust shared_core
  SPORTS_BAND       = [0.10, 0.16]   sports-team hub in this jaccard band -> LLM residual

Rule order: no-split(coherent) -> sports-residual(LLM) -> few-subs rescue ->
bridge-demote(SPLIT) -> primary jaccard. Method per prior runs (res 3.0 Leiden,
top-3 entities_extracted by prominence, top-5 per sub). Usage: python ... [run_id]
"""
from __future__ import annotations

import collections
import itertools
import os
import sys

import igraph as ig
import psycopg2
import psycopg2.extras

RUN_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 1780452139
RES, MIN_SUB_MEMBERS, TOPN_MEMBER, TOPN_SUB = 3.0, 10, 3, 5
THETA = 0.13
HUB_UBIQ_FRAC = 0.80
GENERIC_DF_MIN = 25
SHARED_CORE_KEEP = 4
MIN_SUBS = 4
SPORTS_BAND = (0.10, 0.16)

SPORTS_PAT = [s.lower() for s in [
    "Titans", "Super Kings", "Mumbai Indians", "Knight Riders", "Capitals", "Punjab Kings",
    "Rajasthan Royals", "Sunrisers", "Super Giants", "Challengers Bengaluru", "Royal Challengers",
    " FC", "Football Club", "Mohun Bagan", "East Bengal", "Kerala Blasters", "Bengaluru FC",
    "Real Madrid", "Manchester", "Liverpool", "Arsenal", "Chelsea", "Bagan"]]


def dsn():
    return (os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC")
            or os.environ["DATABASE_URL"]).replace("+asyncpg", "").replace("+psycopg2", "")


def is_sports_entity(name):
    n = (name or "").lower()
    return any(p in n for p in SPORTS_PAT)


def surfaced(r):
    return (r["status"] == "active" and not r["is_template_family"]
            and (r["independent_source_count"] >= 3 or r["rescued_from_story_id"] is not None))


def main():
    conn = psycopg2.connect(dsn())
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    COLS = ("story_id::text, article_count, source_count, independent_source_count, status, "
            "is_template_family, rescued_from_story_id, suppression_reason, representative_title")
    cur.execute(f"SELECT {COLS} FROM analytics.story_clusters WHERE run_id=%s AND article_count>=100 "
                f"ORDER BY article_count DESC", (RUN_ID,))
    sample = list(cur.fetchall())
    ids = [r["story_id"] for r in sample]
    print(f"=== FINAL CLASSIFIER run={RUN_ID} clusters>=100: {len(sample)} | THETA={THETA} "
          f"GENERIC_DF_MIN={GENERIC_DF_MIN} SHARED_CORE_KEEP={SHARED_CORE_KEEP} MIN_SUBS={MIN_SUBS} "
          f"HUB_UBIQ_FRAC={HUB_UBIQ_FRAC} SPORTS_BAND={SPORTS_BAND} ===", flush=True)

    cur.execute("SELECT article_id::text aid, story_id::text sid FROM analytics.story_cluster_members WHERE story_id::text = ANY(%s)", (ids,))
    m2s = {x["aid"]: x["sid"] for x in cur.fetchall()}
    members_of = collections.defaultdict(list)
    for aid, sid in m2s.items():
        members_of[sid].append(aid)
    cur.execute("SELECT article_a::text a, article_b::text b, score FROM analytics.story_edges WHERE run_id=%s", (RUN_ID,))
    edges_of = collections.defaultdict(list)
    for x in cur.fetchall():
        a, b = x["a"], x["b"]
        if m2s.get(a) and m2s.get(a) == m2s.get(b) and a != b:
            edges_of[m2s[a]].append((a, b, float(x["score"]) if x["score"] is not None else 1.0))

    df_cache = {}
    def hub_df(name):
        k = (name or "").lower()
        if k not in df_cache:
            cur.execute("SELECT count(*) c FROM analytics.story_clusters WHERE run_id=%s AND primary_entities ? %s", (RUN_ID, k))
            df_cache[k] = cur.fetchone()["c"]
        return df_cache[k]

    rows = []
    for r in sample:
        sid = r["story_id"]
        members = members_of[sid]
        idx = {m: i for i, m in enumerate(members)}
        ed = edges_of[sid]
        g = ig.Graph(n=len(members), edges=[(idx[a], idx[b]) for a, b, _ in ed])
        w = [s for _, _, s in ed]
        cur.execute("SELECT id::text id, entities_extracted ee FROM articles WHERE id::text = ANY(%s)", (members,))
        m_ents = {}
        for er in cur.fetchall():
            ee = er["ee"]; arr = ee if isinstance(ee, list) else (ee.get("entities") if isinstance(ee, dict) else None)
            names = []
            if isinstance(arr, list):
                items = [e for e in arr if isinstance(e, dict) and e.get("name")]
                items.sort(key=lambda e: (float(e.get("prominence") or 0), float(e.get("confidence") or 0)), reverse=True)
                names = [str(e["name"]) for e in items[:TOPN_MEMBER]]
            m_ents[er["id"]] = names
        try:
            import leidenalg as la
            comms = [list(c) for c in la.find_partition(g, la.RBConfigurationVertexPartition, weights=w or None, resolution_parameter=RES, seed=42)]
        except Exception:
            comms = [list(c) for c in g.community_leiden(objective_function="modularity", weights=w or None, resolution=RES)]
        subs = [c for c in comms if len(c) >= MIN_SUB_MEMBERS]
        sub_top5 = []
        for c in subs:
            ec = collections.Counter()
            for j in c:
                for nm in m_ents.get(members[j], []):
                    ec[nm] += 1
            sub_top5.append(set(nm for nm, _ in ec.most_common(TOPN_SUB)))
        S = len(sub_top5)
        present = collections.Counter()
        for s in sub_top5:
            for e in s:
                present[e] += 1
        shared_core = [e for e, ct in present.items() if S and ct >= 0.5 * S]
        ubiq = [e for e, ct in present.items() if S and ct >= HUB_UBIQ_FRAC * S]
        if S >= 2:
            jl = [len(a & b) / len(a | b) if (a | b) else 0.0 for a, b in itertools.combinations(sub_top5, 2)]
            mean_j = round(sum(jl) / len(jl), 3)
        else:
            mean_j = None
        hub = ubiq[0] if ubiq else None
        hdf = hub_df(hub) if hub else 0
        generic = hub is not None and hdf >= GENERIC_DF_MIN
        sports_frac = (sum(1 for s in sub_top5 if any(is_sports_entity(e) for e in s)) / S) if S else 0.0
        is_sports = sports_frac >= 0.5

        # ---- classify ----
        if S < 2:
            cls, why = "KEEP", "no-split-coherent"
        elif is_sports and mean_j is not None and SPORTS_BAND[0] <= mean_j <= SPORTS_BAND[1]:
            cls, why = "LLM", "sports-residual"
        elif S < MIN_SUBS:
            cls, why = ("KEEP" if len(shared_core) >= SHARED_CORE_KEEP else "SPLIT"), "few-subs-rescue"
        elif hub is not None and generic and len(shared_core) <= 1:
            cls, why = "SPLIT", "bridge-demote"
        elif mean_j is None:
            cls, why = ("KEEP" if len(shared_core) >= SHARED_CORE_KEEP else "SPLIT"), "jaccard-none"
        else:
            cls, why = ("KEEP" if mean_j >= THETA else "SPLIT"), "jaccard-primary"
        rows.append({"sid": sid, "arts": r["article_count"], "surf": "Y" if surfaced(r) else "N",
                     "S": S, "sc": len(shared_core), "j": mean_j, "hub": hub or "-", "hdf": hdf,
                     "gen": "Y" if generic else "N", "sport": "Y" if is_sports else "N",
                     "cls": cls, "why": why})

    # ---- report ----
    print("\nsid\tarts\tsurf\tS\tsc\tjaccard\thub\thub_df\tgeneric\tsports\tCLASS\treason", flush=True)
    for o in sorted(rows, key=lambda x: (x["j"] is None, x["j"] or 0)):
        print(f"{o['sid'][:8]}\t{o['arts']}\t{o['surf']}\t{o['S']}\t{o['sc']}\t{o['j']}\t{o['hub'][:24]}\t{o['hdf']}\t{o['gen']}\t{o['sport']}\t{o['cls']}\t{o['why']}", flush=True)

    cls_ct = collections.Counter(o["cls"] for o in rows)
    why_ct = collections.Counter(o["why"] for o in rows)
    llm = [o for o in rows if o["cls"] == "LLM"]
    demoted = [o for o in rows if o["why"] == "bridge-demote"]
    print(f"\n=== CLASSIFICATION COUNTS (n={len(rows)}) ===", flush=True)
    print(f"KEEP={cls_ct['KEEP']}  SPLIT={cls_ct['SPLIT']}  LLM-residual={cls_ct['LLM']}", flush=True)
    print(f"by-reason: {dict(why_ct)}", flush=True)
    print(f"\nLLM-RESIDUAL BAND ({len(llm)} clusters = {100*len(llm)/max(len(rows),1):.1f}% of >=100):", flush=True)
    for o in llm:
        print(f"  {o['sid'][:8]} arts={o['arts']} surf={o['surf']} hub={o['hub']} j={o['j']}", flush=True)
    print(f"\nBRIDGE-DEMOTED ({len(demoted)}) — watch for generic-geo-as-event-subject false splits:", flush=True)
    for o in demoted:
        print(f"  {o['sid'][:8]} arts={o['arts']} surf={o['surf']} hub={o['hub']} hub_df={o['hdf']} j={o['j']} sc={o['sc']}", flush=True)
    conn.close()
    print("\n=== END (read-only) ===", flush=True)


if __name__ == "__main__":
    main()
