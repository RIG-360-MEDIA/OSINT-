#!/usr/bin/env python3
"""v8_reconfirm_discriminator.py — ONE-COMMAND re-confirmation of the split/keep rule on _v8.

Run AFTER the _v8 dark clustering lands. READ-ONLY on production; writes NOTHING to the DB
(reads the dark _v8 tables, emits a raw report to stdout). For every cluster >=100 it:

  1. sub-splits the member subgraph (Leiden res 3.0, score-weighted), top-5 clean entities
     per sub-community (entities_extracted top-3 by prominence — NOT the alias AEM matviews).
  2. RE-DERIVES GENERIC_DF_MIN from the _v8 hub/core DF histogram (prints the histogram, the
     event-subject/generic gap, and the chosen cutoff — does NOT hardcode 25).
  3. RE-DERIVES THETA from the jaccard gap, and re-confirms HUB_UBIQ_FRAC / SHARED_CORE_KEEP /
     MIN_SUBS / the two bands (reports whether each still separates; FLAGs any that don't).
  4. runs the full variant-B + LLM pass with the RE-DERIVED params -> KEEP / SPLIT / LLM for
     every >=100 cluster, with the LLM verdict on each deferred cluster.
  5. prints: re-derived params, classification table, boundary/gap check — raw. Analytics locks.

LOCKED structural rule (do NOT change): the demote condition is GENERALIZED — DEMOTE/LLM when
the shared-core is ALL-GENERIC (every core entity DF >= GENERIC_DF_MIN), NOT bare sc<=1. Only
the numeric params (GENERIC_DF_MIN, THETA) are re-derived here.

Usage:
  AB_DSN=... python v8_reconfirm_discriminator.py <run_id>
Env overrides (defaults are the kickoff's dark _v8 names):
  CLUSTERS_TBL=analytics.story_clusters_v8  MEMBERS_TBL=analytics.story_cluster_members_v8
  EDGES_TBL=analytics.story_edges_v8        LLM_MODEL=llama-3.3-70b-versatile
  PROVISIONAL fallbacks if a derivation is degenerate: GENERIC_DF_MIN=25, THETA=0.13.
"""
from __future__ import annotations

import asyncio
import collections
import itertools
import json as _json
import math
import os
import re
import sys

import igraph as ig
import psycopg2
import psycopg2.extras

# ---- config (structural params LOCKED; numeric ones re-derived below) ----
RUN_ID = int(sys.argv[1]) if len(sys.argv) > 1 else None
CLUSTERS_TBL = os.environ.get("CLUSTERS_TBL", "analytics.story_clusters_v8")
MEMBERS_TBL = os.environ.get("MEMBERS_TBL", "analytics.story_cluster_members_v8")
EDGES_TBL = os.environ.get("EDGES_TBL", "analytics.story_edges_v8")
LLM_MODEL = os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile")
RES, MIN_SUB_MEMBERS, TOPN_MEMBER, TOPN_SUB = 3.0, 10, 3, 5
HUB_UBIQ_FRAC, SHARED_CORE_KEEP, MIN_SUBS = 0.80, 4, 4          # structural — re-confirmed, not re-derived
SPORTS_BAND, DEMOTE_BOUNDARY = (0.10, 0.16), (0.13, 0.17)
FALLBACK_DF_MIN, FALLBACK_THETA = 25, 0.13
SPORTS_PAT = [s.lower() for s in [
    "Titans", "Super Kings", "Mumbai Indians", "Knight Riders", "Capitals", "Punjab Kings",
    "Rajasthan Royals", "Sunrisers", "Super Giants", "Challengers Bengaluru", "Royal Challengers",
    " FC", "Football Club", "Mohun Bagan", "East Bengal", "Kerala Blasters", "Bengaluru FC"]]

SYS = ("You adjudicate news story clusters. You are shown the sub-communities of ONE cluster; each "
       "sub-community is its most frequent entities plus a representative headline. Decide: is this "
       "ONE coherent mega-event to KEEP whole (every sub-community is a facet/angle/day of the SAME "
       "ongoing event — same core actors and storyline), or a PILE of DISTINCT events that merely "
       "share a common actor, place, topic or template and should be SPLIT? If every sub-community "
       "concerns the SAME single match/incident/day (same teams/actors, same period), answer KEEP; "
       "do NOT infer multiple seasons, editions, or separate events unless the entities or headline "
       "years EXPLICITLY differ. "
       'Reply with EXACTLY one line: "KEEP | <=12 word reason" or "SPLIT | <=12 word reason". '
       "No other text, no JSON, no preamble.")


def dsn():
    d = os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC") or os.environ.get("DATABASE_URL")
    if not d:
        sys.exit("no DSN (AB_DSN/DATABASE_URL_SYNC/DATABASE_URL)")
    return d.replace("+asyncpg", "").replace("+psycopg2", "")


def is_sports(name):
    n = (name or "").lower()
    return any(p in n for p in SPORTS_PAT)


def log_hist(vals, label):
    """Print a coarse log-bucketed histogram of integer DF values."""
    b = collections.Counter()
    for v in vals:
        b["0" if v <= 0 else ("1-3" if v <= 3 else ("4-9" if v <= 9 else ("10-24" if v <= 24 else ("25-49" if v <= 49 else ("50-99" if v <= 99 else "100+")))))] += 1
    order = ["1-3", "4-9", "10-24", "25-49", "50-99", "100+"]
    print(f"  {label} DF histogram: " + "  ".join(f"{k}:{b.get(k,0)}" for k in order), flush=True)


def derive_generic_df_min(hub_dfs):
    """Bimodal split of per-cluster HUB DFs (event-subjects sit low, generic actors/geos high).
    Largest multiplicative gap with the low side >=3 (ignore DF1-2 noise) -> geometric-mid cutoff."""
    xs = sorted({d for d in hub_dfs if d > 0})
    if len(xs) < 4:
        return FALLBACK_DF_MIN, f"FALLBACK (too few hubs: {len(xs)})"
    best = (1.0, None)
    for a, b in zip(xs, xs[1:]):
        if a < 3:           # ignore the very-low-DF noise floor; the meaningful split is higher
            continue
        r = b / max(a, 1)
        if r > best[0]:
            best = (r, (a, b))
    if best[1] is not None and best[0] >= 3.0:
        a, b = best[1]
        return int(round(math.sqrt(a * b))), f"hub-DF ratio-gap {a}->{b} (x{best[0]:.1f}); event-subjects<= {a}, generics>= {b}"
    # tier 2: no clean ratio gap -> valley = largest ABSOLUTE gap in the mid-range [5,100]
    mid = [x for x in xs if 5 <= x <= 100]
    if len(mid) >= 2:
        a, b = max(zip(mid, mid[1:]), key=lambda p: p[1] - p[0])
        if b - a >= 8:
            return int(round((a + b) / 2)), f"hub-DF valley {a}->{b} (no clean ratio gap, max {best[0]:.1f}x); cutoff = mid"
    return FALLBACK_DF_MIN, f"FALLBACK 25 (no ratio gap [max {best[0]:.1f}x] and no clear valley — inspect histogram)"


def derive_theta(jaccards):
    """Largest empty interval in the jaccard boundary window -> midpoint cutoff."""
    js = sorted(j for j in jaccards if j is not None and 0.05 <= j <= 0.30)
    if len(js) < 4:
        return FALLBACK_THETA, f"FALLBACK (too few jaccards: {len(js)})", js
    best = (0.0, None)
    for a, b in zip(js, js[1:]):
        if b - a > best[0]:
            best = (b - a, (a, b))
    if best[1] is None or best[0] < 0.01:
        return FALLBACK_THETA, f"FALLBACK (no clean gap; widest {best[0]:.3f})", js
    a, b = best[1]
    return round((a + b) / 2, 3), f"gap [{a},{b}] width {best[0]:.3f}", js


def main():
    if RUN_ID is None:
        sys.exit("usage: python v8_reconfirm_discriminator.py <run_id>")
    conn = psycopg2.connect(dsn())
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    print(f"=== _v8 RE-CONFIRM  run={RUN_ID}  tables={CLUSTERS_TBL}/{MEMBERS_TBL}/{EDGES_TBL} ===", flush=True)

    cur.execute(f"SELECT story_id::text, article_count, status, is_template_family, rescued_from_story_id, "
                f"suppression_reason, representative_title FROM {CLUSTERS_TBL} "
                f"WHERE run_id=%s AND article_count>=100 ORDER BY article_count DESC", (RUN_ID,))
    sample = list(cur.fetchall())
    ids = [r["story_id"] for r in sample]
    if not sample:
        sys.exit(f"no clusters >=100 in {CLUSTERS_TBL} run {RUN_ID} — is the _v8 build done?")
    print(f"clusters >=100: {len(sample)}", flush=True)

    cur.execute(f"SELECT article_id::text aid, story_id::text sid FROM {MEMBERS_TBL} WHERE story_id::text = ANY(%s)", (ids,))
    m2s = {x["aid"]: x["sid"] for x in cur.fetchall()}
    members_of = collections.defaultdict(list)
    for aid, sid in m2s.items():
        members_of[sid].append(aid)
    cur.execute(f"SELECT article_a::text a, article_b::text b, score FROM {EDGES_TBL} WHERE run_id=%s", (RUN_ID,))
    edges_of = collections.defaultdict(list)
    for x in cur.fetchall():
        a, b = x["a"], x["b"]
        if m2s.get(a) and m2s.get(a) == m2s.get(b) and a != b:
            edges_of[m2s[a]].append((a, b, float(x["score"]) if x["score"] is not None else 1.0))

    df_cache = {}
    def hub_df(name):
        k = (name or "").lower()
        if k not in df_cache:
            cur.execute(f"SELECT count(*) c FROM {CLUSTERS_TBL} WHERE run_id=%s AND primary_entities ? %s", (RUN_ID, k))
            df_cache[k] = cur.fetchone()["c"]
        return df_cache[k]

    # ---- PASS 1: gather per-cluster metrics (no classification yet) ----
    feats = []
    for r in sample:
        sid = r["story_id"]; members = members_of[sid]
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
                its = [e for e in arr if isinstance(e, dict) and e.get("name")]
                its.sort(key=lambda e: (float(e.get("prominence") or 0), float(e.get("confidence") or 0)), reverse=True)
                names = [str(e["name"]) for e in its[:TOPN_MEMBER]]
            m_ents[er["id"]] = names
        try:
            import leidenalg as la
            comms = [list(c) for c in la.find_partition(g, la.RBConfigurationVertexPartition, weights=w or None, resolution_parameter=RES, seed=42)]
        except Exception:
            comms = [list(c) for c in g.community_leiden(objective_function="modularity", weights=w or None, resolution=RES)]
        subs = sorted([c for c in comms if len(c) >= MIN_SUB_MEMBERS], key=len, reverse=True)
        deg = g.degree()
        detail, top5sets = [], []
        for c in subs:
            ec = collections.Counter()
            for j in c:
                for nm in m_ents.get(members[j], []):
                    ec[nm] += 1
            t5 = [nm for nm, _ in ec.most_common(TOPN_SUB)]
            top5sets.append(set(t5))
            detail.append((len(c), t5, members[max(c, key=lambda j: deg[j])]))
        S = len(top5sets)
        present = collections.Counter()
        for s in top5sets:
            for e in s:
                present[e] += 1
        sc = [e for e, ct in present.items() if S and ct >= 0.5 * S]
        ubiq = [e for e, ct in present.items() if S and ct >= HUB_UBIQ_FRAC * S]
        mean_j = round(sum(len(a & b) / len(a | b) if (a | b) else 0 for a, b in itertools.combinations(top5sets, 2)) / (S * (S - 1) / 2), 3) if S >= 2 else None
        max_ubiq = round(max(present.values()) / S, 2) if S else None
        sportf = (sum(1 for s in top5sets if any(is_sports(e) for e in s)) / S >= 0.5) if S else False
        feats.append({"r": r, "sid": sid, "S": S, "sc": sc, "ubiq": ubiq, "mean_j": mean_j,
                      "max_ubiq": max_ubiq, "sportf": sportf, "detail": detail})

    # ---- RE-DERIVE numeric params from the _v8 distribution ----
    # genericness cutoff is derived from per-cluster HUB DFs (bimodal: event-subjects low, generics
    # high) — NOT all core entities, whose DF is continuous and has no clean gap at scale.
    hub_core_dfs = [hub_df(f["ubiq"][0]) for f in feats if f["ubiq"]]
    GENERIC_DF_MIN, df_why = derive_generic_df_min(hub_core_dfs)
    THETA, theta_why, js_sorted = derive_theta([f["mean_j"] for f in feats])

    print("\n=== RE-DERIVED PARAMS (from _v8, not hardcoded) ===", flush=True)
    log_hist(hub_core_dfs, "hub/core")
    print(f"  GENERIC_DF_MIN -> {GENERIC_DF_MIN}   [{df_why}]", flush=True)
    print(f"  THETA          -> {THETA}   [{theta_why}]", flush=True)
    inb = [j for j in js_sorted if DEMOTE_BOUNDARY[0] <= j <= DEMOTE_BOUNDARY[1]]
    print(f"  jaccard near boundary {DEMOTE_BOUNDARY}: {len(inb)} clusters -> {'CLEAN gap' if not inb else 'MUDDY (LLM band)'}", flush=True)

    # ---- RE-CONFIRM structural params (report separation; FLAG if degraded) ----
    print("\n=== RE-CONFIRM structural params ===", flush=True)
    hubbed = sum(1 for f in feats if f["max_ubiq"] is not None and f["max_ubiq"] >= HUB_UBIQ_FRAC)
    print(f"  HUB_UBIQ_FRAC={HUB_UBIQ_FRAC}: {hubbed}/{len(feats)} clusters have a hub at >={HUB_UBIQ_FRAC} ubiquity "
          f"({'OK' if hubbed else 'FLAG: no hubs — frac too high'})", flush=True)
    fewsub = [f for f in feats if 2 <= f["S"] < MIN_SUBS]
    bigsub = [f for f in feats if f["S"] >= MIN_SUBS]
    def jstd(fs):
        xs = [f["mean_j"] for f in fs if f["mean_j"] is not None]
        return round(statistics_pstdev(xs), 3) if len(xs) > 1 else None
    print(f"  MIN_SUBS={MIN_SUBS}: {len(fewsub)} few-sub clusters (jaccard treated unstable); shared_core distribution "
          f"of few-sub = {sorted(len(f['sc']) for f in fewsub)}", flush=True)
    sc_keep = [len(f["sc"]) for f in feats if f["mean_j"] is not None and f["mean_j"] >= THETA]
    sc_split = [len(f["sc"]) for f in feats if f["mean_j"] is not None and f["mean_j"] < THETA]
    print(f"  SHARED_CORE_KEEP={SHARED_CORE_KEEP}: shared_core where j>=THETA (lean keep) median="
          f"{_median(sc_keep)} vs j<THETA (lean split) median={_median(sc_split)} "
          f"({'separates' if _median(sc_keep) > _median(sc_split) else 'FLAG: no separation'})", flush=True)
    sportj = sorted(f["mean_j"] for f in feats if f["sportf"] and f["mean_j"] is not None)
    print(f"  SPORTS_BAND={SPORTS_BAND}: sports-cluster jaccards = {sportj} "
          f"({sum(1 for j in sportj if SPORTS_BAND[0] <= j <= SPORTS_BAND[1])}/{len(sportj)} in band)", flush=True)

    # ---- PASS 2: classify (variant B, generalized all-generic-core demote) ----
    rows, sub_info = [], {}
    for f in feats:
        S, sc, ubiq, mean_j = f["S"], f["sc"], f["ubiq"], f["mean_j"]
        hub = ubiq[0] if ubiq else None
        hdf = hub_df(hub) if hub else 0
        core_generic = len(sc) >= 1 and all(hub_df(e) >= GENERIC_DF_MIN for e in sc)
        if S < 2:
            cls, why = "KEEP", "no-split-coherent"
        elif f["sportf"] and mean_j is not None and SPORTS_BAND[0] <= mean_j <= SPORTS_BAND[1]:
            cls, why = "LLM", "sports-residual"
        elif S < MIN_SUBS:
            cls, why = ("KEEP" if len(sc) >= SHARED_CORE_KEEP else "SPLIT"), "few-subs-rescue"
        elif core_generic:
            if mean_j is not None and DEMOTE_BOUNDARY[0] <= mean_j <= DEMOTE_BOUNDARY[1]:
                cls, why = "LLM", "demote-boundary"
            elif mean_j is not None and mean_j < DEMOTE_BOUNDARY[0]:
                cls, why = "SPLIT", "bridge-demote"
            else:
                cls, why = ("KEEP" if (mean_j or 0) >= THETA else "SPLIT"), "jaccard-primary"
        elif mean_j is None:
            cls, why = ("KEEP" if len(sc) >= SHARED_CORE_KEEP else "SPLIT"), "jaccard-none"
        else:
            cls, why = ("KEEP" if mean_j >= THETA else "SPLIT"), "jaccard-primary"
        rows.append({"sid": f["sid"], "arts": f["r"]["article_count"], "S": S, "sc": len(sc),
                     "j": mean_j, "hub": hub or "-", "hdf": hdf, "cls": cls, "why": why,
                     "rep": (f["r"]["representative_title"] or "")[:70]})
        if cls == "LLM":
            sub_info[f["sid"]] = f["detail"]

    # ---- LLM adjudication of the deferred band ----
    llm_rows = [o for o in rows if o["cls"] == "LLM"]
    rep_ids = [d[2] for sid in sub_info for d in sub_info[sid]]
    cur.execute("SELECT id::text id, title FROM articles WHERE id::text = ANY(%s)", (rep_ids or ['x'],))
    tt = {x["id"]: (x["title"] or "") for x in cur.fetchall()}

    def signature(sid):
        return "\n".join(f"- [{sz} articles] entities: {', '.join(t5)} | headline: {tt.get(rep,'')[:80]}"
                         for sz, t5, rep in sub_info[sid][:10])

    async def judge_all():
        from backend.nlp.groq_client import call_groq
        sem = asyncio.Semaphore(4)
        async def one(o):
            async with sem:
                try:
                    raw = await call_groq(system=SYS, user=f"Cluster '{o['rep']}' sub-communities:\n{signature(o['sid'])}",
                                          task_type="brief_generation", model=LLM_MODEL)  # llama chain (avoids qwen3 TPD)
                    c = " ".join(raw.strip().split())
                    m = re.search(r"\b(KEEP|SPLIT)\b", c, re.I)
                    out = f"{(m.group(1).upper() if m else '?')} | {c[:130]}"
                except Exception as e:  # noqa: BLE001
                    out = f"ERROR | {type(e).__name__}: {str(e)[:90]}"
                return o, out.strip()
        return await asyncio.gather(*[one(o) for o in llm_rows])

    verdicts = [] if os.environ.get("NO_LLM") else (asyncio.run(judge_all()) if llm_rows else [])

    # ---- REPORT ----
    cc = collections.Counter(o["cls"] for o in rows)
    final = collections.Counter()
    vmap = {}
    for o, out in verdicts:
        vmap[o["sid"]] = "KEEP" if out.upper().startswith("KEEP") else ("SPLIT" if out.upper().startswith("SPLIT") else "?")
    for o in rows:
        final[o["cls"] if o["cls"] != "LLM" else (vmap.get(o["sid"], "?"))] += 1

    print(f"\n=== CLASSIFICATION (n={len(rows)}) ===", flush=True)
    print(f"rule: KEEP={cc['KEEP']} SPLIT={cc['SPLIT']} LLM-deferred={cc['LLM']} ({100*cc['LLM']/len(rows):.1f}%)", flush=True)
    print(f"by-reason: {dict(collections.Counter(o['why'] for o in rows))}", flush=True)
    print(f"FINAL after LLM: KEEP={final['KEEP']} SPLIT={final['SPLIT']} unresolved={final.get('?',0)}", flush=True)

    print("\nsid\tarts\tS\tsc\tjaccard\thub\thub_df\tCLASS\treason", flush=True)
    for o in sorted(rows, key=lambda x: (x["j"] is None, x["j"] or 0)):
        print(f"{o['sid'][:8]}\t{o['arts']}\t{o['S']}\t{o['sc']}\t{o['j']}\t{o['hub'][:22]}\t{o['hdf']}\t{o['cls']}\t{o['why']}", flush=True)

    print(f"\n=== LLM VERDICTS ({len(llm_rows)} deferred) ===", flush=True)
    for o, out in verdicts:
        print(f"[{o['sid'][:8]}] arts={o['arts']} hub={o['hub']}(df{o['hdf']}) j={o['j']} {o['why']} | rep: {o['rep']}\n   LLM-> {out[:160]}", flush=True)

    conn.close()
    print("\n=== END (read-only; nothing written to DB) ===", flush=True)


def statistics_pstdev(xs):
    import statistics
    return statistics.pstdev(xs)


def _median(xs):
    if not xs:
        return None
    s = sorted(xs)
    return s[len(s) // 2]


if __name__ == "__main__":
    main()
