#!/usr/bin/env python3
"""
fm_split.py — classify the re-baseline false-merges: DIRECT-SCORER vs TRANSITIVE.

For each cannot-link pair that co-clustered (the 18 false-merges), decide WHY:
  * DIRECT-SCORER = candidate (cosine >= CAND_COS) AND not guard-blocked AND
    score >= theta_high  -> the scorer would put a DIRECT edge between them.
  * TRANSITIVE    = no direct edge by the above, yet they share a cluster -> they were
    chained together through other articles (single-linkage transitivity).

The split decides the fix: TRANSITIVE-heavy -> Leiden/community-detection (break weak
bridges); DIRECT-heavy -> scorer/guard work on shared-subject same-source pairs.

Reuses the SSOT pair_features + template_guard + the exact fit weights (cluster_job_7's
scoring logic, copied verbatim) so the verdict matches the real pipeline.
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import sys

import psycopg2


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


pf = _load(os.environ.get("PF_PATH", "/tmp/pair_features.py"), "pair_features")
tg = _load(os.environ.get("TG_PATH", "/tmp/template_guard.py"), "template_guard")
CAND_COS = float(os.environ.get("CAND_COS", "0.80"))
INDIC = {"te", "hi", "kn", "bn", "ml", "ta", "mr", "gu", "pa", "or", "ne", "as"}
FALLBACK = {"indic-indic", "indic-other", "other-other"}


def bucket(l):
    return "en" if l == "en" else ("indic" if l in INDIC else "other")


def regime_of(al, bl):
    return "-".join(sorted([bucket(al or ""), bucket(bl or "")]))


def pick(regs, reg):
    use = reg
    if reg in FALLBACK or reg not in regs or "weights" not in regs.get(reg, {}):
        use = "en-en"
    r = regs[use]
    return use, r["weights"], r["intercept"], r["scaler"], r["metrics"]["high_threshold"]


def score(feat, regs, reg):
    use, w, b, sc, thi = pick(regs, reg)
    z = float(b)
    for f, wi in w.items():
        if use == "en-other" and f == "shared_numbers":
            wi = 0.0
        x = feat.get(f, 0.0)
        x = float(x) if x not in ("", None) else 0.0
        m = sc["mean"].get(f, 0.0)
        s = sc["std"].get(f, 1.0) or 1.0
        z += float(wi) * ((x - m) / s)
    return 1.0 / (1.0 + math.exp(-z)), float(thi)


def main() -> int:
    regs = json.load(open(os.environ.get("FIT_REPORT", "/tmp/edge-fit.json")))["regimes"]
    conn = psycopg2.connect(os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC")
                            or os.environ.get("DATABASE_URL"))
    cur = conn.cursor()

    cur.execute("""
        SELECT a.id, COALESCE(a.title,''), COALESCE(a.language_detected,''),
          (SELECT lower(e->>'name') FROM jsonb_array_elements(COALESCE(a.entities_extracted,'[]'::jsonb)) e
           WHERE e->>'name' IS NOT NULL
           ORDER BY (e->>'prominence')::float DESC NULLS LAST, (e->>'confidence')::float DESC NULLS LAST LIMIT 1)
        FROM articles a
        WHERE a.id IN (SELECT a_id FROM analytics._fm_pairs UNION SELECT b_id FROM analytics._fm_pairs)
    """)
    info = {str(r[0]): {"title": r[1], "lang": r[2], "lead": r[3]} for r in cur.fetchall()}

    cur.execute("""
        SELECT p.a_id, p.b_id, round((1-(a.labse_embedding <=> b.labse_embedding))::numeric,3)
        FROM analytics._fm_pairs p JOIN articles a ON a.id=p.a_id JOIN articles b ON b.id=p.b_id
    """)
    cosine = {(str(a), str(b)): float(c) for a, b, c in cur.fetchall()}

    cur.execute(pf.structured_sql("analytics._fm_pairs"))
    feats = pf.rows_to_features(cur)

    direct = transitive = 0
    print("verdict | cosine | score/thi | guard | regime | trgm_subj")
    for fr in feats:
        a, b = str(fr["a_id"]), str(fr["b_id"])
        cos = cosine.get((a, b), 0.0)
        reg = regime_of(fr["a_language"], fr["b_language"])
        block, _ = tg.block_edge(
            same_source=(fr["same_source"] == 1),
            title_trgm=float(fr["trgm_title"]) if fr["trgm_title"] not in ("", None) else 0.0,
            a_title=info.get(a, {}).get("title", ""), b_title=info.get(b, {}).get("title", ""),
            a_lead_entity=info.get(a, {}).get("lead"), b_lead_entity=info.get(b, {}).get("lead"),
        )
        s, thi = score(fr, regs, reg)
        is_direct = (cos >= CAND_COS) and (not block) and (s >= thi)
        direct += is_direct
        transitive += (not is_direct)
        ts = fr.get("trgm_subject", "")
        print("%-7s | %5.3f | %.3f/%.3f | %-5s | %-11s | %s"
              % ("DIRECT" if is_direct else "TRANS", cos, s, thi, block, reg, ts))
    print("\n=== SPLIT: direct-scorer=%d  transitive=%d  (of %d false-merges) ==="
          % (direct, transitive, direct + transitive))
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
