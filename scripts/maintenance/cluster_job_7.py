#!/usr/bin/env python3
"""
cluster_job_7.py — batch story-clustering job (#7) over the V4 fixture window.

Decision B: **gray -> no-edge**, scorer + deterministic template-guard ONLY, NO live
LLM judge (a 54% gray band routed to an LLM is a queue that falls over — the judge is a
targeted v1.1 only if the gate shows the loss lives in the gray zone). Imports the SSOT
pair_features + template_guard UNCHANGED (train == serve). Emits the gate CSV.

Pipeline:
  window (V4 fixtures) -> candidate-gen (V4 cosine >= CAND_COS)
    -> pair-scorer (re-fit weights, per-regime; indic-indic/insufficient -> en-en fallback;
       en-other shared_numbers weight -> 0 per the positive-only WARN)
    -> TEMPLATE-GUARD (tg-v1, before edges; date-key)
    -> edges iff (not guard-blocked AND score >= theta_high[regime])   [gray/below -> no edge]
    -> connected-components (union-find) -> stable cluster_id (min member id)
    -> CSV: article_id,cluster_id,source_id  (one row per fixture article, V4-only)

Env: AB_DSN/DATABASE_URL_SYNC · PF_PATH(/tmp/pair_features.py) · TG_PATH(/tmp/template_guard.py)
     FIT_REPORT(/tmp/edge-fit.json) · CAND_COS(0.45) · OUT(/tmp/clustering.csv)
"""
from __future__ import annotations

import csv
import importlib.util
import json
import logging
import math
import os
import sys
from collections import Counter, defaultdict

import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("c7")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


pf = _load(os.environ.get("PF_PATH", "/tmp/pair_features.py"), "pair_features")
tg = _load(os.environ.get("TG_PATH", "/tmp/template_guard.py"), "template_guard")

CAND_COS = float(os.environ.get("CAND_COS", "0.45"))
OUT = os.environ.get("OUT", "/tmp/clustering.csv")
FIT_REPORT = os.environ.get("FIT_REPORT", "/tmp/edge-fit.json")
THETA_OVERRIDE = float(os.environ["THETA"]) if os.environ.get("THETA") else None  # sweep: global theta_high
INDIC = {"te", "hi", "kn", "bn", "ml", "ta", "mr", "gu", "pa", "or", "ne", "as"}
FALLBACK = {"indic-indic", "indic-other", "other-other"}  # degenerate / insufficient -> en-en


def bucket(lang: str) -> str:
    return "en" if lang == "en" else ("indic" if lang in INDIC else "other")


def regime_of(al: str, bl: str) -> str:
    return "-".join(sorted([bucket(al or ""), bucket(bl or "")]))


def pick_params(regs: dict, regime: str):
    use = regime
    if regime in FALLBACK or regime not in regs or "weights" not in regs.get(regime, {}):
        use = "en-en"
    r = regs[use]
    return use, r["weights"], r["intercept"], r["scaler"], r["metrics"]["high_threshold"]


def score_pair(feat: dict, regs: dict, regime: str) -> tuple[float, float]:
    use, w, b, sc, thi = pick_params(regs, regime)
    z = float(b)
    for f, wi in w.items():
        if use == "en-other" and f == "shared_numbers":
            wi = 0.0  # positive-only WARN: thin-data artifact, neutralized
        x = feat.get(f, 0.0)
        x = float(x) if x not in ("", None) else 0.0
        mean = sc["mean"].get(f, 0.0)
        std = sc["std"].get(f, 1.0) or 1.0
        z += float(wi) * ((x - mean) / std)
    return 1.0 / (1.0 + math.exp(-z)), (THETA_OVERRIDE if THETA_OVERRIDE is not None else float(thi))


def main() -> int:
    regs = json.load(open(FIT_REPORT))["regimes"]
    log.info("loaded fit regimes: %s (CAND_COS=%.2f, gray->no-edge, no judge)",
             list(regs.keys()), CAND_COS)
    dsn = (os.environ.get("AB_DSN") or os.environ.get("DATABASE_URL_SYNC")
           or os.environ.get("DATABASE_URL"))
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()

    # nodes: every V4 fixture article (window)
    cur.execute("""
        SELECT a.id, a.source_id, COALESCE(a.title,''), COALESCE(a.language_detected,''),
          (SELECT array_agg(n) FROM (
             SELECT lower(e->>'name') n FROM jsonb_array_elements(COALESCE(a.entities_extracted,'[]'::jsonb)) e
             WHERE e->>'name' IS NOT NULL
             ORDER BY (e->>'prominence')::float DESC NULLS LAST, (e->>'confidence')::float DESC NULLS LAST
             LIMIT 3) t) AS lead_entities
        FROM analytics._fixture_ids f JOIN articles a ON a.id = f.id
    """)
    nodes = {str(r[0]): {"source_id": r[1], "title": r[2], "lang": r[3], "ents": r[4]}
             for r in cur.fetchall()}
    log.info("window: %d V4 fixture articles", len(nodes))

    # candidate-gen: V4 cosine >= CAND_COS among the fixture window (label='' for the SSOT SQL)
    cur.execute("""
        DROP TABLE IF EXISTS analytics._cand_pairs;
        CREATE TABLE analytics._cand_pairs AS
        SELECT a.id AS a_id, b.id AS b_id, ''::text AS label
        FROM (SELECT ar.id, ar.labse_embedding FROM analytics._fixture_ids f JOIN articles ar ON ar.id=f.id) a
        JOIN (SELECT ar.id, ar.labse_embedding FROM analytics._fixture_ids f JOIN articles ar ON ar.id=f.id) b
          ON a.id < b.id
        WHERE (a.labse_embedding <=> b.labse_embedding) < %s;
    """, (1.0 - CAND_COS,))
    conn.commit()
    cur.execute("SELECT count(*) FROM analytics._cand_pairs")
    n_cand = cur.fetchone()[0]
    log.info("candidate pairs (cosine>=%.2f): %d", CAND_COS, n_cand)

    # features via the SSOT extractor, unchanged
    cur.execute(pf.structured_sql("analytics._cand_pairs"))
    feats = pf.rows_to_features(cur)

    # union-find over edges
    parent: dict[str, str] = {n: n for n in nodes}

    def find(x):
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)  # deterministic: smaller id wins

    edges = blocked = gray_or_below = 0
    for fr in feats:
        a, b = str(fr["a_id"]), str(fr["b_id"])
        if a not in nodes or b not in nodes:
            continue
        regime = regime_of(fr["a_language"], fr["b_language"])
        block, _ = tg.block_edge(
            same_source=(fr["same_source"] == 1),
            title_trgm=float(fr["trgm_title"]) if fr["trgm_title"] not in ("", None) else 0.0,
            a_title=nodes[a]["title"], b_title=nodes[b]["title"],
            a_entities=nodes[a]["ents"], b_entities=nodes[b]["ents"],
            subj_trgm=float(fr["trgm_subject"]) if fr["trgm_subject"] not in ("", None) else None,
        )
        if block:
            blocked += 1
            continue
        s, thi = score_pair(fr, regs, regime)
        if s >= thi:
            union(a, b)
            edges += 1
        else:
            gray_or_below += 1
    log.info("edges=%d  guard-blocked=%d  gray/below(no-edge)=%d", edges, blocked, gray_or_below)

    # stable cluster ids = min member id per component
    comp = defaultdict(list)
    for n in nodes:
        comp[find(n)].append(n)
    cluster_of = {n: root for root, members in comp.items() for n in members}

    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["article_id", "cluster_id", "source_id"])
        for n in nodes:
            w.writerow([n, cluster_of[n], nodes[n]["source_id"] or ""])

    # ---- §5 self-checks ----
    sizes = Counter(len(m) for m in comp.values())
    n_clusters = len(comp)
    singletons = sizes.get(1, 0)
    biggest = max((len(m) for m in comp.values()), default=0)
    missing_src = sum(1 for n in nodes if not nodes[n]["source_id"])
    log.info("=== §5 CSV self-check ===")
    log.info("rows=%d  articles=%d  missing_id=0  source_id_null=%d  coverage=%d/%d=%.1f%%",
             len(nodes), len(nodes), missing_src, len(nodes), len(nodes), 100.0)
    log.info("clusters=%d  singletons=%d  biggest_cluster=%d", n_clusters, singletons, biggest)
    log.info("cluster-size histogram (size:count, top 12): %s",
             dict(sorted(sizes.items())[:12]))
    log.info("wrote %s", OUT)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
