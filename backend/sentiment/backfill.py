#!/usr/bin/env python3
"""Two-lane sentiment backfill worker. Runs inside rig-backend.
Claims articles via SKIP LOCKED (each scored exactly once), scores their qualifying
entities (Option C: DICT_MATCH + high-confidence open), upserts, marks done.

Lanes:
  --lane cloud   : batches B (entity,text) items/request, rotates keys + (provider,model) combos
  --lane ollama  : one guided-JSON call per item to a local Ollama endpoint (no rate cap)

Usage (inside container):
  python3 backfill.py --lane cloud   --id c1 --claim 40 --batch 4 --conc 16
  python3 backfill.py --lane ollama  --id t7 --endpoint http://172.30.0.1:11501 --conc 12
"""
import os, sys, json, re, time, argparse, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
import psycopg2
from psycopg2.extras import execute_values

DSN=os.environ.get("DATABASE_URL_SYNC","postgresql://rig:@rig-postgres:5432/rig")
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125 Safari/537.36"
SCHEMA={"type":"object","properties":{
    "stance":{"type":"string","enum":["positive","negative","neutral"]},
    "impact":{"type":"string","enum":["positive","negative","neutral","not_relevant"]},
    "impact_confidence":{"type":"number"}},"required":["stance","impact"]}
# --target stances : map the v2 stance vocab -> legacy article_stances vocab.
# We reuse the SAME per-entity scoring; only the write target + label differ. The
# actor_entity_id is filled by the trg_link_stance_entity BEFORE-INSERT trigger
# (exact name_norm match against entity_lookup) — our actors are clean NER names,
# so they resolve at least as well as the substrate's free-text actors.
STANCE_TO_LEGACY={"positive":"supportive","negative":"critical","neutral":"neutral"}
CLOUD={"groq":("https://api.groq.com/openai/v1/chat/completions","GROQ_API_KEYS"),
       "cerebras":("https://api.cerebras.ai/v1/chat/completions","CEREBRAS_API_KEYS")}
# gate-passing (provider, model) combos rotated for the cloud lane
CLOUD_MODELS=[("groq","llama-3.3-70b-versatile"),("cerebras","llama-3.3-70b"),("groq","openai/gpt-oss-120b")]
SYS_ONE=("You are a precise media analyst. stance=TONE toward the subject (praise/criticise/neither): "
"positive/negative/neutral. impact=are EVENTS good/bad for the subject by CONSEQUENCES "
"(fine/loss/arrest/expulsion=negative; win/deal/award=positive; plain mention=neutral; no stake=not_relevant). "
'Reply ONLY JSON {"stance":"...","impact":"...","impact_confidence":0.0-1.0}.')
SYS_BATCH=("You are a precise media analyst. For EACH numbered item judge its SUBJECT on TWO dims: "
"stance (tone toward subject: positive/negative/neutral) and impact (events good/bad for subject by "
"consequences: positive/negative/neutral/not_relevant). "
'Reply ONLY JSON {"results":[{"n":1,"stance":"...","impact":"...","impact_confidence":0.0-1.0},...]} '
"one entry per item in order, exactly as many as given.")
def um1(e,x): return f"ARTICLE:\n{x[:1500]}\n\nSUBJECT: {e}\n\nReturn JSON."
# per-article multi-subject (local lane): one call scores ALL an article's entities (shared prefill)
BATCH_SCHEMA={"type":"object","properties":{"results":{"type":"array","items":{
    "type":"object","properties":{"stance":{"type":"string","enum":["positive","negative","neutral"]},
    "impact":{"type":"string","enum":["positive","negative","neutral","not_relevant"]},
    "impact_confidence":{"type":"number"}},"required":["stance","impact"]}}},"required":["results"]}
SYS_M=("You are a precise media analyst. For the article, judge EACH numbered subject on TWO dims: "
"stance (tone toward subject: positive/negative/neutral) and impact (events good/bad for the subject by "
"consequences: fine/loss/arrest/expulsion=negative; win/deal/award=positive; plain mention=neutral; no stake=not_relevant). "
'Reply ONLY JSON {"results":[{"stance":"..","impact":"..","impact_confidence":0.0-1.0},...]} one per subject, in order.')
def umM(text,subs):
    numbered="\n".join(f"{i+1}. {s}" for i,s in enumerate(subs))
    return f"ARTICLE:\n{text[:1500]}\n\nSUBJECTS:\n{numbered}\n\nReturn JSON."
def umB(items): return ("Score all "+str(len(items))+" items.\n\n"+
    "\n\n".join(f"ITEM {i+1} — SUBJECT: {e}\nARTICLE: {x[:1500]}" for i,(_,e,x) in enumerate(items))+"\n\nReturn JSON.")
def norm(v,nr=False):
    v=str(v).lower()
    return "not_relevant" if (nr and "not" in v) else "positive" if "pos" in v else "negative" if "neg" in v else "neutral" if "neu" in v else None
def qualify(ents):
    seen=set(); out=[]
    for e in ents or []:
        # entities_extracted elements are usually dicts, but SOME cuttings store bare
        # name strings — treat those as a high-confidence named entity (never .get() a str).
        if isinstance(e,str):
            n=e.strip(); sc=1.0; label=None
        elif isinstance(e,dict):
            n=(e.get("name") or "").strip()
            # articles carry confidence(+label); cuttings/clips carry prominence only.
            sc=e.get("confidence")
            if sc is None: sc=e.get("prominence")
            label=e.get("label")
        else:
            continue
        if not n or len(n)>80: continue
        if label=="DICT_MATCH" or (sc or 0)>=0.5:
            k=n.lower()
            if k in seen: continue
            seen.add(k); out.append(n)
            if len(out)>=8: break
    return out

# --source selects the pillar: which queue, its id column, how to fetch text+entities,
# and where to write. entities_extracted has the SAME shape across articles+cuttings,
# so qualify()/scoring are unchanged — only the source table + write target differ.
SOURCES={
  "articles":{"queue":"analytics.sentiment_backfill_queue","idcol":"article_id",
    "fetch":"SELECT a.id, coalesce(a.title,'')||' — '||coalesce(a.lead_text_original,a.lead_text_translated,''), a.entities_extracted FROM public.articles a WHERE a.id = ANY(%s::uuid[])",
    "write":"analytics.article_entity_sentiment"},
  "cuttings":{"queue":"analytics.clipping_sentiment_queue","idcol":"clipping_id",
    "fetch":"SELECT c.id, coalesce(c.headline_translated,c.headline,'')||' — '||coalesce(c.body_text_translated,c.body_text,''), c.entities_extracted FROM public.clippings c WHERE c.id = ANY(%s::uuid[])",
    "write":"analytics.clipping_entity_sentiment"},
}

def http(url,key,payload):
    req=urllib.request.Request(url,data=json.dumps(payload).encode(),
        headers={"Authorization":"Bearer "+key,"Content-Type":"application/json","User-Agent":UA})
    return json.loads(urllib.request.urlopen(req,timeout=90).read())["choices"][0]["message"]["content"]

# ---- claim / fetch / write ----
def claim(conn, n, wid, qtable, src):
    idc=src["idcol"]
    with conn.cursor() as c:
        c.execute(f"""UPDATE {qtable} q SET status='processing',worker=%s,
            attempts=attempts+1,updated_at=now()
            FROM (SELECT {idc} FROM {qtable} WHERE status='pending'
                  ORDER BY pub_at DESC NULLS LAST LIMIT %s FOR UPDATE SKIP LOCKED) s
            WHERE q.{idc}=s.{idc} RETURNING q.{idc}""",(wid,n))
        ids=[r[0] for r in c.fetchall()]; conn.commit()
        if not ids: return []
        c.execute(src["fetch"],(ids,))
        got={r[0]:(r[1],r[2]) for r in c.fetchall()}
    return [(aid, got.get(aid,("",None))[0], got.get(aid,("",None))[1]) for aid in ids]

def write(conn, rows, done_ids, retry_ids, qtable, target, src):
    idc=src["idcol"]
    with conn.cursor() as c:
        if rows:
            if target=="stances":
                # rows shape: (aid,entity,stance,impact,impact_confidence,model)
                # -> article_stances(article_id,actor,stance[legacy],intensity).
                # DELETE-then-insert per article for idempotency on retry (mirrors
                # the substrate _persist_stances contract), then the trigger links
                # actor_entity_id.
                aids=list({r[0] for r in rows})
                c.execute("DELETE FROM public.article_stances WHERE article_id=ANY(%s::uuid[])",(aids,))
                srows=[(r[0], r[1][:200], STANCE_TO_LEGACY.get(r[2], r[2]),
                        max(0.0, min(1.0, float(r[4]) if r[4] is not None else 0.5)))
                       for r in rows]
                execute_values(c, """INSERT INTO public.article_stances
                    (article_id,actor,stance,intensity) VALUES %s""", srows)
            else:
                execute_values(c, f"""INSERT INTO {src['write']}
                    ({idc},entity,stance,impact,impact_confidence,model) VALUES %s
                    ON CONFLICT ({idc},entity) DO NOTHING""", rows)
        if done_ids:
            c.execute(f"UPDATE {qtable} SET status='done',updated_at=now() WHERE {idc}=ANY(%s::uuid[])",(done_ids,))
        if retry_ids:  # scoring failed -> back to pending, or 'error' after too many tries
            c.execute(f"""UPDATE {qtable}
                SET status=(CASE WHEN attempts>=8 THEN 'error' ELSE 'pending' END),updated_at=now()
                WHERE {idc}=ANY(%s::uuid[])""",(retry_ids,))
    conn.commit()
MAXTRY=8

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--lane",required=True,choices=["cloud","ollama"])
    ap.add_argument("--id",required=True); ap.add_argument("--endpoint",default="http://127.0.0.1:11434")
    ap.add_argument("--model",default="qwen2.5:7b-instruct")
    ap.add_argument("--claim",type=int,default=40); ap.add_argument("--batch",type=int,default=4)
    ap.add_argument("--conc",type=int,default=12); ap.add_argument("--limit",type=int,default=0)
    ap.add_argument("--source",default="articles",choices=list(SOURCES.keys()))
    ap.add_argument("--queue",default=None)
    ap.add_argument("--target",default="entity_sentiment",choices=["entity_sentiment","stances"])
    a=ap.parse_args()
    src=SOURCES[a.source]
    queue=a.queue or src["queue"]
    conn=psycopg2.connect(DSN)
    # startup reap: reset stale processing rows
    with conn.cursor() as c:
        c.execute(f"UPDATE {queue} SET status='pending' WHERE status='processing' AND updated_at < now()-interval '20 min'")
    conn.commit()
    keys={p:[k.strip() for k in os.environ.get(v,'').split(',') if k.strip()] for p,(_,v) in CLOUD.items()}
    rr={"i":0}
    def score_cloud(items):
        out=[None]*len(items)
        for att in range(4):                      # retry rate-limits w/ backoff + rotate key+model
            prov,model=CLOUD_MODELS[rr["i"]%len(CLOUD_MODELS)]; rr["i"]+=1
            url,_=CLOUD[prov]; kl=keys[prov]; key=kl[rr["i"]%len(kl)]
            try:
                c=http(url,key,{"model":model,"temperature":0,"max_tokens":700,"response_format":{"type":"json_object"},
                    "messages":[{"role":"system","content":SYS_BATCH},{"role":"user","content":umB(items)}]})
                m=re.search(r"\{.*\}",c,re.S); res=json.loads(m.group(0)).get("results",[]) if m else []
                for k in range(len(items)):
                    if k<len(res) and isinstance(res[k],dict):
                        s=norm(res[k].get("stance")); im=norm(res[k].get("impact"),True)
                        if s and im: out[k]=(s,im,res[k].get("impact_confidence"),model)
                return out
            except urllib.error.HTTPError as e:
                if e.code in (429,500,502,503) and att<3: time.sleep(1.5*(att+1)); continue
                return out
            except Exception:
                return out
        return out
    def score_ollama(item):
        _,e,x=item
        try:
            c=http_ollama(a.endpoint,a.model,e,x); j=json.loads(c)
            s=norm(j.get("stance")); im=norm(j.get("impact"),True)
            if s and im: return (s,im,j.get("impact_confidence"),a.model)
        except Exception: pass
        return None
    def http_ollama(ep,model,e,x):
        body=json.dumps({"model":model,"stream":False,"options":{"temperature":0},"format":SCHEMA,
            "messages":[{"role":"system","content":SYS_ONE},{"role":"user","content":um1(e,x)}]}).encode()
        req=urllib.request.Request(ep.rstrip('/')+"/api/chat",data=body,headers={"Content-Type":"application/json"})
        return json.loads(urllib.request.urlopen(req,timeout=90).read())["message"]["content"]
    def score_ollama_article(text, subs):   # one call, all entities of one article
        out=[None]*len(subs)
        try:
            body=json.dumps({"model":a.model,"stream":False,"options":{"temperature":0},"format":BATCH_SCHEMA,
                "messages":[{"role":"system","content":SYS_M},{"role":"user","content":umM(text,subs)}]}).encode()
            req=urllib.request.Request(a.endpoint.rstrip('/')+"/api/chat",data=body,headers={"Content-Type":"application/json"})
            res=json.loads(json.loads(urllib.request.urlopen(req,timeout=120).read())["message"]["content"]).get("results",[])
            for k in range(len(subs)):
                if k<len(res) and isinstance(res[k],dict):
                    s=norm(res[k].get("stance")); im=norm(res[k].get("impact"),True)
                    if s and im: out[k]=(s,im,res[k].get("impact_confidence"),a.model)
        except Exception: pass
        return out
    total=0; t0=time.time()
    while True:
        try:
            claimed=claim(conn,a.claim,a.id,queue,src)
            if not claimed: print(f"[{a.id}] queue drained",flush=True); break
            items=[]
            for aid,text,ents in claimed:
                for name in qualify(ents): items.append((aid,name,text))
            rows=[]
            if a.lane=="cloud":
                batches=[items[i:i+a.batch] for i in range(0,len(items),a.batch)]
                with ThreadPoolExecutor(max_workers=a.conc) as ex:
                    for bat,res in zip(batches, ex.map(score_cloud,batches)):
                        for (aid,name,_),r in zip(bat,res):
                            if r: rows.append((aid,name,r[0],r[1],r[2],r[3]))
            else:  # local: one call per article scoring all its entities
                byart={}
                for aid,name,text in items: byart.setdefault(aid,[text,[]]); byart[aid][1].append(name)
                arts=list(byart.items())
                with ThreadPoolExecutor(max_workers=a.conc) as ex:
                    res=list(ex.map(lambda kv: score_ollama_article(kv[1][0], kv[1][1]), arts))
                for (aid,(text,names)),rl in zip(arts,res):
                    for name,r in zip(names,rl):
                        if r: rows.append((aid,name,r[0],r[1],r[2],r[3]))
            have={it[0] for it in items}; got={r[0] for r in rows}
            cids=[aid for aid,_,_ in claimed]
            done_ids=[x for x in cids if x not in have or x in got]
            retry_ids=[x for x in cids if x in have and x not in got]
            write(conn,rows,done_ids,retry_ids,queue,a.target,src)
            total+=len(done_ids)
            if total % (a.claim*5)==0 or total<=a.claim:
                print(f"[{a.id}] {total} done, {len(rows)} last rows, {total/(time.time()-t0):.1f} art/s",flush=True)
            if a.limit and total>=a.limit: print(f"[{a.id}] hit limit {a.limit}",flush=True); break
        except Exception as ex:
            print(f"[{a.id}] loop error: {type(ex).__name__} {str(ex)[:90]}",flush=True)
            try: conn.rollback()
            except Exception:
                try: conn.close()
                except Exception: pass
                conn=psycopg2.connect(DSN)
            time.sleep(2)
    try: conn.close()
    except Exception: pass

if __name__=="__main__": main()
