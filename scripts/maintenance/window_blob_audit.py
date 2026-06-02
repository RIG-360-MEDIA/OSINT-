#!/usr/bin/env python3
"""window_blob_audit.py — audit a cluster_job_7 window CSV for blobs + the §2b verdict.

For each cluster in the window output (article_id,cluster_id,source_id) above a size floor,
computes size, distinct sources, article:source ratio, entity_core_cov (stoplist-cleaned,
top-3 by prominence), title_cohesion (strongest 2-3 word title n-gram), and the LOCKED §2b
is_template_family flag (src>=25 AND core<0.45 AND title_coh<0.35). Prints the biggest
clusters with their verdict + sample titles, so a real mega-event is distinguishable from a
topic-blob and we can confirm §2b catches the fake-top-story. Read-only (TEMP table + SELECT).

Env: AB_DSN/DATABASE_URL_SYNC · IN (/tmp/win_new_leiden.csv) · MIN_SHOW (50) · TOP (24)
"""
from __future__ import annotations

import os
import re
import sys
from collections import Counter, defaultdict

import psycopg2

IN = os.environ.get("IN", "/tmp/win_new_leiden.csv")
MIN_SHOW = int(os.environ.get("MIN_SHOW", "50"))
TOP = int(os.environ.get("TOP", "24"))

STOP_ENT = {
    "bbc", "reuters", "afp", "pti", "ani", "ap", "ians", "bloomberg", "ndtv", "cnn",
    "agence france-presse", "associated press", "press trust of india",
    "indo-asian news service", "the associated press", "reuters india",
    "rebel wilson", "russia and china",
}
STOPWORDS = set(
    "the a an of in on at to for and or but with from by as is are was were be been over "
    "after into amid say says said new latest update live news his her its it he she they "
    "this that will more than has have had not no".split()
)


def grams(title: str) -> set[str]:
    toks = [t for t in re.sub(r"[^a-z0-9 ]", " ", (title or "").lower()).split() if t]
    out: set[str] = set()
    for nlen in (2, 3):
        for i in range(len(toks) - nlen + 1):
            g = toks[i : i + nlen]
            if all(w in STOPWORDS for w in g):
                continue
            out.add(" ".join(g))
    return out


def main() -> int:
    dsn = os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC") or os.environ.get("DATABASE_URL")
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute("CREATE TEMP TABLE _wc(article_id uuid, cluster_id text, source_id text)")
    with open(IN) as f:
        cur.copy_expert("COPY _wc FROM STDIN WITH (FORMAT csv, HEADER true)", f)
    cur.execute(
        """
        SELECT w.cluster_id, w.source_id, a.title,
          (SELECT array_agg(lower(e->>'name')) FROM (
             SELECT e FROM jsonb_array_elements(coalesce(a.entities_extracted,'[]'::jsonb)) e
             WHERE e->>'name' IS NOT NULL
             ORDER BY (e->>'prominence')::float DESC NULLS LAST LIMIT 3) t)
        FROM _wc w JOIN articles a ON a.id = w.article_id
        WHERE w.cluster_id IN (SELECT cluster_id FROM _wc GROUP BY 1 HAVING count(*) >= %s)
        """,
        (MIN_SHOW,),
    )
    cl: dict = defaultdict(lambda: {"n": 0, "src": set(), "ent": Counter(), "gram": Counter(), "titles": []})
    for cid, sid, title, ents in cur:
        d = cl[str(cid)]
        d["n"] += 1
        if sid:
            d["src"].add(sid)
        for e in {x for x in (ents or []) if x and x not in STOP_ENT}:
            d["ent"][e] += 1
        for g in grams(title):
            d["gram"][g] += 1
        if title and len(d["titles"]) < 3:
            d["titles"].append(title[:62])

    rows = []
    for cid, d in cl.items():
        n = max(d["n"], 1)
        src = len(d["src"])
        core_e, core_c = d["ent"].most_common(1)[0] if d["ent"] else ("-", 0)
        gram, gram_c = d["gram"].most_common(1)[0] if d["gram"] else ("-", 0)
        core, tcoh = core_c / n, gram_c / n
        tf = src >= 25 and core < 0.45 and tcoh < 0.35
        rows.append({"n": d["n"], "src": src, "ratio": d["n"] / max(src, 1), "core": core,
                     "core_e": core_e, "tcoh": tcoh, "gram": gram, "tf": tf, "titles": d["titles"]})
    rows.sort(key=lambda r: -r["n"])
    print(f"clusters size>={MIN_SHOW}: {len(rows)} | §2b is_template_family = src>=25 AND core<0.45 AND tcoh<0.35")
    for r in rows[:TOP]:
        flag = "FLAG-TF " if r["tf"] else ("real?   " if r["src"] >= 25 else "low-src ")
        print(f"  n={r['n']:4d} src={r['src']:3d} ratio={r['ratio']:5.1f} core={r['core']:.2f}({r['core_e'][:15]:15s}) "
              f"tcoh={r['tcoh']:.2f}({r['gram'][:16]:16s}) [{flag}]")
        print(f"       ex: {' | '.join(r['titles'])}")
    nflag = sum(1 for r in rows if r["tf"])
    big_unflagged = [r for r in rows if not r["tf"] and r["src"] >= 25 and r["ratio"] >= 5.0]
    print(f"\n§2b flags {nflag}/{len(rows)} clusters (size>={MIN_SHOW}) as template-family -> suppressed from surfacing")
    print(f"unflagged BUT high-source high-ratio (src>=25 & ratio>=5, NOT TF) = {len(big_unflagged)} "
          f"(these are the ones to eyeball: real mega-event vs §2b miss)")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
