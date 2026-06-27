#!/bin/sh
# rig_nlp_watchdog.sh — detect a HUNG nlp Celery worker and restart rig-backend.
#
# The failure mode (2026-06-14): the nlp worker silently deadlocks (asyncio.Lock reused
# across per-task asyncio.run() loops — root-caused + fixed in groq_client._loop_bound_lock).
# This is the belt-and-suspenders net in case it ever recurs: the worker process stays ALIVE
# but stops consuming, so a process-existence check (drain_watchdog.sh) misses it. We detect
# it by THROUGHPUT — Beat keeps scheduling `process-nlp` every 30s, but if the worker executes
# ZERO process_nlp_batch tasks over the window, it's hung (a no-work worker still logs
# "succeeded ... No pending articles", so succeeded==0 means not-executing, not idle).
#
# Install: */5 * * * * via /etc/cron.d/rig-nlp-watchdog (added alongside rig-matview-refresh).
set -u

WINDOW=7m
COOLDOWN=900                       # don't restart more than once / 15 min
STAMP=/tmp/rig_nlp_watchdog.last
LOG=/tmp/rig_nlp_watchdog.log

logs() { docker logs rig-backend --since "$WINDOW" 2>&1; }

sends=$(logs | grep -c "Sending due task process-nlp")
execd=$(logs | grep -c "tasks.process_nlp_batch.* succeeded")

# Need enough beat cycles to be sure (≈3 min of 30s sends) before calling it hung.
if [ "$sends" -ge 6 ] && [ "$execd" -eq 0 ]; then
    now=$(date +%s)
    last=$(cat "$STAMP" 2>/dev/null || echo 0)
    if [ $((now - last)) -ge "$COOLDOWN" ]; then
        echo "$now" > "$STAMP"
        echo "$(date -u +%FT%TZ) HUNG nlp worker (sends=$sends execd=0) -> restarting rig-backend" >> "$LOG"
        docker restart rig-backend >> "$LOG" 2>&1
    else
        echo "$(date -u +%FT%TZ) hung but in cooldown ($((now-last))s < ${COOLDOWN}s) — skip" >> "$LOG"
    fi
fi
