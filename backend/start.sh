#!/bin/bash

# --- Stale Beat pidfile cleanup ---------------------------------------------
# The named volume rig-beat-schedule persists pidfiles across container
# recreates; if Beat died ungracefully last time, its pidfile would block
# restart in this instance. See infrastructure/DEPLOYMENT_NOTES.md (2026-04-29).
PID_FILE=/app/beat/celerybeat.pid
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE" 2>/dev/null || echo "")
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        echo "celerybeat.pid points at running PID $PID -- leaving alone"
    else
        echo "celerybeat.pid stale (PID=$PID not running) -- clearing"
        rm -f "$PID_FILE"
    fi
fi
# ----------------------------------------------------------------------------

set -e

echo "Starting RIG SURVEILLANCE backend"
echo "================================="

# Dedicated collector worker — HTML scraping never starves NLP
celery -A backend.celery_app worker \
  --queues=collectors \
  --concurrency=3 \
  --hostname=worker-collectors@%h \
  --loglevel=info &

# Dedicated social worker — Reddit / Telegram never starve behind
# slow HTML scrapes. SIG-11 fix. --prefetch-multiplier=1 prevents one
# slow collect from blocking sibling tasks (P5 fix, 2026-04-28).
celery -A backend.celery_app worker \
  --queues=social \
  --concurrency=2 \
  --prefetch-multiplier=1 \
  --hostname=worker-social@%h \
  --loglevel=info &

# Dedicated YouTube worker — transcript fetch + entity detection + embedding
celery -A backend.celery_app worker \
  --queues=youtube \
  --concurrency=1 \
  --hostname=worker-youtube@%h \
  --loglevel=info &

# Dedicated documents worker — govt PDF extraction (Java JVM is heavy; isolate from RSS)
celery -A backend.celery_app worker \
  --queues=documents \
  --concurrency=2 \
  --prefetch-multiplier=1 \
  --hostname=worker-documents@%h \
  --loglevel=info &

# Dedicated NLP worker — 4 parallel batches
celery -A backend.celery_app worker \
  --queues=nlp \
  --concurrency=4 \
  --hostname=worker-nlp@%h \
  --loglevel=info &

# Dedicated relevance/brief worker — scoring never waits on NLP
celery -A backend.celery_app worker \
  --queues=relevance,brief \
  --concurrency=4 \
  --hostname=worker-relevance@%h \
  --loglevel=info &

# Dedicated whisper worker — THE NEWSROOM 3-Lens transcript pipeline +
# live HLS monitors. concurrency=1 because L3 local ASR is CPU-bound and
# one live_monitor task streams a single channel for hours; prefetch=1
# prevents a long live pull from starving sibling broadcast jobs.
celery -A backend.celery_app worker \
  --queues=whisper \
  --concurrency=1 \
  --prefetch-multiplier=1 \
  --hostname=worker-whisper@%h \
  --loglevel=info &

# Start Celery Beat scheduler.
# --schedule points at a persistent volume (see docker-compose.yml's
# rig-beat-schedule volume on /app/beat). Without this, container
# restarts reset Beat's last-run-times DB and crontab/timedelta entries
# drift — e.g. the daily newspaper cron would never fire if the stack
# was restarted between the previous run and the next anchor.
mkdir -p /app/beat
celery -A backend.celery_app beat \
  --schedule=/app/beat/celerybeat-schedule \
  --pidfile=/app/beat/celerybeat.pid \
  --loglevel=info &

# Start FastAPI in foreground (keeps container alive)
exec uvicorn backend.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload
