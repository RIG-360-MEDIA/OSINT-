#!/usr/bin/env python3
"""entity_signature_classify_b.py — variant B classifier + REAL LLM adjudication of the residual.

READ-ONLY. Same metrics as the A run (res-3.0 Leiden, top-3 entities_extracted, top-5/sub).
Variant B: the demote-BOUNDARY (generic hub + sc<=1 + jaccard in [0.13,0.17]) is routed to the
LLM instead of a hard SPLIT; clearly-low generic-hub piles (j<0.13) still hard-SPLIT. Sports-team
hub in [0.10,0.16] also -> LLM. Then we ACTUALLY CALL the LLM on every deferred cluster and print
its verdict (KEEP/SPLIT + reason).

PROVISIONAL params (re-derive on _v8): THETA .13, HUB_UBIQ_FRAC .80, GENERIC_DF_MIN 25,
SHARED_CORE_KEEP 4, MIN_SUBS 4, SPORTS_BAND [.10,.16], DEMOTE_BOUNDARY [.13,.17].
"""
from __future__ import annotations

import asyncio
import collections
import itertools
import os
import sys

import igraph as ig
import psycopg2
import psycopg2.extras

RUN_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 1780452139
RES, MIN_SUB_MEMBERS, TOPN_MEMBER, TOPN_SUB = 3.0, 10, 3, 5
THETA, HUB_UBIQ_FRAC, GENERIC_DF_MIN, SHARED_CORE_KEEP, MIN_SUBS = 0.13, 0.80, 25, 4, 4
SPORTS_BAND, DEMOTE_BOUNDARY = (0.10, 0.16), (0.13, 0.17)
SPORTS_PAT = [s.lower() for s in [
    "Titans", "Super Kings", "Mumbai Indians", "Knight Riders", "Capitals", "Punjab Kings",
    "Rajasthan Royals", "Sunrisers", "Super Giants", "Challengers Bengaluru", "Royal Challengers",
    " FC", "Football Club", "Mohun Bagan", "East Bengal", "Kerala Blasters", "Bengaluru FC"]]

SYS = ("You adjudicate news story clusters. You are shown the sub-communities of ONE cluster; each "
       "sub-community is its most frequent entities plus a representative headline. Decide: is this "
       "ONE coherent mega-event to KEEP whole (every sub-community is a facet/angle/day of the SAME "
       "ongoing event — same core actors and storyline), or a PILE of DISTINCT events that merely "
       "share a common actor, place, topic or template and should be SPLIT? "
       'Respond ONLY with JSON: {"verdict":"KEEP" or "SPLIT","reason":"<=12 words"}. No other text.')


def dsn():
    return (os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC")
            or os.environ["DATABASE_URL"]).replace("+asyncpg", "").replace("+psycopg2", "")


def is_sports(name):
    n = (name or "").lower()
    return any(p in n for p in SPORTS_PAT)


def main():
    conn = psycopg2.connect(dsn())
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT story_id::text, article_count, status, is_template_family, rescued_from_story_id, "
                "suppression_reason, representative_title FROM analytics.story_clusters "
                "WHERE run_id=%s AND article_count>=100 ORDER BY article_count DESC", (RUN_ID,))
    sample = list(cur.fetchall())
    ids = [r["story_id"] for r in sample]
    print(f"=== VARIANT B  clusters>=100: {len(sample)}  (demote-boundary {DEMOTE_BOUNDARY} -> LLM) ===", flush=True)

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

    rows, sub_info = [], {}
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
            top5 = [nm for nm, _ in ec.most_common(TOPN_SUB)]
            top5sets.append(set(top5))
            rep = members[max(c, key=lambda j: deg[j])]
            detail.append((len(c), top5, rep))
        S = len(top5sets)
        present = collections.Counter()
        for s in top5sets:
            for e in s:
                present[e] += 1
        sc = [e for e, ct in present.items() if S and ct >= 0.5 * S]
        ubiq = [e for e, ct in present.items() if S and ct >= HUB_UBIQ_FRAC * S]
        mean_j = round(sum(len(a & b) / len(a | b) if (a | b) else 0 for a, b in itertools.combinations(top5sets, 2)) / (S * (S - 1) / 2), 3) if S >= 2 else None
        hub = ubiq[0] if ubiq else None
        hdf = hub_df(hub) if hub else 0
        generic = hub is not None and hdf >= GENERIC_DF_MIN
        # core is 'all-generic' if it has no event-specific (low-DF) anchor — generalizes sc<=1
        # so it also catches actor-piles whose core is 2+ generic names (e.g. Tinubu+Nigeria)
        core_generic = len(sc) >= 1 and all(hub_df(e) >= GENERIC_DF_MIN for e in sc)
        sportsc = (sum(1 for s in top5sets if any(is_sports(e) for e in s)) / S) if S else 0.0
        sportf = sportsc >= 0.5

        # ---- variant B classify ----
        if S < 2:
            cls, why = "KEEP", "no-split-coherent"
        elif sportf and mean_j is not None and SPORTS_BAND[0] <= mean_j <= SPORTS_BAND[1]:
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
        rows.append({"sid": sid, "arts": r["article_count"], "S": S, "sc": len(sc), "j": mean_j,
                     "hub": hub or "-", "hdf": hdf, "cls": cls, "why": why,
                     "rep": (r["representative_title"] or "")[:70]})
        if cls == "LLM":
            sub_info[sid] = detail

    # ---- LLM adjudication of the deferred band ----
    llm_rows = [o for o in rows if o["cls"] == "LLM"]
    rep_ids = [d[2] for sid in sub_info for d in sub_info[sid]]
    cur.execute("SELECT id::text id, title FROM articles WHERE id::text = ANY(%s)", (rep_ids or ['x'],))
    tt = {x["id"]: (x["title"] or "") for x in cur.fetchall()}

    def signature(sid):
        lines = []
        for sz, top5, rep in sub_info[sid][:10]:
            lines.append(f"- [{sz} articles] entities: {', '.join(top5)} | headline: {tt.get(rep,'')[:80]}")
        return "\n".join(lines)

    async def judge_all():
        import json as _json
        from backend.nlp.groq_client import call_groq
        sem = asyncio.Semaphore(4)
        async def one(o):
            async with sem:
                try:
                    raw = await call_groq(
                        system=SYS,
                        user=f"Cluster '{o['rep']}' has these sub-communities:\n{signature(o['sid'])}",
                        task_type="classification",
                        model="llama-3.3-70b-versatile",  # non-reasoning, strong enough for the call
                        json_response=True,
                    )
                    c = raw.strip()
                    if c.startswith("```"):
                        c = c.split("\n", 1)[1].rsplit("```", 1)[0]
                    try:
                        d = _json.loads(c)
                        v = str(d.get("verdict", "?")).upper()
                        out = f"{v} | {d.get('reason','')}"
                    except Exception:  # truncated JSON — verdict is first, recover it by regex
                        import re as _re
                        m = _re.search(r'verdict"\s*:\s*"(KEEP|SPLIT)', c, _re.I)
                        rs = _re.search(r'reason"\s*:\s*"([^"]*)', c, _re.I)
                        v = m.group(1).upper() if m else "?"
                        out = f"{v} | {(rs.group(1) if rs else '(truncated)')[:120]}"
                except Exception as e:  # noqa: BLE001
                    out = f"ERROR | {type(e).__name__}: {str(e)[:90]}"
                return o, out.strip()
        return await asyncio.gather(*[one(o) for o in llm_rows])

    verdicts = asyncio.run(judge_all()) if llm_rows else []

    # ---- report ----
    cc = collections.Counter(o["cls"] for o in rows)
    print(f"\n=== VARIANT B COUNTS (n={len(rows)}) ===", flush=True)
    print(f"KEEP={cc['KEEP']}  SPLIT={cc['SPLIT']}  LLM={cc['LLM']}  by-reason={dict(collections.Counter(o['why'] for o in rows))}", flush=True)
    print(f"\n=== LLM VERDICTS on the {len(llm_rows)} deferred ({100*len(llm_rows)/len(rows):.1f}%) ===", flush=True)
    for o, out in verdicts:
        v = "KEEP" if out.upper().startswith("KEEP") else ("SPLIT" if out.upper().startswith("SPLIT") else "?")
        print(f"\n[{o['sid'][:8]}] arts={o['arts']} hub={o['hub']}(df{o['hdf']}) j={o['j']} reason={o['why']}", flush=True)
        print(f"  rep: {o['rep']}", flush=True)
        print(f"  LLM-> {v}  :: {out[:200]}", flush=True)
    conn.close()
    print("\n=== END (read-only) ===", flush=True)


if __name__ == "__main__":
    main()
