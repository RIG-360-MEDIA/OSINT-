#!/bin/sh
# Launcher for the 0c V4 shadow re-embed. Logic lives in this file (not an ssh
# one-liner) so no nested-quote mangling. Runs nice'd so the live nlp worker keeps
# CPU priority; the script self-pauses if host RAM drops under the floor.
cd /app
export AB_DSN=$(python -c "import os;print(os.environ.get('DATABASE_URL_SYNC') or os.environ['DATABASE_URL'].replace('+asyncpg','').replace('+psycopg2',''))")
export RECIPE_PATH=/tmp/embedding_recipe.py
export C_BATCH=128
export C_MIN_AVAIL_MB=1200          # pause if host MemAvailable < 1.2 GB (live workers share the box)
export OMP_NUM_THREADS=2            # leave cores for the live nlp worker (gentle throttle)
nice -n 19 python /tmp/reembed_0c_v4.py >> /tmp/reembed_0c.log 2>&1
echo "reembed_0c exited rc=$? at $(date)" >> /tmp/reembed_0c.log
