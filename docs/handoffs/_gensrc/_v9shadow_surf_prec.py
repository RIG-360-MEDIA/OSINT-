#!/usr/bin/env python3
"""Surfaceable same-event precision of the confident-merge SHADOW keeper (story_clusters_v9shadow,
source_count>=3) — local-32B judge. Answers Phase-1: does the confident backbone beat the ~25% v7 floor?"""
import asyncio, re, json, random, collections, aiohttp, psycopg2
random.seed(21)
LURL = "http://172.30.0.1:11434"; LMODEL = "qwen2.5:32b"; SEM = asyncio.Semaphore(12)
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
async def judge(sess, a, b):
    body = {"model": LMODEL, "messages": [{"role": "system", "content": SYS},
            {"role": "user", "content": f"A: {desc(a)}\nB: {desc(b)}"}],
            "stream": False, "format": "json", "options": {"temperature": 0, "num_predict": 60}}
    async with SEM:
        for _ in range(2):
            try:
                async with sess.post(LURL + "/api/chat", json=body, timeout=aiohttp.ClientTimeout(total=90)) as r:
                    d = await r.json(); v = pj(d.get("message", {}).get("content", ""))
                    if v is not None: return v
            except Exception: pass
        return None
async def main():
    async with aiohttp.ClientSession() as s:
        res = [x for x in await asyncio.gather(*[judge(s, a, b) for a, b in pairs]) if x is not None]
    P = 100 * sum(res) / max(len(res), 1)
    print(f"PREC v9shadow SURFACEABLE (>=3src, confident-only): {sum(res)}/{len(res)} = {P:.0f}%  "
          f"(v7 floor ~25%, v9+gray ~81%)", flush=True)
asyncio.run(main())
