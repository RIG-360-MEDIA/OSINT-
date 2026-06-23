#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# askrig-server.sh — durable Ask-RIG dev server.
#
# The preview-managed server is tied to the agent session and dies whenever that
# session cycles, which shows up in the UI as "Connection lost: Failed to fetch".
# This runs the server INDEPENDENTLY (Startup item) so it survives session cycles
# and reboots. A restart loop also recovers from any crash. --reload means .py
# edits hot-reload — no manual restart after code changes.
#
# Needs: the SearXNG tunnel (8899) for web search, and the Postgres tunnel (15432)
# for the corpus. Those are separate; this only keeps the API server up.
# ─────────────────────────────────────────────────────────────────────────────
set -u

VENV_PY="/c/Users/Dell/Desktop/rig-surveillance/products/ask-rig/.venv/Scripts/python.exe"
APP_DIR="/c/Users/Dell/Desktop/rig-surveillance/products/ask-rig"
LOG="/c/Users/Dell/.askrig-server.log"

log(){ echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

log "askrig-server supervisor starting (:8010)"
while true; do
  log "launching uvicorn"
  "$VENV_PY" -m uvicorn app.main:app \
      --app-dir "$APP_DIR" \
      --host 127.0.0.1 --port 8010 \
      --reload --reload-dir "$APP_DIR/app" >> "$LOG" 2>&1
  log "uvicorn exited ($?) — restarting in 3s"
  sleep 3
done
