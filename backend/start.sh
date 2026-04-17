#!/bin/bash
set -e

echo "Starting RIG SURVEILLANCE backend"
echo "================================="

# Start Celery worker (collectors, nlp, relevance, brief queues)
celery -A backend.celery_app worker \
  --queues=collectors,nlp,relevance,brief \
  --concurrency=2 \
  --loglevel=info &

# Start Celery Beat scheduler
celery -A backend.celery_app beat \
  --loglevel=info &

# Start FastAPI in foreground (keeps container alive)
exec uvicorn backend.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload
