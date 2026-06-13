"""A/B/C eval: relevance scorer v1 vs v2 vs v3, judged by an independent LLM.

No human labels exist, so we use an LLM judge as pseudo-ground-truth: for each
(user, article) in a contested sample, the judge rates relevance 0-1. Then per user we
measure how well each scorer's ranking AGREES with the judge (Spearman rank-corr, NDCG@10,
precision@10 with judge>=0.5). Higher agreement = better. Run inside rig-backend.
"""
import asyncio
import json
import math
import statistics

import psycopg2

from backend.nlp.relevance_scorer import (
    compute_stage1_score, compute_entity_score, compute_entity_score_v2,
    compute_stage1_score_v3,
)

conn = psycopg2.connect(host="rig-postgres", port=5432, dbname="rig", user="rig", password="")
cur = conn.cursor()

# ---- alias_map for #1 canonicalization (alias.lower() -> canonical.lower()); empty if table absent
alias_map = {}
try:
    cur.execute("SELECT canonical_name, aliases FROM entity_dictionary WHERE aliases IS NOT NULL")
    for canon, aliases in cur.fetchall():
        if not canon:
            continue
        al = aliases
        if isinstance(al, str):
            try:
                al = json.loads(al)
            except Exception:
                al = [x for x in al.split(",")]
        if isinstance(al, list):
            for a in al:
                if a:
                    alias_map[str(a).strip().lower()] = canon.strip().lower()
    print(f"alias_map: {len(alias_map)} alias->canonical pairs")
except Exception as e:
    print(f"alias_map unavailable ({str(e)[:80]}); v3 canonicalization = identity")
    conn.rollback()

SYN = [
 dict(name="SYN-BROAD", profile=dict(signal_priorities={"POLITICS":9}, geo_primary="", geo_secondary=[], role_context="national politics analyst"),
   entities=[{"canonical_name":"Narendra Modi","priority":10},{"canonical_name":"Bharatiya Janata Party","priority":9},{"canonical_name":"All India Trinamool Congress","priority":9}]),
 dict(name="SYN-GEO", profile=dict(signal_priorities={}, geo_primary="Telangana", geo_secondary=["Hyderabad"], role_context="Telangana desk"),
   entities=[{"canonical_name":"Telangana","priority":6},{"canonical_name":"Hyderabad","priority":6},{"canonical_name":"Revanth Reddy","priority":8}]),
 dict(name="SYN-POWER", profile=dict(signal_priorities={"POLITICS":7,"BUSINESS":6}, geo_primary="", geo_secondary=[], role_context="power user"),
   entities=[{"canonical_name":"Narendra Modi","priority":10},{"canonical_name":"Donald J. Trump","priority":7},{"canonical_name":"Iran","priority":6},{"canonical_name":"Israel","priority":6},{"canonical_name":"Telangana","priority":5},{"canonical_name":"Hyderabad","priority":4}]),
]

# ---- real users (with a non-empty watchlist) for the definitive eval
cur.execute("""
 SELECT up.user_id, up.geo_primary, up.geo_secondary, up.signal_priorities, up.role_context,
  json_agg(json_build_object('canonical_name', ue.canonical_name,'priority', ue.priority))
    FILTER (WHERE ue.canonical_name IS NOT NULL) AS entities
 FROM user_profiles up LEFT JOIN user_entities ue ON ue.user_id=up.user_id
 GROUP BY up.user_id, up.geo_primary, up.geo_secondary, up.signal_priorities, up.role_context
""")
REAL = []
for uid, gp, gs, sp, rc, ents in cur.fetchall():
    if ents:
        REAL.append(dict(name="REAL:" + str(uid)[:8],
            profile=dict(signal_priorities=sp or {}, geo_primary=gp or "", geo_secondary=gs or [], role_context=rc or ""),
            entities=ents))
USERS = REAL + SYN
print(f"users: {len(REAL)} real (with watchlist) + {len(SYN)} synthetic = {len(USERS)}")

cur.execute("""
 SELECT id, title, lead_text_translated, lead_text_original, topic_category, geo_primary,
        source_tier, entities_extracted, nlp_confidence, published_at
 FROM articles WHERE substrate_status='ok' AND collected_at > now()-interval '10 days'
   AND jsonb_typeof(entities_extracted)='array' ORDER BY collected_at DESC LIMIT 800
""")
arts = []
for r in cur.fetchall():
    ee = r[7]
    if isinstance(ee, str):
        ee = json.loads(ee)
    arts.append(dict(id=str(r[0]), title=r[1], lead_text_translated=r[2], lead_text_original=r[3],
                     topic_category=r[4], geo_primary=r[5], source_tier=r[6], entities_extracted=ee or [],
                     nlp_confidence=r[8], published_at=r[9], source_name=None))
print(f"== {len(arts)} articles, {len(SYN)} synthetic users ==")


def score_all(a, prof, ue):
    v1, _ = compute_stage1_score(a, prof, ue, [], entity_scorer=compute_entity_score)
    v2, _ = compute_stage1_score(a, prof, ue, [], entity_scorer=compute_entity_score_v2)
    v3, _ = compute_stage1_score_v3(a, prof, ue, [], alias_map=alias_map)
    return v1, v2, v3


def spearman(xs, ys):
    n = len(xs)
    if n < 3:
        return 0.0
    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        rk = [0.0]*n
        i = 0
        while i < n:
            j = i
            while j+1 < n and v[order[j+1]] == v[order[i]]:
                j += 1
            avg = (i+j)/2.0
            for k in range(i, j+1):
                rk[order[k]] = avg
            i = j+1
        return rk
    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a-mx)*(b-my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a-mx)**2 for a in rx) * sum((b-my)**2 for b in ry))
    return num/den if den else 0.0


def ndcg_at(order_idx, gains, k=10):
    dcg = sum((gains[i]/math.log2(rank+2)) for rank, i in enumerate(order_idx[:k]))
    ideal = sorted(gains, reverse=True)
    idcg = sum((g/math.log2(rank+2)) for rank, g in enumerate(ideal[:k]))
    return dcg/idcg if idcg else 0.0


JUDGE_SYS = ('Rate how relevant a news article is to THIS reader\'s monitoring interests. '
             '1.0 = directly about a watched entity/place/topic; 0.5 = tangentially related; '
             '0.0 = unrelated. Output ONLY JSON: {"relevance": 0.0-1.0}.')


async def judge_all(pairs):
    from backend.nlp.groq_client import call_groq
    sem = asyncio.Semaphore(6)
    async def one(p):
        a, prof, ue = p["a"], p["prof"], p["ue"]
        lead = (a["lead_text_translated"] or a["lead_text_original"] or "")[:400]
        watch = ", ".join(f"{e['canonical_name']}(p{e['priority']})" for e in ue)
        user = (f"Reader: {prof['role_context']}; watches entities: {watch}; "
                f"geo: {prof['geo_primary'] or 'none'}.\nArticle: {a['title']}\n{lead}")
        async with sem:
            # 'relevance_explanation' is NOT a fast-task type, so the model= is honored
            # (classification would force FAST_MODEL=qwen3-32b, which is TPD-exhausted).
            # llama-3.1-8b-instant has huge TPD headroom + is non-reasoning. Lenient parse
            # (no strict json_response → avoids the Cerebras JSON-validate 400s). Retry twice.
            import re as _re
            for attempt in range(3):
                try:
                    raw = await call_groq(system=JUDGE_SYS, user=user,
                                          task_type="relevance_explanation",
                                          model="llama-3.1-8b-instant")
                    m = _re.search(r'(?:relevance"?\s*[:=]\s*)?([01]?\.\d+|[01](?!\d))', raw)
                    if m:
                        return p, max(0.0, min(1.0, float(m.group(1))))
                except Exception:
                    await asyncio.sleep(1.0)
            return p, None
    return await asyncio.gather(*[one(p) for p in pairs])


def main():
    results = {}
    judge_pairs = []
    per_user_scored = {}
    for u in USERS:
        prof, ue = u["profile"], u["entities"]
        scored = []
        for a in arts:
            v1, v2, v3 = score_all(a, prof, ue)
            scored.append(dict(id=a["id"], a=a, v1=v1, v2=v2, v3=v3))
        per_user_scored[u["name"]] = scored
        # contested judge sample: union of each scorer's top-15 + 10 mid-rank
        idx = {}
        for key in ("v1", "v2", "v3"):
            for s in sorted(scored, key=lambda x: -x[key])[:15]:
                idx[s["id"]] = s
        mid = sorted(scored, key=lambda x: -x["v3"])[20:40:2]
        for s in mid:
            idx[s["id"]] = s
        for s in idx.values():
            judge_pairs.append(dict(uname=u["name"], a=s["a"], prof=prof, ue=ue, sid=s["id"]))
    print(f"judging {len(judge_pairs)} (user,article) pairs with llama-3.3-70b ...", flush=True)
    judged = asyncio.run(judge_all(judge_pairs))
    jmap = {}
    for p, rel in judged:
        if rel is not None:
            jmap[(p["uname"], p["sid"])] = rel
    print(f"judge returned {len(jmap)} valid scores\n", flush=True)

    print(f"{'user':12s} {'metric':10s} {'v1':>7s} {'v2':>7s} {'v3':>7s}")
    agg = {k: {"spear": [], "ndcg": [], "p10": []} for k in ("v1", "v2", "v3")}
    for u in USERS:
        scored = per_user_scored[u["name"]]
        judged_items = [s for s in scored if (u["name"], s["id"]) in jmap]
        if len(judged_items) < 5:
            continue
        gains = [jmap[(u["name"], s["id"])] for s in judged_items]
        line_sp, line_nd, line_p10 = [], [], []
        for key in ("v1", "v2", "v3"):
            xs = [s[key] for s in judged_items]
            sp = spearman(xs, gains)
            order = sorted(range(len(judged_items)), key=lambda i: -xs[i])
            nd = ndcg_at(order, gains, 10)
            top10 = order[:10]
            p10 = sum(1 for i in top10 if gains[i] >= 0.5) / max(len(top10), 1)
            agg[key]["spear"].append(sp); agg[key]["ndcg"].append(nd); agg[key]["p10"].append(p10)
            line_sp.append(sp); line_nd.append(nd); line_p10.append(p10)
        print(f"{u['name']:12s} {'spearman':10s} {line_sp[0]:7.3f} {line_sp[1]:7.3f} {line_sp[2]:7.3f}")
        print(f"{'':12s} {'ndcg@10':10s} {line_nd[0]:7.3f} {line_nd[1]:7.3f} {line_nd[2]:7.3f}")
        print(f"{'':12s} {'prec@10':10s} {line_p10[0]:7.3f} {line_p10[1]:7.3f} {line_p10[2]:7.3f}")
    print("\n=== MEAN across users (higher = closer to the independent judge) ===")
    for metric in ("spear", "ndcg", "p10"):
        vals = {k: statistics.mean(agg[k][metric]) if agg[k][metric] else 0.0 for k in ("v1", "v2", "v3")}
        win = max(vals, key=vals.get)
        print(f"  {metric:8s}: v1={vals['v1']:.3f}  v2={vals['v2']:.3f}  v3={vals['v3']:.3f}   -> WINNER {win}")


if __name__ == "__main__":
    main()
