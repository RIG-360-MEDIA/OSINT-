#!/usr/bin/env python3
"""§5b pair-level board re-eval — OLD vs NEW entities, apples-to-apples.

Same canonical labeled pairs, same locked edge-fit.json scorer (train==serve). Computes the
board on:
  NEW entities  -> features via SSOT pair_features.structured_sql (live, re-backfilled)
  OLD entities  -> features from analytics.pair_scores (pre-computed on old entities)
Reports precision / must-link recall / false-merge, POOLED + PER-REGIME, OLD vs NEW.

Sets (settled by analytics):
  pos = _edge_stage.label='same_event'
  neg = _edge_stage.label='not_same_event' + hard_neg_candidates_v3.label='not_same_event'
  fm  = _fm_pairs (cannot-link canaries; a tag over negatives, counted once)
Dedup: each pair once; pos wins ties. fm tracked as a membership set (no double-count).
Read-mostly (one scratch table, dropped)."""
from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
from collections import defaultdict

import psycopg2

pf = importlib.util.spec_from_file_location("pair_features", os.environ.get("PF_PATH", "/tmp/pair_features.py"))
_m = importlib.util.module_from_spec(pf)
sys.modules["pair_features"] = _m
pf.loader.exec_module(_m)
pf = _m

regs = json.load(open(os.environ.get("FIT_REPORT", "/tmp/edge-fit.json")))["regimes"]
INDIC = {"te", "hi", "kn", "bn", "ml", "ta", "mr", "gu", "pa", "or", "ne", "as"}
FALLBACK = {"indic-indic", "indic-other", "other-other"}
WEIGHTS_KEYS = set()
for rg in regs.values():
    WEIGHTS_KEYS |= set(rg.get("weights", {}).keys())


def bucket(l):
    return "en" if l == "en" else ("indic" if l in INDIC else "other")


def regime_of(a, b):
    return "-".join(sorted([bucket(a or ""), bucket(b or "")]))


def score(feat, regime):
    use = regime
    if regime in FALLBACK or regime not in regs or "weights" not in regs.get(regime, {}):
        use = "en-en"
    r = regs[use]
    z = float(r["intercept"])
    for f, wi in r["weights"].items():
        if use == "en-other" and f == "shared_numbers":
            wi = 0.0
        x = feat.get(f, 0.0)
        x = float(x) if x not in ("", None) else 0.0
        mean = r["scaler"]["mean"].get(f, 0.0)
        std = r["scaler"]["std"].get(f, 1.0) or 1.0
        z += float(wi) * ((x - mean) / std)
    return 1.0 / (1.0 + math.exp(-z)), float(r["metrics"]["high_threshold"])


def tally(rows_iter, lab, fmset):
    """rows_iter yields (a_id, b_id, a_language, b_language, feat_dict)."""
    pooled = defaultdict(lambda: {"e": 0, "n": 0})
    perreg = defaultdict(lambda: defaultdict(lambda: {"e": 0, "n": 0}))
    fmp = {"e": 0, "n": 0}
    seen = 0
    for a, b, al, bl, feat in rows_iter:
        fs = frozenset((str(a), str(b)))
        g = lab.get(fs)
        if not g:
            continue
        rg = regime_of(al, bl)
        s, thi = score(feat, rg)
        e = 1 if s >= thi else 0
        pooled[g]["e"] += e
        pooled[g]["n"] += 1
        perreg[rg][g]["e"] += e
        perreg[rg][g]["n"] += 1
        if fs in fmset:
            fmp["e"] += e
            fmp["n"] += 1
        seen += 1
    return pooled, perreg, fmp, seen


def board(d):
    tp, fp = d["pos"]["e"], d["neg"]["e"]
    pos, neg = d["pos"]["n"], d["neg"]["n"]
    return (tp / max(tp + fp, 1)), (tp / max(pos, 1)), tp, fp, pos, neg


def main():
    dsn = os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC") or os.environ.get("DATABASE_URL")
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    # load labeled pairs, dedup (pos wins), fm membership
    lab, rep, fmset = {}, {}, set()
    cur.execute("SELECT a_id,b_id FROM analytics._edge_stage WHERE label='same_event'")
    for a, b in cur.fetchall():
        fs = frozenset((str(a), str(b)))
        lab[fs] = "pos"
        rep[fs] = (a, b)
    cur.execute("SELECT a_id,b_id FROM analytics._edge_stage WHERE label='not_same_event' "
                "UNION SELECT a_id,b_id FROM analytics.hard_neg_candidates_v3 WHERE label='not_same_event'")
    for a, b in cur.fetchall():
        fs = frozenset((str(a), str(b)))
        if fs not in lab:
            lab[fs] = "neg"
            rep[fs] = (a, b)
    cur.execute("SELECT a_id,b_id FROM analytics._fm_pairs")
    for a, b in cur.fetchall():
        fs = frozenset((str(a), str(b)))
        fmset.add(fs)
        if fs not in lab:
            lab[fs] = "neg"
            rep[fs] = (a, b)
    cur.execute("DROP TABLE IF EXISTS analytics._board_pairs")
    cur.execute("CREATE TABLE analytics._board_pairs(a_id uuid, b_id uuid, label text)")
    cur.executemany("INSERT INTO analytics._board_pairs(a_id,b_id,label) VALUES (%s,%s,'x')", list(rep.values()))
    conn.commit()
    print(f"labeled universe: {len(lab)} distinct pairs (pos={sum(1 for v in lab.values() if v=='pos')}, "
          f"neg={sum(1 for v in lab.values() if v=='neg')}, fm-tagged={len(fmset)})")

    # NEW entities: structured_sql stream
    st = conn.cursor(name="bstream")
    st.itersize = 5000
    st.execute(pf.structured_sql("analytics._board_pairs"))
    new_rows = ((fr["a_id"], fr["b_id"], fr["a_language"], fr["b_language"], fr) for fr in pf.iter_features(st, batch=5000))
    npool, nreg, nfm, nseen = tally(new_rows, lab, fmset)
    st.close()

    # OLD entities: full pair_scores row as the feature dict (robust to which columns exist)
    ocur = conn.cursor()
    ocur.execute("""SELECT ps.* FROM analytics.pair_scores ps JOIN analytics._board_pairs bp
          ON (ps.a_id=bp.a_id AND ps.b_id=bp.b_id) OR (ps.a_id=bp.b_id AND ps.b_id=bp.a_id)""")
    ocols = [d[0] for d in ocur.description]

    def old_iter():
        for row in ocur.fetchall():
            d = dict(zip(ocols, row))
            yield d["a_id"], d["b_id"], d.get("a_language"), d.get("b_language"), d

    opool, oreg, ofm, oseen = tally(old_iter(), lab, fmset)
    cur.execute("DROP TABLE IF EXISTS analytics._board_pairs")
    conn.commit()

    print(f"\nscored: NEW={nseen} pairs (live structured_sql), OLD={oseen} pairs (pair_scores coverage)")
    for tag, pool, reg, fm in (("OLD", opool, oreg, ofm), ("NEW", npool, nreg, nfm)):
        p, r, tp, fp, pos, neg = board(pool)
        print(f"\n=== {tag} entities ===")
        print(f"POOLED  precision={p:.3f} ({tp}/{tp+fp})  must-link recall={r:.3f} ({tp}/{pos})  "
              f"neg={neg}  false-merge={fm['e']}/{fm['n']}")
        for rg in sorted(reg):
            p, r, tp, fp, pos, neg = board(reg[rg])
            print(f"  {rg:13s} P={p:.3f} ({tp}/{tp+fp})  recall={r:.3f} ({tp}/{pos})  neg_edges={fp}/{neg}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
