import json, statistics, sys
import psycopg2
from backend.nlp.relevance_scorer import (
    compute_stage1_score, compute_entity_score, compute_entity_score_v2,
)

conn = psycopg2.connect(host="rig-postgres", port=5432, dbname="rig", user="rig", password="")
cur = conn.cursor()

# ---- load real users
cur.execute("""
SELECT up.user_id, up.geo_primary, up.geo_secondary, up.signal_priorities, up.role_context,
 json_agg(json_build_object('canonical_name', ue.canonical_name,'priority', ue.priority))
   FILTER (WHERE ue.canonical_name IS NOT NULL) AS entities
FROM user_profiles up
LEFT JOIN user_entities ue ON ue.user_id=up.user_id
GROUP BY up.user_id, up.geo_primary, up.geo_secondary, up.signal_priorities, up.role_context
""")
real = []
for uid, gp, gs, sp, rc, ents in cur.fetchall():
    ents = ents or []
    real.append(dict(
        name="REAL:" + str(uid)[:8],
        profile=dict(signal_priorities=sp or {}, geo_primary=gp or "",
                     geo_secondary=gs or [], role_context=rc or ""),
        entities=ents))

# ---- synthetic users (canonical names verified present in data)
synth = [
 dict(name="SYN-BROAD",
   profile=dict(signal_priorities={"POLITICS":9}, geo_primary="", geo_secondary=[], role_context="national politics analyst"),
   entities=[{"canonical_name":"Narendra Modi","priority":10},
             {"canonical_name":"Bharatiya Janata Party","priority":9},
             {"canonical_name":"All India Trinamool Congress","priority":9}]),
 dict(name="SYN-NICHE",
   profile=dict(signal_priorities={}, geo_primary="", geo_secondary=[], role_context="defence-PSU watcher"),
   entities=[{"canonical_name":"Rashtriya Ispat Nigam","priority":8}]),
 dict(name="SYN-GEO",
   profile=dict(signal_priorities={}, geo_primary="Telangana", geo_secondary=["Hyderabad"], role_context="Telangana desk"),
   entities=[{"canonical_name":"Telangana","priority":6},
             {"canonical_name":"Hyderabad","priority":6}]),
 dict(name="SYN-POWER",
   profile=dict(signal_priorities={"POLITICS":7,"BUSINESS":6}, geo_primary="", geo_secondary=[], role_context="power user"),
   entities=[{"canonical_name":"Narendra Modi","priority":10},
             {"canonical_name":"Bharatiya Janata Party","priority":8},
             {"canonical_name":"Donald J. Trump","priority":7},
             {"canonical_name":"United States","priority":5},
             {"canonical_name":"Iran","priority":6},
             {"canonical_name":"Israel","priority":6},
             {"canonical_name":"Russia and China","priority":5},
             {"canonical_name":"Life Insurance Corporation of India","priority":7},
             {"canonical_name":"United Spirits","priority":4},
             {"canonical_name":"Telangana","priority":5},
             {"canonical_name":"Hyderabad","priority":4}]),
]
users = real + synth

# ---- load articles
cur.execute("""
SELECT id, title, lead_text_translated, lead_text_original, topic_category, geo_primary,
       source_tier, entities_extracted, nlp_confidence
FROM articles
WHERE substrate_status='ok' AND collected_at > now()-interval '10 days'
  AND jsonb_typeof(entities_extracted)='array'
LIMIT 600
""")
arts = []
for r in cur.fetchall():
    ee = r[7]
    if isinstance(ee, str):
        ee = json.loads(ee)
    arts.append(dict(id=r[0], title=r[1], lead_text_translated=r[2], lead_text_original=r[3],
                     topic_category=r[4], geo_primary=r[5], source_tier=r[6],
                     entities_extracted=ee or [], nlp_confidence=r[8]))

def tier(s):
    if s>=0.50: return 1
    if s>=0.25: return 2
    if s>=0.10: return 3
    return 0

def n_matches(art, uents):
    names={e["name"].lower() for e in art["entities_extracted"] if e.get("name") and e["name"]!="None"}
    return sum(1 for ue in uents if ue["canonical_name"].lower() in names)

print(f"== {len(arts)} articles, {len(real)} real users, {len(synth)} synthetic ==")
for u in real:
    print(f"   {u['name']} watchlist={len(u['entities'])} geo={u['profile']['geo_primary']}")

for u in users:
    ue = u["entities"]; prof=u["profile"]
    rows=[]
    for a in arts:
        o,_ = compute_stage1_score(a, prof, ue, [])
        n,_ = compute_stage1_score(a, prof, ue, [], entity_scorer=compute_entity_score_v2)
        rows.append((a["id"], o, n, n_matches(a, ue), a))
    to=[tier(r[1]) for r in rows]; tn=[tier(r[2]) for r in rows]
    def dist(ts): return {k:ts.count(k) for k in (1,2,3,0)}
    print(f"\n### {u['name']}  (watchlist={len(ue)})")
    print(f"  TIERS old {dist(to)}  ->  new {dist(tn)}")
    # multi-entity discrimination
    print("  match-bucket mean(old)->mean(new) [count]:")
    for b,lbl in [(0,"0"),(1,"1"),(2,"2"),(3,"3+")]:
        sel=[r for r in rows if (r[3]==b if b<3 else r[3]>=3)]
        if sel:
            mo=statistics.mean(r[1] for r in sel); mn=statistics.mean(r[2] for r in sel)
            print(f"    {lbl}: {mo:.3f} -> {mn:.3f}  [{len(sel)}]")
    # ranking churn top15
    top_o=set(r[0] for r in sorted(rows,key=lambda r:-r[1])[:15])
    top_n=set(r[0] for r in sorted(rows,key=lambda r:-r[2])[:15])
    ov=len(top_o&top_n)
    print(f"  top15 overlap: {ov}/15 = {100*ov/15:.0f}%")
    # biggest movers by rank
    ro={r[0]:i for i,r in enumerate(sorted(rows,key=lambda r:-r[1]))}
    rn={r[0]:i for i,r in enumerate(sorted(rows,key=lambda r:-r[2]))}
    movers=sorted(rows,key=lambda r:-(ro[r[0]]-rn[r[0]]))  # moved UP in new
    def desc(r):
        a=r[4]; names=[(e["name"],e.get("prominence")) for e in a["entities_extracted"]
                       if e.get("name") and e["name"].lower() in {x["canonical_name"].lower() for x in ue}]
        return f"id={r[0]} rank {ro[r[0]]}->{rn[r[0]]} old={r[1]:.3f} new={r[2]:.3f} m={r[3]} {names} :: {(a['title'] or '')[:60]}"
    print("  UP movers:"); [print("    "+desc(m)) for m in movers[:3]]
    print("  DOWN movers:"); [print("    "+desc(m)) for m in movers[-3:]]
    # passing-mention floor: articles with a matched entity all at prominence 0 (or floor) that flip into feed
    flips=0; fl_ex=[]
    for r in rows:
        a=r[4]
        matched=[e for e in a["entities_extracted"]
                 if e.get("name") and e["name"].lower() in {x["canonical_name"].lower() for x in ue}]
        if matched and all((e.get("prominence") or 0)==0 for e in matched):
            if tier(r[1])==0 and tier(r[2])>=3:
                flips+=1
                if len(fl_ex)<2: fl_ex.append((r[0],r[1],r[2]))
    print(f"  passing-mention(prom=0) flips 0->feed: {flips}  ex={fl_ex}")

# primary-vs-secondary example pair: find a high-prom #1 article vs a name-drop-many article
pu=synth[3]  # power user
ue=pu["entities"]; prof=pu["profile"]
def score_pair(a):
    o,_=compute_stage1_score(a,prof,ue,[]); n,_=compute_stage1_score(a,prof,ue,[],entity_scorer=compute_entity_score_v2)
    return o,n
central=[]; namedrop=[]
for a in arts:
    matched=[(e["name"],e.get("prominence") or 0) for e in a["entities_extracted"]
             if e.get("name") and e["name"].lower() in {x["canonical_name"].lower() for x in ue}]
    if not matched: continue
    modi=[m for m in matched if m[0].lower()=="narendra modi" and m[1]>=0.6]
    if modi and len(matched)<=2: central.append((a["id"],matched,score_pair(a)))
    if len(matched)>=3 and all(m[1]<=0.3 for m in matched): namedrop.append((a["id"],matched,score_pair(a)))
print("\n### PRIMARY-vs-SECONDARY (power user)")
print("  central #1 (Modi prom>=.6) examples:")
for c in central[:2]: print("    ",c)
print("  many-low-prom name-drop examples:")
for c in namedrop[:2]: print("    ",c)
