#!/usr/bin/env bash
# Dedicated LOCAL-ONLY backlog drainer.
#
# Grinds the OLD substrate backlog (oldest-first) using only the local Ollama
# 32b node on :11434, leaving the cloud Groq/Cerebras keys entirely for the
# Celery beat task that handles fresh inflow (newest-first). Survives container
# restarts because each iteration re-execs into the container.
#
# Constraints honoured:
#   - :11435 (in-use workstation) is deliberately EXCLUDED.
#   - LLM_LOCAL_ONLY=1 => zero cloud-key consumption from this drainer.
#   - DRAIN_OLDEST_FIRST=1 => attacks the backlog, not the fresh rows.
set -u

LOG=/root/rig/logs/local_backlog_drain.log
mkdir -p /root/rig/logs
STOP_AT=500          # stop once pending falls below this (fresh inflow handles the rest)
BATCH=300

echo "[start] $(date -u) local-only oldest-first backlog drainer" >> "$LOG"

while true; do
  PENDING=$(docker exec rig-postgres psql -U rig -d rig -tA \
    -c "SELECT count(*) FROM articles WHERE substrate_status='pending'" 2>>"$LOG" | tr -d '[:space:]')
  PENDING=${PENDING:-0}

  if ! [[ "$PENDING" =~ ^[0-9]+$ ]]; then
    echo "[warn] $(date -u) bad pending read '$PENDING'; retrying in 30s" >> "$LOG"
    sleep 30; continue
  fi

  echo "[tick] $(date -u) pending=$PENDING" >> "$LOG"
  if [ "$PENDING" -le "$STOP_AT" ]; then
    echo "[done] $(date -u) pending=$PENDING <= $STOP_AT; exiting" >> "$LOG"
    break
  fi

  docker exec \
    -e LLM_LOCAL_ONLY=1 \
    -e LOCAL_LLM_PRIMARY=1 \
    -e DRAIN_OLDEST_FIRST=1 \
    -e OLLAMA_ENDPOINTS="http://172.30.0.1:11434|qwen2.5:32b" \
    -e LOCAL_LLM_MAX_CONCURRENT=6 \
    rig-backend python3 -m backend.tasks.substrate.run_corpus_pass --limit "$BATCH" \
    >> "$LOG" 2>&1 || { echo "[err] $(date -u) batch failed; sleep 20" >> "$LOG"; sleep 20; }
done
