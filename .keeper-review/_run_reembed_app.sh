#!/bin/sh
# Relaunch the 0c V4 shadow re-embed from bind-mounted /app paths (survive container recreate).
cd /app
export AB_DSN=$(python -c "import os;print(os.environ.get('DATABASE_URL_SYNC') or os.environ['DATABASE_URL'].replace('+asyncpg','').replace('+psycopg2',''))")
export RECIPE_PATH=/app/backend/nlp/embedding_recipe.py
export C_BATCH=128
export C_MIN_AVAIL_MB=1200
export OMP_NUM_THREADS=2
nice -n 19 python /app/scripts/_reembed_0c_v4.py >> /tmp/reembed_0c.log 2>&1
echo "reembed_0c exited rc=$? at $(date)" >> /tmp/reembed_0c.log
