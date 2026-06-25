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
REPO_ROOT="/c/Users/Dell/Desktop/rig-surveillance"
LOG="/c/Users/Dell/.askrig-server.log"

log(){ echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

# CRITICAL: pin CWD to the repo root. When launched hidden via wscript the CWD is
# System32 (not writable), so the app's relative SQLite path ./askrig_app.db fails
# to open and uvicorn crash-loops on startup. cd here fixes that.
cd "$REPO_ROOT" || { log "FATAL: cannot cd to $REPO_ROOT"; exit 1; }

PORT="${ASKRIG_PORT:-8020}"   # 8020, not 8010: dodges the stuck 8010 zombie socket
log "askrig-server supervisor starting (:$PORT, cwd=$REPO_ROOT)"
while true; do
  log "launching uvicorn on :$PORT"
  # No --reload: it proved unreliable here (stale workers + overlapping supervisors
  # holding the port with old code). This is a clean single process; restart it
  # explicitly after code changes (kill the python, the loop relaunches in 3s).
  "$VENV_PY" -m uvicorn app.main:app \
      --app-dir "$APP_DIR" \
      --host 127.0.0.1 --port "$PORT" >> "$LOG" 2>&1
  log "uvicorn exited ($?) — restarting in 3s"
  sleep 3
done
