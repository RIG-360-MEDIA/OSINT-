#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# searxng-tunnel.sh — durable SSH tunnel for Ask-RIG local dev.
#
# SearXNG on Hetzner has NO published host port — it lives only on the Docker
# network as rig-searxng:8080. Ask-RIG's .env points web search at
# http://localhost:8899, so local dev needs this tunnel up. It used to be a
# manual `ssh -L` that silently died on reboot/sleep — this script is the fix.
#
# Self-healing: reconnects on drop, AND re-resolves the container IP each cycle
# so it survives a rig-searxng container recreate (IP is dynamic). Run it once;
# it loops forever. Registered to run at logon via a Windows Scheduled Task
# (see install-searxng-tunnel-task.ps1).
# ─────────────────────────────────────────────────────────────────────────────
set -u

KEY="/c/Users/Dell/.ssh/rig_hetzner"
HOST="root@178.105.63.154"
LOCAL_PORT="${ASKRIG_SEARXNG_LOCAL_PORT:-8899}"
CONTAINER="rig-searxng"
CPORT="8080"

log(){ echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

log "searxng-tunnel starting (local :$LOCAL_PORT -> $CONTAINER:$CPORT @ $HOST)"

while true; do
  # Re-resolve the container IP every reconnect — robust to a container recreate.
  IP=$(ssh -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 "$HOST" \
        "docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' $CONTAINER" \
        2>/dev/null | tr -d '\r')

  if [ -z "$IP" ]; then
    log "could not resolve $CONTAINER IP (ssh or docker unreachable) — retry in 15s"
    sleep 15
    continue
  fi

  log "tunnel up: localhost:$LOCAL_PORT -> $IP:$CPORT"
  # -N: no remote command, just forward. Keepalives detect a dead link fast.
  ssh -i "$KEY" \
      -o StrictHostKeyChecking=no \
      -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
      -o ExitOnForwardFailure=yes \
      -N -L "${LOCAL_PORT}:${IP}:${CPORT}" "$HOST"

  log "tunnel dropped (ssh exit $?) — reconnecting in 5s"
  sleep 5
done
