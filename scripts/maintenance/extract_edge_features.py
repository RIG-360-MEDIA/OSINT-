#!/usr/bin/env python3
"""
extract_edge_features.py — #3: build the edge-scorer TRAINING features CSV.

Imports the SSOT pair_features module (BY FILE) so the training features are computed
by the exact same code the production clustering job (#7) will import — train/serve
skew impossible. Assembles the deduped UNION:

  * golden + recall fixture pairs   (analytics._edge_stage, from edge-pairs CSV)
  * free hard negatives             (analytics.hard_neg_fps, 13)
  * verified-clean mined negatives   (hard_neg_candidates/_v2 WHERE human_clean;
                                       _v3 date-keyed not_same_event)

pair_scores is NOT used as a feature source (its builder is lost + values predate
shared_numbers); only as a pair source elsewhere. Dedups by unordered pair; pairs with
conflicting labels across sources are DROPPED and counted. Emits exactly
pair_features.FEATURE_HEADER. grayzone rows are kept (the fit holds them out).

Env: AB_DSN/DATABASE_URL_SYNC · PF_PATH (/tmp/pair_features.py) · OUT (/tmp/edge_features.csv)
"""
from __future__ import annotations

import csv
import importlib.util
import logging
import os
import sys
from collections import Counter

import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("feat")

PF_PATH = os.environ.get("PF_PATH", "/tmp/pair_features.py")
OUT = os.environ.get("OUT", "/tmp/edge_features.csv")

_spec = importlib.util.spec_from_file_location("pair_features", PF_PATH)
pf = importlib.util.module_from_spec(_spec)
sys.modules["pair_features"] = pf
_spec.loader.exec_module(pf)

UNION_SQL = """
DROP TABLE IF EXISTS analytics._feat_pairs_raw;
CREATE TABLE analytics._feat_pairs_raw AS
  SELECT a_id,b_id,label                FROM analytics._edge_stage
    WHERE label IN ('same_event','not_same_event','grayzone')
  UNION ALL SELECT a_id,b_id,'not_same_event' FROM analytics.hard_neg_fps
  UNION ALL SELECT a_id,b_id,'not_same_event' FROM analytics.hard_neg_candidates    WHERE human_clean
  UNION ALL SELECT a_id,b_id,'not_same_event' FROM analytics.hard_neg_candidates_v2 WHERE human_clean
  UNION ALL SELECT a_id,b_id,'not_same_event' FROM analytics.hard_neg_candidates_v3
    WHERE label='not_same_event' AND key_reason LIKE 'title dates%';
"""

DEDUP_SQL = """
DROP TABLE IF EXISTS analytics._feat_pairs;
CREATE TABLE analytics._feat_pairs AS
WITH counts AS (
  SELECT least(a_id,b_id) x, greatest(a_id,b_id) y, count(DISTINCT label) nlabels
  FROM analytics._feat_pairs_raw GROUP BY 1,2
),
ranked AS (
  SELECT a_id, b_id, label,
         row_number() OVER (PARTITION BY least(a_id,b_id), greatest(a_id,b_id) ORDER BY a_id) rn
  FROM analytics._feat_pairs_raw
)
SELECT rk.a_id, rk.b_id, rk.label
FROM ranked rk
JOIN counts c ON c.x = least(rk.a_id,rk.b_id) AND c.y = greatest(rk.a_id,rk.b_id)
WHERE c.nlabels = 1 AND rk.rn = 1;
"""


def _regime(al: str, bl: str) -> str:
    if al == "en" and bl == "en":
        return "en-en"
    if al and bl and al != "en" and bl != "en":
        return "indic-indic"
    return "cross_lingual"


def main() -> int:
    dsn = (os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC")
           or os.environ.get("DATABASE_URL"))
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()

    cur.execute(UNION_SQL)
    cur.execute(DEDUP_SQL)
    conn.commit()

    cur.execute("SELECT count(*) FROM (SELECT 1 FROM analytics._feat_pairs_raw "
                "GROUP BY least(a_id,b_id),greatest(a_id,b_id) HAVING count(DISTINCT label)>1) c")
    conflicts = cur.fetchone()[0]
    cur.execute("SELECT label,count(*) FROM analytics._feat_pairs GROUP BY label ORDER BY label")
    by_label = cur.fetchall()
    log.info("union deduped: labels=%s | %d conflicting pairs dropped", dict(by_label), conflicts)

    cur.execute(pf.structured_sql("analytics._feat_pairs"))
    recs = pf.rows_to_features(cur)

    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(pf.FEATURE_HEADER)
        for r in recs:
            w.writerow([r[c] for c in pf.FEATURE_HEADER])

    # Summary: per-regime x label, + coverage of the computed (non-flagged) features.
    grid = Counter()
    null_len = 0
    for r in recs:
        grid[(_regime(r["a_language"], r["b_language"]), r["label"])] += 1
        if r["length_ratio"] == "":
            null_len += 1
    log.info("wrote %d rows -> %s (version=%s)", len(recs), OUT, pf.PAIR_FEATURES_VERSION)
    for (reg, lab), n in sorted(grid.items()):
        log.info("  %-13s %-15s %d", reg, lab, n)
    log.info("coverage: length_ratio null=%d ; FLAGGED-all-zero=%s", null_len, pf.FLAGGED_NULL_FEATURES)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
