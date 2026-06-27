#!/usr/bin/env python3
"""Independent double-check of the confident-backbone surfaceable precision.
Re-judges the SAME 150 surfaceable pairs (seed=21) with TWO model families:
  - qwen2.5:32b (local) — the original judge
  - llama-3.3-70b-versatile (Groq, Meta family) — the INDEPENDENT judge
Reports each judge's same-event %, their agreement, and the cross-tab."""
import asyncio, re, json, random, collections, aiohttp, psycopg2, sys
sys.path.insert(0, "/app")
from backend.nlp.groq_client import call_groq
random.seed(21)
LURL = "http://172.30.0.1:11434"; QWEN = "qwen2.5:32b"; LLAMA = "llama-3.3-70b-versatile"
SEM = asyncio.Semaphore(12)
conn = psycopg2.connect(host="rig-postgres", dbname="rig", user="rig", password=""); conn.autocommit = True
cur = conn.cursor()
cur.execute("""
  SELECT m.article_id::text, m.story_id
  FROM analytics.story_cluster_members_v9shadow m
  JOIN analytics.story_clusters_v9shadow c ON c.story_id = m.story_id
  WHERE c.source_count >= 3
""")
byc = collections.defaultdict(list)
for a, sid in cur.fetchall():
    byc[sid].append(a)
cl = [c for c, m in byc.items() if 2 <= len(m) <= 300]
random.shuffle(cl)
pairs = []
for c in cl:
    a, b = random.sample(byc[c], 2)
    pairs.append((a, b))
    if len(pairs) >= 150:
        break
need = {x for p in pairs for x in p}
cur.execute("SELECT id::text, coalesce(title,''), coalesce(left(lead_text_translated,160),left(lead_text_original,160),'') "
            "FROM articles WHERE id = ANY(%s::uuid[])", (list(need),))
TXT = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
def desc(a):
    t, l = TXT.get(a, ("", "")); return (t + " -- " + l)[:240]
SYS = ('You judge whether two news items report the SAME specific news EVENT -- same incident, same day(s), '
       'same actors/place -- NOT merely same topic/person/tournament/genre. Return ONLY JSON {"same_event": true|false}.')
def pj(c):
    for m in reversed(re.findall(r'\{[^{}]*\}', c or '')):
        try:
            d = json.loads(m)
            if "same_event" in d: return bool(d["same_event"])
        except Exception: pass
    return None
def usr(a, b):
    return f"A: {desc(a)}\nB: {desc(b)}"
async def qwen_judge(sess, a, b):
    body = {"model": QWEN, "messages": [{"role": "system", "content": SYS}, {"role": "user", "content": usr(a, b)}],
            "stream": False, "format": "json", "options": {"temperature": 0, "num_predict": 60}}
    async with SEM:
        for _ in range(2):
            try:
                async with sess.post(LURL + "/api/chat", json=body, timeout=aiohttp.ClientTimeout(total=90)) as r:
                    d = await r.json(); v = pj(d.get("message", {}).get("content", ""))
                    if v is not None: return v
            except Exception: pass
        return None
async def llama_judge(a, b):
    for _ in range(2):
        try:
            r = await call_groq(system=SYS, user=usr(a, b), task_type="generation",
                                model=LLAMA, json_response=True, max_tokens_override=60, temperature_override=0.0)
            v = pj(r or "")
            if v is not None: return v
        except Exception: pass
    return None
async def _llama_raw(a, b):
    try:
        return await call_groq(system=SYS, user=usr(a, b), task_type="generation",
                               model=LLAMA, json_response=True, max_tokens_override=60, temperature_override=0.0)
    except Exception as e:
        return f"EXC {type(e).__name__}: {str(e)[:120]}"
async def main():
    async with aiohttp.ClientSession() as s:
        qs = await asyncio.gather(*[qwen_judge(s, a, b) for a, b in pairs])
        ls = await asyncio.gather(*[llama_judge(a, b) for a, b in pairs])
    nq = sum(1 for q in qs if q is not None)
    nl = sum(1 for l in ls if l is not None)
    print(f"qwen non-None: {nq}/{len(pairs)}   llama non-None: {nl}/{len(pairs)}", flush=True)
    if nq:
        qy_all = sum(1 for q in qs if q)
        print(f"QWEN  same-event: {qy_all}/{nq} = {100*qy_all/nq:.0f}%   (original judge; first run=76%)", flush=True)
    if nl:
        ly_all = sum(1 for l in ls if l)
        print(f"LLAMA same-event: {ly_all}/{nl} = {100*ly_all/nl:.0f}%   (INDEPENDENT, Meta 70B)", flush=True)
    both = [(q, l) for q, l in zip(qs, ls) if q is not None and l is not None]
    n = len(both)
    if n == 0:
        print("(no agreement stats — one judge unavailable; compare LLAMA% above vs qwen first-run 76%)", flush=True)
        return
    qy = sum(1 for q, _ in both if q)
    ly = sum(1 for _, l in both if l)
    agree = sum(1 for q, l in both if q == l)
    bb = sum(1 for q, l in both if q and l)        # both say same-event
    nn = sum(1 for q, l in both if not q and not l)  # both say different
    qonly = sum(1 for q, l in both if q and not l)
    lonly = sum(1 for q, l in both if l and not q)
    print(f"pairs judged by both: {n}", flush=True)
    print(f"QWEN  same-event: {qy}/{n} = {100*qy/n:.0f}%   (original judge)", flush=True)
    print(f"LLAMA same-event: {ly}/{n} = {100*ly/n:.0f}%   (independent, Meta 70B)", flush=True)
    print(f"AGREEMENT: {agree}/{n} = {100*agree/n:.0f}%   "
          f"[both-same={bb}, both-diff={nn}, qwen-only={qonly}, llama-only={lonly}]", flush=True)
asyncio.run(main())
