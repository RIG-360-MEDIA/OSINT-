#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# postgres-tunnel.sh — durable SSH tunnel to the Hetzner corpus Postgres.
#
# Ask-RIG's .env points ASKRIG_DB_URL at localhost:15432. rig-postgres on Hetzner
# is host-published at 0.0.0.0:5433 (docker maps 5432->5433), so the forward target
# is a STABLE host port — no container-IP resolution needed. Self-healing loop:
# reconnects on drop. Runs hidden at logon via the Startup item.
# ─────────────────────────────────────────────────────────────────────────────
set -u

KEY="/c/Users/Dell/.ssh/rig_hetzner"
HOST="root@178.105.63.154"
LOCAL_PORT="${ASKRIG_DB_LOCAL_PORT:-15432}"
REMOTE_PORT="5433"   # rig-postgres host-published port on Hetzner
LOG="/c/Users/Dell/.postgres-tunnel.log"

log(){ echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

log "postgres-tunnel starting (local :$LOCAL_PORT -> $HOST:localhost:$REMOTE_PORT)"
while true; do
  ssh -i "$KEY" \
      -o StrictHostKeyChecking=no \
      -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
      -o ExitOnForwardFailure=yes \
      -N -L "${LOCAL_PORT}:localhost:${REMOTE_PORT}" "$HOST" >> "$LOG" 2>&1
  log "tunnel dropped (ssh exit $?) — reconnecting in 5s"
  sleep 5
done
