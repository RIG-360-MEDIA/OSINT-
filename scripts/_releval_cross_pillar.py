"""Per-user relevance QUALITY across all 3 pillars (articles / clips / cuttings).
For each user with a watchlist, pulls their TOP-10 scored items per pillar (from the
relevance tables), has an LLM judge rate each item's true relevance, and reports
precision@10 (judge>=0.5) + mean judge score. Higher = the scorer surfaces genuinely
relevant items for that pillar. Run inside rig-backend.
"""
import asyncio
import statistics

import psycopg2

# pillar: (rel_table, fk, item_table, id_col, title_col, text_col)
PILLARS = {
    "article": ("user_article_relevance", "article_id", "articles", "id", "title", "lead_text_translated"),
    "clip":    ("user_clip_relevance", "clip_id", "youtube_clips_v2", "id", "video_title", "summary"),
    "cutting": ("user_cutting_relevance", "clipping_id", "clippings", "id", "headline", "body_text_translated"),
}
JUDGE_SYS = ('Rate how relevant a news item is to THIS reader\'s monitoring interests. '
             '1.0 = directly about a watched entity/place/topic; 0.5 = tangential; 0.0 = unrelated. '
             'Output ONLY JSON: {"relevance": 0.0-1.0}.')

conn = psycopg2.connect(host="rig-postgres", port=5432, dbname="rig", user="rig", password="")
cur = conn.cursor()
cur.execute("""
 SELECT up.user_id::text, up.geo_primary, up.role_context,
   string_agg(ue.canonical_name, ', ') FILTER (WHERE ue.canonical_name IS NOT NULL)
 FROM user_profiles up LEFT JOIN user_entities ue ON ue.user_id=up.user_id
 GROUP BY up.user_id, up.geo_primary, up.role_context
 HAVING string_agg(ue.canonical_name, ', ') FILTER (WHERE ue.canonical_name IS NOT NULL) IS NOT NULL
""")
USERS = [dict(uid=r[0], geo=r[1] or "", role=r[2] or "", watch=r[3]) for r in cur.fetchall()]
print(f"users with watchlist: {len(USERS)}", flush=True)


def top_items(uid, pillar, n=10):
    rt, fk, it, idc, tcol, xcol = PILLARS[pillar]
    cur.execute(f"""
        SELECT r.score_final, i.{tcol}, COALESCE(i.{xcol},'')
        FROM {rt} r JOIN {it} i ON i.{idc} = r.{fk}
        WHERE r.user_id = %s::uuid ORDER BY r.score_final DESC NULLS LAST LIMIT %s
    """, (uid, n))
    return cur.fetchall()


async def judge(pairs):
    from backend.nlp.groq_client import call_groq
    import re
    sem = asyncio.Semaphore(6)
    async def one(p):
        u, title, text = p
        msg = f"Reader: {u['role']}; watches: {u['watch']}; geo: {u['geo'] or 'none'}.\nItem: {title}\n{(text or '')[:400]}"
        async with sem:
            for _ in range(3):
                try:
                    raw = await call_groq(system=JUDGE_SYS, user=msg, task_type="relevance_explanation",
                                          model="llama-3.1-8b-instant")
                    m = re.search(r'([01]?\.\d+|[01](?!\d))', raw)
                    if m:
                        return max(0.0, min(1.0, float(m.group(1))))
                except Exception:
                    await asyncio.sleep(1)
            return None
    return await asyncio.gather(*[one(p) for p in pairs])


def main():
    print(f"\n{'user':10s} {'pillar':8s} {'n':>3s} {'mean_score':>10s} {'prec@10':>8s} {'mean_judge':>10s}", flush=True)
    for u in USERS:
        pend = {}
        for pillar in PILLARS:
            items = top_items(u["uid"], pillar)
            pend[pillar] = items
        # judge all
        flat = [(u, t, x) for pillar in PILLARS for (_, t, x) in pend[pillar]]
        scores = asyncio.run(judge(flat))
        idx = 0
        for pillar in PILLARS:
            items = pend[pillar]
            n = len(items)
            js = scores[idx:idx + n]; idx += n
            if not n:
                print(f"{u['uid'][:8]:10s} {pillar:8s} {0:>3d} {'-':>10s} {'-':>8s} {'-':>10s}", flush=True)
                continue
            mean_score = statistics.mean(it[0] for it in items)
            valid = [j for j in js if j is not None]
            prec = (sum(1 for j in valid if j >= 0.5) / len(valid)) if valid else 0
            mj = statistics.mean(valid) if valid else 0
            print(f"{u['uid'][:8]:10s} {pillar:8s} {n:>3d} {mean_score:>10.3f} {prec:>8.2f} {mj:>10.3f}", flush=True)
    print("\n(prec@10 = fraction of top-10 the judge rates >=0.5 relevant; mean_judge = avg judge score)", flush=True)


if __name__ == "__main__":
    main()
