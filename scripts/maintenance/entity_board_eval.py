#!/usr/bin/env python3
"""§5b pair-level board re-eval — OLD vs NEW entities, apples-to-apples.

Same canonical labeled pairs, same locked edge-fit.json scorer (train==serve). Computes the
board on:
  NEW entities  -> features via SSOT pair_features.structured_sql (live, re-backfilled)
  OLD entities  -> the SAME structured_sql, entity source swapped to the pre-backfill snapshot
                   (entities_extracted_bak_20260602), live-fallback for articles not in it.
Embeddings / numbers / trgm / dates are identical between the two runs, so the OLD<->NEW
delta isolates EXACTLY the entity-backfill effect (the only thing the scorer-refit hinges on).
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
    feat_acc = defaultdict(lambda: {"sa": 0, "sl": 0, "sa0": 0, "n": 0})  # (regime,label) -> feature sums
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
        sa = feat.get("shared_actors", 0) or 0
        for key in ((rg, g), ("POOLED", g)):
            d = feat_acc[key]
            d["sa"] += sa
            d["sl"] += feat.get("shared_locations", 0) or 0
            d["sa0"] += 1 if sa == 0 else 0
            d["n"] += 1
        if fs in fmset:
            fmp["e"] += e
            fmp["n"] += 1
        seen += 1
    return pooled, perreg, fmp, feat_acc, seen


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
    cur.execute("""SELECT count(*) FILTER (WHERE bak.id IS NOT NULL), count(*) FROM (
                     SELECT a_id x FROM analytics._board_pairs
                     UNION SELECT b_id FROM analytics._board_pairs) q
                   LEFT JOIN entities_extracted_bak_20260602 bak ON bak.id = q.x""")
    inbak, totart = cur.fetchone()
    print(f"backup coverage: {inbak}/{totart} distinct articles in pre-backfill snapshot "
          f"(the {totart-inbak} not in it use live = unchanged entities)")

    # NEW entities: structured_sql stream
    st = conn.cursor(name="bstream")
    st.itersize = 5000
    st.execute(pf.structured_sql("analytics._board_pairs"))
    new_rows = ((fr["a_id"], fr["b_id"], fr["a_language"], fr["b_language"], fr) for fr in pf.iter_features(st, batch=5000))
    npool, nreg, nfm, nfeat, nseen = tally(new_rows, lab, fmset)
    st.close()

    # OLD entities: SAME structured_sql + scorer + pairs, entity source swapped to the
    # pre-backfill snapshot. coalesce(backup, live) so articles NOT re-backfilled fall back
    # to their (unchanged) live entities. Everything else in the SQL is byte-identical to NEW.
    OLD_A = "coalesce((SELECT entities_extracted FROM entities_extracted_bak_20260602 WHERE id=a.id), a.entities_extracted)"
    OLD_B = "coalesce((SELECT entities_extracted FROM entities_extracted_bak_20260602 WHERE id=b.id), b.entities_extracted)"
    sql_old = (pf.structured_sql("analytics._board_pairs")
               .replace("a.entities_extracted", OLD_A)
               .replace("b.entities_extracted", OLD_B))
    ost = conn.cursor(name="ostream")
    ost.itersize = 5000
    ost.execute(sql_old)
    old_rows = ((fr["a_id"], fr["b_id"], fr["a_language"], fr["b_language"], fr) for fr in pf.iter_features(ost, batch=5000))
    opool, oreg, ofm, ofeat, oseen = tally(old_rows, lab, fmset)
    ost.close()
    cur.execute("DROP TABLE IF EXISTS analytics._board_pairs")
    conn.commit()

    print(f"\nscored: NEW={nseen} pairs (live entities), OLD={oseen} pairs (pre-backfill snapshot) "
          f"— SAME pairs, SAME scorer, only entity source differs")
    for tag, pool, reg, fm in (("OLD", opool, oreg, ofm), ("NEW", npool, nreg, nfm)):
        p, r, tp, fp, pos, neg = board(pool)
        print(f"\n=== {tag} entities ===")
        print(f"POOLED  precision={p:.3f} ({tp}/{tp+fp})  must-link recall={r:.3f} ({tp}/{pos})  "
              f"neg={neg}  false-merge={fm['e']}/{fm['n']}")
        for rg in sorted(reg):
            p, r, tp, fp, pos, neg = board(reg[rg])
            print(f"  {rg:13s} P={p:.3f} ({tp}/{tp+fp})  recall={r:.3f} ({tp}/{pos})  neg_edges={fp}/{neg}")

    print("\n=== feature diagnostic: mean shared_actors / shared_locations, OLD -> NEW ===")
    print("  (recall-loss smoking gun = shared_actors DROPS on 'pos'; FP-growth = RISES on 'neg')")
    for rg, g in (("POOLED", "pos"), ("POOLED", "neg"), ("en-en", "pos"), ("en-en", "neg"),
                  ("en-indic", "pos"), ("en-other", "pos"), ("other-other", "pos")):
        o, nf = ofeat.get((rg, g)), nfeat.get((rg, g))
        if not o or not nf:
            continue
        print(f"  {rg:11s} {g}: shared_actors {o['sa']/max(o['n'],1):.2f}->{nf['sa']/max(nf['n'],1):.2f}  "
              f"shared_loc {o['sl']/max(o['n'],1):.2f}->{nf['sl']/max(nf['n'],1):.2f}  "
              f"zero-actor {100*o['sa0']/max(o['n'],1):.0f}%->{100*nf['sa0']/max(nf['n'],1):.0f}%  n={nf['n']}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
