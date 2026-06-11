#!/bin/bash
# v3_groq_resume.sh — auto-fire v3 backfill after Groq+Cerebras TPD reset at 00:00 UTC.
#
# Sleeps until target time, then triggers semantic_repass --all in the rig-backend
# container with LOCAL_LLM_ENABLED=0 — so the pool serves from Groq (21 keys) +
# Cerebras (27 keys) only. Ollama is excluded because (a) cloud is 100x faster
# when quotas are fresh, (b) Ollama's qwen3-30b-a3b has a 60% JSON failure rate
# we measured at 13:28 UTC today (only 8 of 20 sample articles succeeded).
#
# Idempotency:
#   - exits early if semantic_repass --all is already running
#   - exits early if fewer than 100 v2 articles remain
#
# Usage: nohup /usr/local/bin/v3_groq_resume.sh > /tmp/v3_resume_scheduler.log 2>&1 &

set -u

TARGET_UTC="2026-05-25 00:05:00 UTC"
LOG=/tmp/v3_resume_scheduler.log

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" >> "$LOG"; }

TARGET_TS=$(date -d "$TARGET_UTC" +%s)
NOW_TS=$(date +%s)
SLEEP=$((TARGET_TS - NOW_TS))

if [ "$SLEEP" -gt 0 ]; then
    log "scheduled for $TARGET_UTC — sleeping $SLEEP seconds"
    sleep "$SLEEP"
else
    log "target time $TARGET_UTC already passed (delta ${SLEEP}s) — proceeding immediately"
fi

# Safety: skip if a v3 backfill is already running
if docker exec rig-backend pgrep -f "semantic_repass --all" > /dev/null 2>&1; then
    log "ABORT: semantic_repass --all already running in rig-backend"
    exit 0
fi

# Safety: skip if v2 backlog is nearly done
REMAIN=$(docker exec rig-postgres psql -U rig -d rig -tA -c \
    "SELECT COUNT(*) FROM articles WHERE extraction_version=2 AND substrate_status='ok'" 2>/dev/null || echo 0)

if [ "$REMAIN" -lt 100 ]; then
    log "ABORT: only $REMAIN v2 articles remaining — nothing to do"
    exit 0
fi

log "v2_remaining=$REMAIN — launching cloud-only v3 backfill (Groq+Cerebras, no Ollama)"
docker exec -d rig-backend bash -c \
    'LOCAL_LLM_ENABLED=0 python3 -m backend.tasks.substrate.semantic_repass --all >> /tmp/v3_groq_resume.log 2>&1'

sleep 5
if docker exec rig-backend pgrep -f "semantic_repass --all" > /dev/null 2>&1; then
    log "OK: process started"
else
    log "WARN: process did not start cleanly — check /tmp/v3_groq_resume.log"
fi
