#!/usr/bin/env python3
"""story_digest.py — STEP 2 inspect digest for a story-layer partition (the human-review gate).

Reads analytics.story_clusters{SUF} (+ members). Prints, for human review before any swap/enrich:
  - summary counts (surfaceable / suppressed / rescued / singletons / surfaced>=3indep)
  - TOP surfaceable stories (real events vs broad topics — eyeball core/tcoh)
  - BLOB-WATCH: big surfaceable clusters spared only by title-cohesion (src>=25, core<0.45)
  - §2b SUPPRESSED sample (the fake-top-stories caught)
  - RESCUED sub-stories sample (buried real stories surfaced; confirm real)
  - RANDOM-10 surfaceable multi-article clusters (unbiased spot-inspection)
Read-only. Env: AB_DSN/DATABASE_URL_SYNC, STORY_TBL_SUFFIX (e.g. _new).
"""
from __future__ import annotations

import os
import sys

import psycopg2

SUF = os.environ.get("STORY_TBL_SUFFIX", "")
C = f"analytics.story_clusters{SUF}"


def q(cur, sql):
    cur.execute(sql)
    return cur.fetchall()


def row(r):
    n, src, core, tcoh, resc, tf, title = r
    core = f"{core:.2f}" if core is not None else " -  "
    tcoh = f"{tcoh:.2f}" if tcoh is not None else " -  "
    tag = "R" if resc else ("S" if tf else " ")
    return f"  [{tag}] n={n:5d} src={src:3d} core={core} tcoh={tcoh} | {(title or '')[:50]}"


COLS = "article_count, source_count, entity_core_cov, title_cohesion, (rescued_from_story_id IS NOT NULL), is_template_family, representative_title"


def main() -> int:
    dsn = os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC") or os.environ.get("DATABASE_URL")
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    print(f"===== STORY-LAYER INSPECT DIGEST  ({C}) =====")
    s = q(cur, f"""SELECT count(*), count(*) FILTER (WHERE NOT is_template_family),
                     count(*) FILTER (WHERE is_template_family),
                     count(*) FILTER (WHERE rescued_from_story_id IS NOT NULL),
                     count(*) FILTER (WHERE article_count=1),
                     count(*) FILTER (WHERE article_count>1),
                     count(*) FILTER (WHERE NOT is_template_family AND independent_source_count>=3)
                   FROM {C}""")[0]
    print(f"clusters={s[0]}  surfaceable={s[1]}  suppressed(template-family)={s[2]}  rescued-subs={s[3]}")
    print(f"singletons={s[4]}  multi-article={s[5]}  surfaced(>=3 indep src)={s[6]}")
    m = q(cur, f"SELECT count(*) FROM analytics.story_cluster_members{SUF}")[0][0]
    print(f"members={m}  (legend: [S]=suppressed  [R]=rescued sub-story  [ ]=ordinary surfaceable)")

    print(f"\n--- TOP surfaceable stories (real event = high core; broad topic = low core/high tcoh) ---")
    for r in q(cur, f"SELECT {COLS} FROM {C} WHERE NOT is_template_family ORDER BY article_count DESC LIMIT 15"):
        print(row(r))

    print(f"\n--- BLOB-WATCH: big surfaceable clusters spared ONLY by title-cohesion (src>=25 & core<0.45) ---")
    bw = q(cur, f"SELECT {COLS} FROM {C} WHERE NOT is_template_family AND source_count>=25 AND entity_core_cov<0.45 ORDER BY article_count DESC LIMIT 10")
    for r in bw:
        print(row(r))
    if not bw:
        print("  (none)")

    print(f"\n--- §2b SUPPRESSED (fake-top-stories caught; biggest first) ---")
    for r in q(cur, f"SELECT {COLS} FROM {C} WHERE is_template_family ORDER BY article_count DESC LIMIT 8"):
        print(row(r))

    print(f"\n--- RESCUED sub-stories (buried real stories surfaced; biggest first) ---")
    for r in q(cur, f"SELECT {COLS} FROM {C} WHERE rescued_from_story_id IS NOT NULL ORDER BY article_count DESC LIMIT 10"):
        print(row(r))

    print(f"\n--- RANDOM-10 surfaceable multi-article clusters (unbiased spot-check) ---")
    for r in q(cur, f"SELECT {COLS} FROM {C} WHERE NOT is_template_family AND article_count>=3 ORDER BY random() LIMIT 10"):
        print(row(r))
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
