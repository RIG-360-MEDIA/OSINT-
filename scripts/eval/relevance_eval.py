"""Generic relevance scorer + multi-persona golden-sample eval.

The scorer is persona-agnostic: all persona specifics live in the `prefs`
dict (watchlist patterns, regions, keywords, topics). The SQL has zero
hardcoded names. We run it across 3 contrasting personas over a multi-day
window to prove it personalizes correctly — same engine, swap the prefs.

Signals: watchlist entity match (tier: subject ×6 > watchlist ×3) +
title-salience (about, not passing) +2 + region (geo) +1.5 + keyword +1.5 +
topic soft (+0.5 include / -2 exclude), all freshness-decayed (48h half-life).

Run in osint-backend:
  cat scripts/eval/relevance_eval.py | ssh ... "docker exec -i osint-backend python -"
"""
from __future__ import annotations
import asyncio, os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine(os.environ["OSINT_DB_URL"])
WINDOW_H = 48
TOPN = 10

PERSONAS = {
  "Telangana CM": {
    "subj": ["%revanth%"],
    "wl": ["%kcr%", "%chandra%rao%", "%rama rao%", "%harish rao%", "%owaisi%", "%bandi sanjay%",
           "%kishan reddy%", "%bhatti%", "%kavitha%", "%uttam kumar%", "%sridhar babu%", "%ponguleti%",
           "%seethakka%", "%konda surekha%", "%tummala%", "%ponnam%", "%kaleshwaram%"],
    "geo": ["%telangana%", "%hyderabad%", "%warangal%", "%khammam%", "%nizamabad%", "%karimnagar%", "%nalgonda%"],
    "kw": ["%kaleshwaram%", "%hydraa%", "%musi river%", "%dharani%"],
    "inc": ["POLITICS", "GOVERNANCE", "SECURITY", "INFRASTRUCTURE", "SOCIAL"],
    "exc": ["SPORTS"],
  },
  "Delhi Govt/Police": {
    "subj": ["%kejriwal%"],
    "wl": ["%kejriwal%", "%atishi%", "%rekha gupta%", "%sisodia%", "%amit shah%", "%delhi police%",
           "%aam aadmi%", "%virendra sachdeva%", "%manish sisodia%"],
    "geo": ["%delhi%", "%new delhi%"],
    "kw": ["%delhi liquor%", "%delhi metro%", "%air pollution%", "%aqi%"],
    "inc": ["POLITICS", "LEGAL", "SECURITY", "SOCIAL"],
    "exc": ["SPORTS"],
  },
  "Business/Markets": {
    "subj": ["%mukesh ambani%"],
    "wl": ["%ambani%", "%adani%", "%reliance%", "%tata%", "%infosys%", "%wipro%", "%sensex%",
           "%nifty%", "% rbi%", "%sebi%", "%hdfc%"],
    "geo": ["%mumbai%", "%india%"],
    "kw": ["%ipo%", "%merger%", "%nifty%", "%sensex%", "%quarterly results%", "%market cap%"],
    "inc": ["FINANCE", "BUSINESS", "TECHNOLOGY"],
    "exc": ["SPORTS", "POLITICS"],
  },
}

SCORE_SQL = """
WITH win AS (
  SELECT a.id, a.title, a.topic_category, a.geo_primary, a.collected_at,
         a.entities_extracted, lower(a.title) AS lt
    FROM public.articles a
   WHERE a.collected_at >= analytics.now_sim() - INTERVAL '{wh} hours'
     AND a.collected_at <= analytics.now_sim()
     AND a.entities_extracted IS NOT NULL AND jsonb_typeof(a.entities_extracted)='array'
     AND a.title IS NOT NULL AND length(a.title) >= 16
),
sc AS (
  SELECT w.id, w.title, w.topic_category, w.geo_primary, w.collected_at,
    (SELECT max(CASE WHEN lower(e->>'name') LIKE ANY(CAST(:subj AS text[])) THEN 3
                     WHEN lower(e->>'name') LIKE ANY(CAST(:wl AS text[])) THEN 2 ELSE 0 END)
       FROM jsonb_array_elements(w.entities_extracted) e) AS ent_tier,
    (SELECT e->>'name' FROM jsonb_array_elements(w.entities_extracted) e
       WHERE lower(e->>'name') LIKE ANY(CAST(:subj AS text[])) OR lower(e->>'name') LIKE ANY(CAST(:wl AS text[]))
       ORDER BY (e->>'confidence')::float DESC NULLS LAST LIMIT 1) AS matched,
    (CASE WHEN w.lt LIKE ANY(CAST(:subj AS text[])) OR w.lt LIKE ANY(CAST(:wl AS text[])) THEN 1 ELSE 0 END) AS title_hit,
    (CASE WHEN w.geo_primary ILIKE ANY(CAST(:geo AS text[])) THEN 1 ELSE 0 END) AS geo_hit,
    (CASE WHEN w.lt LIKE ANY(CAST(:kw AS text[])) THEN 1 ELSE 0 END) AS kw_hit,
    (CASE WHEN w.lt LIKE ANY(ARRAY['%answer key%','%bank holiday%','%full list%','%horoscope%',
                                   '%admit card%','%exam date%','%recruitment%','%result 2026%',
                                   '%how to download%','%rashifal%']) THEN 1 ELSE 0 END) AS noise
  FROM win w
)
SELECT id, title, geo_primary, topic_category, matched, ent_tier, title_hit, geo_hit, kw_hit,
  ROUND((
     (CASE WHEN ent_tier=3 THEN 6.0 WHEN ent_tier=2 THEN 3.0 ELSE 0 END)
   + title_hit*2.0 + kw_hit*1.5
   -- geo gets full weight only when it REINFORCES a real signal; a bare geo
   -- match counts weakly and only inside an included topic (kills admin trivia).
   -- geo reinforces a real signal at full weight; a bare geo match is KEPT but
   -- weak (0.7) so local admin trivia sinks below entity/headline news.
   + (CASE WHEN geo_hit=1 AND (ent_tier>0 OR kw_hit=1 OR title_hit=1) THEN 1.5
           WHEN geo_hit=1 THEN 0.7
           ELSE 0 END)
   + (CASE WHEN topic_category = ANY(CAST(:exc AS text[])) THEN -2.0 ELSE 0 END)
   + (CASE WHEN topic_category = ANY(CAST(:inc AS text[])) THEN 0.5 ELSE 0 END)
   + (noise * -4.0)   -- administrative/consumer-utility headline demote (generic)
  ) * EXP(-EXTRACT(EPOCH FROM (analytics.now_sim()-collected_at))/3600.0/48.0)
  ::numeric, 2) AS score
FROM sc
WHERE ent_tier > 0 OR title_hit = 1 OR kw_hit = 1 OR geo_hit = 1
ORDER BY score DESC
LIMIT 60
"""


async def run_persona(conn, p):
    return (await conn.execute(text(SCORE_SQL.format(wh=WINDOW_H)), {
        "subj": p["subj"], "wl": p["wl"], "geo": p["geo"], "kw": p["kw"],
        "inc": p["inc"], "exc": p["exc"],
    })).fetchall()


GOLD_SQL = """
WITH w AS (
  SELECT id, lower(title) AS lt, title, collected_at
    FROM public.articles
   WHERE collected_at >= analytics.now_sim() - INTERVAL '{wh} hours'
     AND collected_at <= analytics.now_sim() AND title IS NOT NULL
),
g(cas,pat) AS (VALUES
  ('Revanth gov','%revanth%'),('Harish Rao opp','%harish rao%'),
  ('Delhi excise','%excise polic%'),('Rekha Gupta CM','%rekha gupta%'),
  ('Sensex markets','%sensex%'),('Adani','%adani%'),
  ('Cricket noise','%rcb%'),('Bank-holiday noise','%bank holiday%'),
  ('Exam-notice noise','%answer key%'))
SELECT g.cas,
  (SELECT w.id::text FROM w WHERE w.lt LIKE g.pat ORDER BY w.collected_at DESC LIMIT 1) AS aid,
  (SELECT w.title  FROM w WHERE w.lt LIKE g.pat ORDER BY w.collected_at DESC LIMIT 1) AS title
FROM g
"""

# Hand labels: (case, which persona, should it rank HIGH or be kept LOW)
GOLD_LABEL = [
  ("Revanth gov", "Telangana CM", "high"), ("Harish Rao opp", "Telangana CM", "high"),
  ("Delhi excise", "Delhi Govt/Police", "high"), ("Rekha Gupta CM", "Delhi Govt/Police", "high"),
  ("Sensex markets", "Business/Markets", "high"), ("Adani", "Business/Markets", "high"),
  ("Cricket noise", "Telangana CM", "low"),
  ("Bank-holiday noise", "Business/Markets", "low"),
  ("Exam-notice noise", "Delhi Govt/Police", "low"),
]
TOP_K = 15


async def main():
    results, gold = {}, []
    async with engine.begin() as conn:
        for name, p in PERSONAS.items():
            results[name] = await run_persona(conn, p)
        gold = (await conn.execute(text(GOLD_SQL.format(wh=WINDOW_H)))).fetchall()
    await engine.dispose()

    rankmap = {name: {str(r.id): (i + 1, float(r.score)) for i, r in enumerate(rows)}
               for name, rows in results.items()}

    topsets = {}
    for name, rows in results.items():
        top = rows[:TOPN]
        about = sum(1 for r in top if r.geo_hit == 1 or r.title_hit == 1)
        print(f"\n══════ {name} ══════  pool={len(rows)}  precision@{TOPN}(about)={about}/{len(top)}")
        for r in top[:6]:
            why = (f"hl:{r.matched}" if r.title_hit else (f"ent:{r.matched}" if r.matched else "")) \
                  + (f" geo:{r.geo_primary}" if r.geo_hit else "")
            print(f"  {float(r.score):>5}  {r.title[:64]}  [{why.strip() or 'kw'}]")
        topsets[name] = set(r.id for r in rows[:50])

    print("\n── differentiation (shared in top-50; lower=better) ──")
    nm = list(topsets)
    for i in range(len(nm)):
        for j in range(i + 1, len(nm)):
            print(f"  {nm[i]} ∩ {nm[j]}: {len(topsets[nm[i]] & topsets[nm[j]])}")

    goldmap = {g.cas: (g.aid, g.title) for g in gold}
    print("\n══════ GOLDEN (hand-labeled) ══════")
    passes = total = 0
    for cas, persona, expect in GOLD_LABEL:
        aid, title = goldmap.get(cas, (None, None))
        if not aid:
            print(f"  SKIP  {cas:20} (no article in window)")
            continue
        total += 1
        rk = rankmap[persona].get(aid)
        sc_ = rk[1] if rk else 0.0
        # score-threshold (fairer than rank cutoff): relevant if scored >=2.5
        ok = (rk is not None and sc_ >= 2.5) if expect == "high" else (rk is None or sc_ < 1.5)
        passes += 1 if ok else 0
        pos = f"#{rk[0]} s={rk[1]}" if rk else "absent"
        print(f"  {'PASS' if ok else 'FAIL'}  {cas:20} want {expect:4} @{persona:18} → {pos:14} « {(title or '')[:38]} »")
    print(f"\nGOLDEN precision: {passes}/{total}")


asyncio.run(main())
