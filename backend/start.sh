#!/bin/bash
set -e

echo "Starting RIG SURVEILLANCE backend"
echo "================================="

# Dedicated collector worker — HTML scraping never starves NLP
celery -A backend.celery_app worker \
  --queues=collectors \
  --concurrency=1 \
  --hostname=worker-collectors@%h \
  --loglevel=info &

# Dedicated YouTube worker — transcript fetch + entity detection + embedding
celery -A backend.celery_app worker \
  --queues=youtube \
  --concurrency=1 \
  --hostname=worker-youtube@%h \
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

# Start Celery Beat scheduler
celery -A backend.celery_app beat \
  --loglevel=info &

# Start FastAPI in foreground (keeps container alive)
exec uvicorn backend.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload
