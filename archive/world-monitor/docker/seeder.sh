#!/bin/sh
# =============================================================================
# World Monitor seed loop driver
# =============================================================================
# Runs every seed-*.mjs script with a per-seed timeout, then sleeps and
# repeats. Designed to be the CMD of a Docker container; restart: unless-stopped
# handles crashes from outside.
#
# Env knobs:
#   SEEDER_INTERVAL_SEC          — wait between full cycles (default 3600)
#   SEEDER_PER_SEED_TIMEOUT      — kill a seed after this many seconds (default 180)
#   SEEDER_INITIAL_DELAY_SEC     — wait before the first cycle (default 5)
#
# All API key env vars expected by the individual seeds (UPSTASH_*, FINNHUB_*,
# FRED_*, etc.) are inherited from the docker-compose service definition.
# =============================================================================
set -u

INTERVAL_SEC=${SEEDER_INTERVAL_SEC:-3600}
PER_SEED_TIMEOUT=${SEEDER_PER_SEED_TIMEOUT:-180}
INITIAL_DELAY=${SEEDER_INITIAL_DELAY_SEC:-5}

log() { echo "[seeder] $(date -u +%FT%TZ) $*"; }

run_all() {
  log "cycle start"
  ok=0
  fail=0
  for f in /app/scripts/seed-*.mjs; do
    name=$(basename "$f")
    if timeout "$PER_SEED_TIMEOUT" node "$f" >/dev/null 2>&1; then
      ok=$((ok + 1))
      printf "."
    else
      rc=$?
      fail=$((fail + 1))
      log "FAIL  $name (rc=$rc)"
    fi
  done
  echo
  log "cycle end ok=$ok fail=$fail"
}

log "starting; interval=${INTERVAL_SEC}s, per-seed-timeout=${PER_SEED_TIMEOUT}s"
sleep "$INITIAL_DELAY"

while :; do
  run_all
  log "sleeping ${INTERVAL_SEC}s"
  sleep "$INTERVAL_SEC"
done
