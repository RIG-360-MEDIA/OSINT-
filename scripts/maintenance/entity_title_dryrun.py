#!/usr/bin/env python3
"""entity_title_dryrun.py — §2b revised: stoplist-cleaned entity_core_cov + title_cohesion.

For every high-source loaded cluster (independent_source_count >= MIN_SRC), recompute:
  - core_cov_clean = max single-entity article coverage AFTER removing wire/agency + known
    NER-junk entities (the signal cleaned of bylines / mis-parses).
  - title_cohesion = max coverage of any strong 2-3 word title n-gram (fraction of the
    cluster's articles whose title contains it). Rescues real events with broken entities
    but near-identical headlines (the Myanmar case).
Read-only. Prints the distribution so T_title can be locked off real numbers."""
from __future__ import annotations

import os
import re
import sys
from collections import Counter, defaultdict

import psycopg2

MIN_SRC = int(os.environ.get("MIN_SRC", "25"))

STOP_ENT = {
    "bbc", "reuters", "afp", "pti", "ani", "ap", "ians", "bloomberg", "ndtv", "cnn",
    "agence france-presse", "associated press", "press trust of india",
    "indo-asian news service", "the associated press", "reuters india",
    "rebel wilson", "russia and china",  # known mis-parses ("rebel-held", "Chinese border")
}
STOPWORDS = set(
    "the a an of in on at to for and or but with from by as is are was were be been over "
    "after into amid say says said new latest update live news his her its it he she they "
    "this that will more than has have had not no".split()
)


def title_grams(title: str) -> set[str]:
    toks = [t for t in re.sub(r"[^a-z0-9 ]", " ", (title or "").lower()).split() if t]
    grams: set[str] = set()
    for nlen in (2, 3):
        for i in range(len(toks) - nlen + 1):
            g = toks[i : i + nlen]
            if all(w in STOPWORDS for w in g):
                continue
            grams.add(" ".join(g))
    return grams


def main() -> int:
    dsn = os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC") or os.environ.get("DATABASE_URL")
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT sc.story_id, sc.article_count, sc.independent_source_count, sc.entity_core_cov,
               sc.representative_title,
               m.article_id, a.title,
               (SELECT array_agg(lower(e->>'name')) FROM (
                  SELECT e FROM jsonb_array_elements(coalesce(a.entities_extracted,'[]'::jsonb)) e
                  WHERE e->>'name' IS NOT NULL
                  ORDER BY (e->>'prominence')::float DESC NULLS LAST LIMIT 3) t)
        FROM analytics.story_clusters sc
        JOIN analytics.story_cluster_members m ON m.story_id = sc.story_id
        JOIN articles a ON a.id = m.article_id
        WHERE sc.independent_source_count >= {MIN_SRC}
        """
    )
    cl: dict = defaultdict(lambda: {"ac": 0, "src": 0, "old": None, "rep": "", "n": 0, "ent": Counter(), "gram": Counter()})
    for sid, ac, src, old, rep, aid, title, ents in cur:
        d = cl[str(sid)]
        d["ac"], d["src"], d["old"], d["rep"] = ac, src, old, rep
        d["n"] += 1
        for e in {x for x in (ents or []) if x and x not in STOP_ENT}:
            d["ent"][e] += 1
        for g in title_grams(title):
            d["gram"][g] += 1

    rows = []
    for sid, d in cl.items():
        n = max(d["n"], 1)
        core_e, core_n = d["ent"].most_common(1)[0] if d["ent"] else ("-", 0)
        gram, gram_n = d["gram"].most_common(1)[0] if d["gram"] else ("-", 0)
        rows.append(
            {
                "ac": d["ac"], "src": d["src"], "old": float(d["old"]) if d["old"] is not None else None,
                "core": round(core_n / n, 2), "core_e": core_e,
                "tcoh": round(gram_n / n, 2), "gram": gram, "rep": d["rep"],
            }
        )
    rows.sort(key=lambda r: r["core"])
    print(f"{len(rows)} clusters with src >= {MIN_SRC} | core_cov_clean = after wire/junk stoplist")
    print("  cleanCore  title_coh  src  size | top_title_ngram        | rep_title")
    for r in rows:
        mark = "  LOW-CORE" if r["core"] < 0.45 else ""
        print(f"  {r['core']:.2f}       {r['tcoh']:.2f}     {r['src']:3d}  {r['ac']:4d} | {r['gram'][:22]:22s} | {r['rep'][:40]}{mark}")
    print("\nFor the locked rule, the gate is: src>=25 AND cleanCore<0.45 AND title_coh<T_title.")
    print("Low-core set (cleanCore<0.45) — these are decided by title_coh vs T_title:")
    for r in sorted([r for r in rows if r["core"] < 0.45], key=lambda r: -r["tcoh"]):
        print(f"  title_coh={r['tcoh']:.2f}  cleanCore={r['core']:.2f}  src={r['src']:3d} | {r['rep'][:55]}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
