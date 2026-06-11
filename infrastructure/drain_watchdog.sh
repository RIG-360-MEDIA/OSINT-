#!/bin/bash
# Watchdog: drain + worker-nlp health.
# Restarts drain on death, restarts worker-nlp on death.
#
# CHANGES 2026-05-20:
#   1. semantic_repass --all  →  run_corpus_pass --since 14
#      (semantic_repass is for v1→v2 upgrades of already-extracted articles;
#      it never touched the 'pending' backlog. run_corpus_pass selects
#      substrate_processed_at IS NULL, which is what we actually need to drain.)
#   2. Removed MIXED ↔ LOCAL_ONLY mode flipping based on Cerebras probe.
#      The probe regex ("REMAINING today: \K[0-9,]+") was returning empty,
#      causing cb_pct=0 → forced LOCAL_ONLY → Ollama-only → which is currently
#      unreachable, so drain crashed on every connect attempt. The unified
#      LLM pool already handles Cerebras + Groq rotation + fail-over
#      internally; we don't need to second-guess it from a bash probe.
#      Drain now runs with LOCAL_LLM_ENABLED=0 — pool routes only across
#      24 Groq + 27 Cerebras keys (51 cloud slots, ~27M TPD).
#      When Ollama is reachable again and we want to re-introduce local LLM,
#      flip LOCAL_LLM_ENABLED back to 1 in restart_drain().

set -u

INTERVAL=300
LOG=/tmp/watchdog.log

DRAIN_CMD='python3 -u -m backend.tasks.substrate.run_corpus_pass --since 14'
DRAIN_PATTERN='run_corpus_pass'

restart_drain() {
  docker exec rig-backend pkill -f "$DRAIN_PATTERN" 2>/dev/null
  sleep 4
  docker exec -d \
    -e LOCAL_LLM_ENABLED=0 \
    -e PARALLEL_LLM_POOL=1 \
    -e LOCAL_LLM_PRIMARY=0 \
    rig-backend bash -c "cd /app && nohup $DRAIN_CMD > /tmp/drain_cerebras.log 2>&1 &"
  echo "[$(date)] drain restarted (Cerebras+Groq pool, no Ollama)" >> $LOG
}

restart_worker_nlp() {
  echo "[$(date)] worker-nlp dead — restarting" >> $LOG
  docker exec -d rig-backend celery -A backend.celery_app worker \
    --queues=nlp --concurrency=2 --hostname=worker-nlp@%h --loglevel=warning
}

while true; do
  drain_alive=$(docker exec rig-backend pgrep -f "$DRAIN_PATTERN" 2>/dev/null | wc -l)
  nlp_alive=$(docker exec rig-backend pgrep -f "queues=nlp" 2>/dev/null | wc -l)
  pending=$(docker exec rig-postgres psql -U rig -d rig -t -A -c \
    "SELECT COUNT(*) FROM articles WHERE substrate_processed_at IS NULL" 2>/dev/null)
  echo "[$(date)] drain=$drain_alive nlp=$nlp_alive pending=$pending" >> $LOG

  [ "$nlp_alive" -lt 1 ] && restart_worker_nlp
  [ "$drain_alive" -lt 2 ] && restart_drain

  sleep $INTERVAL
done
