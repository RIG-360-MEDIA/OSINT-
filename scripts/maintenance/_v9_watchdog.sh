#!/usr/bin/env bash
# Worldwide-feed watchdog for the v9-forward loop.
#
# Runs via a systemd TIMER (not cron) — deliberately, so it still fires even when the
# cron daemon itself dies (the exact failure that froze the feed for 22h on 2026-07-08:
# cron.service went inactive and nothing noticed). Alarms + auto-nudges when the feed
# stalls while ingest is healthy. Log: /var/log/rig-v9-watchdog.log
set -uo pipefail
LOG=/var/log/rig-v9-watchdog.log
KILL=/root/rig/.v9_forward_OFF
WRAP=/root/rig/scripts/maintenance/_v9_forward_cron.sh
LAG_LIMIT_MIN=120          # stale threshold: cluster lag > 2h
STALE_KILL_MIN=60          # a kill-switch older than this is treated as stale/abandoned
ts(){ date -u +%Y-%m-%dT%H:%M:%SZ; }
PG(){ docker exec -i rig-postgres psql -U rig -d rig -tAc "$1" 2>/dev/null | tr -cd '0-9-'; }

LAG_MIN=$(PG "SELECT COALESCE(EXTRACT(EPOCH FROM (now()-max(last_seen_at)))/60,999999)::int FROM analytics.story_clusters_v8")
INGEST=$(PG "SELECT count(*) FROM public.articles WHERE collected_at > now()-interval '1 hour'")
LAG_MIN=${LAG_MIN:-999999}; INGEST=${INGEST:-0}

# Healthy (feed fresh) OR nothing to cluster (no ingest) -> stay quiet.
if [ "$LAG_MIN" -le "$LAG_LIMIT_MIN" ] || [ "$INGEST" -le 0 ]; then
  exit 0
fi

echo "$(ts) ALARM: cluster lag ${LAG_MIN}m (> ${LAG_LIMIT_MIN}) while ingest_last_hr=${INGEST}. Auto-nudging." >> "$LOG"

# Nudge 1: the cron daemon must be alive (this is what actually died).
if ! systemctl is-active --quiet cron; then
  systemctl start cron 2>/dev/null && echo "$(ts)   -> cron.service was DEAD; restarted" >> "$LOG"
fi

# Nudge 2: clear a STALE kill-switch (a fresh one may be a genuine runaway-mega trip — leave it).
if [ -f "$KILL" ]; then
  AGE_MIN=$(( ( $(date +%s) - $(stat -c %Y "$KILL") ) / 60 ))
  if [ "$AGE_MIN" -ge "$STALE_KILL_MIN" ]; then
    rm -f "$KILL" && echo "$(ts)   -> removed STALE kill-switch (age ${AGE_MIN}m)" >> "$LOG"
  else
    echo "$(ts)   -> kill-switch present but fresh (age ${AGE_MIN}m) — leaving (possible real runaway mega); alarm only" >> "$LOG"
  fi
fi

# Nudge 3: kick a run now. The wrapper's own flock makes this a no-op if a fire is already active.
nohup timeout 40m "$WRAP" >> /var/log/rig-v9-forward.log 2>&1 &
echo "$(ts)   -> kicked a v9-forward run (pid $!)" >> "$LOG"
exit 0
