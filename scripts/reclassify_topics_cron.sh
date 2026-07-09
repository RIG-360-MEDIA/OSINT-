#!/usr/bin/env bash
# Safety-net: continuously reclassify articles the ingest pipeline stamped topic=OTHER.
# Runs the working classifier over the recent OTHER backlog. flock => no overlap.
set -uo pipefail
exec 9>/tmp/.topic_reclass.lock
flock -n 9 || { echo "$(date -u +%FT%TZ) previous run active — skip"; exit 0; }
docker exec -e CAP="${CAP:-500}" -e HOURS="${HOURS:-72}" -e CONC="${CONC:-6}" -w /app \
  rig-backend python3 /app/scripts/reclassify_topics.py 2>&1 | grep -E "reclassify:" | \
  sed "s/^/$(date -u +%FT%TZ) /"
