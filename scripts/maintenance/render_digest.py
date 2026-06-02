#!/usr/bin/env python3
"""
render_digest.py — render an existing clustering CSV into a human-judgeable digest.

NOT a re-cluster: reads the locked latest-window run (scale_leiden.csv = ~37K, last 10d,
V4-only, theta=0.90, CAND_COS=0.80, tg-v3 guards, Leiden res=1.0) and emits a markdown
digest a human can read to answer "are these stories good?" — face validity, grouping
correctness, granularity, cross-lingual, headline quality.

Output: docs/plans/latest-window-digest-2026-06-02.md (via OUT). Clusters ranked by
INDEPENDENT-SOURCE count (source diversity = real significance, not raw size).

Env: AB_DSN/DATABASE_URL_SYNC · CSV (/tmp/scale_leiden.csv) · OUT (/tmp/digest.md)
     SPLIT_COUNT (oversized comps split by Leiden, from the run log) · CONFIG (header line)
"""
from __future__ import annotations

import os
import random
import sys
from collections import Counter, defaultdict

import psycopg2

CSV = os.environ.get("CSV", "/tmp/scale_leiden.csv")
OUT = os.environ.get("OUT", "/tmp/digest.md")
SPLIT_COUNT = os.environ.get("SPLIT_COUNT", "8")
CONFIG = os.environ.get("CONFIG", "last 10d, V4-only, CAND_COS=0.80, theta=0.90, tg-v3 guards, Leiden res=1.0")
random.seed(42)


def rep_headline(titles):  # titles: list of (title, lang)
    # median-length English title in a clean band -> avoids verbose clickbait (the longest)
    # and truncated stubs (the shortest); falls back to any title.
    en = sorted([t for t, l in titles if l == "en" and t and 25 <= len(t) <= 95], key=len)
    if not en:
        en = sorted([t for t, l in titles if t], key=len)
    return en[len(en) // 2][:96] if en else "(no title)"


def member_titles(titles):
    en = [t for t, l in titles if l == "en" and t]
    non_en = [(t, l) for t, l in titles if l != "en" and t]
    out = [t[:60] for t in en[:3]]
    if non_en:
        out.append(non_en[0][0][:56] + f"  [{non_en[0][1]}]")
    return out[:4]


def main() -> int:
    dsn = (os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC")
           or os.environ.get("DATABASE_URL"))
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute("CREATE TEMP TABLE _dg(article_id uuid, cluster_id uuid, source_id uuid)")
    with open(CSV) as fh:
        cur.copy_expert("COPY _dg FROM STDIN WITH (FORMAT csv, HEADER true)", fh)

    cur.execute("SELECT count(*), count(DISTINCT cluster_id) FROM _dg")
    n_articles, n_clusters = cur.fetchone()
    cur.execute("SELECT cluster_id, count(*) n FROM _dg GROUP BY 1")
    sizes = {str(c): n for c, n in cur.fetchall()}
    singletons = sum(1 for n in sizes.values() if n == 1)
    multi = sum(1 for n in sizes.values() if n > 1)
    cur.execute("SELECT a.language_detected, count(*) FROM _dg s JOIN articles a ON a.id=s.article_id "
                "GROUP BY 1 ORDER BY 2 DESC NULLS LAST LIMIT 8")
    lang_mix = cur.fetchall()

    # multi-article cluster member rows
    cur.execute("""
        SELECT s.cluster_id, s.source_id, a.title, a.language_detected, a.geo_primary
        FROM _dg s JOIN articles a ON a.id = s.article_id
        WHERE s.cluster_id IN (SELECT cluster_id FROM _dg GROUP BY 1 HAVING count(*) > 1)
    """)
    cl = defaultdict(lambda: {"src": set(), "titles": [], "langs": set(), "geos": Counter()})
    for cid, src, title, lang, geo in cur.fetchall():
        d = cl[str(cid)]
        d["src"].add(str(src))
        d["titles"].append((title, lang or "?"))
        if lang:
            d["langs"].add(lang)
        if geo:
            d["geos"][geo] += 1
    conn.close()

    rows = []
    for cid, d in cl.items():
        n = len(d["titles"])
        srcn = len(d["src"])
        region = d["geos"].most_common(1)[0][0] if d["geos"] else "—"
        rows.append({"cid": cid, "n": n, "src": srcn, "langs": sorted(d["langs"]),
                     "region": region, "ratio": round(n / max(srcn, 1), 1),
                     "rep": rep_headline(d["titles"]), "members": member_titles(d["titles"])})

    by_src = sorted(rows, key=lambda r: (r["src"], r["n"]), reverse=True)

    def block(r, i):
        out = [f"**{i}. {r['rep']}**",
               f"  · {r['n']} articles · **{r['src']} independent sources** · "
               f"{'/'.join(r['langs']) or '?'} · region: {r['region']}"]
        out += [f"  · _{m}_" for m in r["members"]]
        return "\n".join(out)

    L = []
    L.append("# Latest-window clustering digest — 2026-06-02")
    L.append(f"**Config:** {CONFIG}. **Rendered, not re-clustered** — this is what the locked "
             "engine produced, for human judgement.\n")
    L.append("> **How to read this.** ~92% singletons is the **known recall-hobbled v1.1 setting** "
             "(gray->no-edge, no live judge) — we are judging *the clusters that formed*, not "
             "\"why isn't everything grouped.\" **\"Story\" = cluster + representative headline**, "
             "not generated prose (that's Phase 4). Clusters are ranked by **independent-source "
             "count** (cross-source corroboration = real significance), not raw size.\n")
    L.append("> **What to judge:** (1) face validity — are the big clusters the period's big "
             "stories? (2) grouping correctness — is each cluster one event? (3) granularity — does "
             "event-level feel right or too fine? (4) cross-lingual — do te/hi articles land right? "
             "(5) headline quality.\n")
    L.append("## Header stats")
    L.append(f"- **Articles:** {n_articles:,} (V4-only window)")
    L.append(f"- **Clusters:** {n_clusters:,}  ·  **singletons:** {singletons:,} "
             f"({100.0*singletons/max(n_clusters,1):.1f}% of clusters)  ·  "
             f"**multi-article clusters:** {multi:,}")
    L.append(f"- **Oversized components split by Leiden (res=1.0):** {SPLIT_COUNT} "
             "(914 Trump|Iran|petrol, 597 IPL, 131 APC, + 5 small) — from the run log")
    L.append("- **Language mix:** " + " · ".join(f"{l or '?'}={c:,}" for l, c in lang_mix))
    L.append("- _independent sources = distinct source_id (each outlet once); explicit wire-dedup "
             "was not a separate step in this run, so this is the proxy._\n")

    L.append(f"## Top 50 multi-article clusters (by independent-source count)\n")
    for i, r in enumerate(by_src[:50], 1):
        L.append(block(r, i))
        L.append("")

    blobs = [r for r in by_src if r["ratio"] >= 4.0]
    L.append(f"## Blob watch — clusters still article:source ratio >= 4 after Leiden ({len(blobs)})")
    L.append("_If these are coherent single stories from few outlets, fine; if chained, Leiden left "
             "something._\n")
    for i, r in enumerate(sorted(blobs, key=lambda r: r["ratio"], reverse=True)[:20], 1):
        L.append(f"{i}. ratio **{r['ratio']}** ({r['n']}a/{r['src']}s) — {r['rep']}")
        L.append(f"   _{' · '.join(r['members'][:3])}_")
    L.append("")

    sample = random.sample(rows, min(10, len(rows)))
    L.append("## Random 10 multi-article clusters (the median, not the winners)\n")
    for i, r in enumerate(sample, 1):
        L.append(block(r, i))
        L.append("")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    sys.stderr.write(f"wrote {OUT}: {n_articles} articles, {multi} multi-clusters, "
                     f"{len(blobs)} ratio>=4, top by {by_src[0]['src']} sources\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
