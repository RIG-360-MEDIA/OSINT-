#!/bin/sh
# run_v8_stages.sh — the in-container clustering stages for the _v8 build-dark rerun.
# Runs INSIDE a `docker run --memory=10g` container (kernel OOM-kills ONLY this scope).
# Crash-safe: fail-loud igraph (no networkx fallback), checkpoint per stage (resumable).
# Arg $1 = THETA (edge threshold for the scorer). Driven by run_v8.sh on the host.
set -eu
THETA="${1:-0.668}"
export AB_DSN="${AB_DSN:-postgresql://rig@rig-postgres:5432/rig}"
cd /app
echo "=== _v8 stages start theta=$THETA $(date -u +%FT%TZ) ==="

# Rail 3: fail-loud graph backend — the silent networkx fallback is the OOM landmine on 273K nodes.
python -c "import igraph, leidenalg; print('graph backend OK: igraph', igraph.__version__)" \
  || { echo "FATAL: igraph/leidenalg not importable — REFUSING to run (networkx fallback would OOM the box)"; exit 4; }

MEM=/tmp/v8_members.csv
EDG=/tmp/v8_edges.csv

# ── Stage 1: cluster_job_7 — whole-corpus over labse_embedding_v4 (ANN via the new HNSW index) ──
# Wide window => WINDOWED ANN mode over ALL rows WHERE labse_embedding_v4 IS NOT NULL (label-agnostic).
if [ -s "$MEM" ]; then
  echo "stage1 SKIP — $MEM already present ($(wc -l < "$MEM") rows)"
else
  echo "--- stage1 cluster_job_7 (CAND_COS=0.80, theta=$THETA) ---"
  CAND_COS=0.80 THETA="$THETA" WINDOW_START=2000-01-01 WINDOW_END=2100-01-01 CAND_K=30 LEIDEN=1 \
    PF_PATH=/tmp/pair_features.py TG_PATH=/tmp/template_guard.py \
    FIT_REPORT=/app/docs/fixtures/edge-fit-report-2026-06-03-refit.json \
    OUT="$MEM" EDGES_OUT="$EDG" \
    python /app/scripts/maintenance/cluster_job_7.py
fi
echo "stage1 done: members=$(wc -l < "$MEM") edges=$(wc -l < "$EDG" 2>/dev/null || echo 0)"

# ── Stage 2: story_loader -> analytics.story_clusters_v8 / _members_v8 (integrated §2b rescue) ──
echo "--- stage2 story_loader -> _v8 ---"
MEMBERS="$MEM" EDGES="$EDG" STORY_TBL_SUFFIX=_v8 \
  RESCUE_ON=1 RESCUE_PATH=/app/scripts/maintenance/story_rescue.py \
  RESCUE_MIN_SRC=12 RESCUE_MIN_SZ=10 RESCUE_RES=4.0 RESCUE_ALLOW_TCOH=0 \
  FLAG_MIN_SRC=25 CORE_T=0.45 TCOH_T=0.35 TCOH_CAP=1000 SIZE_CORE_LOW=0.25 \
  PROVISIONAL=1 ALGO_VERSION="cluster_job_7/v4/leiden-res1.0/rescue-v1/_v8" \
  python /app/scripts/maintenance/story_loader.py

echo "=== _v8 stages DONE $(date -u +%FT%TZ) ==="
