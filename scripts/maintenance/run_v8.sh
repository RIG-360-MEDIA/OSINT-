#!/bin/sh
# run_v8.sh — HOST orchestrator for the _v8 whole-corpus build-dark rerun.
# Pauses ingestion (user-approved) to free RAM, runs the pipeline inside a 10G cgroup cap,
# applies migrations 093/094 (_v8), resumes ingestion. NEVER touches job_7 / story_*_old.
# Launch detached:  nohup sh /root/rig/scripts/maintenance/run_v8.sh 0.668 &
set -eu
THETA="${1:-0.668}"
NET=infrastructure_rig-network
IMG=infrastructure-rig-backend
LOG=/tmp/v8_run.log
exec >>"$LOG" 2>&1
echo "############ _v8 RUN theta=$THETA  $(date -u +%FT%TZ) ############"

restore() { docker start rig-backend >/dev/null 2>&1 || true; \
            mv /tmp/rig-nlp-watchdog.disabled /etc/cron.d/rig-nlp-watchdog 2>/dev/null || true; }

# 0. pause ingestion to free RAM; park the nlp watchdog so it doesn't restart the box mid-run.
mv /etc/cron.d/rig-nlp-watchdog /tmp/rig-nlp-watchdog.disabled 2>/dev/null || true
echo "stopping rig-backend (ingestion paused for the run)..."
docker stop rig-backend >/dev/null
sleep 10

# 1. pre-flight gate (rail 2) — now that ingestion RAM is freed.
AVAIL=$(free -m | awk '/^Mem:/{print $7}')
echo "pre-flight: free=${AVAIL}MB (need >=11000)"
if [ "$AVAIL" -lt 11000 ]; then echo "ABORT: free ${AVAIL}MB < 11000 — resuming ingestion, no run."; restore; exit 3; fi

# 2. build-dark target tables: LIKE the live schema (additive; live story_* untouched).
docker exec -i rig-postgres psql -U rig -d rig -v ON_ERROR_STOP=1 <<'SQL'
CREATE TABLE IF NOT EXISTS analytics.story_clusters_v8        (LIKE analytics.story_clusters INCLUDING ALL);
CREATE TABLE IF NOT EXISTS analytics.story_cluster_members_v8 (LIKE analytics.story_cluster_members INCLUDING ALL);
CREATE TABLE IF NOT EXISTS analytics.story_edges_v8           (LIKE analytics.story_edges INCLUDING ALL);
TRUNCATE analytics.story_clusters_v8, analytics.story_cluster_members_v8, analytics.story_edges_v8;
SQL
echo "_v8 tables ready (truncated for clean build)."

# 3. pipeline inside the 10G cgroup cap (rail 1): kernel OOM-kills ONLY this container.
echo "launching capped pipeline (memory=10g)..."
docker run --rm --name v8_pipeline --memory=10g --memory-swap=10g --network "$NET" \
  -v /root/rig:/app -v /tmp:/tmp -w /app "$IMG" \
  sh /app/scripts/maintenance/run_v8_stages.sh "$THETA"

# 4. migrations 093/094 on _v8 (suppression_reason parity strings + subject_country).
echo "applying 093_v8 + 094_v8..."
docker exec -i rig-postgres psql -U rig -d rig -v ON_ERROR_STOP=1 < /root/rig/scripts/migrations/093_v8.sql
docker exec -i rig-postgres psql -U rig -d rig -v ON_ERROR_STOP=1 < /root/rig/scripts/migrations/094_v8.sql

# 5. resume ingestion + re-arm watchdog.
echo "resuming ingestion..."
restore
echo "############ _v8 RUN COMPLETE  $(date -u +%FT%TZ) ############"
