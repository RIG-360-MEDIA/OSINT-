#!/usr/bin/env python3
"""sweep_driver.py — clean in-container sweep of cluster_job_7 (no nested-shell quoting).

Runs cluster_job_7 as a subprocess with a fully-controlled env per config, parses the
log (stderr), and prints one line per config: cand_pairs, edges, clusters, singletons,
biggest. Two sub-sweeps to find the lever that reproduces v11 (454 clusters, 340 singletons):
  A) THETA high-range at CAND_COS=0.45  — does the scorer threshold ever fragment?
  B) CAND_COS range at THETA=0.668      — does the candidate cosine gate fragment?
Writes each partition to /tmp/sw_<tag>.csv for scoring.
"""
import os
import re
import subprocess
import sys

DSN = os.environ.get("DATABASE_URL_SYNC") or os.environ["DATABASE_URL"].replace("+asyncpg", "").replace("+psycopg2", "")
BASE = dict(
    os.environ,
    AB_DSN=DSN,
    PF_PATH="/tmp/pair_features.py",
    TG_PATH="/tmp/template_guard.py",
    FIT_REPORT="/tmp/edge-fit.json",
    LEIDEN="1",
    RESOLUTION="1.0",
)


def run(tag, **over):
    env = dict(BASE, OUT=f"/tmp/sw_{tag}.csv", **{k: str(v) for k, v in over.items()})
    r = subprocess.run([sys.executable, "/tmp/cluster_job_7.py"], env=env,
                       capture_output=True, text=True)
    log = r.stderr + r.stdout
    g = lambda pat: (re.search(pat, log) or [None, "?"])[1] if re.search(pat, log) else "?"
    cand = g(r"candidate pairs.*?: (\d+)")
    edges = g(r"edges=(\d+)")
    clusters = g(r"clusters=(\d+)")
    singit = g(r"singletons=(\d+)")
    big = g(r"biggest_cluster=(\d+)")
    cfg = g(r"(config:.*)")
    print(f"{tag:18s} cand={cand:>7} edges={edges:>7} clusters={clusters:>4} "
          f"singletons={singit:>4} biggest={big:>4}", flush=True)
    if r.returncode != 0:
        print(f"   !! rc={r.returncode} tail={log.strip().splitlines()[-1][:160] if log.strip() else 'NO LOG'}", flush=True)


print("=== A) THETA high-range @ CAND_COS=0.45 ===", flush=True)
for th in ["0.62", "0.72", "0.82", "0.90", "0.95"]:
    run(f"th{th}", THETA=th, CAND_COS="0.45")

print("=== B) CAND_COS range @ THETA=0.668 ===", flush=True)
for cc in ["0.55", "0.65", "0.75", "0.80", "0.83"]:
    run(f"cc{cc}", THETA="0.668", CAND_COS=cc)
