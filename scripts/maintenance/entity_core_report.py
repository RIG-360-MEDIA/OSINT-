#!/usr/bin/env python3
"""entity_core_report.py — §1 decisive diagnostic, re-run on the NEW (re-backfilled) entities.

Metric is IDENTICAL to entity_core.py: for each cluster >= MIN_SZ articles, core_cov = the
fraction of its articles that contain the single most-common entity (entity = one of an
article's top-3 by the now-fixed prominence). Hypothesis (analytics §1): real events have HIGH
core_cov (one actor in most articles); cross-source TOPIC over-merges (the 533/27 blob) have LOW.

Reporting is richer than entity_core.py so the threshold can be locked off the distribution:
full per-cluster CSV + bucketed distribution + lowest/highest + test-keyword matches.
Read-only (TEMP table + SELECT only; no writes to real tables)."""
from __future__ import annotations

import csv as _csv
import os
import re
import sys
from collections import Counter, defaultdict

import psycopg2

CSV = os.environ.get("CSV", "/tmp/whole_corpus_xs.csv")
MIN_SZ = int(os.environ.get("MIN_SZ", "60"))
OUT = os.environ.get("OUT", "/tmp/entity_core_report.csv")
KW = re.compile(
    r"paint|zydus|budget|nigeria|share price|sensex|nifty|stock|q4|psg|paris|champions|"
    r"ebola|israel|leban|petrol|diesel|fuel",
    re.I,
)


def main() -> int:
    dsn = os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC") or os.environ.get("DATABASE_URL")
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute("CREATE TEMP TABLE _x(article_id uuid, cluster_id uuid, source_id uuid)")
    with open(CSV) as f:
        cur.copy_expert("COPY _x FROM STDIN WITH (FORMAT csv, HEADER true)", f)
    cur.execute(
        f"""
        SELECT x.cluster_id, x.source_id, a.title, coalesce(a.language_detected,'?'),
               (SELECT array_agg(lower(e->>'name')) FROM (
                  SELECT e FROM jsonb_array_elements(coalesce(a.entities_extracted,'[]'::jsonb)) e
                  WHERE e->>'name' IS NOT NULL
                  ORDER BY (e->>'prominence')::float DESC NULLS LAST LIMIT 3) t)
        FROM _x x JOIN articles a ON a.id = x.article_id
        WHERE x.cluster_id IN (SELECT cluster_id FROM _x GROUP BY 1 HAVING count(*) >= {MIN_SZ})
        """
    )
    cl = defaultdict(lambda: {"n": 0, "src": set(), "ent": Counter(), "titles": []})
    for cid, sid, title, lang, ents in cur:
        d = cl[str(cid)]
        d["n"] += 1
        if sid:
            d["src"].add(str(sid))
        for e in set(ents or []):
            d["ent"][e] += 1
        if lang == "en" and title and 25 <= len(title) <= 95:
            d["titles"].append(title)

    rows = []
    for cid, d in cl.items():
        core, cov = d["ent"].most_common(1)[0] if d["ent"] else ("-", 0)
        rep = sorted(d["titles"], key=len)[len(d["titles"]) // 2] if d["titles"] else "?"
        rows.append({"cid": cid, "n": d["n"], "src": len(d["src"]), "cov": cov / max(d["n"], 1), "core": core, "rep": rep})

    with open(OUT, "w", newline="") as f:
        w = _csv.writer(f)
        w.writerow(["cluster_id", "size", "sources", "core_cov", "core_entity", "rep_title"])
        for r in sorted(rows, key=lambda r: -r["n"]):
            w.writerow([r["cid"], r["n"], r["src"], round(r["cov"], 3), r["core"], r["rep"]])

    n = len(rows)
    print(f"{n} clusters >= {MIN_SZ} articles (new entities) | full per-cluster table -> {OUT}")
    print("core_cov distribution:")
    for lo, hi in [(0.0, 0.2), (0.2, 0.35), (0.35, 0.5), (0.5, 0.7), (0.7, 1.01)]:
        c = sum(1 for r in rows if lo <= r["cov"] < hi)
        print(f"  [{lo:.2f},{hi:.2f}): {c:3d}  {'#' * c}")

    def line(r: dict) -> str:
        return f"  size={r['n']:4d} src={r['src']:3d} core_cov={r['cov']:.2f} core={r['core'][:20]:20s} | {r['rep'][:52]}"

    print("\nLOWEST core_cov (topic-over-merge / blob candidates):")
    for r in sorted(rows, key=lambda r: r["cov"])[:15]:
        print(line(r))
    print("\nHIGHEST core_cov (real-event candidates):")
    for r in sorted(rows, key=lambda r: -r["cov"])[:12]:
        print(line(r))
    print("\nTEST-SET matches (rep_title or core_entity matches the named clusters):")
    hits = [r for r in sorted(rows, key=lambda r: r["cov"]) if KW.search(r["rep"] or "") or KW.search(r["core"] or "")]
    for r in hits:
        print(line(r))
    if not hits:
        print("  (no keyword matches — inspect the full CSV)")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
