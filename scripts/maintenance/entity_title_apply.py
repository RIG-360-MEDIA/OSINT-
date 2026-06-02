#!/usr/bin/env python3
"""Write title_cohesion onto analytics.story_clusters for high-source clusters (>= MIN_SRC) —
the only ones that can be flagged. Same strong 2-3 word title n-gram metric as the dry-run.
Bounded UPDATE (a few dozen rows)."""
from __future__ import annotations

import os
import re
import sys
from collections import Counter, defaultdict

import psycopg2

MIN_SRC = int(os.environ.get("MIN_SRC", "25"))
STOPWORDS = set(
    "the a an of in on at to for and or but with from by as is are was were be been over "
    "after into amid say says said new latest update live his her its it he she they this "
    "that will more than has have had not no".split()
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
    dsn = os.environ.get("DATABASE_URL_SYNC") or os.environ.get("DATABASE_URL")
    conn = psycopg2.connect(dsn)
    read = conn.cursor()
    read.execute(
        f"""SELECT sc.story_id, a.title
            FROM analytics.story_clusters sc
            JOIN analytics.story_cluster_members m ON m.story_id = sc.story_id
            JOIN articles a ON a.id = m.article_id
            WHERE sc.independent_source_count >= {MIN_SRC}"""
    )
    cl: dict = defaultdict(lambda: {"n": 0, "g": Counter()})
    for sid, title in read.fetchall():
        d = cl[str(sid)]
        d["n"] += 1
        for g in grams(title):
            d["g"][g] += 1

    vals = []
    for sid, d in cl.items():
        tc = (d["g"].most_common(1)[0][1] / max(d["n"], 1)) if d["g"] else 0.0
        vals.append((round(tc, 3), sid))

    w = conn.cursor()
    w.executemany("UPDATE analytics.story_clusters SET title_cohesion = %s WHERE story_id = %s::uuid", vals)
    conn.commit()
    print(f"updated title_cohesion on {len(vals)} clusters (src >= {MIN_SRC})")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
